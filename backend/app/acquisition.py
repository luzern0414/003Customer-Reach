"""获客机会的只读投影；公告、产品匹配与CRM状态分开。"""
import re
from sqlalchemy import select, func
from .db import Evidence, Job, Conversation, now, serialize


def related_jobs(lead_id):
    """SQL子查询限定真正关联的Job，不扫描或截断历史任务。"""
    entries=func.json_each(Job.lead_ids).table_valued('value')
    return select(Job).where(select(1).select_from(entries).where(entries.c.value==lead_id).exists())


def field_span(body, labels):
    """取带明确字段标签的连续原文；不解释表格列或从标题猜值。"""
    match=re.search(r'(?m)^[ \t]*(?:'+labels+r')[：:][ \t]*([^\n；;]+)',body)
    return {'value':match[1].strip(),'quote':match[0].strip()} if match else None


def project_scope(body, record, name):
    """只采用单买方单项目正文，或引文中独立具名项目；复杂组合页保持未知。"""
    from .procurement_accounts import BUYER
    def belongs(text):
        buyers=list(BUYER.finditer(text))
        return len(buyers)==1 and buyers[0]['name'].strip()==name and len(re.findall(r'(?m)^\s*项目名称[：:]',text))<=1
    if body and belongs(body):return body
    quote=record.get('quote','')
    return quote if quote and quote in body and belongs(quote) else ''


def requirement_span(body, limit=6000):
    start=re.search(r'(?m)^[ \t]*(?:采购需求|采购内容|服务内容|招标范围|技术要求)[：:][ \t]*',body)
    if not start:return None
    tail=body[start.end():]
    end=re.search(r'(?m)^\s*(?:(?:[一二三四五六七八九十]+[、.．]|\d+[、.．])\s*)?(?:申请人的?资格(?:要求)?|资格要求|采购人(?:信息|名称)|采购代理|招标代理|响应文件|投标文件|合同履行期限|预算金额|采购预算|最高限价|项目名称|项目编号)(?:[：:\s]|$)',tail)
    span=body[start.start():start.end()+(end.start() if end else len(tail))].rstrip()
    truncated=len(span)>limit;quote=span[:limit]
    return {'value':quote[start.end()-start.start():].strip(),'quote':quote,'truncated':truncated}


def notice_projection(record, source, facts, name):
    from .procurement import signal_status, open_buyer_signal, closed_notice
    from .schemas import ProcurementSignal
    status=signal_status(record,now());body=source.get('body','')
    if any(facts.get(k,{}).get('verification') in {'disputed','inactive'} for k in ['name','buyer_role','procurement']):
        status='争议' if any(facts.get(k,{}).get('verification')=='disputed' for k in ['name','buyer_role','procurement']) else '失效'
    elif closed_notice(source.get('title',''),body):status='已结束'
    elif status=='公开采购':
        try:valid=open_buyer_signal(name,ProcurementSignal.model_validate(record),source,now())
        except ValueError:valid=False
        if not valid:status='待核验公告'
    scope=project_scope(body,record,name)
    amounts=[]
    for label in ['预算金额','采购预算','最高限价','中标金额','成交金额']:
        value=field_span(scope,re.escape(label)+r'(?:[（(][^）)\n]+[）)])?')
        if value:
            unit=re.search(r'[（(]((?:人民币)?[万亿]?元)[）)]',value['quote'].split('：',1)[0].split(':',1)[0])
            if unit and re.fullmatch(r'\d+(?:,\d{3})*(?:\.\d+)?',value['value']):value['value']+=unit[1]
            amounts.append({'label':label,**value})
    requirement=requirement_span(scope)
    # 需求章节跨行时提供连续区间，并保留已保存项目原文供详细查看。
    return {'source_id':record.get('source_id',''),'title':source.get('title') or record.get('title',''),
        'url':source.get('url') or record.get('url',''),'published_at':source.get('published_at') or '',
        'captured_at':source.get('captured_at') or record.get('captured_at',''),'status':status,'stage':record.get('stage',''),
        'buyer':record.get('buyer',''),'deadline':record.get('deadline',''),'deadline_quote':record.get('deadline_quote',''),
        'name':field_span(scope,'项目名称'),'number':field_span(scope,'项目编号|采购编号|招标编号'),
        'amounts':amounts,'requirements':requirement,'quote':record.get('quote',''),
        'buyer_quote':record.get('buyer_quote',''),'has_body':bool(body),'scope_quote':scope,
        'field_scope_verified':bool(scope),
        'source_truncated':bool((source.get('source_meta') or {}).get('truncated'))}


def acquisition_views(db, leads, include_scope=False):
    """批量读公告一次，再按每条线索的绑定关系投影，避免分页N次正文查询。"""
    from .procurement import procurement_views
    signals={lead['id']:procurement_views(lead.get('qualification'),now()) for lead in leads}
    ids={r.get('source_id') for rows in signals.values() for r in rows}
    sources={r.id:serialize(r) for r in db.scalars(select(Evidence).where(Evidence.id.in_(ids)))} if ids else {}
    views={}
    for lead in leads:
        projects=[notice_projection(row,sources.get(row.get('source_id'),{}),lead.get('facts') or {},lead['display_name']) for row in signals[lead['id']]]
        if not include_scope:
            for project in projects:project.pop('scope_quote',None)
        projects.sort(key=lambda p:(p['status']!='公开采购',p['deadline'] or '9999',p['source_id']))
        gaps=[]
        if not projects:gaps.append('尚无绑定该买方的采购公告；主体资料不证明采购需求')
        if projects and any(not p['requirements'] or re.search('详见|见附件',p['requirements']['value']) for p in projects):gaps.append('详细技术规格需要获取采购文件核验')
        if any(not p['field_scope_verified'] for p in projects):gaps.append('组合页面尚未定位本买方独立项目范围，项目字段保留未知')
        if any(p['requirements'] and p['requirements'].get('truncated') for p in projects):gaps.append('需求章节超过展示上限，剩余技术条件须查看归档全文')
        if not lead.get('contact_summary',{}).get('usable_fields'):gaps.append('公开业务联系方式待补')
        if not lead.get('matched_products'):gaps.append('具体产品适配及供应商资格待核验')
        views[lead['id']]={'projects':projects,'open_count':sum(p['status']=='公开采购' for p in projects),'gaps':gaps,
            'as_of':now(),'priority_basis':'原评分衡量角色、产品证据、联系覆盖与公告信号，不是购买概率'}
    return views


def acquisition_detail(db, lead, include_scope=False, conversation_id=''):
    view=acquisition_views(db,[lead],include_scope)[lead['id']]
    query=related_jobs(lead['id'])
    if conversation_id:query=query.where(Job.conversation_id==conversation_id)
    job=db.scalar(query.order_by(Job.created_at.desc(),Job.id.desc()).limit(1))
    if conversation_id and not job:
        from .service import ServiceError
        raise ServiceError('该对话未关联此客户，请返回对应获客结果',409)
    conv=db.get(Conversation,job.conversation_id) if job else None
    view['research_context']={'conversation_id':conv.id if conv else '',
        'products':(conv.profile or {}).get('products',[]) if conv else [],'title':conv.title if conv else ''}
    return view
