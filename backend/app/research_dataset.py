"""清洗资料与逐轮快照服务；原始Evidence不可重写，未核验提议不能进入企业事实投影。"""
import hashlib
import re
from sqlalchemy import select
from .db import Session, Job, Evidence, Lead, now, serialize
from .company_models import ResearchDataset, Company
from .company_service import stable_key
from .service import ServiceError

CLEANING_VERSION='research-clean-1'
FIELD_LABELS={'name':'企业身份','industry':'行业','business':'主营业务','products':'产品','phone':'公开电话','email':'邮箱',
    'address':'地址','website':'官网','headcount':'人员规模','revenue':'经营规模','procurement_rule':'采购机制',
    'procurement':'采购公告','supplier':'上游供应商','customer':'下游客户','subsidiary':'子公司','credit_code':'信用代码',
    'competitor':'竞争线索','detail':'工商与其他资料'}


def save_dataset(job_id: str, phase: str, batch_key: str, payload: dict, source_ids=None, status='pending', company_id=None) -> str:
    """job_id/phase/batch_key必填，payload为可序列化资料，来源为空表示无来源阶段。

    返回幂等数据集ID；任务不存在404，同批更新状态和元信息，不修改Evidence。
    """
    key=stable_key(job_id,phase,batch_key,CLEANING_VERSION)
    with Session.begin() as db:
        job=db.get(Job,job_id)
        if not job:raise ServiceError('任务不存在',404)
        row=db.scalar(select(ResearchDataset).where(ResearchDataset.unique_key==key))
        if not row:
            row=ResearchDataset(unique_key=key,job_id=job_id,conversation_id=job.conversation_id,phase=phase)
            db.add(row);db.flush()
        row.payload,row.source_ids,row.status,row.company_id=payload,list(dict.fromkeys(source_ids or [])),status,company_id
        row.updated_at=now()
        return row.id


def clean_source(source: dict, requested_fields=None, targets=None, chunk_size=6000) -> dict:
    """source为实际Evidence投影，字段/目标可空，chunk_size>=1000；返回清洗全文与原文片段。

    原数字、单位、公司名和表格顺序保持，模型片段使用原文连续区间，禁止拼接远处段落举证。
    """
    from .industry_navigation import factual_body
    original=factual_body(source.get('body',''))
    lines=[]
    for line in original.splitlines():
        value=line.strip()
        if value.startswith('URL: https://') or value.startswith('URL: http://'):continue
        if value and (not lines or value!=lines[-1]):lines.append(value)
    cleaned='\n'.join(lines)
    chunks=[]
    labels=[FIELD_LABELS.get(field,field) for field in requested_fields or []]
    terms=[*labels,*(targets or []),'公司简介','主营','采购','招标','供应商','主要客户','营业收入','员工','联系方式']
    cursor=0
    while cursor<len(original):
        end=min(len(original),cursor+max(1000,chunk_size))
        if end<len(original):
            boundary=original.rfind('\n',cursor+max(1000,chunk_size)//2,end)
            if boundary>cursor:end=boundary+1
        body=original[cursor:end]
        score=sum(min(body.count(term),8) for term in terms if term)
        chunks.append({'start':cursor,'end':end,'body':body,'score':score,'key':stable_key(source['id'],cursor,end,CLEANING_VERSION)})
        cursor=end
    chunks.sort(key=lambda item:(-item['score'],item['start']))
    return {'source_id':source['id'],'url':source.get('url',''),'title':source.get('title',''),
        'original_chars':len(original),'cleaned_chars':len(cleaned),'cleaned_body':cleaned,
        'cleaned_hash':hashlib.sha256(cleaned.encode()).hexdigest(),'chunks':chunks,'total_chunks':len(chunks)}


def defer_clean(job_id: str, source: dict, requested_fields=None, targets=None) -> str:
    """job_id/真实source必填，字段与主体可空；持久化可重放的清洗任务，返回ID，缺任务404。

    不覆盖已清洗资料；进程退出前只需写源ID和参数，原文已在不可变Evidence中。
    """
    key=stable_key(job_id,'clean',source['id'],CLEANING_VERSION)
    with Session() as db:
        old=db.scalar(select(ResearchDataset).where(ResearchDataset.unique_key==key))
        if old:return old.id
    return save_dataset(job_id,'clean',source['id'],{'deferred':True,'source_id':source['id'],'title':source.get('title',''),
        'requested_fields':requested_fields or [],'targets':targets or [],'has_full_text':False,
        'origin':'network' if source.get('job_id')==job_id else 'local_history','source_kind':source.get('kind','')},[source['id']],'pending')


def drain_deferred(limit=4) -> int:
    """limit为1..20的小批上限；处理持久pending资料，返回成功数，失败保留类型和原任务供排查。

    Worker仅运行一个后台消费者，重启再次扫描；摘要整理后仍pending/has_full_text=false。
    """
    from .observability import safe_error
    with Session() as db:
        rows=[serialize(row) for row in db.scalars(select(ResearchDataset).where(ResearchDataset.phase=='clean',ResearchDataset.status=='pending',
            ResearchDataset.payload['deferred'].as_boolean()==True).order_by(ResearchDataset.created_at).limit(max(1,min(20,limit))))]
    count=0
    for row in rows:
        payload=row['payload']
        try:
            with Session() as db:source=db.get(Evidence,payload['source_id']);source=serialize(source) if source else None
            if not source:raise ValueError('来源不存在')
            full=source['kind'] in {'网页正文','网页读取','Edge网页正文','历史归档正文'}
            cleaned=clean_source(source,payload.get('requested_fields'),payload.get('targets'))
            save_dataset(row['job_id'],'clean',source['id'],{**cleaned,'origin':payload['origin'],'source_kind':source['kind'],
                'has_full_text':full,'deferred':False},[source['id']],'completed' if full else 'pending')
            count+=1
        except Exception as exc:
            with Session.begin() as db:
                current=db.get(ResearchDataset,row['id'])
                current.status='failed';current.payload={**payload,'error_type':safe_error(exc)};current.updated_at=now()
    return count


def local_research(query: str, targets=None, limit=8) -> dict:
    """query为本轮问题，targets为模型提出的原主体名（可空），limit为1..20；只读已有清洗/核验资料。

    返回真实企业/数据集摘要及来源ID，保留历史标记，不发网络、不将未核验提议作为事实。
    """
    terms=[name.strip() for name in targets or [] if name.strip()]
    if not terms:terms=[part for part in re.split(r'[，,。\s]+',query) if 2<=len(part)<=100][:4]
    with Session() as db:
        companies=[]
        for name in terms:
            rows=db.scalars(select(Company).where(Company.name.contains(name,autoescape=True)|Company.short_name.contains(name,autoescape=True)).limit(limit))
            companies.extend(serialize(row) for row in rows)
        ids={row['id'] for row in companies}
        candidates=list(db.scalars(select(ResearchDataset).where(ResearchDataset.phase.in_(['final','review'])).order_by(ResearchDataset.updated_at.desc()).limit(100)))
        datasets=[];source_ids=[]
        for row in candidates:
            payload=row.payload or {};names=payload.get('targets',[])
            if row.company_id not in ids and not any(term in name or name in term for term in terms for name in names):continue
            datasets.append({'id':row.id,'job_id':row.job_id,'phase':row.phase,'status':row.status,'captured_at':row.updated_at,
                'summary':{key:payload.get(key) for key in ('targets','coverage','gaps','accepted','stop_reason')}})
            source_ids.extend(row.source_ids or [])
            if len(datasets)>=limit:break
        # 初代任务尚无清洗数据集，真实归档正文仍可作为历史资料入口，随后由当前清洗节点处理。
        for name in terms:
            prior=db.scalars(select(Evidence).where(Evidence.kind.in_(['网页正文','网页读取','Edge网页正文','历史归档正文']),
                Evidence.title.contains(name,autoescape=True)|Evidence.body.contains(name,autoescape=True)).order_by(Evidence.captured_at.desc()).limit(limit))
            source_ids.extend(source.id for source in prior)
        return {'companies':list({row['id']:row for row in companies}.values())[:limit],'datasets':datasets,
            'source_ids':list(dict.fromkeys(source_ids))[:limit],'origin':'local_history'}


def dataset_summary(rows: list) -> dict:
    """rows为同一任务数据集行（可空）；返回计数/覆盖/缺口，无原文或内部模型提议。"""
    cleaned=[row for row in rows if row.phase=='clean'];reviews=[row for row in rows if row.phase=='review']
    final=next((row for row in reversed(rows) if row.phase=='final'),None)
    latest=(final or (reviews[-1] if reviews else None))
    payload=latest.payload if latest else {}
    receipts=[row.payload for row in rows if row.phase=='save']
    refs={}
    for receipt in receipts:
        for item in receipt.get('accepted_refs',[]):
            key=(item.get('kind'),item.get('id'))
            if key not in refs or item.get('change')=='new':refs[key]=item
    accepted=[item for item in refs.values() if item.get('kind')!='identity']
    return {'cleaned_documents':len({sid for row in cleaned for sid in row.source_ids or []}),
        'pending_documents':sum(bool(row.payload.get('deferred')) for row in cleaned if row.status=='pending'),
        'extracted_batches':sum(row.phase=='extract' and row.status=='completed' for row in rows),
        'accepted':len(accepted),'new_records':sum(item.get('change')=='new' for item in accepted),
        'reconfirmed_records':sum(item.get('change')=='reconfirmed' for item in accepted),
        'rejected':sum(len(item.get('rejected',[])) for item in receipts),
        'coverage':payload.get('coverage',{}),'gaps':payload.get('gaps',[]),'round':payload.get('round',0),
        'stop_reason':payload.get('stop_reason',''),'dataset_count':len(rows),
        'datasets':[{'id':row.id,'phase':row.phase,'status':row.status,'source_ids':row.source_ids,'created_at':row.created_at,
            'title':row.payload.get('title',''),'origin':row.payload.get('origin',''),'source_kind':row.payload.get('source_kind','')} for row in rows if row.phase in {'clean','final'}]}


def field_coverage(targets: list, requested: list, receipts: list, source_count=0, analyzed=0, pending=0) -> dict:
    """targets/requested为本轮主体和字段，receipts为核验回执；空主体不能冒称完成，返回逐主体缺口。

    仅统计通过保存的引用；同名目标按完整原名或已核验简称绑定，A的字段不能替B完成。
    """
    from .company_validation import target_matches
    from .company_models import CompanyFact
    ids={ref['id'] for receipt in receipts for ref in receipt.get('accepted_refs',[]) if ref.get('kind') in {'identity','fact'} and ref.get('id')}
    with Session() as db:
        invalid=set(db.scalars(select(CompanyFact.id).where(CompanyFact.id.in_(ids),CompanyFact.status!='verified'))) if ids else set()
    by_company=[]
    for target in targets:
        matching=[receipt for receipt in receipts if target_matches(receipt.get('company_name',''),target,receipt.get('identity_quote',''))]
        fields={ref['field'] for receipt in matching for ref in receipt.get('accepted_refs',[]) if ref.get('field') and ref.get('id') not in invalid}
        by_company.append({'target':target,'company_ids':list(dict.fromkeys(receipt['company_id'] for receipt in matching if receipt.get('company_id'))),
            'verified_fields':sorted(fields),'missing_fields':[field for field in requested if field not in fields]})
    missing=[field for field in requested if not by_company or any(field in item['missing_fields'] for item in by_company)]
    return {'requested_fields':requested,'verified_fields':[field for field in requested if field not in missing],
        'missing_fields':missing,'companies':by_company,'source_count':source_count,'analyzed_chunks':analyzed,'pending_chunks':pending}


def research_summary(job_id: str) -> dict:
    """job_id为真实非空任务ID；返回完整同轮数据集汇总，缺任务404。"""
    with Session() as db:
        if not db.get(Job,job_id):raise ServiceError('任务不存在',404)
        return dataset_summary(list(db.scalars(select(ResearchDataset).where(ResearchDataset.job_id==job_id).order_by(ResearchDataset.created_at,ResearchDataset.id))))


def record_stage(state: dict, node: str, output: dict) -> None:
    """state为真实research图状态，node为read/extract/save/gap，output为实际节点返回；其他阶段不处理。

    获客分支同样沉淀逐轮资料；提议保留pending，只有真实保存的Lead引用统计为核验结果，无返回值。
    """
    if state.get('intent')!='research' or node not in {'search','read','extract','save','gap'}:return
    job_id=state['job_id'];sources=output.get('source_ids',state.get('source_ids',[]))
    key=stable_key(*sources,state.get('cursor',0))
    if node in {'search','read'}:
        with Session() as db:
            rows=[serialize(row) for sid in (sources if node=='search' else output.get('recent_read_source_ids',[])) if (row:=db.get(Evidence,sid))]
        for row in rows:
            full_text=row['kind'] in {'网页正文','网页读取','Edge网页正文'}
            save_dataset(job_id,'clean',row['id'],{**clean_source(row),'origin':'network' if row.get('job_id')==job_id else 'local_history',
                'source_kind':row['kind'],'has_full_text':full_text},[row['id']],'completed' if full_text else 'pending')
    elif node=='extract':
        save_dataset(job_id,'extract',key,{'candidates':output.get('candidates',[]),'gaps':output.get('gaps',[]),'verification':'pending'},sources,'completed')
    elif node=='save':
        refs=[]
        with Session() as db:
            for lid in output.get('saved_ids',[]):
                lead=db.get(Lead,lid)
                if not lead:continue
                evidence=[item for item in lead.evidence or [] if item.get('source_id') in sources]
                if evidence:refs.append({'kind':'lead','id':lid,'source_ids':list(dict.fromkeys(item['source_id'] for item in evidence))})
        save_dataset(job_id,'save',key,{'accepted_refs':refs,'lead_ids':output.get('saved_ids',[]),'gaps':output.get('gaps',[])},sources,'completed')
    else:
        save_dataset(job_id,'review',key,{'gaps':output.get('gaps',[]),'remaining_budget':output.get('remaining_budget',{}),'lead_ids':state.get('saved_ids',[])},sources,'completed')


def dataset_detail(dataset_id: str) -> dict:
    """dataset_id为真实持久ID；返回显式标记阶段的清洗资料，缺记录404，未核验提议保留pending语义。"""
    with Session() as db:
        row=db.get(ResearchDataset,dataset_id)
        if not row:raise ServiceError('研究数据集不存在',404)
        return serialize(row)


def finalize_dataset(job_id: str, status: str) -> None:
    """job_id为结束的研究，status为实际终态；即使预算/异常结束也持久最终统计，暂停只保留中间数据。"""
    if status=='paused':return
    with Session() as db:
        job=db.get(Job,job_id)
        if not job or (job.metrics or {}).get('intent') not in {'research','company_query'}:return
        rows=list(db.scalars(select(ResearchDataset).where(ResearchDataset.job_id==job_id).order_by(ResearchDataset.created_at,ResearchDataset.id)))
        previous=next((row for row in rows if row.phase=='final'),None)
        payload={**(previous.payload or {})} if previous else {}
        summary=dataset_summary(rows)
        requested=(job.metrics or {}).get('requested_fields',[])
        targets=(job.metrics or {}).get('intent_decision',{}).get('targets',[])
        coverage=payload.get('coverage') or field_coverage(targets,requested,[row.payload for row in rows if row.phase=='save'])
        gaps=payload.get('gaps') or [FIELD_LABELS.get(field,field)+'尚未取得可核验资料' for field in coverage.get('missing_fields',[])]
        sources=list(dict.fromkeys([sid for row in rows for sid in row.source_ids or []]))
        payload.update(status=status,coverage=coverage,gaps=gaps,accepted=summary['accepted'],
            new_records=summary['new_records'],reconfirmed_records=summary['reconfirmed_records'],company_ids=job.company_ids,
            targets=(job.metrics or {}).get('intent_decision',{}).get('targets',[]),
            stop_reason=payload.get('stop_reason') or ('budget_exhausted' if (job.metrics or {}).get('budget_exhausted') else status))
    save_dataset(job_id,'final','final',payload,sources,status)
