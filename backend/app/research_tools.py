"""受约束工具执行与多渠道适配；模型只能提出schema内调用，不能任意访问网络或写CRM。"""
import asyncio
import hashlib
import ipaddress
import json
import re
import socket
import time
import threading
import weakref
from contextlib import asynccontextmanager
from typing import Literal
from urllib.parse import urlparse
import httpx
from langsmith import traceable
from pydantic import BaseModel, Field, model_validator
from sqlalchemy import select, text, func
from .db import Session, Job, Evidence, ToolCall, Lead, serialize, now
from .service import ServiceError, save_candidate
from .schemas import Candidate
from .gateway import call_exa, split_sources, archive_sources
from .knowledge import store, search_knowledge, upsert_knowledge, expires, WORKSPACE
from .observability import logger, safe_error, error_details
from .tool_views import trace_tool_inputs, tool_result
from .source_errors import SourceRateLimit, source_limit, retry_delay
from .source_catalog import CHANNELS,SearchChannel,matches_channel,reference_urls
from .qcc_mcp import QccMcpClient, QccCallResult, archive_qcc_result, operation_key as qcc_operation_key, resolve_binding
from .source_access import access_issue
from .company_research_schemas import CompanySnapshot

LOG=logger('agent')
TRACE_NAMES={'search_accounts':'工具·公开检索','fetch_source':'工具·读取网页','fetch_browser':'工具·浏览器读取','search_knowledge':'工具·知识库',
    'search_research_data':'工具·历史研究','parse_account':'工具·解析目录','persist_lead':'工具·保存线索','persist_company':'工具·核验保存企业'}
SITE_CLOCK={}
SITE_LOCK=threading.Lock()
PENDING_CLEANUP: dict[asyncio.Task,str]={}
PROVIDER_GATES=weakref.WeakKeyDictionary()


@asynccontextmanager
async def provider_slot(job_id: str):
    """job_id为当前非空任务；全Worker最多两路供应商请求，等待时可暂停，退出释放槽位。

    槽位在工具预算预留前取得，排队期间的限流由原预算事务重查；不同事件循环不共享锁。
    """
    loop=asyncio.get_running_loop()
    gate=PROVIDER_GATES.setdefault(loop,asyncio.Semaphore(2))
    task=asyncio.create_task(gate.acquire())
    try:
        while not task.done():
            await asyncio.wait({task},timeout=.4)
            guard(job_id)
        await task;guard(job_id)
        yield
    finally:
        if task.done() and not task.cancelled() and task.exception() is None:gate.release()
        elif not task.done():await cancel_task(task,job_id)


class SearchAccounts(BaseModel):
    """公开渠道搜索参数；字段有界，不允许任意供应商或执行指令。"""
    query: str=Field(min_length=3,max_length=500)
    channel: SearchChannel


class FetchSource(BaseModel):
    """仅接受已发现的公开来源URL。"""
    url: str=Field(min_length=8,max_length=2000)
    channel: SearchChannel


class SearchKnowledge(BaseModel):
    """作用域由服务注入，不由模型选择。"""
    query: str=Field(max_length=500)


class PersistLead(BaseModel):
    """只有带逐字段证据的候选可以入库。"""
    candidate: Candidate


class ParseAccount(BaseModel):
    """已取得网页的有界模板解析参数，不允许模型提交正文或自定义解析规则。"""
    source_id: str=Field(min_length=1,max_length=64)
    channel: SearchChannel
    target_roles: list[Literal['dealer','retailer','mall','project_buyer','manufacturer']]=Field(default_factory=list,max_length=5)


class Paused(Exception):
    """任务请求暂停，图保留待执行节点与工具账本。"""


class PersistCompany(BaseModel):
    """企业持久工具只接受逐项带来源的结构，不接受任意SQL、正文或文件路径。"""
    snapshot: CompanySnapshot
    targets: list[str] = Field(default_factory=list, max_length=8)
    relation_id: str | None = Field(default=None, max_length=64)

class QccCompanyLookup(BaseModel):
    model_config = {'extra': 'forbid'}
    name: str = Field(min_length=2, max_length=200)
    credit_code: str | None = Field(default=None, max_length=30)
    action: Literal['basic','identity','profile','contact','annual'] = 'basic'

class QccOperationLookup(BaseModel):
    model_config = {'extra': 'forbid'}
    company_id: str | None = Field(default=None, max_length=64)
    credit_code: str | None = Field(default=None, max_length=64)

    @model_validator(mode='after')
    def require_identifier(self):
        if not any(isinstance(value, str) and value.strip() for value in (self.company_id, self.credit_code)):
            raise ValueError('company identifier required')
        return self

QccRiskLookup = QccOperationLookup

class QccTenderLookup(BaseModel):
    model_config = {'extra':'forbid'}
    company_id: str = Field(min_length=1,max_length=64)

    @model_validator(mode='after')
    def require_id(self):
        if not self.company_id.strip():raise ValueError('company_id required')
        return self

async def _qcc_action(job_id: str, request: BaseModel, server: str, action: str) -> dict:
    from .config import qcc_mcp_key
    if not qcc_mcp_key(): return {'error':'qcc_not_configured','sources':[],'authorized':False}
    from pathlib import Path
    import yaml
    binding_file=Path(__file__).resolve().parents[2] / 'config' / 'qcc_mcp_bindings.yaml'
    try:
        if not binding_file.exists():binding_file=binding_file.with_name('qcc_mcp_bindings.example.yaml')
        document=yaml.safe_load(binding_file.read_text(encoding='utf-8'))
    except Exception:
        document={}
    bindings=((document or {}).get('servers',{}).get(server,{}) if isinstance(document,dict) else {})
    client=QccMcpClient(server, bindings=bindings)
    try:
        args={'searchKey':getattr(request,'credit_code',None) or getattr(request,'name',None) or getattr(request,'company_id',None)}
        if server=='tender':args={'id':request.company_id}
        call=await client.call(action, args, action=True)
        source=archive_qcc_result(job_id,call, f'企查查授权 MCP·{getattr(request,"name","")}·{action}')
        return {'error':'','company':call.response if server=='company' else {}, 'records':call.response if server!='company' else [], 'sources':[source], 'authorized':True}
    except Exception as exc:
        return {'error': getattr(exc,'code',None) or 'qcc_invalid_response', 'sources':[], 'authorized':False}

async def qcc_company_lookup(job_id: str, request: QccCompanyLookup) -> dict:
    return await _qcc_action(job_id, request, 'company', request.action)
async def qcc_operation_lookup(job_id: str, request: QccOperationLookup) -> dict:
    return await _qcc_action(job_id, request, 'operation', 'operation')
async def qcc_risk_lookup(job_id: str, request: QccRiskLookup) -> dict:
    return await _qcc_action(job_id, request, 'risk', 'risk')
async def qcc_tender_lookup(job_id: str, request: QccTenderLookup) -> dict:
    return await _qcc_action(job_id, request, 'tender', 'tender')


def public_url(url: str) -> bool:
    """url须http(s)且无用户凭证；解析到任何非公网IP即拒绝，DNS失败也不猜测为可用。"""
    uri=urlparse(url)
    if uri.scheme not in {'http','https'} or not uri.hostname or uri.username:return False
    try:
        addresses=socket.getaddrinfo(uri.hostname,uri.port or (443 if uri.scheme=='https' else 80))
        return all(ipaddress.ip_address(row[4][0]).is_global for row in addresses)
    except (ValueError,OSError):return False


def emit(job_id: str, event_type: str, payload: dict, message: str='', stage: str='') -> int:
    """job_id非空、event_type为程序事件、payload不含密钥；持久事件ID供SSE重放。"""
    from .db import JobEvent
    with Session.begin() as db:
        event=JobEvent(job_id=job_id,event_type=event_type,payload=payload,message=message,stage=stage)
        db.add(event);db.flush()
        return event.id


def guard(job_id: str) -> None:
    """检查非空job_id暂停标志，暂停抛Paused；不启动新的外部请求。"""
    with Session() as db:
        row=db.get(Job,job_id)
        if not row or row.cancel_requested:raise Paused()


def observe_task(task: asyncio.Task, job_id: str) -> None:
    """task为已完成或待清理异步请求，job_id用于安全日志；消费异常防止后台报未取回错误，不保存返回正文。"""
    PENDING_CLEANUP.pop(task,None)
    with Session.begin() as db:
        row=db.get(Job,job_id)
        if row:row.metrics={**(row.metrics or {}),'pending_cleanup':sum(owner==job_id and not item.done() for item,owner in PENDING_CLEANUP.items())}
    if not task.cancelled():
        error=task.exception()
        if error:LOG.warning('request_cleanup_error',extra={'details':{'job_id':job_id,'error_type':safe_error(error)}})


async def cancel_task(task: asyncio.Task, job_id: str) -> None:
    """task为外部请求/流关闭，job_id非空；取消后最多等0.5秒，迟到完成只消费异常，不阻塞停止。"""
    task.cancel()
    if not task.done():await asyncio.wait({task},timeout=.5)
    if task.done():observe_task(task,job_id)
    else:
        track_pending(task,job_id)
        LOG.warning('request_cleanup_pending',extra={'details':{'job_id':job_id,'pending':len(PENDING_CLEANUP)}})


def track_pending(task: asyncio.Task, job_id: str) -> None:
    """task为仍在途的请求/事务，job_id为当前任务；持久标记并收尾清理，返回None，不重新发送请求。"""
    PENDING_CLEANUP[task]=job_id
    with Session.begin() as db:
        row=db.get(Job,job_id)
        if row:row.metrics={**(row.metrics or {}),'pending_cleanup':sum(owner==job_id and not item.done() for item,owner in PENDING_CLEANUP.items())}
    task.add_done_callback(lambda done:observe_task(done,job_id))


async def parallel(coroutines: list, job_id: str) -> list:
    """coroutines为独立只读工具协程（可空），job_id为实际任务；正常保持顺序，异常取消兄弟请求再上抛。

    清理有界，迟到请求持久标记pending_cleanup，防止恢复后重复发送仍在途的操作。
    """
    tasks=[asyncio.create_task(item) for item in coroutines]
    try:return await asyncio.gather(*tasks)
    except BaseException:
        await asyncio.gather(*(cancel_task(task,job_id) for task in tasks if not task.done()))
        raise


async def close_stream(stream, job_id: str) -> None:
    """stream可支持aclose，job_id用于日志；关闭最多等0.5秒，不把清理错误覆盖原暂停/超时。"""
    if not hasattr(stream,'aclose'):return
    task=asyncio.create_task(stream.aclose())
    await asyncio.wait({task},timeout=.5)
    if task.done():observe_task(task,job_id)
    else:await cancel_task(task,job_id)


async def cancellable(awaitable, job_id: str, timeout: int=120):
    """awaitable为单外部操作，job_id当前任务，timeout为秒；轮询暂停并取消客户端等待，返回结果或抛异常。"""
    task=asyncio.create_task(awaitable);started=time.monotonic()
    try:
        while not task.done():
            await asyncio.wait({task},timeout=0.4)
            guard(job_id)
            if time.monotonic()-started>timeout:raise TimeoutError()
        return await task
    finally:
        if not task.done():await cancel_task(task,job_id)


async def cancellable_stream(stream, job_id: str):
    """stream为模型异步迭代器，job_id非空；等待首块/下一块也检查停止，关闭客户端连接。

    暂停抛Paused，单块等待超过120秒抛TimeoutError；不承诺provider已停止计费。
    """
    try:
        while True:
            try:
                chunk = await cancellable(anext(stream), job_id, 120)
            except StopAsyncIteration:
                return
            yield chunk
    finally:
        pending=[task for task,owner in PENDING_CLEANUP.items() if owner==job_id]
        if pending:
            # anext仍执行时不能同步aclose；在它结束后关闭流，不拖住业务任务的paused终态。
            for task in pending:
                task.add_done_callback(lambda done:asyncio.create_task(close_stream(stream,job_id)))
        else:await close_stream(stream,job_id)


def recipe(channel: str, success: bool, elapsed_ms: int, profile: dict, valid_leads: int=0, record_call: bool=True, lead_ids: list[str] | None=None):
    """channel为渠道，success为实际来源结果，耗时非负，profile为画像；valid_leads为产出数，record_call控制工具计次。

    lead_ids可空；提供时按真实客户ID去重累计，用于反馈归因，空时沿用产出数；无返回值，不学习客户事实。
    """
    category=' '.join(x['name'] for x in profile.get('products',[]))[:100]
    key=hashlib.sha256(f'{profile.get("region","")}|{category}|{channel}'.encode()).hexdigest()[:24]
    previous=store.get((WORKSPACE,'recipes'),key)
    data=previous.value if previous else {'channel':channel,'region':profile.get('region',''),'category':category,'calls':0,'successes':0,'elapsed_ms':0,'valid_leads':0}
    credited=list(data.get('credited_lead_ids',[]))
    if lead_ids is not None:
        fresh=[x for x in set(lead_ids) if x not in credited]
        valid_leads=len(fresh);credited.extend(sorted(fresh))
    store.put((WORKSPACE,'recipes'),key,{**data,'calls':data['calls']+int(record_call),'successes':data['successes']+int(success and record_call),
        'elapsed_ms':data['elapsed_ms']+elapsed_ms,'valid_leads':data['valid_leads']+valid_leads,'credited_lead_ids':credited,'source':'实际工具与销售反馈'})


class ToolBroker:
    """按Pydantic白名单执行工具，统一配额、失败码、缓存及可恢复操作ID。"""
    def __init__(self, job_id: str, options: dict, profile: dict):
        """job_id非空，options是校验后的预算，profile是当前画像；初始化临时允许来源集合。"""
        from .source_catalog import active_channels
        with Session() as db:job=db.get(Job,job_id);prompt=((job.metrics or {}).get('research_prompt') or job.prompt) if job else ''
        options={**options}
        if 'enabled_channels' in options:options['enabled_channels']=active_channels(prompt,options['enabled_channels'])
        self.job_id,self.options,self.profile=job_id,options,profile
        self.prompt=prompt
        self.allowed_sources=set()
        # 并发读取按原URL隔离诊断，结果只存状态/计数，不能把网页或协议原文写进工具投影。
        self.read_outcomes={}
        self.search_history={}
        with Session() as db:
            self.allowed_sources.update(db.scalars(select(Evidence.id).where(Evidence.job_id==job_id)))
            job=db.get(Job,job_id)
            from .source_catalog import public_entries
            self.reference_urls={x['url'] for x in [*reference_urls(prompt,options.get('enabled_channels',[])),
                *public_entries(profile,options.get('enabled_channels',[]),'',None,prompt)]}

    @traceable(name='客户资料工具', run_type='tool', process_inputs=trace_tool_inputs, process_outputs=tool_result)
    async def execute(self, name: str, arguments: dict) -> dict:
        """name须在白名单、arguments须符合schema；成功复用，临时失败仅显式恢复后重试且累计预算。"""
        if name=='search_tenders':return await self.search_tenders(arguments)
        if name=='get_tender_detail':return await self.get_tender_detail(arguments)
        if name=='search_accounts':
            if arguments.get('channel')=='procurement' and self.options.get('bidresearch_enabled',False):
                from .bidresearch_mcp import runtime_status
                if runtime_status()['installed']:
                    if 'procurement' not in self.options.get('enabled_channels',[]):return {'error':'channel_disabled','sources':[]}
                    parsed=SearchAccounts.model_validate(arguments)
                    targets=self.options.get('research_targets',[])
                    company=next((t for t in targets if t in parsed.query),'')
                    # 平台检索先行节点已完成；自由规划的公共资源/买方原公告应保留完整查询词。
                    # 否则所有企业采购查询都退化成同一企业名检索，永远只返回相同列表。
                    with Session() as db:
                        listed=bool(company and any((r.arguments or {}).get('company')==company for r in
                            db.scalars(select(ToolCall).where(ToolCall.job_id==self.job_id,ToolCall.tool=='search_tenders',ToolCall.channel=='bidresearch'))))
                    if listed:
                        async with provider_slot(self.job_id):return await self._execute(name,arguments)
                    from .bidresearch_mcp import procurement_keywords
                    keywords=[company] if company else procurement_keywords(parsed.query,self.profile.get('products',[]))
                    request={'keywords':keywords,'company':company}
                    if company:request['days']=min(365,self.options.get('tender_days',365))
                    result=await self.search_tenders(request)
                    if result.get('sources') or result.get('error')=='channel_disabled':return result
                    # A second public search spends the same Job search pool and is itself reusable.
                    async with provider_slot(self.job_id):fallback=await self._execute(name,arguments)
                    return {**fallback,'mcp_status':{'error':result.get('error',''),'coverage':result.get('coverage',[])}}
            async with provider_slot(self.job_id):return await self._execute(name,arguments)
        return await self._execute(name,arguments)

    async def search_tenders(self, arguments):
        """单一采购入口，来源/详情/请求由应用许可，外部结果进入同一 Evidence。"""
        import os
        from .bidresearch_mcp import BidSearch, search, DOMAINS
        from .mcp_tools import run_bounded
        from .source_scope import reference_only
        guard(self.job_id)
        if not self.options.get('bidresearch_enabled',False) or os.getenv('CLIENTREACH_BIDRESEARCH_ENABLED','').lower() in {'0','false','off'}:
            return {'error':'channel_disabled','sources':[]}
        if 'procurement' not in self.options.get('enabled_channels',[]) or reference_only(self.prompt,reference_urls(self.prompt,self.options.get('enabled_channels',[]))):
            return {'error':'channel_disabled','sources':[]}
        try:request=BidSearch.model_validate(arguments)
        except ValueError:return {'error':'invalid_arguments','sources':[]}
        if request.company:
            from .bidresearch_mcp import company_time_window
            mode,days=company_time_window(self.prompt,min(365,self.options.get('tender_days',365)))
            if mode=='recent':
                request.mode='recent';request.days=days
                if 'pages' not in arguments:request.pages=1
                if 'limit' not in arguments:request.limit=20
        # 企业候选人常出现在正文，先检索已验证可返回该类正文的平台；产品采购仍优先官方。
        if request.company and 'sources' not in arguments:request.sources=['ebnew'] if request.mode=='history' else ['ebnew','ggzy']
        from .bidresearch_mcp import software_service_profile,active_procurement_requested
        if not request.company and software_service_profile(self.profile):request.category='software_services'
        if not request.company and active_procurement_requested(self.prompt):request.active_only=True
        from .source_catalog import blocked_source
        request.sources=[source for source in request.sources if not any(blocked_source('https://'+domain,self.prompt) for domain in DOMAINS[source])]
        if not request.sources:return {'error':'channel_disabled','sources':[]}
        calls=self.options.get('max_bidresearch_calls',0)
        requests=self.options.get('bidresearch_max_requests',0)
        # 留出至少一半读取额度给检索后的原页补读；详情额度是每次上限，而非必须花满。
        details=0 if request.company else min(self.options.get('bidresearch_max_details',0),self.options.get('max_reads',0)//(2*max(1,calls)))
        grant={'searches':1,'reads':details,'requests':min(requests//max(1,calls),len(request.sources)*len(request.keywords)*request.pages+1) if request.company else requests//max(1,calls)}
        if grant['requests']<=0:return {'error':'budget_exhausted','sources':[]}
        async def invoke():
            options={**self.options,'bidresearch_max_details':grant['reads'],'bidresearch_max_requests':grant['requests']}
            return await search(self.job_id,request,options)
        async with provider_slot(self.job_id):
            result=await run_bounded(self.job_id,'search_tenders','bidresearch',request.model_dump(),calls,invoke,
                timeout=self.options.get('bidresearch_timeout',90)+5,
                limits={'searches':self.options.get('max_searches',0),'reads':self.options.get('max_reads',0),'requests':requests},reservation=grant)
        self.allowed_sources.update(s['id'] for s in result.get('sources',[]))
        return result

    async def get_tender_detail(self, arguments):
        """只读取本任务实际发现且获许可的公告，独立计调用，共用请求/读取预算。"""
        import os
        from .bidresearch_mcp import BidDetail,detail,ACCESS_REFUSALS,refused_detail
        from .mcp_tools import run_bounded
        from .source_scope import reference_only
        from .source_catalog import blocked_source
        guard(self.job_id)
        if not self.options.get('bidresearch_enabled',False) or os.getenv('CLIENTREACH_BIDRESEARCH_ENABLED','').lower() in {'0','false','off'} or 'procurement' not in self.options.get('enabled_channels',[]) or reference_only(self.prompt,reference_urls(self.prompt,self.options.get('enabled_channels',[]))):
            return {'error':'channel_disabled','sources':[]}
        try:request=BidDetail.model_validate(arguments)
        except ValueError:return {'error':'invalid_arguments','sources':[]}
        if blocked_source(request.url,self.prompt):return {'error':'channel_disabled','sources':[]}
        with Session() as db:
            if issue:=refused_detail(db,self.job_id,request.url):return {'error':issue,'sources':[]}
            prior=list(db.scalars(select(Evidence).where(Evidence.job_id==self.job_id,Evidence.id.in_(self.allowed_sources),Evidence.url==request.url,Evidence.channel=='procurement')))
            if not any((s.source_meta or {}).get('origin')=='bidresearch_mcp' and (s.source_meta or {}).get('source')==request.source for s in prior):
                return {'error':'source_not_allowed','sources':[]}
            if any((s.source_meta or {}).get('detail_status') in ACCESS_REFUSALS for s in prior):return {'error':'site_access_restricted','sources':[]}
        # Upstream detail allows at most eight transport requests, including redirects.
        grant={'reads':1,'requests':8}
        async def invoke():
            if grant['reads']<1:return {'error':'budget_exhausted','sources':[]}
            return await detail(self.job_id,request,self.options)
        async with provider_slot(self.job_id):
            result=await run_bounded(self.job_id,'get_tender_detail','bidresearch_detail',request.model_dump(),
                self.options.get('bidresearch_max_details',0),invoke,timeout=self.options.get('bidresearch_timeout',90)+5,
                limits={'searches':self.options.get('max_searches',0),'reads':self.options.get('max_reads',0),'requests':self.options.get('bidresearch_max_requests',0)},reservation=grant,strict_limits={'reads'})
        self.allowed_sources.update(s['id'] for s in result.get('sources',[]))
        return result

    async def _execute(self, name: str, arguments: dict) -> dict:
        """name/arguments为原工具请求；内部统一核验、预算和落账，外部调用使用execute获取并发槽。"""
        qcc_schemas={'qcc_company_lookup':QccCompanyLookup,'qcc_operation_lookup':QccOperationLookup,'qcc_risk_lookup':QccRiskLookup,'qcc_tender_lookup':QccTenderLookup}
        if name in qcc_schemas:
            guard(self.job_id)
            if isinstance(arguments, dict) and 'tool' in arguments:
                return {'error':'qcc_tool_not_allowed','sources':[],'authorized':False}
            try: args=qcc_schemas[name].model_validate(arguments).model_dump(exclude_none=True)
            except Exception: return {'error':'qcc_invalid_arguments','sources':[]}
            import os
            from .source_scope import reference_only
            if not self.options.get('qcc_enabled',True) or os.getenv('CLIENTREACH_QCC_ENABLED','').lower() in {'0','false','off'} or reference_only(self.prompt,reference_urls(self.prompt,self.options.get('enabled_channels',[]))):
                return {'error':'channel_disabled','sources':[]}
            from .mcp_tools import run_bounded
            fn={'qcc_company_lookup':qcc_company_lookup,'qcc_operation_lookup':qcc_operation_lookup,'qcc_risk_lookup':qcc_risk_lookup,'qcc_tender_lookup':qcc_tender_lookup}[name]
            result=await run_bounded(self.job_id,name,'qcc_mcp',args,self.options.get('max_qcc_calls',0),
                lambda:fn(self.job_id,qcc_schemas[name].model_validate(args)),timeout=55,in_flight='qcc_in_flight',exhausted='qcc_budget_exhausted')
            self.allowed_sources.update(source['id'] for source in result.get('sources',[]))
            return result
        schemas={'search_accounts':SearchAccounts,'fetch_source':FetchSource,'fetch_browser':FetchSource,'search_knowledge':SearchKnowledge,'search_research_data':SearchKnowledge,'persist_lead':PersistLead,'parse_account':ParseAccount,'persist_company':PersistCompany}
        guard(self.job_id)
        if name not in schemas:raise ServiceError('未授权工具调用')
        args=schemas[name].model_validate(arguments).model_dump()
        from langsmith.run_helpers import get_current_run_tree
        tree=get_current_run_tree()
        if tree:
            # 每类工具在LangSmith中独立命名，便于按工具筛选耗时与失败。
            tree.name=TRACE_NAMES.get(name,name)
            tree.add_metadata({'tool_name':name,'channel':args.get('channel','knowledge'),'job_id':self.job_id})
        # 明确关闭的平台连旧成功操作也不复用；在预算/供应商挡板前拒绝，不伪造实际尝试。
        if name in {'search_accounts','fetch_source','fetch_browser'} and args['channel'] not in self.options.get('enabled_channels',[]):
            return {'error':'channel_disabled','sources':[]}
        from .source_catalog import blocked_source
        if name in {'fetch_source','fetch_browser'} and blocked_source(args['url'],self.prompt):return {'error':'channel_disabled','sources':[]}
        if name in {'fetch_source','fetch_browser'}:
            with Session() as db:
                from .bidresearch_mcp import refused_detail
                if issue:=refused_detail(db,self.job_id,args['url']):return {'error':issue,'sources':[]}
                prior=db.scalars(select(Evidence).where(Evidence.job_id==self.job_id,Evidence.url==args['url']))
                issues={'blocked':'site_access_restricted','robots_denied':'site_robots_disallowed','robots_disallowed':'site_robots_disallowed','robots_unavailable':'site_policy_unavailable',
                        'login_required':'site_login_required','verification_required':'site_verification_required','captcha_required':'site_verification_required'}
                for source in prior:
                    meta=source.source_meta or {}
                    if meta.get('origin')=='bidresearch_mcp' and meta.get('detail_status') in issues:
                        return {'error':issues[meta['detail_status']],'sources':[]}
        from .public_accounts import PARSER_POLICY
        from .industry_navigation import NAVIGATION_POLICY
        from .evidence_role import ROLE_POLICY
        from .company_validation import COMPANY_POLICY
        policy=PARSER_POLICY if name=='parse_account' else NAVIGATION_POLICY+':contact-decode-3' if name=='fetch_source' else ROLE_POLICY if name=='persist_lead' else COMPANY_POLICY if name=='persist_company' else 'role-policy-2'
        search_objective=self.search_goal(args) if name=='search_accounts' else ''
        if search_objective:policy='entity-objective-1:'+hashlib.sha256(search_objective.encode()).hexdigest()
        operation=hashlib.sha256(json.dumps([policy,self.job_id,name,args],ensure_ascii=False,sort_keys=True).encode()).hexdigest()
        with Session.begin() as db:
            # SQLite串行预留后再释放事务发网络请求，两个并发读取不能互相挤掉额度。
            db.execute(text('BEGIN IMMEDIATE'))
            old=db.scalar(select(ToolCall).where(ToolCall.operation_id==operation))
            job=db.get(Job,self.job_id)
            resume_epoch=(job.metrics or {}).get('resume_epoch',0)
            retryable=bool(old and old.status in {'unavailable','rate_limited','paused','running'} and
                           resume_epoch>(old.last_attempt_epoch or 0))
            if retryable and (old.retry_after_epoch or 0)>time.time():
                return {'error':(old.result or {}).get('error','provider_rate_limited'),'sources':[],'retry_after_epoch':old.retry_after_epoch}
            if old and old.status=='running' and not retryable:
                return {'error':'operation_in_progress','sources':[]}
            if old and old.status=='paused' and not retryable:
                return {'error':'operation_paused','sources':[]}
            if old and name!='persist_lead' and old.status in {'completed','unavailable','rate_limited','rejected'} and not retryable:
                result={**(old.result or {}),'reused':True};reused_status=old.status
                sources=result.get('sources') or []
                permitted=[source for source in sources if not blocked_source(source.get('url',''),self.prompt)]
                if len(permitted)!=len(sources):
                    result={**result,'sources':permitted,'error':result.get('error') or ('' if permitted else 'empty_results')}
                self.allowed_sources.update(x['id'] for x in result.get('sources',[]))
                attempt=old.attempts or 1
            else:
                result=None
                if name in {'search_accounts','fetch_source','fetch_browser'}:
                    # 冷却挡板在预留额度前检查，未发送的请求不记作实际尝试。
                    limited=list(db.scalars(select(ToolCall).where(ToolCall.status=='rate_limited',ToolCall.retry_after_epoch>time.time())))
                    host=urlparse(args.get('url','')).hostname
                    for record in limited:
                        failure=record.result or {}
                        if (name=='search_accounts' and failure.get('error')=='provider_rate_limited') or (host and failure.get('host')==host):
                            return {'error':failure['error'],'sources':[],'retry_after_epoch':record.retry_after_epoch}
                    ceiling=self.options['max_searches'] if name=='search_accounts' else self.options['max_reads']
                    names=[name] if name=='search_accounts' else ['fetch_source','fetch_browser']
                    from .mcp_tools import network_usage
                    count=network_usage(db,self.job_id)['searches' if name=='search_accounts' else 'reads']
                    if count>=ceiling:return {'error':'budget_exhausted','sources':[]}
                    if name=='fetch_browser':
                        from .browser_reader import browser_settings
                        browser_count=db.scalar(select(func.coalesce(func.sum(ToolCall.attempts),0)).where(ToolCall.job_id==self.job_id,ToolCall.tool==name))
                        if browser_count>=browser_settings()['max_pages']:return {'error':'browser_budget_exhausted','sources':[]}
                    if args['channel'] not in self.options['enabled_channels']:return {'error':'channel_disabled','sources':[]}
                    if name=='search_accounts':
                        job=db.get(Job,self.job_id)
                        prior=list(db.scalars(select(ToolCall).where(ToolCall.job_id==self.job_id,ToolCall.tool==name)))
                        for lead in db.scalars(select(Lead).where(Lead.id.in_(job.lead_ids or []))):
                            if lead.display_name in args['query'] and sum((x.attempts or 1) for x in prior if lead.display_name in x.arguments.get('query',''))>=self.options.get('max_candidate_searches',3):
                                return {'error':'candidate_budget_exhausted','sources':[]}
                if not old:
                    attempt=1
                    db.add(ToolCall(job_id=self.job_id,operation_id=operation,tool=name,channel=args.get('channel','knowledge'),arguments=args,last_attempt_epoch=time.time()))
                else:
                    old.attempts=(old.attempts or 1)+1;old.last_attempt_epoch=time.time();old.status='running';old.retry_after_epoch=0
                    attempt=old.attempts
        if result is not None:
            from .tool_views import tool_arguments, tool_result
            emit(self.job_id,'tool.reused',{'tool':name,'operation_id':operation,'channel':args.get('channel','knowledge'),
                 'arguments':tool_arguments(args),'status':reused_status,'attempts':attempt,**tool_result(result)},'复用已取得结果' if reused_status=='completed' else '保留本轮失败记录')
            return result
        channel=args.get('channel','knowledge')
        start=time.monotonic()
        from .tool_views import tool_arguments, tool_result
        emit(self.job_id,'tool.started',{'tool':name,'channel':channel,'operation_id':operation,
             'arguments':tool_arguments(args),'status':'running','attempts':attempt},CHANNELS.get(channel,{}).get('name',name))
        state='completed'
        try:
            if name in {'search_accounts','fetch_source','fetch_browser'}:
                if channel not in self.options['enabled_channels']:raise ServiceError('channel_disabled')
            if name=='search_accounts': result=await self.search(args)
            elif name=='fetch_source':result=await self.fetch(args)
            elif name=='fetch_browser':result=await self.fetch_browser(args)
            elif name=='parse_account':
                if args['source_id'] not in self.allowed_sources:raise ServiceError('来源未被本任务取得')
                with Session() as db:source=serialize(db.get(Evidence,args['source_id']))
                if source['channel']!=channel or channel not in self.options['enabled_channels']:raise ServiceError('channel_disabled')
                from .public_accounts import parse_accounts
                candidates=parse_accounts(source,self.profile.get('region',''),self.profile.get('products',[]),args['target_roles'])
                result={'candidates':[candidate.model_dump() for candidate in candidates],'sources':[source] if candidates else [],'error':''}
            elif name=='search_knowledge':
                if 'knowledge' not in self.options['enabled_channels']:raise ServiceError('channel_disabled')
                items=search_knowledge(args['query'])
                with Session() as db:
                    sources=[serialize(row) for x in items if x.get('source_id') and not x['source_id'].startswith('attachment:') and (row:=db.get(Evidence,x['source_id']))]
                result={'knowledge':items,'sources':sources,'cached':True}
            elif name=='search_research_data':
                from .research_dataset import local_research
                result=local_research(args['query'],self.options.get('research_targets',[]))
                with Session() as db:
                    # 历史导入渠道可能是disclosure等原平台名，按真实URL许可筛选，不能因此丢弃合法年报。
                    from .source_catalog import blocked_source
                    result['sources']=[serialize(source) for sid in result['source_ids'] if (source:=db.get(Evidence,sid))
                        and any(matches_channel(channel,source.url) for channel in self.options.get('enabled_channels',[]) if channel!='knowledge')
                        and not blocked_source(source.url,self.prompt)]
                result['cached']=True
            elif name=='persist_company':
                from .company_validation import save_snapshot
                # 数据库事务在独立线程执行；提交和来源绑定完成后才发tool.finished与展示结果。
                save_task=asyncio.create_task(asyncio.to_thread(save_snapshot,self.job_id,CompanySnapshot.model_validate(args['snapshot']),set(self.allowed_sources),args['targets'],args.get('relation_id')))
                try:result=await asyncio.shield(save_task)
                except asyncio.CancelledError:
                    # 线程事务不能强杀；阻止立即恢复重放，提交后清理标记，业务保存本身仍幂等。
                    if not save_task.done():track_pending(save_task,self.job_id)
                    raise
            else:result=self.persist(Candidate.model_validate(args['candidate']))
            if name=='fetch_source' and result.get('error')=='empty_body':state='unavailable'
            self.allowed_sources.update(x['id'] for x in result.get('sources',[]))
        except (Paused,asyncio.CancelledError):
            elapsed=round((time.monotonic()-start)*1000)
            result={'error':'operation_paused','sources':[]}
            with Session.begin() as db:
                row=db.scalar(select(ToolCall).where(ToolCall.operation_id==operation))
                row.status,row.updated_at,row.result='paused',now(),result
                row.elapsed_ms=(row.elapsed_ms or 0)+elapsed;elapsed=row.elapsed_ms
            emit(self.job_id,'tool.finished',{'tool':name,'channel':channel,'operation_id':operation,'elapsed_ms':elapsed,
                'status':'paused','attempts':attempt,**tool_result(result)},'已暂停')
            raise
        except Exception as exc:
            reason=safe_error(exc)
            if not isinstance(exc,ServiceError):
                # 未预期工具错误只记录类型和栈位置，避免模糊error无法定位，也不泄露参数/网页正文。
                LOG.warning('tool_error',extra={'details':{'job_id':self.job_id,'tool':name,
                    'channel':channel,'error_type':reason,**error_details(exc)}})
            limited=source_limit(exc)
            if not limited and isinstance(exc,ServiceError) and str(exc) in {'provider_rate_limited','site_rate_limited'}:
                limited=SourceRateLimit('site' if str(exc).startswith('site') else 'provider',host=urlparse(args.get('url','')).hostname or '')
            if limited:
                state='rate_limited';result={'error':str(limited),'sources':[],'retry_after_epoch':time.time()+limited.delay,'host':limited.host}
            else:
                state='rejected' if isinstance(exc,ServiceError) and str(exc) not in {'site_login_required','site_verification_required','site_access_restricted','site_robots_disallowed','site_policy_unavailable'} else 'unavailable'
                result={'error':str(exc) if isinstance(exc,ServiceError) else reason,'sources':[]}
            if name=='search_accounts' and self.options.get('hybrid_research'):
                result={**result,'sources':self.search_history.get(args['query'],[]),'cached_source_ids':[source['id'] for source in self.search_history.get(args['query'],[])],
                    'fresh_source_ids':[],'network_attempted':True}
            outcome=self.read_outcomes.get(args.get('url','')) if name=='fetch_source' else None
            if outcome:
                phase='fallback_status' if outcome['fallback_status']=='reading' else 'primary_status'
                if outcome[phase]=='reading':outcome[phase]=str(limited) if limited else 'failed'
        if name=='fetch_source' and args['url'] in self.read_outcomes:
            result={**result,'read_outcome':dict(self.read_outcomes[args['url']])}
        self.allowed_sources.update(source['id'] for source in result.get('sources',[]))
        elapsed=round((time.monotonic()-start)*1000);attempt_elapsed=elapsed
        with Session.begin() as db:
            row=db.scalar(select(ToolCall).where(ToolCall.operation_id==operation))
            row.result,row.status,row.elapsed_ms,row.updated_at=result,state,(row.elapsed_ms or 0)+elapsed,now()
            if state=='rate_limited':row.retry_after_epoch=result['retry_after_epoch']
            elapsed=row.elapsed_ms
        emit(self.job_id,'tool.finished',{'tool':name,'channel':channel,'operation_id':operation,'elapsed_ms':elapsed,'status':state,
             'attempts':attempt,**tool_result(result)},'完成' if state=='completed' else '该渠道未取得结果')
        LOG.info('tool_finished',extra={'details':{'job_id':self.job_id,'tool':name,'channel':channel,'status':state,'elapsed_ms':elapsed,'operation_id':operation}})
        if name in {'search_accounts','fetch_source','fetch_browser'} and not self.options.get('company_force_refresh'):
            # 企业研究没有卖方产品画像，不生成无关空品类渠道经验。
            recipe(channel,bool(result.get('sources')),attempt_elapsed,self.profile)
        return result

    def search_goal(self, args: dict) -> str:
        """args含非空已校验query/channel；返回有界检索目标，仅用本任务已存事实，不新增证据或授权。"""
        objective=CHANNELS[args['channel']]['objective']
        with Session() as db:
            job=db.get(Job,self.job_id)
            leads=list(db.scalars(select(Lead).where(Lead.id.in_(job.lead_ids or [])))) if job else []
            if job and job.query_mode=='company_query':
                objective='研究用户指定企业的身份、行业、主营、公开联系、经营报告、实际买方采购公告与年度具名上下游。优先企业官网、原始年报/财报与原公告，集团和子公司分开；未知可返回空，不从相似企业借字段。'
        from .contact_view import contact_view
        from .public_directory import branch_key
        for lead in sorted(leads,key=lambda item:item.id):
            if lead.display_name not in args['query']:continue
            contacts=contact_view(lead.facts,lead.evidence)
            identity={'name':lead.display_name,'city':lead.city}
            if 'phone' in contacts['usable_fields']:identity['phone']=lead.facts['phone']['value']
            if 'email' in contacts['usable_fields']:identity['email']=lead.facts['email']['value']
            objective+=' 当前补查已保存主体：'+json.dumps(identity,ensure_ascii=False)+'。优先同一主体的明确介绍与联系记录；名称相似不算匹配，查询无合格证据可返回空。'
            if any(item.get('field')=='name' and branch_key(item.get('url','')) for item in lead.evidence or []):
                objective+=' 这是分店目录的商户原名，不是已确认工商公司名；优先原电话或相同分店明确关联记录，排除仅同品牌的集团、制造公司或其他门店，不能用其资料填补本商户。'
        return objective[:4096]

    async def search(self, args: dict) -> dict:
        """args是已校验查询/渠道；从实际主体计算目标，同目标24小时缓存，失败抛出原异常，不绕provider限流。"""
        capability=CHANNELS[args['channel']]
        suffix=self.search_goal(args)
        context_hash=hashlib.sha256(suffix.encode()).hexdigest()
        cached_sources=[]
        with Session() as db:
            previous=list(db.scalars(select(ToolCall).where(ToolCall.tool=='search_accounts',ToolCall.status=='completed').order_by(ToolCall.updated_at.desc()).limit(60)))
            for row in previous:
                if row.arguments==args and row.result and row.result.get('search_context_hash')==context_hash and row.updated_at>expires(-1):
                    from .source_catalog import blocked_source
                    sources=[source for source in row.result.get('sources',[]) if not blocked_source(source.get('url',''),self.prompt)]
                    if not self.options.get('hybrid_research'):
                        return {**row.result,'sources':sources,'error':row.result.get('error') or ('' if sources else 'empty_results'),'cached':True}
                    cached_sources=sources;break
        self.search_history[args['query']]=cached_sources
        import re
        projects=re.findall(r'(?<![A-Za-z0-9])[A-Z]{2,}\d{6,}(?![A-Za-z0-9])',args['query']) if capability.get('procurement') else []
        query=(' '.join('"'+key+'"' for key in projects)+' '+args['query']+' '+capability.get('scope','')).strip()
        if projects:suffix+=' 必须匹配项目编号 '+','.join(projects)+'，不得返回其他项目替代。'
        count=min(20,max(8,self.options.get('research_pages_per_query',4)*2)) if self.options.get('hybrid_research') else 5
        provider='exa'
        try:
            body=await cancellable(call_exa('web_search_exa',{'query':query,'objective':suffix,'numResults':count}),self.job_id,60)
            found=split_sources(body)
        except (Paused,asyncio.CancelledError):raise
        except Exception as exc:
            # Exa限流/失败时改用内置OpenCLI中文检索；兜底也失败才把Exa原异常交给上层分类为限流或不可用。
            found=await self.fallback_search(query)
            if found is None:raise exc
            provider='opencli'
        # 来源必须真的属于所选平台，搜索返回其他黄页不能伪称1688或企查查结果。
        from .source_catalog import blocked_source
        discovered=[x for x in found if matches_channel(args['channel'],x.get('url','')) and not blocked_source(x.get('url',''),self.prompt)]
        if projects:discovered=[x for x in discovered if all(key in x.get('title','')+' '+x.get('body','')+' '+x.get('url','') for key in projects)]
        sources=archive_sources(self.job_id,discovered,'搜索摘录',args['channel'])
        fresh_ids=[source['id'] for source in sources]
        # 同URL的新摘录优先，其他历史命中保留原取得时间，不冒充本轮新搜索。
        combined=list({source['url']:source for source in [*cached_sources,*sources]}.values())
        return {'sources':combined,'channel':args['channel'],'error':'' if sources else 'empty_results','search_context_hash':context_hash,'provider':provider,
            'fresh_source_ids':fresh_ids,'cached_source_ids':[source['id'] for source in combined if source['id'] not in fresh_ids],
            'network_attempted':True,'cached':False}

    async def fallback_search(self, query: str) -> list[dict] | None:
        """query为已拼好的检索词；经内置OpenCLI百度/搜狗检索，返回与Exa解析一致的来源列表，运行时不可用或全部失败返回None。"""
        from .web_search import opencli_search_async, available
        if not available():return None
        results=await opencli_search_async([query],10)
        rows=[row for item in results for row in item.rows]
        if not rows and all(item.error for item in results):return None
        return [{'url':row.url,'title':row.title,'body':(row.title+'\n'+row.snippet).strip(),'published_at':row.published_at or None,
                 'source_meta':{'origin':'agent','search_provider':'opencli_'+row.engine}} for row in rows]

    async def fetch(self, args: dict) -> dict:
        """args含发现的url和渠道；缓存有效正文优先，公开HTML提取优先，独立读取失败码可驱动换渠道。"""
        outcome={'primary_status':'not_attempted','fallback_status':'not_attempted'}
        self.read_outcomes[args['url']]=outcome
        from .source_catalog import blocked_source
        # 离线诊断的最小options可省渠道配置；明确空名单/禁用仍拒，实际工具execute始终要求任务渠道。
        if ('enabled_channels' in self.options and args['channel'] not in self.options['enabled_channels']) or blocked_source(args['url'],self.prompt):raise ServiceError('channel_disabled')
        if not matches_channel(args['channel'],args['url']):raise ServiceError('source_channel_mismatch')
        with Session() as db:
            discovered=list(db.scalars(select(Evidence).where(Evidence.id.in_(self.allowed_sources))))
            from .public_directory import directory_links
            # 许可只来自本任务实际读取的同渠道目录，不能让模型任意拼出公告或分店URL。
            linked={link for row in discovered if row.channel==args['channel'] and row.kind=='网页正文'
                for link in directory_links(row.body,row.url,self.profile,row.channel)}
            from .public_website import website_links
            job=db.get(Job,self.job_id)
            selected=[serialize(row) for key in (job.lead_ids or []) if (row:=db.get(Lead,key))] if job else []
            linked.update(item['url'] for item in website_links([serialize(row) for row in discovered],selected,self.options.get('enabled_channels',[])) if item['channel']==args['channel'])
            if args['url'] not in {x.url for x in discovered} and args['url'] not in self.reference_urls and args['url'] not in linked:raise ServiceError('url_not_discovered')
            cached=db.scalar(select(Evidence).where(Evidence.url==args['url'],Evidence.kind.in_(['网页正文','网页读取']),Evidence.expires_at>now(),func.length(Evidence.body)>150).order_by(Evidence.captured_at.desc()))
            # 历史错误解码正文不作为有效缓存；保留旧Evidence，不重写审计原文。
        from .source_content import has_content
        cache_ready=not self.options.get('company_force_refresh',False) and cached and cached.body.count('\ufffd')<=max(3,len(cached.body)//100) and not access_issue(cached.url,cached.title,cached.body) and has_content(serialize(cached))
        origin=(urlparse(args['url']).hostname or '').lower()
        from .source_policy import requires_policy
        if cache_ready and not requires_policy(args['url']):
            outcome['primary_status']='cached'
            return {'sources':[serialize(cached)],'cached':True}
        if not await asyncio.to_thread(public_url,args['url']):raise ServiceError('url_not_public')
        from .source_policy import reading_delay
        await cancellable(reading_delay(args['url']),self.job_id,12)
        if cache_ready:
            outcome['primary_status']='cached'
            return {'sources':[serialize(cached)],'cached':True}
        # 无登录态公开HTML；重定向逐跳校验，遇到反爬/付费入口不伪装取得正文。
        async def read_html():
            from trafilatura import extract
            async with httpx.AsyncClient(timeout=20,follow_redirects=False,headers={'User-Agent':'ClientReach/0.2 PublicResearch'}) as client:
                url=args['url']
                for _ in range(4):
                    if blocked_source(url,self.prompt):raise ServiceError('channel_disabled')
                    if not await asyncio.to_thread(public_url,url):raise ServiceError('url_not_public')
                    if not matches_channel(args['channel'],url):raise ServiceError('source_channel_mismatch')
                    delay=await reading_delay(url)
                    host=urlparse(url).hostname
                    with SITE_LOCK:
                        scheduled=max(time.monotonic(),SITE_CLOCK.get(host,0));SITE_CLOCK[host]=scheduled+delay
                    # 同站公开页面至少间隔1秒；暂停会取消等待，不靠重试绕过限制。
                    await asyncio.sleep(max(0,scheduled-time.monotonic()))
                    # 已排队的同站请求也必须服从前一请求刚返回的Retry-After。
                    with Session() as db:
                        blocked=db.scalar(select(ToolCall).where(ToolCall.status=='rate_limited',
                            ToolCall.retry_after_epoch>time.time(),ToolCall.result['host'].as_string()==host))
                        if blocked:raise SourceRateLimit('site',blocked.retry_after_epoch-time.time(),host)
                    outcome['primary_status']='reading'
                    response=await client.get(url)
                    outcome['http_status']=response.status_code
                    emit(self.job_id,'source.http',{'host':host,'status_code':response.status_code,
                        'content_bytes':len(response.content),'html': 'html' in response.headers.get('content-type','')})
                    if response.is_redirect:
                        from urllib.parse import urljoin
                        url=urljoin(url,response.headers.get('location',''));continue
                    if response.status_code in {401,403}:raise ServiceError('site_access_restricted')
                    if response.status_code==567 and (host=='qcc.com' or host.endswith('.qcc.com')):raise ServiceError('site_access_restricted')
                    if response.status_code==429:raise SourceRateLimit('site',retry_delay(response.headers.get('retry-after')),host)
                    response.raise_for_status()
                    if response.content.startswith(b'%PDF'):
                        if len(response.content)>16_000_000: raise ServiceError('pdf_too_large')
                        import io
                        from pypdf import PdfReader
                        from .config import DATA
                        def parse_pdf():
                            """无参数；只解析已读PDF字节，保留页界与原文，坏PDF向上传递错误。"""
                            reader=PdfReader(io.BytesIO(response.content))
                            return '\n\n'.join(f'===== PDF PAGE {index+1} =====\n'+(page.extract_text() or '') for index,page in enumerate(reader.pages))
                        body=await asyncio.to_thread(parse_pdf)
                        if len(body)<150:raise ServiceError('pdf_no_text')
                        digest=hashlib.sha256(response.content).hexdigest()
                        archive=DATA/'research_sources/agent';archive.mkdir(parents=True,exist_ok=True)
                        target=archive/(digest+'.pdf')
                        if not target.exists():target.write_bytes(response.content)
                        outcome.update(primary_status='completed',body_chars=len(body),format='pdf')
                        return {'url':url,'title':body.splitlines()[1][:120] or url,'body':body,
                            'source_meta':{'origin':'agent','format':'pdf','sha256':digest,'hash_object':'original_pdf','archive_path':str(target)}}
                    if len(response.content)>2_000_000 or 'html' not in response.headers.get('content-type',''):
                        outcome['primary_status']='unsupported_content'
                        return None
                    # 原始字节交给trafilatura识别HTML charset；httpx对无charset头默认UTF-8会损坏GB2312站点。
                    clean=await asyncio.to_thread(extract,response.content,output_format='json',with_metadata=True,include_tables=True,favor_recall=True)
                    data=json.loads(clean) if clean else {}
                    from .public_subject import subject_title
                    subject=await asyncio.to_thread(subject_title,response.content,url)
                    if subject:data['title']=subject
                    body=data.get('text','')
                    if args['channel'] in {'official','procurement'}:
                        from .public_tender_tables import table_text
                        tables=await asyncio.to_thread(table_text,response.content,url)
                        # 单元格来自可见DOM；重复行省略，缺失表格保留单独原文块。
                        existing={re.sub(r'\s+','',line) for line in body.splitlines()}
                        if tables and any(re.sub(r'\s+','',line) not in existing for line in tables.splitlines()):body+='\n\n'+tables
                    from .industry_navigation import factual_body
                    # 网页自行写出的导航附录不授予许可；只保留实际DOM抽取后由工具生成的链接。
                    body=factual_body(body)
                    from .public_directory import directory_text
                    directory=await asyncio.to_thread(directory_text,response.content,url)
                    if directory:body=directory
                    # 明确登录/人机验证页不能作为企业正文，也不通过其他供应商再次读同一限制页。
                    issue=access_issue(url,data.get('title',''),body)
                    if issue:raise ServiceError(issue)
                    import os
                    if os.getenv('CLIENTREACH_CAPTURE_HTML')=='1':
                        from .config import DATA,ROOT
                        # 仅隔离诊断库存真实已允许读取的HTML；不让调试开关写生产文件或用网址控制路径。
                        if DATA.resolve().is_relative_to((ROOT/'.codex-tmp').resolve()):
                            folder=DATA/'source-html';folder.mkdir(parents=True,exist_ok=True)
                            (folder/(hashlib.sha256(url.encode()).hexdigest()+'.html')).write_bytes(response.content)
                    from .public_contacts import contact_blocks
                    contact=await asyncio.to_thread(contact_blocks,response.content)
                    if contact and contact not in body:body+='\n\n'+contact
                    if args['channel']=='industry_directory':
                        from .industry_navigation import navigation_text,factual_body
                        # 页面自己写的“目录导航”文字不授予链接许可；仅附加真实DOM抽取的导航。
                        body=factual_body(body)
                        navigation=await asyncio.to_thread(navigation_text,response.content,url,self.profile)
                        if navigation:body+='\n\n'+navigation
                    from .public_website import website_text
                    websites=await asyncio.to_thread(website_text,response.content,url,data.get('title',''))
                    if websites:body+='\n\n'+websites
                    from .industry_navigation import navigation_links
                    emit(self.job_id,'source.parsed',{'host':host,'body_chars':len(body),
                        'navigation_count':len(navigation_links(body,url,self.profile)) if args['channel']=='industry_directory' else 0,
                        'has_content':has_content({'title':data.get('title') or url,'url':url,'body':body})})
                    outcome['body_chars']=len(body)
                    if len(body)<150 or body.count('\ufffd')>max(3,len(body)//100) or not has_content({'title':data.get('title') or url,'url':url,'body':body}):
                        outcome['primary_status']='empty_body'
                        return None
                    outcome['primary_status']='completed'
                    # 首页抽取器常把首条新闻日期当页面日期；不能拿它给公司介绍/能力标发布日期。
                    published=data.get('date') if urlparse(url).path not in {'','/'} else None
                    return {'url':url,'title':data.get('title') or url,'body':body,'published_at':published}
            outcome['primary_status']='redirect_limit'
            return None
        try:item=await cancellable(read_html(),self.job_id,30)
        except (httpx.HTTPError,TimeoutError) as error:
            emit(self.job_id,'source.read_failed',{'error_type':type(error).__name__,'host':origin})
            outcome['primary_status']='failed'
            item=None
        if item:sources=archive_sources(self.job_id,[item],'网页正文',args['channel'])
        else:
            with Session() as db:
                blocked=db.scalar(select(ToolCall).where(ToolCall.status=='rate_limited',
                    ToolCall.retry_after_epoch>time.time(),ToolCall.result['error'].as_string()=='provider_rate_limited'))
                if blocked:
                    outcome['fallback_status']='provider_rate_limited'
                    raise SourceRateLimit(delay=blocked.retry_after_epoch-time.time())
            async with provider_slot(self.job_id):
                # 搜索与备用读取共享供应商门；排队后重查冷却，不能以并发绕过限流。
                with Session() as db:
                    blocked=db.scalar(select(ToolCall).where(ToolCall.status=='rate_limited',ToolCall.retry_after_epoch>time.time(),
                        ToolCall.result['error'].as_string()=='provider_rate_limited'))
                    if blocked:raise SourceRateLimit(delay=blocked.retry_after_epoch-time.time())
                outcome['fallback_status']='reading'
                content=await cancellable(call_exa('web_fetch_exa',{'urls':[args['url']],'maxCharacters':18000}),self.job_id,45)
            fetched=[x for x in split_sources(content) if matches_channel(args['channel'],x.get('url','')) and not blocked_source(x.get('url',''),self.prompt)]
            issues=[access_issue(x.get('url',''),x.get('title',''),x.get('body','')) for x in fetched]
            usable=[x for x,issue in zip(fetched,issues) if not issue and has_content(x)]
            if not usable and any(issues):raise ServiceError(next(issue for issue in issues if issue))
            sources=archive_sources(self.job_id,usable,'网页读取',args['channel'])
            outcome['fallback_status']='completed' if sources else 'empty_body'
        return {'sources':sources,'error':'' if sources else 'empty_body'}

    async def fetch_browser(self, args: dict) -> dict:
        """args为已发现URL/渠道；专用Edge读取服从同一许可/取消和预算，明确访问拒绝不绕过，返回真实归档。"""
        if not matches_channel(args['channel'],args['url']):raise ServiceError('source_channel_mismatch')
        with Session() as db:
            discovered=list(db.scalars(select(Evidence).where(Evidence.id.in_(self.allowed_sources))))
            if args['url'] not in {s.url for s in discovered} and args['url'] not in self.reference_urls:raise ServiceError('url_not_discovered')
            denied=db.scalar(select(ToolCall).where(ToolCall.job_id==self.job_id,ToolCall.tool=='fetch_source',
                ToolCall.arguments['url'].as_string()==args['url'],ToolCall.result['error'].as_string().in_(['site_access_restricted','site_login_required','site_verification_required','site_robots_disallowed'])))
            if denied:raise ServiceError('browser_read_not_permitted_after_access_denial')
        from .browser_reader import read_edge
        result=await cancellable(read_edge(args['url'],self.job_id),self.job_id,120)
        if not matches_channel(args['channel'],result['url']):raise ServiceError('source_channel_mismatch')
        sources=archive_sources(self.job_id,[{'url':result['url'],'title':result['title'],'body':result['body'],
            'source_meta':{'origin':'agent','backend':result['backend'],'opencli_version':result['opencli_version'],
                'truncated':result['truncated'],'screenshot':result['screenshot'],'requested_url':args['url']}}], 'Edge网页正文',args['channel'])
        return {'sources':sources,'backend':result['backend'],'error':'' if sources else 'empty_body'}

    def persist(self, candidate: Candidate) -> dict:
        """candidate为校验结构；角色/原文/来源作用域满足后才入库，不保存已被用户排除的主体。"""
        allowed_products={x['name'] for x in self.profile.get('products',[])}
        if any(x not in allowed_products for x in candidate.matched_products):raise ServiceError('产品不在用户资料中')
        excluded=store.search((WORKSPACE,'exclusion'),limit=200)
        if any(x.value.get('content')==candidate.display_name for x in excluded):raise ServiceError('用户已排除此客户')
        with Session() as db:
            job=db.get(Job,self.job_id)
            if job and len(job.lead_ids or [])>=self.options['max_leads']:
                from .identity import city_key
                existing=[x for x in db.scalars(select(Lead).where(Lead.id.in_(job.lead_ids))) if x.display_name==candidate.display_name and city_key(x.city)==city_key(candidate.city)]
                if not existing:raise ServiceError('target_count_reached')
                from .public_directory import branch_key
                incoming_branches={branch_key(row.url) for fact in candidate.facts if fact.field=='name' and
                    (row:=db.get(Evidence,fact.source_id)) and branch_key(row.url)}
                if incoming_branches:
                    existing=[lead for lead in existing if incoming_branches & {branch_key(item.get('url','')) for item in lead.evidence or [] if item.get('field')=='name'}]
                    if not existing:raise ServiceError('branch_identity_conflict')
                incoming_address=next((x.value for x in candidate.facts if x.field=='address'),'')
                old_address=(existing[0].facts or {}).get('address',{}).get('value','')
                if incoming_address and old_address and incoming_address!=old_address:
                    from .evidence_role import same_subject_page
                    name_ids={fact.source_id for fact in candidate.facts if fact.field=='name'}
                    name_sources={row.id:serialize(row) for row in db.scalars(select(Evidence).where(Evidence.id.in_(name_ids)))}
                    if not same_subject_page(candidate.display_name,existing[0].evidence or [],name_sources):raise ServiceError('branch_identity_conflict')
            ids=[x.source_id for x in candidate.facts]
            if candidate.procurement_signal:ids.append(candidate.procurement_signal.source_id)
            if not set(ids).issubset(self.allowed_sources):raise ServiceError('来源未被本任务取得')
            rows={x.id:serialize(x) for x in db.scalars(select(Evidence).where(Evidence.id.in_(ids)))}
        from .source_catalog import blocked_source
        if any(blocked_source(row['url'],self.prompt) for row in rows.values()):raise ServiceError('channel_disabled')
        from .bidresearch_mcp import software_service_profile,software_service_match,active_procurement_requested
        if candidate.buyer_role=='project_buyer' and software_service_profile(self.profile):
            ids={fact.source_id for fact in candidate.facts if fact.field in {'buyer_role','procurement'}}
            if candidate.procurement_signal:ids.add(candidate.procurement_signal.source_id)
            if not any(software_service_match(rows[sid]['title'],rows[sid]['body']) for sid in ids):
                raise ServiceError('采购原文未证明软件或AI服务需求')
            if active_procurement_requested(self.prompt):
                signal=candidate.procurement_signal
                from .procurement import open_buyer_signal
                if not open_buyer_signal(candidate.display_name,signal,rows.get(signal.source_id) if signal else None,now()):
                    raise ServiceError('尚未核验到正在开放的软件或服务采购机会')
        result=save_candidate(candidate,rows,self.job_id)
        with Session() as db:validated_facts=db.get(Lead,result['id']).facts or {}
        for cite in candidate.facts:
            if validated_facts.get(cite.field,{}).get('verification') in {'disputed','inactive'}:continue
            source=rows[cite.source_id]
            upsert_knowledge(candidate.display_name,cite.quote,'public_fact',cite.source_id,source['url'],result['id'],source.get('expires_at') or expires(30))
        if candidate.procurement_signal:
            signal=candidate.procurement_signal;source=rows[signal.source_id]
            for excerpt in dict.fromkeys([signal.quote,signal.buyer_quote,signal.deadline_quote]):
                if excerpt:upsert_knowledge(candidate.display_name,excerpt,'public_fact',signal.source_id,source['url'],result['id'],source.get('expires_at') or expires(30))
        return result
