"""固定本地七站 MCP 入口、业务契约及原文归档；不允许模型选择执行路径。"""
import asyncio
import hashlib
import json
import os
import re
import time
import uuid
from datetime import date, timedelta
from pathlib import Path
from typing import Literal
from urllib.parse import urlparse
from pydantic import BaseModel, Field, field_validator, model_validator

Source = Literal['chinabidding','qianlima','jianyu','ebnew','yfbzb','chinabidding_org','ggzy']
DOMAINS = {'chinabidding':('chinabidding.com.cn','chinabidding.cn'), 'qianlima':('qianlima.com',),
           'jianyu':('jianyu360.cn',), 'ebnew':('ebnew.com',), 'yfbzb':('yfbzb.com',),
           'chinabidding_org':('chinabidding.org.cn',), 'ggzy':('ggzy.gov.cn',)}
HTTP_SOURCES = ['ggzy','ebnew']
DEFAULT_HOME = Path('D:/Codes/000GithubProject/Result/001_bid_research_tool')
ACCESS_REFUSALS={'blocked','robots_denied','robots_disallowed','robots_unavailable','login_required','verification_required','captcha_required'}


def refused_detail(db,job_id,url):
    import time
    from .db import ToolCall,Job
    from sqlalchemy import select
    job=db.get(Job,job_id)
    host=(urlparse(url).hostname or '').lower()
    for row in db.scalars(select(ToolCall).where(ToolCall.job_id==job_id,ToolCall.tool=='get_tender_detail')):
        error=(row.result or {}).get('error')
        prior_url=(row.arguments or {}).get('url','')
        if prior_url==url and error in ACCESS_REFUSALS:return 'site_access_restricted'
        if (urlparse(prior_url).hostname or '').lower()==host and error=='rate_limited' and (time.time()<(row.last_attempt_epoch or time.time())+60 or (job.metrics or {}).get('resume_epoch',0)<=(row.last_attempt_epoch or 0)):
            return 'site_rate_limited'
    return ''


def procurement_keywords(query, products):
    """采购站按短关键词检索；去掉服务宣传句式，只保留本轮查询实际提到的产品词。"""
    cores=[word for word in ('软件开发','知识库','大模型','人工智能','软件','AI') if word.casefold() in query.casefold()]
    # A narrower software-development term already covers the generic software substring.
    if '软件开发' in cores and '软件' in cores:cores.remove('软件')
    if '人工智能' in cores and 'AI' in cores:cores.remove('AI')
    if cores and all(word in {'人工智能','AI'} for word in cores) and any('软件开发' in p.get('name','') for p in products):
        cores.insert(0,'软件开发')
    if cores:return cores[:2]
    terms=[p['name'] for p in products if p.get('name') and p['name'] in query and len(p['name'])<=100]
    return list(dict.fromkeys(re.sub(r'(?:开发)?服务$','',p) or p for p in terms))[:2] or [query[:100]]


def software_service_profile(profile):
    return bool(re.search(r'软件|知识库|大模型|智能体|(?:人工智能|AI).{0,12}(?:应用|开发|服务)',
        ' '.join(p.get('name','') for p in profile.get('products',[])),re.I))


def active_procurement_requested(prompt):
    return bool(re.search('正在采购|仍在采购|正在招标|仍在招标|在招项目|未截止|开放采购|仍可投标',prompt or ''))


def company_time_window(prompt,default_days=365):
    """Explicit current request controls recency; historical research has no recent cutoff."""
    found=re.search(r'(?:近|最近)(\d+|[一二两三四五六七八九十]+)(?:个)?(天|月|年)',prompt or '')
    if found:
        raw,unit=found.groups();numbers={'一':1,'二':2,'两':2,'三':3,'四':4,'五':5,'六':6,'七':7,'八':8,'九':9,'十':10}
        value=int(raw) if raw.isdigit() else numbers.get(raw,0)
        if not value and '十' in raw:
            left,right=raw.split('十',1);value=numbers.get(left,1)*10+numbers.get(right,0)
        return 'recent',max(1,min(365,value*{'天':1,'月':30,'年':365}[unit]))
    if re.search(r'(?:近|最近)半年',prompt or ''):return 'recent',180
    return ('recent',default_days) if active_procurement_requested(prompt) else ('history',default_days)


def software_service_match(title,body):
    """需要实际软件/AI服务对象；园区工程、学院名和单纯仪器采购不能凭AI字样入选。"""
    return substantive_match(title,body,['软件','知识库','大模型','智能体','算法','数据标注','人工智能应用开发',
        '人工智能应用服务','AI应用开发','AI应用服务','平台开发','系统开发','云服务','SaaS'])


class BidSearch(BaseModel):
    model_config = {'extra':'forbid'}
    keywords: list[str] = Field(min_length=1,max_length=3)
    company: str = Field(default='',max_length=200)
    sources: list[Source] = Field(default_factory=lambda:HTTP_SOURCES.copy(),min_length=1,max_length=7)
    days: int = Field(default=30,ge=1,le=365)
    limit: int = Field(default=8,ge=1,le=100)
    mode: Literal['history','recent'] = 'recent'
    pages: int = Field(default=1,ge=1,le=5)
    category: Literal['any','software_services'] = 'any'
    active_only: bool = False

    @model_validator(mode='after')
    def company_history_defaults(self):
        if self.company and 'mode' not in self.model_fields_set:self.mode='history'
        if self.mode=='history':
            if 'pages' not in self.model_fields_set:self.pages=5
            if 'limit' not in self.model_fields_set:self.limit=100
        return self

    @field_validator('keywords')
    @classmethod
    def bounded_keywords(cls, values):
        if any(not v.strip() or len(v)>100 for v in values):raise ValueError('invalid keyword')
        return list(dict.fromkeys(v.strip() for v in values))


class BidDetail(BaseModel):
    model_config = {'extra':'forbid'}
    source: Source
    url: str = Field(max_length=2000)
    company: str = Field(min_length=1,max_length=200)
    mode: Literal['history','recent'] = 'history'
    days: int = Field(default=365,ge=1,le=365)

    @model_validator(mode='after')
    def public_notice(self):
        try:
            parsed=urlparse(self.url);host=(parsed.hostname or '').lower()
            valid=parsed.scheme in {'http','https'} and not parsed.username and not parsed.password and parsed.port in {None,80,443} and any(host==d or host.endswith('.'+d) for d in DOMAINS[self.source])
        except ValueError:valid=False
        if not valid:raise ValueError('invalid source URL')
        return self


def runtime_status():
    home=Path(os.getenv('CLIENTREACH_BIDRESEARCH_HOME', str(DEFAULT_HOME))).resolve()
    python=home/'.venv-runtime'/'Scripts'/'python.exe'
    if os.name!='nt':python=home/'.venv-runtime'/'bin'/'python'
    return {'installed':python.is_file() and (home/'bidresearch/mcp_server.py').is_file(), 'home':home, 'python':python,'launcher':home/'scripts/run_mcp.py'}


class BidResearchClient:
    async def call(self, tool, arguments, timeout=90):
        """官方 SDK stdio，关闭会话收尾子进程；工具名固定，真实 tools/list 再核对。"""
        if tool not in {'health_check','get_source_capabilities','search_tenders','get_tender_detail'}:raise ValueError('tool_not_allowed')
        runtime=runtime_status()
        if not runtime['installed']:raise RuntimeError('bidresearch_not_installed')
        from mcp import ClientSession, StdioServerParameters
        from mcp.client.stdio import stdio_client
        launcher=runtime.get('launcher',runtime['home']/'scripts/run_mcp.py')
        entry=[str(launcher)] if launcher.is_file() else ['-m','bidresearch.mcp_server']
        params=StdioServerParameters(command=str(runtime['python']),args=['-X','utf8',*entry],
            cwd=str(runtime['home']),env={'PYTHONUTF8':'1','PYTHONIOENCODING':'utf-8'})
        async def invoke():
            async with stdio_client(params) as (read,write):
                async with ClientSession(read,write,read_timeout_seconds=float(timeout)) as session:
                    await session.initialize()
                    listed=await session.list_tools()
                    if tool not in {t.name for t in listed.tools}:raise RuntimeError('bidresearch_tool_unmapped')
                    result=await session.call_tool(tool,arguments=arguments)
                    if getattr(result,'is_error',getattr(result,'isError',False)):raise RuntimeError('bidresearch_call_failed')
                    value=getattr(result,'structured_content',getattr(result,'structuredContent',None))
                    if not isinstance(value,dict):
                        parts=[x.text for x in result.content if hasattr(x,'text')]
                        value=json.loads('\n'.join(parts))
                    if not isinstance(value,dict):raise RuntimeError('bidresearch_invalid_response')
                    return value
        return await asyncio.wait_for(invoke(),timeout)


def substantive_match(title, body, keywords):
    """采购标题/需求范围中的真实命中；机构名或投标软件安装说明不作需求。"""
    if re.search('报废|资产.{0,30}(?:转让|处置|拍卖)|产权交易|招租|出租|招聘|招商',title):return []
    if not re.search('采购|招标|询价|询比|磋商|谈判|比选|竞价|中标|成交|征集|遴选',title) and not re.search('采购需求|采购内容|招标范围|技术需求',body):return []
    matches=[];context=False
    for line in [title,*body.splitlines()]:
        if re.search('资格要求|投标须知|文件获取|采购人信息|代理机构信息',line):context=False
        if re.search('采购需求|项目名称|项目概况|服务内容|招标范围|技术要求|技术需求|采购内容',line):context=True
        if line!=title and not context:continue
        for keyword in keywords:
            pattern=re.escape(keyword)
            if re.fullmatch('[A-Za-z]{1,3}',keyword):pattern=r'(?<![A-Za-z0-9_])'+pattern+r'(?![A-Za-z0-9_])'
            for found in re.finditer(pattern,line,re.I):
                prefix=line[max(0,found.start()-30):found.start()]
                suffix=line[found.end():found.end()+25]
                if re.search('不采购|不包括|无需|不得使用',prefix):continue
                if re.match(r'(?:开发|技术|管理|服务|信息|应用)*(?:中心|公司|研究院|学院|部门|处|科)',suffix):continue
                if re.search('(?:投标|响应|报价)文件',line) and re.search('下载|安装|制作|编制|递交|提交',line):continue
                matches.append({'keyword':keyword,'quote':line[:1000]})
    return matches


def table_quote(body, quote, label, value):
    """表头与数据列必须实际对应；返回包含两者的连续原文，不能借用其他列的标签。"""
    compact=lambda text:re.sub(r'\s+','',text)
    cells=lambda text:[c.strip() for c in text.strip().strip('|').split('|')]
    if not quote or quote not in body or not label or '|' not in quote:return ''
    data=cells(quote);position=body.find(quote)
    prefix=body[:position];lines=prefix.splitlines(keepends=True)
    # The immediately preceding table header may have separator/data rows between it and this row.
    for count in range(1,min(5,len(lines))+1):
        header=lines[-count].strip();columns=cells(header)
        if len(columns)!=len(data):continue
        indexes=[i for i,text in enumerate(columns) if compact(text)==compact(label)]
        if not indexes:continue
        if len(indexes)!=1 or compact(data[indexes[0]])!=compact(value):return ''
        start=len(prefix)-sum(len(line) for line in lines[-count:])
        span=body[start:position+len(quote)]
        return span if len(span)<=1200 else ''
    return ''


def grounded_party(body, party):
    if not isinstance(party,dict):return None
    quote=party.get('quote');name=party.get('name');label=party.get('label','')
    if not isinstance(quote,str) or not quote or not name or quote not in body or name not in quote:return None
    if party.get('role')=='winner':
        backup=re.search(r'(?m)^\s*备选供应商中标人[：:\s]*'+re.escape(name)+r'(?=$|[\s，。；;|])',body)
        if backup and quote in backup[0]:
            return {**party,'role':'candidate','label':'备选供应商中标人','quote':backup[0].strip()}
    if party.get('role')=='candidate' and label=='备选成交供应商':
        lines=quote.splitlines()
        if not lines or not re.fullmatch(r'备选成交\s*[:：]',lines[0].strip()):return None
        row=lines[-1].strip()
        span=table_quote(body,row,'供应商名称',name)
        if not span or span not in quote or not quote.endswith(span):return None
        return {**party,'quote':quote}
    roles={'buyer':'采购人|采购单位|招标人|招标单位|采购方','winner':r'(?:第[一二三四五六七八九十\d]+)?(?:中标人|中标单位|成交供应商|中标供应商)|供应商名称',
        'candidate':r'(?:第[一二三四五六七八九十\d]+)?(?:中标|成交)?候选人|备选供应商中标人','agency':'(?:采购|招标)?代理机构'}
    pattern=roles.get(party.get('role'))
    if not pattern or label and not re.fullmatch(r'(?:'+pattern+r')(?:信息|名称)?',re.sub(r'\s+','',label)):return None
    if '|' in quote:
        if not label:return None
        if party.get('role')=='winner' and label=='供应商名称':
            row=quote.splitlines()[-1].strip();position=body.find(row)
            sections=list(re.finditer(r'(?m)^\s*(备选成交|成交)\s*[:：]',body[:position]))
            if sections and sections[-1][1]=='备选成交':return None
        quote=table_quote(body,quote.splitlines()[-1].strip(),label,name)
        if not quote:return None
    elif not re.search(r'(?:'+pattern+r')(?:信息)?[：:\s]*(?:名\s*称[：:\s]*)?'+(r'(?:为)?[：:\s]*' if party.get('role')=='candidate' else '')+re.escape(name)+r'(?=$|[\s，。；;|])',quote):return None
    return {**party,'quote':quote}


def grounded_amount(body, amount):
    if not isinstance(amount,dict):return None
    quote=amount.get('quote');original=amount.get('original');label=amount.get('label','')
    if not isinstance(quote,str) or not quote or quote not in body or not isinstance(original,str) or not original or original not in quote:return None
    if not isinstance(label,str) or not label:return None
    if amount.get('kind')=='award' and (re.search('候选|报价|预算|限价|控制价',label)
        or not re.search(r'(?:中标|成交)(?:[（(]成交[）)])?(?:金额|价|价格|总价)',label)):return None
    if '|' in quote:
        quote=table_quote(body,quote.splitlines()[-1].strip(),label,original)
        if not quote:return None
    elif not re.search(re.escape(label)+r'[\s：:]*'+re.escape(original)+r'(?![\d.])',quote):return None
    display=original
    if '元' not in original:
        unit=re.search(r'([万亿]?元)',label)
        if unit and label in quote and re.fullmatch(r'\d+(?:,\d{3})*(?:\.\d+)?',original):display=original+unit[1]
    return {**amount,'quote':quote,'display_value':display}


def archive_result(job_id, payload, keywords, days, limit, company='', channel='procurement',category='any',active_only=False,mode='recent'):
    from .gateway import archive_sources
    from .source_content import has_content
    from .source_access import access_issue
    records=[];sources=[];seen=set();notice_keys={};rejected=0
    candidates=[row for row in payload.get('records',[])[:200] if isinstance(row,dict)]
    diagnostics={'mode':mode,'raw_count':len(candidates),'date_rejected':0,'subject_rejected':0,'access_rejected':0,'duplicate_count':0,'limit_rejected':0,'full_text_count':0,'navigation_count':0,'confirmed_count':0,'missing_body_count':0}
    def rank(row):
        detail=row.get('detail') if isinstance(row.get('detail'),dict) else {}
        return (bool(detail.get('text') and detail.get('status') in {'public','masked'}),str(row.get('published_at') or ''))
    candidates.sort(key=rank,reverse=True)
    for row in candidates:
        if not isinstance(row,dict):continue
        title=row.get('title','');url=row.get('url','');source=row.get('source','')
        host=(urlparse(url).hostname or '').lower()
        if urlparse(url).scheme not in {'http','https'} or urlparse(url).username or not any(host==d or host.endswith('.'+d) for d in DOMAINS.get(source,())):
            rejected+=1;continue
        published=str(row.get('published_at') or '')[:10];confirmed=False
        try:
            stamp=date.fromisoformat(published);confirmed=True
            if stamp>date.today() or mode=='recent' and stamp<date.today()-timedelta(days=days):
                diagnostics['date_rejected']+=1;continue
        except ValueError:published=''
        detail=row.get('detail') if isinstance(row.get('detail'),dict) else {}
        body=str(detail.get('text') or '');status=detail.get('status','not_requested')
        full=bool(body and status in {'public','masked'} and has_content({'title':title,'body':body,'url':url}) and not access_issue(url,title,body))
        # Masked public pages retain visible spans only; individual missing values remain unknown.
        evidence_body=body if full else title
        reasons=[{'keyword':company,'quote':company}] if company and company in title+'\n'+body else substantive_match(title,body,keywords) if not company else []
        proof=row.get('list_evidence') if isinstance(row.get('list_evidence'),dict) else {}
        proof_host=(urlparse(str(proof.get('url') or '')).hostname or '').lower()
        navigation=bool(company and not full and status in {'not_requested','network_error','time_budget_exhausted','budget_exhausted'}
            and row.get('query') in keywords and proof.get('sha256') and
            any(proof_host==d or proof_host.endswith('.'+d) for d in DOMAINS.get(source,())))
        if navigation:reasons=[{'keyword':company,'kind':'search_navigation','quote':''}]
        if not reasons:
            diagnostics['subject_rejected']+=1;continue
        if category=='software_services' and not company and not software_service_match(title,body):continue
        from .procurement import closed_notice
        if active_only and closed_notice(title,body):continue
        key=(url,published,hashlib.sha256(body.encode()).hexdigest())
        if key in seen:
            diagnostics['duplicate_count']+=1;continue
        seen.add(key)
        meta={'origin':'bidresearch_mcp','source':source,'detail_status':status,'date_filter':'confirmed' if confirmed else 'unconfirmed',
              'sha256':key[2], 'snapshot_refs':detail.get('evidence',[]), 'truncated':len(evidence_body)>180000,'category':category,'active_only':active_only,
              'navigation_only':navigation,'query':row.get('query',''),'mode':mode,'list_evidence':proof}
        evidence_body=evidence_body[:180000]
        parties=[p for item in detail.get('parties',[]) if (p:=grounded_party(evidence_body,item))] if full else []
        amounts=[a for item in detail.get('amounts',[]) if (a:=grounded_amount(evidence_body,item))] if full else []
        meta['native_tender_confirmed']=bool(company and full and any(p['name']==company for p in parties))
        buyers=tuple(sorted(p['name'] for p in parties if p.get('role')=='buyer'))
        # Same-day same-title projects may be separate lots; only identical visible content is a repost.
        notice_key=(re.sub(r'\s+','',title),published,buyers,hashlib.sha256(re.sub(r'\s+','',body).encode()).hexdigest()) if confirmed and buyers else key
        duplicate=notice_keys.get(notice_key)
        if duplicate is None and len(records)>=limit:
            diagnostics['limit_rejected']+=1;continue
        archived=archive_sources(job_id,[{'url':url,'title':title,'body':evidence_body[:180000],'published_at':published or None,'source_meta':meta}],
            '网页正文' if full else '搜索摘录',channel)
        if not archived:continue
        sources.extend(archived)
        if duplicate is not None:
            duplicate.setdefault('alternate_sources',[]).append({'source_id':archived[0]['id'],'url':url,'source':source})
            continue
        records.append({'source':source,'source_id':archived[0]['id'],'title':title,'url':url,'published_at':published,
            'region':row.get('region') or '', 'detail_status':status,'has_full_text':full,'parties':parties,'amounts':amounts,
            'match_reasons':reasons,'date_filter':meta['date_filter']})
        notice_keys[notice_key]=records[-1]
        diagnostics['full_text_count']+=int(full)
        diagnostics['missing_body_count']+=int(not full)
        diagnostics['navigation_count']+=int(navigation)
        diagnostics['confirmed_count']+=int(full and any(p['name']==company for p in parties))
    report=payload.get('report',{})
    coverage=[{k:r.get(k) for k in ('source','status','pages_fetched','retrieved_count','details_attempted','cache_hits','latency_ms','errors','time_window')}
              for r in report.get('sources',[]) if isinstance(r,dict)]
    return {'records':records,'sources':sources,'coverage':coverage,'error':'' if records else 'empty_results',
        'status':'partial' if any(r.get('status') not in {'ok','empty'} for r in coverage) or any(not r['has_full_text'] or r['date_filter']=='unconfirmed' for r in records) else 'complete',
        'request_count':report.get('request_count',0),'rejected_count':rejected,'provider':'bidresearch_mcp','diagnostics':{**diagnostics,'access_rejected':rejected},
        'fresh_source_ids':[s['id'] for s in sources], 'network_attempted':bool(report.get('request_count',0)),
        'reused':any((r.get('cache_hits') or 0)>0 for r in coverage)}


async def search(job_id, request: BidSearch, options, channel='procurement'):
    if options.get('bidresearch_max_requests',0)<=0:return {'error':'budget_exhausted','sources':[]}
    runtime=runtime_status()
    if not runtime['installed']:return {'error':'bidresearch_not_installed','sources':[]}
    sources=request.sources if options.get('bidresearch_browser',False) else [s for s in request.sources if s not in {'qianlima','jianyu'}]
    if not sources:return {'error':'browser_disabled','sources':[]}
    timeout=options.get('bidresearch_timeout',90)
    # The upstream detail allowance is per source; convert the Job's total allowance.
    per_source=0 if request.company else options.get('bidresearch_max_details',4)//(len(sources)*len(request.keywords))
    args={'keywords':request.keywords,'sources':sources,'pages':request.pages,'details':per_source,
        'limit':request.limit,'max_requests':options['bidresearch_max_requests'],'days':request.days,'browser':options.get('bidresearch_browser',False),
        'delay':2,'timeout':min(15,timeout),'max_seconds':max(1,timeout-20),'retries':0,
        'output':str(runtime['home']/'data'/'clientreach-mcp'/uuid.uuid4().hex)}
    if options.get('company_force_refresh'):args['cache_search_ttl']=0
    interrupted=False;started=time.monotonic();recovered=False
    try:payload=await BidResearchClient().call('search_tenders',args,timeout=max(5,timeout-10))
    except TimeoutError:
        snapshot=Path(args['output'])/'partial.json'
        try:
            if snapshot.stat().st_size>40_000_000:raise ValueError('partial_too_large')
            payload=json.loads(snapshot.read_text(encoding='utf-8'))
            if not isinstance(payload,dict) or not isinstance(payload.get('records'),list) or not isinstance(payload.get('report'),dict):
                raise ValueError('invalid_partial')
        except (OSError,ValueError):raise TimeoutError() from None
        if not payload['records']:raise TimeoutError() from None
        interrupted=True
    report=payload.get('report') or {}
    statuses={r.get('status') for r in report.get('sources',[]) if isinstance(r,dict)}
    # One bounded recovery only for transport failures; never retry access refusals/rate limits.
    remaining=max(0,timeout-10-(time.monotonic()-started))
    requests_left=max(0,args['max_requests']-int(report.get('request_count',0)))
    if request.company and not payload.get('records') and statuses and statuses<={'network_error','time_budget_exhausted'} and remaining>25 and requests_left:
        retry={**args,'cache_search_ttl':3600 if request.mode=='history' else 900,'max_requests':requests_left,'max_seconds':max(1,int(remaining-20)),
            'output':str(runtime['home']/'data'/'clientreach-mcp'/uuid.uuid4().hex)}
        try:
            retried=await BidResearchClient().call('search_tenders',retry,timeout=remaining)
            other=retried.get('report') or {}
            retried['report']={**other,'sources':[*report.get('sources',[]),*other.get('sources',[])],
                'request_count':report.get('request_count',0)+other.get('request_count',0)}
            payload=retried;recovered=True
        except Exception:pass  # Keep the first real failure report; no unbounded retries.
    result=archive_result(job_id,payload,request.keywords,request.days,request.limit,request.company,channel,request.category,request.active_only,request.mode)
    if interrupted:result.update(status='partial',partial_recovery=True)
    if recovered:result['recovery']='retry_after_network_failure'
    return result


async def detail(job_id, request: BidDetail, options):
    """读取已发现公告；列表标题/日期来自本任务存档，正文来自真实MCP响应。"""
    from .db import Session,Evidence
    from sqlalchemy import select
    with Session() as db:
        prior=db.scalar(select(Evidence).where(Evidence.job_id==job_id,Evidence.url==request.url).order_by(Evidence.captured_at.desc()))
        if not prior:return {'error':'source_not_allowed','sources':[]}
        row={'source':request.source,'url':request.url,'title':prior.title,'published_at':prior.published_at,
             'query':(prior.source_meta or {}).get('query',''),'list_evidence':(prior.source_meta or {}).get('list_evidence',{})}
    timeout=options.get('bidresearch_timeout',90)
    payload=await BidResearchClient().call('get_tender_detail',{'source':request.source,'url':request.url,
        'timeout':min(15,timeout),'max_seconds':max(1,min(35,timeout-20)),
        'cache_detail_ttl':0 if options.get('company_force_refresh') else 3600},timeout=max(5,timeout-10))
    row['detail']=payload.get('detail',{})
    report=payload.get('report',{})
    cache=report.get('cache_stats') or {}
    result=archive_result(job_id,{'records':[row],'report':{'request_count':report.get('request_count',0),
        'sources':[{'source':request.source,'status':row['detail'].get('status','unknown'),'cache_hits':cache.get('hits',0)}]}},
        [request.company],request.days,1,request.company,mode=request.mode)
    if row['detail'].get('status') not in {'public','masked'}:result['error']=row['detail'].get('status','empty_body')
    return result
