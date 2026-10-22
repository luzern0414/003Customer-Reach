"""有界、可追溯的产品匹配；复用图预算和模型缓存，分析不进入事实表。"""
import hashlib
import json
import re
import time
from typing import Literal
from pydantic import BaseModel, Field, ConfigDict
from sqlalchemy import select
from .db import Session, Job, Lead, Conversation, Evidence, Feedback, ToolCall, serialize, now
from .prompts.acquisition import ACQUISITION_ANALYSIS

POLICY='acquisition-analysis-1'


class Match(BaseModel):
    model_config=ConfigDict(extra='forbid')
    product_index: int = Field(ge=0)
    requirement_ref: str = Field(min_length=1,max_length=100)
    quote: str = Field(min_length=3,max_length=1200)
    fit: Literal['related','gap','unknown']
    reason: str = Field(min_length=1,max_length=450)
    next_step: str = Field(min_length=1,max_length=240)


class AnalysisItem(BaseModel):
    model_config=ConfigDict(extra='forbid')
    lead_id: str
    matches: list[Match] = Field(default_factory=list,max_length=4)
    questions: list[str] = Field(default_factory=list,max_length=4)


class AnalysisBatch(BaseModel):
    model_config=ConfigDict(extra='forbid')
    items: list[AnalysisItem] = Field(max_length=3)


def input_fingerprint(context):
    """不包含运行时间/跟进字段，状态和原文变化会失效；跨任务不复用过时判断。"""
    return hashlib.sha256(json.dumps(context,ensure_ascii=False,sort_keys=True).encode()).hexdigest()


def bounded_context(context, limit=12000):
    """按完整记录裁剪，不切JSON；每个遗漏明确计数，原文不拼段。"""
    payload=json.loads(json.dumps(context,ensure_ascii=False))
    total=len(payload.get('evidence',[]));total_projects=len(payload.get('projects',[]))
    payload['coverage']={'total_evidence':total,'selected_evidence':total,'omitted_evidence':0,'total_projects':total_projects,'selected_projects':total_projects}
    payload.setdefault('limitations',[])
    while len(json.dumps(payload,ensure_ascii=False))>limit:
        if payload.get('evidence'):payload['evidence'].pop()
        elif payload.get('projects'):payload['projects'].pop()
        else:raise ValueError('产品与目标资料超过分析输入上限，请精简产品画像')
        payload['coverage'].update(selected_evidence=len(payload.get('evidence',[])),omitted_evidence=total-len(payload.get('evidence',[])),selected_projects=len(payload.get('projects',[])))
        note='本次输入仅包含部分归档记录；未纳入部分不能据此判断。'
        if note not in payload['limitations']:payload['limitations'].append(note)
    return payload


def analysis_context(db, lead, profile, note='', request=''):
    from .service import lead_view
    from .acquisition import acquisition_detail
    view=lead_view(lead);acquisition=acquisition_detail(db,view,include_scope=True)
    products=profile.get('products') or []
    evidence=[]
    for i,project in enumerate(acquisition['projects']):
        for field in ['requirements','name']:
            value=project.get(field)
            if value and value['quote']:
                evidence.append({'ref':f'p{i}.{field}','value':value['value'],'quote':value['quote'],
                    'source_id':project['source_id'],'url':project['url'],
                    'status':'verified' if project['status'] not in {'争议','失效','待核验公告'} and project['has_body'] else 'unverified'})
        # 保存的连续需求段保留技术条件；不把正文中的其他主体事实作为该买方能力。
        quote=project['scope_quote']
        source=db.get(Evidence,project['source_id'])
        if quote and source and quote in (source.body or ''):
            evidence.append({'ref':f'p{i}.notice','value':quote,'quote':quote,'source_id':source.id,'url':source.url,
                'status':'verified' if project['status'] not in {'争议','失效','待核验公告'} else 'unverified'})
    for field in ['categories','brands','procurement']:
        fact=(lead.facts or {}).get(field,{})
        if not fact.get('value') or fact.get('verification') in {'disputed','inactive'}:continue
        citation=next((x for x in lead.evidence or [] if x.get('field')==field and x.get('source_id')==fact.get('source_id') and x.get('value')==fact.get('value')),None)
        source=db.get(Evidence,fact.get('source_id')) if fact.get('source_id') else None
        if citation and source and citation.get('quote') and citation['quote'] in (source.body or ''):
            evidence.append({'ref':'f.'+field,'value':fact['value'],'quote':citation['quote'],'source_id':source.id,'url':source.url,'status':'verified'})
    feedback=[{'kind':x.kind,'content':x.content} for x in db.scalars(select(Feedback).where(Feedback.lead_id==lead.id).order_by(Feedback.created_at,Feedback.id))]
    return {'lead_id':lead.id,'name':lead.display_name,'buyer_role':lead.buyer_role,'products':products,
        'evidence':evidence,'projects':[{k:p[k] for k in ['source_id','title','buyer','status','deadline','amounts','published_at','source_truncated']} for p in acquisition['projects']],
        'contact_summary':{'status':view['contact_summary']['status'],'purpose':view['contact_summary']['purpose']},
        'feedback':feedback,'seller_note':note,'request':request[:2000],'limitations':acquisition['gaps'],
        'fact_states':{k:v.get('verification','') for k,v in (lead.facts or {}).items()}}


def validate_matches(matches, context):
    """验证引用/连续原文/产品归属，不宣称程序能证明所有自由文本推理。"""
    evidence={e['ref']:e for e in context.get('evidence',[])};accepted=[];rejected=0;seen=set()
    for raw in matches:
        row=raw.model_dump() if isinstance(raw,BaseModel) else dict(raw)
        e=evidence.get(row.get('requirement_ref'))
        key=(row.get('product_index'),row.get('requirement_ref'))
        text=row.get('reason','')+' '+row.get('next_step','')
        valid=bool(e and e.get('status')=='verified' and row.get('quote') and row['quote'] in e['quote']
            and isinstance(row.get('product_index'),int) and 0<=row['product_index']<len(context.get('products',[]))
            and not re.search(r'购买概率|成交率|高意向|完全符合|已满足所有|预算余量|\d+(?:\.\d+)?\s*%',text))
        if valid and key not in seen:
            accepted.append({**row,'evidence':e,'product':context['products'][row['product_index']]});seen.add(key)
        elif not valid:rejected+=1
    return accepted,rejected


def latest_analysis(db, detail, conversation_id=''):
    query=select(ToolCall).where(ToolCall.tool=='lead_analysis_result',ToolCall.arguments['lead_id'].as_string()==detail['id'])
    if conversation_id:query=query.where(ToolCall.result['conversation_id'].as_string()==conversation_id)
    row=db.scalar(query.order_by(ToolCall.result['analysis_epoch'].as_float().desc(),ToolCall.created_at.desc(),ToolCall.id.desc()).limit(1))
    if not row:return None
    result=dict(row.result or {});conv=db.get(Conversation,result.get('conversation_id'))
    lead=db.get(Lead,detail['id'])
    context=analysis_context(db,lead,(conv.profile or {}) if conv else {},result.get('seller_note',''),result.get('request',''))
    result['stale']=result.get('input_hash')!=input_fingerprint(context) or result.get('policy')!=POLICY
    result['status']='stale' if result['stale'] else result.get('status','unavailable')
    return result


def enqueue_analysis(lead_id, values):
    from .service import ServiceError,submit
    with Session() as db:
        lead=db.get(Lead,lead_id);conv=db.get(Conversation,values['conversation_id'])
        if not lead or lead.archived:raise ServiceError('客户线索不存在',404)
        if not conv:raise ServiceError('产品资料对话不存在',404)
        if not (conv.profile or {}).get('products'):raise ServiceError('请先在工作台介绍产品或上传资料，形成产品画像后分析',409)
    result=submit(conv.id,{'content':'分析 '+lead.display_name+' 的需求与我司产品匹配，列出依据、待核条件和下一步。',
        'client_token':values['client_token'],'attachment_ids':[]},operation={'target_lead_id':lead_id,
        'operation_scope':'lead_product_analysis','analysis_note':values.get('content','')})
    with Session.begin() as db:
        job=db.get(Job,result['id']);job.lead_ids=list(dict.fromkeys([*(job.lead_ids or []),lead_id]))
        return serialize(job)


async def analyze_leads(state, lead_ids, profile, note=''):
    from .agent import cached_model
    from .research_tools import guard, Paused
    from .observability import safe_error
    from .service import ServiceError
    results=[]
    for offset in range(0,len(lead_ids),3):
        guard(state['job_id'])
        contexts=[];reused=[]
        with Session() as db:
            for lid in lead_ids[offset:offset+3]:
                lead=db.get(Lead,lid)
                if lead and not lead.archived:
                    context=analysis_context(db,lead,profile,note,state['prompt'])
                    cached=db.scalar(select(ToolCall).where(ToolCall.tool=='lead_analysis_result',
                        ToolCall.arguments['lead_id'].as_string()==lid,ToolCall.result['input_hash'].as_string()==input_fingerprint(context),
                        ToolCall.result['status'].as_string()=='completed',ToolCall.result['policy'].as_string()==POLICY).order_by(ToolCall.created_at.desc(),ToolCall.id.desc()).limit(1))
                    if cached:
                        reused.append({**cached.result,'reused':True,'conversation_id':state['conversation_id'],
                            'job_id':state['job_id'],'created_at':now(),'analysis_epoch':time.time(),
                            'analysis_as_of':cached.result.get('analysis_as_of') or cached.result['created_at'],
                            'reused_from_job':cached.result.get('reused_from_job') or cached.job_id})
                    else:contexts.append((context,bounded_context(context)))
        for result in reused:
            record_analysis(state,result);results.append(result)
        if not contexts:continue
        prompt=ACQUISITION_ANALYSIS.format(request=state['prompt'][:2000],context=json.dumps([c[1] for c in contexts],ensure_ascii=False))
        error=''
        try:batch=await cached_model(state,AnalysisBatch,prompt,'acquisition_analysis:'+POLICY)
        except (Paused,ServiceError):raise
        except Exception as exc:
            error=safe_error(exc);batch=None
        for full,provided in contexts:
            items=[item for item in batch.items if item.lead_id==full['lead_id']] if batch else []
            accepted,rejected=validate_matches(items[0].matches,provided) if len(items)==1 else ([],0)
            result={'lead_id':full['lead_id'],'input_hash':input_fingerprint(full),'policy':POLICY,
                'status':'completed' if len(items)==1 and not rejected and not provided['coverage']['omitted_evidence'] else 'partial' if accepted or len(items)==1 else 'unavailable',
                'matches':accepted,'questions':items[0].questions if len(items)==1 else ['匹配分析尚未完成，请重试或先核验采购文件'],
                'rejected_count':rejected,'coverage':provided['coverage'],'limitations':provided['limitations'],
                'created_at':now(),'analysis_epoch':time.time(),'job_id':state['job_id'],'conversation_id':state['conversation_id'],
                'seller_note':note,'request':state['prompt'][:2000],'products':profile.get('products',[]),'error':error}
            record_analysis(state,result)
            results.append(result)
    return results


def record_analysis(state,result):
    operation=hashlib.sha256((state['job_id']+POLICY+result['lead_id']+result['input_hash']).encode()).hexdigest()
    with Session.begin() as db:
        row=db.scalar(select(ToolCall).where(ToolCall.operation_id==operation))
        if not row:
            row=ToolCall(job_id=state['job_id'],operation_id=operation,tool='lead_analysis_result',channel='model',arguments={'lead_id':result['lead_id']});db.add(row)
        row.result=result;row.status=result['status'];row.updated_at=now()


def analysis_markdown(leads, results, site_target=1):
    from .answer_summary import saved_summary
    answer=saved_summary(leads,site_target)
    for result in results:
        lead=next((l for l in leads if l['id']==result['lead_id']),{})
        answer+='\n\n**'+lead.get('display_name','客户')+' · 产品匹配分析**'
        if result['status']!='completed':answer+='\n\n分析未完整通过引用核验，以下仅展示已通过部分。'
        for match in result['matches']:
            e=match['evidence'];label={'related':'方向相关','gap':'能力缺口','unknown':'待核验'}[match['fit']]
            answer+='\n\n- '+match['product']['name']+'：'+label+'。'+match['reason']+'\n  原文：“'+match['quote']+'” · [依据]('+e['url']+')\n  下一步：'+match['next_step']
        if result['questions']:answer+='\n\n待核：'+'；'.join(result['questions'])
    return answer
