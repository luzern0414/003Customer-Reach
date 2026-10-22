"""基于已经保存的CRM资料生成降级答复；不调用模型、不补采购意图或未知联系字段。"""
import re
from .contact_view import contact_view,website_link
from .industry_navigation import factual_body
from .source_content import has_content


def read_pages(result: dict) -> list[dict]:
    """result为真实工具结果可空；仅返回取得有效正文的页面元信息，不包含正文/密钥，搜索摘录及标题假正文排除。"""
    pages={}
    for source in (result or {}).get('sources',[]):
        if source.get('kind') not in {'网页正文','网页读取'} or not has_content({**source,'body':factual_body(source.get('body',''))}):continue
        pages.setdefault(source.get('id') or source.get('url'),{key:source.get(key,'') for key in ['id','title','url','kind']})
    return list(pages.values())


def channel_summary(operations: list[dict]) -> tuple[str,bool]:
    """operations为本任务已核正文投影（可空）；返回失败渠道中文摘要及是否同渠道成功/失败并存，不将读取当客户字段核验。"""
    from .source_catalog import CHANNELS
    channels={}
    for item in operations:
        if item.get('tool') not in {'search_accounts','fetch_source'}:continue
        channel=item.get('channel','')
        row=channels.setdefault(channel,{'read':set(),'failed':0,'search':0})
        if item['tool']=='search_accounts' and item.get('status')=='completed':row['search']+=item.get('source_count',0)
        if item['tool']=='fetch_source':
            if item.get('status')=='completed':row['read'].update(page.get('id') or page.get('url') for page in item.get('read_pages',[]))
            elif item.get('status') not in {'running','queued','paused'}:row['failed']+=1
    parts=[];mixed=False
    for channel,row in channels.items():
        if not row['failed']:continue
        label=CHANNELS.get(channel,{}).get('name','公开网页')
        if row['read']:
            mixed=True;parts.append(label+'：已取得正文，部分页面读取未成功')
        elif row['search']:parts.append(label+'：有搜索摘录，读取未取得正文')
        else:parts.append(label+'：读取未取得正文')
    return ('；'.join(parts)+'。' if parts else ''),mixed


def review_context(operations: list[dict], reference_urls: list[str], limit: int=8000) -> list[dict]:
    """operations为本任务实际工具结果，reference_urls为当前指定入口，limit为正文字符预算；仅提供成功读到的原正文，不联网、不当已存客户。"""
    sources={}
    for operation in operations:
        if operation.get('tool')!='fetch_source' or operation.get('status')!='completed':continue
        for source in (operation.get('result') or {}).get('sources',[]):
            # 用户可能引用实际成功响应的最终URL；重定向不意味着正文没读到，只认本job成功账本中的对应关系。
            if (operation.get('arguments') or {}).get('url') not in reference_urls and source.get('url') not in reference_urls:continue
            body=factual_body(source.get('body',''))
            if source.get('kind') not in {'网页正文','网页读取'} or not has_content({**source,'body':body}):continue
            sources.setdefault(source['id'],{key:source.get(key,'') for key in ['id','url','title']}|{'body':body})
    share=max(0,limit//len(sources)) if sources else 0
    return [{**source,'body':source['body'][:share],'truncated':len(source['body'])>share} for source in sources.values()] if share else []


def proposal_summary(operations: list[dict], saved_count: int) -> dict:
    """operations为真实工具账本摘要、saved_count为本任务保存数；统计成功提取输出条目（可重复），不称已核验不同客户。"""
    records=0;batches=0
    for operation in operations:
        tool=operation.get('tool','')
        if operation.get('status')!='completed' or not (tool.startswith('extract:') or tool=='parse_account'):continue
        candidates=(operation.get('result') or {}).get('candidates') or []
        count=sum(isinstance(item,dict) and bool(item.get('display_name')) for item in candidates)
        records+=count;batches+=bool(count)
    return {'proposed_records':records,'nonempty_batches':batches,'saved_leads':saved_count,
        'meaning':'候选提议记录可重复，未经保存校验，不代表不同客户数或可联系客户数'}


def answer_context(leads: list[dict]) -> list[dict]:
    """leads为已保存数据库行（可空）；返回覆盖每条客户的精简答复资料，保留事实状态与来源，不补值或截断整批JSON。"""
    result=[]
    for lead in leads:
        facts=lead.get('facts') or {};evidence=lead.get('evidence') or []
        contacts=contact_view(facts,evidence)
        compact={field:{key:fact[key] for key in ['value','verification','scope','effective_date','additional_contact'] if key in fact}
                 for field,fact in facts.items()}
        for field,fact in facts.items():
            alternatives=fact.get('alternatives') or []
            if alternatives:
                # 争议值不等于长引文；保留字段值及真实总数，不能压缩后让回答误称没有替代记录。
                compact[field]['alternatives']=[{key:item[key] for key in ['value','verification','scope','effective_date','source_id','relation'] if key in item} for item in alternatives[:4]]
                compact[field]['alternatives_count']=len(alternatives)
                compact[field]['alternatives_truncated']=len(alternatives)>4
        qualification=lead.get('qualification') or {}
        signals=[{key:value for key,value in item.items() if key not in {'quote','buyer_quote','deadline_quote'}}
                 for item in qualification.get('procurement_signals',[])]
        # 原文角色标题用于分店区分；其他冗长逐字段引文留在CRM，不挤掉后面的客户。
        roles=[{'url':item.get('url',''),'quote':item.get('quote','')} for item in evidence if item.get('field')=='buyer_role']
        cards=[]
        for item in evidence:
            if item.get('field') not in {'name','phone','wechat','contact_name','city'}:continue
            quote=item.get('quote','');url=item.get('url','')
            if not quote or len(quote)>1500:continue
            existing=next((card for card in cards if card['url']==url and card['quote']==quote),None)
            if existing:
                if item['field'] not in existing['fields']:existing['fields'].append(item['field'])
            elif len(cards)<4:
                # 保留原文商户与电话的同条记录，只有角色表头会让回答误以为缺主体对应；不拼不同片段。
                cards.append({'fields':[item['field']],'url':url,'quote':quote})
        result.append({key:lead.get(key) for key in ['id','display_name','city','buyer_role','match_reason','matched_products']}|
                      {'facts':compact,'contact_summary':contacts,'role_context':roles,'contact_evidence':cards,'procurement_signals':signals})
    return result


def saved_summary(leads: list[dict], site_target: int=1) -> str:
    """leads为真实数据库行序列（可空），site_target为当前要求网站数默认1；返回Markdown及真实来源缺口，不补值或提供失效入口。"""
    lines=[]
    for lead in leads:
        facts=lead.get('facts') or {};evidence=lead.get('evidence') or []
        contacts=contact_view(facts,evidence)
        values=[('微信：' if field=='wechat' else '')+facts[field]['value'] for field in contacts['usable_fields']]
        source=next((item.get('url','') for item in evidence if item.get('field')=='name'),'')
        title='['+lead['display_name']+']('+source+')' if website_link(source) else lead['display_name']
        info=[facts[field]['value'] for field in ['categories','address'] if facts.get(field,{}).get('verification') not in {'disputed','inactive'} and facts.get(field,{}).get('value')]
        person=facts.get('contact_name',{})
        if person.get('value') and person.get('verification') not in {'disputed','inactive'}:info.insert(0,'联系人：'+person['value'])
        for field in contacts['usable_fields']:
            fact=facts[field]
            citation=next((item for item in evidence if item.get('field')==field and item.get('source_id')==fact.get('source_id')),None)
            if citation and website_link(citation.get('url')):info.append('[联系来源]('+citation['url']+')')
            if fact.get('scope'):info.append(fact['scope'])
        if site_target>1:info.append(str(contacts['site_count'])+'个网站')
        lines.append('- '+title+'：'+(' / '.join(values) if values else '联系信息待核验')+('  \n  '+' · '.join(info) if info else ''))
        from .procurement import procurement_views
        from .db import now
        notices=[item for item in procurement_views(lead.get('qualification'),now()) if item.get('verification') not in {'disputed','inactive'}]
        displayed=set()
        for notice in notices[:4]:
            quote=notice.get('quote','');deadline=notice.get('deadline','')
            detail=notice.get('title','')+' · '+notice['display_status']+(' · 截止：'+deadline if deadline else '')
            url=notice.get('url') or next((item.get('url','') for item in evidence if item.get('source_id')==notice.get('source_id')),'')
            if website_link(url):detail+=' · [公告原始来源]('+url+')'
            lines.append('  \n  '+detail)
            if quote and quote not in displayed:
                lines.append('  \n  公告原文：'+quote);displayed.add(quote)
        if not notices:
            purchase=facts.get('procurement',{})
            if purchase.get('value') and purchase.get('verification') not in {'disputed','inactive'}:
                lines.append('  \n  采购原文：'+purchase['value'])
        if len(notices)>4:lines.append('  \n  其余'+str(len(notices)-4)+'条公告保留在该客户详情中。')
    if any(contact_view(lead.get('facts') or {},lead.get('evidence') or [])['usable_fields'] for lead in leads):
        lines.append('联系方式当前有效性待核，公开联系记录不代表已确认采购。')
    # 模型漏联系方式触发摘要替换时，也不能丢掉用户明确的多站核验要求。
    missing=sum(contact_view(lead.get('facts') or {},lead.get('evidence') or [])['site_count']<site_target for lead in leads)
    if site_target>1 and missing:lines.append(f'仍有{missing}条线索未达到每条至少{site_target}个网站的核验要求。')
    return '\n\n'.join(lines) if lines else '现有资料尚不足以确认可联系客户。'


def contact_answer_missing(leads: list[dict], answer: str, prompt: str) -> bool:
    """leads为已存客户、answer为模型草稿、prompt为当前要求（均可空）；仅检查获客/联系补查的必要原值，返回是否遗漏，不验证全部语义或触发新请求。"""
    # 解释、比较和原文诊断不能被联系人列表代替；此检查只修复结果交付契约。
    if not re.search(r'找|寻找|补查|补全|获取|推荐|筛选|查询|核验|联系',prompt or ''):return False
    if re.search(r'为什么|为何|解释|原文|复核|比较|候选|日期|耗时|采集时间',prompt or ''):return False
    for lead in leads or []:
        facts=lead.get('facts') or {}
        if facts.get('name',{}).get('verification') in {'disputed','inactive'}:continue
        fields=contact_view(facts,lead.get('evidence') or [])['usable_fields']
        if not fields:continue
        required=[lead['display_name']]+[facts[field]['value'] for field in fields]
        person=facts.get('contact_name',{})
        if person.get('value') and person.get('verification') not in {'disputed','inactive'}:required.append(person['value'])
        if any(value not in answer for value in required):return True
    return False


def empty_summary(operations: list[dict]) -> str:
    """operations为本任务工具账本，可空；只总结真实过程，不把页面标题或未通过候选作为核验客户。"""
    from .source_catalog import source_label
    read=[]
    for item in operations:
        if item.get('tool')=='fetch_source' and item.get('status')=='completed' and item.get('source_count',0)>0:
            for page in item.get('read_pages',[]):
                label=source_label(page.get('url',''))
                if label and label not in read:read.append(label)
    parts=['本轮尚无通过完整校验的客户线索。']
    if read:parts.append('已读取：'+'、'.join(read)+'。')
    details=list(dict.fromkeys(source_label(item.get('url',''))+'：'+item['read_summary']+'。' for item in operations
        if item.get('tool')=='fetch_source' and item.get('read_summary')))
    parts.extend(details[:3])
    if any(item.get('tool')=='search_accounts' and item.get('error')=='provider_rate_limited' for item in operations):
        parts.append('检索供应商额度受限；已读取的网页不受此结论影响。')
    if any(item.get('tool')=='persist_lead' and item.get('status')=='rejected' for item in operations):
        parts.append('候选资料未通过校验，未作为可联系客户交付。')
    parts.append('下一步：换公开来源补齐主体、目标角色及业务联系方式。')
    return '\n\n'.join(parts)
