"""Web API入口：只编排请求，业务与Agent在独立模块。"""
import asyncio
import io
import json
import time
import uuid
import os
from pathlib import Path
from contextlib import asynccontextmanager
from datetime import datetime
from fastapi import FastAPI, UploadFile, File, Query, Request
from fastapi.responses import JSONResponse, StreamingResponse, FileResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from sqlalchemy import select, func
from .config import ROOT
from .db import initialize, Session, Conversation, Job, JobEvent, Lead, Followup, Setting, Evidence, serialize, now
from .schemas import MessageInput, LeadInput, FollowupInput, SettingsInput, FeedbackInput, MemoryInput, KnowledgeInput, CompanyResearchInput, BrowserSettingsInput, BrowserReadInput, IdentityConfirmationInput, LeadAnalysisInput
from .service import ServiceError, settings, save_settings, conversation_detail, submit, list_leads, lead_detail, edit_lead, import_sample, export_workbook, job_detail, job_events, resume_task
from .files import save_attachment, attachment_detail
from .observability import logger, safe_error

LOG = logger('api')


@asynccontextmanager
async def lifespan(app: FastAPI):
    """app为当前FastAPI实例，启动建立本地表，退出不删除任何数据。"""
    initialize()
    yield


app = FastAPI(title='Client Reach API', version='0.3.0', lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=['http://127.0.0.1:5173', 'http://localhost:5173'],
                   allow_methods=['GET', 'POST', 'PATCH', 'DELETE'], allow_headers=['Content-Type', 'X-Request-ID'])


@app.middleware('http')
async def correlation(request: Request, call_next):
    """request和call_next由框架提供；生成请求ID，记录状态耗时，不记录正文和授权头。"""
    request_id = uuid.uuid4().hex[:12]
    request.state.request_id = request_id
    start = time.perf_counter()
    try:
        response = await call_next(request)
    except Exception as exc:
        LOG.error('unhandled_error', extra={'details': {'request_id': request_id, 'type': safe_error(exc)}})
        response = JSONResponse({'error': '服务执行失败，请根据请求ID查看日志', 'request_id': request_id}, status_code=500)
    response.headers['X-Request-ID'] = request_id
    LOG.info('request', extra={'details': {'request_id': request_id, 'method': request.method,
        'path': request.url.path, 'status': response.status_code, 'duration_ms': round((time.perf_counter() - start) * 1000)}})
    return response


@app.exception_handler(ServiceError)
async def service_error(request: Request, exc: ServiceError):
    """request与业务exc非空；返回规范错误和请求ID，不暴露内部provider数据。"""
    return JSONResponse({'error': str(exc), 'request_id': getattr(request.state, 'request_id', '')}, status_code=exc.status)


@app.get('/api/health')
def health():
    """返回本地服务和Worker心跳；不存在心跳明确offline，不代替模型连接测试。"""
    with Session() as db:
        worker = db.get(Setting, 'worker')
        alive = bool(worker and (datetime.strptime(now(), '%Y-%m-%d %H:%M:%S') - datetime.strptime(worker.value['last_seen'], '%Y-%m-%d %H:%M:%S')).total_seconds() < 20)
    from .company_models import Company
    with Session() as db:
        data_as_of = db.scalar(select(func.max(Company.research_as_of))) or ''
    return {'status': 'ok', 'version': '0.3.0', 'worker_online': alive, 'model': 'gpt-6-luna','engine':'LangGraph', 'data_as_of': data_as_of,
            'worker_heartbeat':worker.value.get('heartbeat_epoch',0) if worker else 0}


@app.get('/api/tracing')
def get_tracing():
    """无参数；返回LangSmith可用状态，未配置密钥时关闭，不进行探测或泄露凭据。"""
    from .tracing import tracing_status
    return tracing_status()


@app.get('/api/conversations')
def conversations():
    """返回最近100段持久化会话，空库返回空列表。"""
    with Session() as db:
        from .conversation import short_title
        return [{**serialize(x),'title':short_title(x.title)} for x in db.scalars(select(Conversation).order_by(Conversation.updated_at.desc()).limit(100))]


@app.post('/api/conversations', status_code=201)
def new_conversation():
    """创建空获客会话并返回ID，不立即调用外部模型或搜索。"""
    with Session.begin() as db:
        row = Conversation()
        db.add(row)
        db.flush()
        return serialize(row)


@app.get('/api/conversations/{conversation_id}')
def get_conversation(conversation_id: str):
    """conversation_id须非空，返回对话详情；不存在404。"""
    return conversation_detail(conversation_id)


@app.post('/api/conversations/{conversation_id}/messages', status_code=202)
def send_message(conversation_id: str, body: MessageInput):
    """非空conversation_id及已校验body入任务队列；重复请求幂等，活动任务409。"""
    return submit(conversation_id, body.model_dump())


@app.post('/api/attachments', status_code=201)
async def upload(file: UploadFile = File(...)):
    """file须为支持的产品附件且<=10MB；解析线程不阻塞API，返回元信息。"""
    content = await file.read(10 * 1024 * 1024 + 1)
    return await asyncio.to_thread(save_attachment, file.filename or 'file', content)


@app.get('/api/attachments/{attachment_id}')
def get_attachment(attachment_id: str):
    """attachment_id非空；返回已提取文本与解析范围，不存在404，不公开本地文件路径。"""
    return attachment_detail(attachment_id)


@app.get('/api/jobs/{job_id}')
def get_job(job_id: str):
    """job_id非空；返回任务、关联日志和来源计数，不返回模型密钥或附件正文。"""
    return job_detail(job_id)


@app.get('/api/jobs/{job_id}/events')
async def job_stream(job_id: str, request: Request, after: int = Query(default=0, ge=0)):
    """非空job_id推送持久事件；request断开即结束，after为非负事件ID以重放恢复。"""
    get_job(job_id)
    async def stream():
        try:
            cursor = max(after,int(request.headers.get('last-event-id','0')))
        except ValueError:
            cursor = after
        while not await request.is_disconnected():
            payload = get_job(job_id)
            events = job_events(job_id,cursor)
            for event in events:
                cursor = event['id']
                event_type=event['event_type'] or 'stage'
                data={**(event['payload'] or {}),'event_id':cursor,'created_at':event['created_at'],'stage':event['stage'],'message':event['message']}
                yield f'id: {cursor}\nevent: {event_type}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n'
            # 必须先排空持久事件，否则前端收到终态就关闭，会丢掉第二页以后的delta。
            if len(events)>=150:continue
            yield f'event: status\ndata: {json.dumps({k: v for k, v in payload.items() if k not in {"events","tools"}}, ensure_ascii=False)}\n\n'
            if payload['status'] not in {'queued', 'running', 'cancelling'}:
                if len(events)<150:break
                continue
            await asyncio.sleep(.15)
    return StreamingResponse(stream(), media_type='text/event-stream', headers={'Cache-Control': 'no-cache', 'X-Accel-Buffering': 'no'})


@app.post('/api/jobs/{job_id}/pause')
def pause_job(job_id: str):
    """非空job_id请求安全暂停；排队作业立即暂停，运行作业在下一安全点停止。"""
    with Session.begin() as db:
        row = db.get(Job, job_id)
        if not row:
            raise ServiceError('任务不存在', 404)
        if row.status in {'queued', 'running'}:
            row.cancel_requested = True
            row.status = 'paused' if row.status == 'queued' else 'cancelling'
        return serialize(row)


@app.post('/api/jobs/{job_id}/resume')
def resume_job(job_id: str):
    """非空job_id恢复暂停/失败/部分完成任务；保留已保存证据线索，重复运行状态409。"""
    return resume_task(job_id)


@app.post('/api/jobs/{job_id}/identity-confirmation', status_code=202)
def job_identity_confirmation(job_id: str, body: 'IdentityConfirmationInput'):
    """job_id为待确认任务、body含同会话/版本/token；确认后原任务排队，候选过期409。"""
    from .company_identity import confirm_identity
    return confirm_identity(job_id, body.model_dump())


@app.get('/api/leads')
def leads(q: str = '', status: str = '', city: str = '', buyer_role: str='', conversation_id: str='', page: int = Query(1, ge=1), page_size: int = Query(20, ge=1, le=100)):
    """q/status/city为空不筛选；page>=1且page_size<=100，返回分页与状态统计。"""
    return list_leads(q, status, city, page, page_size,buyer_role,conversation_id)


@app.get('/api/leads/export')
def export_leads(q: str = '', status: str = '', city: str = '', buyer_role: str = ''):
    """q/status/city/buyer_role为空不限；返回最多10000条xlsx，不导出密钥或来源全文。"""
    stream = export_workbook(q, status, city, buyer_role)
    return StreamingResponse(stream, media_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
                             headers={'Content-Disposition': 'attachment; filename="client-reach-leads.xlsx"'})


@app.post('/api/leads/import-sample')
def sample():
    """仅在用户主动选择时导入标明日期的历史研究样本；重复导入不重复创建。"""
    return import_sample()


@app.post('/api/leads', status_code=201)
def create_lead(body: LeadInput):
    """body为非空人工线索；必须有名称，人工字段保持未核验状态。"""
    return edit_lead(None, body)


@app.get('/api/leads/{lead_id}')
def get_lead(lead_id: str, conversation_id: str = ''):
    """lead_id非空，返回详情与跟进，不存在404。"""
    return lead_detail(lead_id,conversation_id)


@app.patch('/api/leads/{lead_id}')
def patch_lead(lead_id: str, body: LeadInput):
    """非空lead_id和body更新CRM字段，空字符串可清除值，保留原始证据。"""
    return edit_lead(lead_id, body)


@app.post('/api/leads/{lead_id}/analysis',status_code=202)
def lead_product_analysis(lead_id: str, body: LeadAnalysisInput):
    """固定线索、仅读归档资料，排入原Worker，模型预算/暂停/恢复仍沿Job。"""
    from .lead_analysis import enqueue_analysis
    return enqueue_analysis(lead_id,body.model_dump())


@app.delete('/api/leads/{lead_id}')
def archive_lead(lead_id: str):
    """非空lead_id软归档，保留证据及历史；不存在404，返回归档状态。"""
    lead_detail(lead_id)
    with Session.begin() as db:
        row = db.get(Lead, lead_id)
        row.archived, row.updated_at = True, now()
    return {'archived': True}


@app.post('/api/leads/{lead_id}/followups', status_code=201)
def followup(lead_id: str, body: FollowupInput):
    """非空lead_id和body记录销售跟进，不自动转换为客户真实采购事实。"""
    lead_detail(lead_id)
    with Session.begin() as db:
        row = Followup(lead_id=lead_id, **body.model_dump())
        db.add(row)
        db.flush()
        lead = db.get(Lead, lead_id)
        lead.updated_at = now()
        return serialize(row)


@app.get('/api/settings')
def get_settings():
    """返回非敏感设置与密钥是否配置，绝不返回API Key。"""
    return settings()


@app.patch('/api/settings')
def patch_settings(body: SettingsInput):
    """body为完整校验的非敏感设置，返回保存值，不修改用户apikey文件。"""
    return save_settings(body.model_dump())


@app.post('/api/settings/test-model')
async def test_model():
    """真实调用配置的6luna并验证工具能力；失败502，返回安全错误类型而非密钥。"""
    from .model_gateway import test_connection
    return await asyncio.wait_for(test_connection(),timeout=90)


@app.get('/api/channels')
def channels():
    """返回真实渠道准备状态与启用配置；需授权的商业来源明确不具备调用权限。"""
    from .channel_status import channel_status
    options=settings()
    return channel_status(options['enabled_channels'],options)


@app.get('/api/memories')
def memories():
    """列出本机工作空间长期记忆；默认无跨租户访问能力。"""
    from .knowledge import memory_list
    return memory_list()


@app.post('/api/memories',status_code=201)
def memory_add(body: MemoryInput):
    """body为用户明确记忆；校验类型/长度后持久化，不向外部发送消息。"""
    from .knowledge import add_memory
    return add_memory(body.kind,body.content)


@app.delete('/api/memories/{item_id}')
def memory_remove(item_id: str):
    """item_id非空，软停用记忆并保留历史；不存在404。"""
    from .knowledge import deactivate_memory
    return deactivate_memory(item_id)


@app.get('/api/knowledge')
def knowledge(q: str=''):
    """q为空列出本机最近150条知识，非空查询管理列表，不返回其他作用域。"""
    from .knowledge import knowledge_list, search_knowledge
    if q:
        items=search_knowledge(q,30)
        return {'items':items,'active':len(items)}
    return knowledge_list()


@app.post('/api/knowledge',status_code=201)
def knowledge_add(body: KnowledgeInput):
    """body为用户明确文档知识；标题正文必填，来源固定user，不能伪装公开采购证据。"""
    from .knowledge import upsert_knowledge
    return upsert_knowledge(body.title,body.body,'product')


@app.delete('/api/knowledge/{item_id}')
def knowledge_remove(item_id: str):
    """item_id非空；知识软失效，后续召回排除，不物理删除原文。"""
    from .knowledge import deactivate_knowledge
    return deactivate_knowledge(item_id)


@app.post('/api/leads/{lead_id}/feedback',status_code=201)
def feedback(lead_id: str, body: FeedbackInput):
    """lead_id非空且存在，body为用户反馈；服务负责知识失效及排除记忆。"""
    from .knowledge import record_feedback
    return record_feedback(lead_id,body.kind,body.content)


@app.get('/api/site-guides')
def site_guides():
    """无入参；返回各数据源的能力、访问方式、重试策略与质量约束（只读配置，不含凭据）。"""
    from .site_guides import GUIDES
    return [guide.model_dump() for guide in GUIDES]


@app.get('/api/agent/graph')
def graph_info():
    """只返回图拓扑及可审阅State字段，无密钥、原始对话或用户文件。"""
    from .agent import build_graph, ResearchState, GRAPH_VERSION
    graph=build_graph(None).get_graph()
    return {'engine':'LangGraph','version':GRAPH_VERSION,'nodes':list(graph.nodes),'edges':[{'source':x.source,'target':x.target} for x in graph.edges],
            'state_fields':list(ResearchState.__annotations__),'checkpoint':'AsyncSqliteSaver','store':'WorkspaceStore'}


@app.get('/api/jobs/{job_id}/state')
async def state_info(job_id: str):
    """job_id已存在；返回checkpoint的计划/预算/引用/节点位置，隐藏原始用户内容和内部模型参数。"""
    get_job(job_id)
    from .agent import build_graph
    from .config import DATA
    from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
    async with AsyncSqliteSaver.from_conn_string(str(DATA/'checkpoints.db')) as saver:
        await saver.setup();state=await build_graph(saver).aget_state({'configurable':{'thread_id':job_id}})
        allowed={'schema_version','workspace_id','job_id','conversation_id','plan','cursor','source_ids','saved_ids','gaps','attempts','stage_timings','remaining_budget','metrics'}
        return {'next':list(state.next),'checkpoint_id':state.config.get('configurable',{}).get('checkpoint_id'),
                'state':{k:v for k,v in state.values.items() if k in allowed}}


@app.get('/api/evidence/{source_id}')
def evidence(source_id: str):
    """非空source_id返回实际归档正文；不存在404，不把用户产品附件充作公开证据。"""
    from .service import evidence_detail
    return evidence_detail(source_id)


@app.get('/api/source-fragments/{fragment_id}')
def source_fragment(fragment_id: str):
    """fragment_id为非空持久ID；返回显式选定的完整片段，不存在404。"""
    from .source_service import fragment_detail
    return fragment_detail(fragment_id)


@app.get('/api/companies/{company_id}/documents/{source_id}')
def company_source_document(company_id: str, source_id: str):
    """两个ID均必填；只返回当前企业关联文档及独立条目摘录，无关联404。"""
    from .source_service import company_document
    return company_document(company_id, source_id)


@app.get('/api/jobs/{job_id}/research')
def job_research(job_id: str):
    """job_id非空；返回真实逐轮清洗/核验汇总，未知值保持缺口，任务不存在404。"""
    from .research_dataset import research_summary
    return research_summary(job_id)


@app.get('/api/research-datasets/{dataset_id}')
def get_research_dataset(dataset_id: str):
    """dataset_id非空；按阶段返回真实清洗/快照资料，未核验提议不作为企业事实，缺记录404。"""
    from .research_dataset import dataset_detail
    return dataset_detail(dataset_id)


@app.get('/api/jobs/{job_id}/trace')
def job_trace(job_id: str):
    """job_id为存在的任务；按需查询实际LangSmith记录，无正文/凭据，云端不可读时返回明确状态。"""
    from .tracing import research_trace
    return research_trace(job_id)


@app.get('/api/companies')
def companies(q: str = '', entity_kind: str = '', conversation_id: str = '', visibility: str = 'primary',
              page: int = Query(1, ge=1), page_size: int = Query(20, ge=1, le=100)):
    """各字符串为空不筛选；page>=1/page_size<=100，返回真实企业分页与摘要；会话不存在404。"""
    from .company_service import list_companies
    return list_companies(q, entity_kind, conversation_id, page, page_size, visibility)


@app.post('/api/companies/import-history')
def company_history_import():
    """无入参；幂等导入已审阅项目历史快照，原文缺失422，不创建实时研究任务。"""
    from .company_import import import_history
    return import_history()


@app.get('/api/companies/{company_id}')
def get_company(company_id: str):
    """company_id为非空持久ID；返回统一画像/采购/关系与来源投影，不存在404。"""
    from .company_service import company_detail
    return company_detail(company_id)


@app.get('/api/companies/{company_id}/logo')
def get_company_logo(company_id: str):
    """company_id为非空ID；返回已缓存的企业站点图标，未取得时404（前端显示首字头像）。"""
    from .logo_service import logo_file
    path = logo_file(company_id)
    if not path: raise ServiceError('暂无企业标识', 404)
    # 第三方SVG可能内嵌脚本：沙箱CSP禁止脚本与外部请求，仅允许作为图片显示。
    return FileResponse(path, headers={'Cache-Control': 'public, max-age=86400', 'X-Content-Type-Options': 'nosniff',
                                       'Content-Security-Policy': "default-src 'none'; style-src 'unsafe-inline'; sandbox"})


@app.post('/api/companies/{company_id}/logo/refresh')
async def refresh_company_logo(company_id: str):
    """company_id为非空ID；重新访问企业官网获取标识，企业不存在404，未找到返回status=not_found。"""
    from .logo_service import refresh_logo
    from .company_models import Company
    with Session() as db:
        if not db.get(Company, company_id): raise ServiceError('企业不存在', 404)
    return await asyncio.to_thread(refresh_logo, company_id, True)


@app.get('/api/companies/{company_id}/relations/{relation_id}')
def get_company_relation(company_id: str, relation_id: str):
    """两个ID均必填；返回该关系的双方说明和对手方自身资料，无归属或不存在404。"""
    from .relation_service import relation_detail
    return relation_detail(company_id, relation_id)


@app.post('/api/companies/{company_id}/counterparties/research', status_code=202)
def company_counterparties_research(company_id: str, body: CompanyResearchInput):
    """company_id须存在、body为显式补齐及幂等token；只研究当前首屏上下游，任务冲突409。"""
    from .relation_service import research_counterparties
    return research_counterparties(company_id, body.model_dump())


@app.post('/api/companies/{company_id}/relations/{relation_id}/research', status_code=202)
def company_relation_research(company_id: str, relation_id: str, body: CompanyResearchInput):
    """两个ID须同一关系归属，body为显式补齐和幂等token；只研究该对手方，不存在404。"""
    from .relation_service import research_counterparties
    return research_counterparties(company_id, body.model_dump(), relation_id)


@app.get('/api/companies/{company_id}/export')
def company_export(company_id: str):
    """company_id须存在；下载含原值、统计口径和来源的XLSX，未知为空，不导出凭据或存档路径。"""
    from .company_service import export_company
    return StreamingResponse(export_company(company_id), media_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        headers={'Content-Disposition': 'attachment; filename="company-research.xlsx"'})


@app.post('/api/companies/{company_id}/research', status_code=202)
def research_company(company_id: str, body: CompanyResearchInput):
    """company_id必存在、body为补查意图与幂等token；返回真实Job，会话/主体缺失404、活动冲突409。"""
    from .company_service import company_research
    return company_research(company_id, body.model_dump())


@app.get('/api/browser/status')
def get_browser_status():
    """无参数；返回Edge/OpenCLI安装信息和最近真实读取，未验证不声称已连接。"""
    from .browser_reader import browser_status
    return browser_status()


@app.patch('/api/browser/settings')
def patch_browser_settings(body: BrowserSettingsInput):
    """body为非敏感固定读取配置；不允许路径/任意命令，校验失败422，返回保存结果。"""
    from .browser_reader import save_browser_settings
    return save_browser_settings(body.model_dump())


@app.post('/api/browser/test')
async def test_browser_read(body: BrowserReadInput):
    """body.url为用户明确公开页、backend限定枚举；返回真实读取摘要，不制造Agent任务或业务事实，受限明确失败。"""
    from .browser_reader import read_edge
    result=await read_edge(body.url,preference=body.backend)
    return {key:result[key] for key in ('url','title','body_chars','total_chars','truncated','backend','elapsed_ms','opencli_version')} | {'preview':result['body'][:1500]}


DIST = Path(os.getenv('CLIENTREACH_WEB_DIST', str(ROOT / 'web/dist')))
if (DIST / 'assets').exists():
    app.mount('/assets', StaticFiles(directory=DIST / 'assets'), name='assets')


@app.get('/{route:path}', include_in_schema=False)
def frontend(route: str):
    """route为SPA导航路径，api未知路径返回404；前端未构建时明确提示。"""
    if route.startswith('api/'):
        raise ServiceError('接口不存在', 404)
    if not (DIST / 'index.html').exists():
        return JSONResponse({'message': '前端尚未构建，请在web运行npm run build'}, status_code=503)
    public_file=(DIST/route).resolve()
    if public_file.is_relative_to(DIST.resolve()) and public_file.is_file():
        return FileResponse(public_file)
    return FileResponse(DIST / 'index.html')
