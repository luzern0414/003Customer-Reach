"""已消歧主体的工商资料补齐；确定性字段通过原有逐字段持久门禁。"""
import os
from .qcc_evidence import primary_object, primary_matches, identity_quote
from .company_research_schemas import CompanySnapshot, ResearchFact

FIELDS = {'统一社会信用代码':('credit_code','统一社会信用代码'), '注册地址':('address','注册地址'),
          '经营范围':('business','经营范围'), 'credit_code':('credit_code','统一社会信用代码'),
          'address':('address','注册地址'), 'business':('business','经营范围')}
REGISTRATION_FIELDS={'法定代表人':'法定代表人','注册资本':'注册资本','实缴资本':'实缴资本',
    '成立日期':'成立日期','工商注册号':'工商注册号','登记状态':'经营状态','企业类型':'企业类型',
    '登记机关':'登记机关','营业期限':'营业期限','核准日期':'核准日期'}
FIELDS.update({key:('detail',label) for key,label in REGISTRATION_FIELDS.items()})


async def enrich_company(state):
    options=state.get('options',{})
    if (not options.get('qcc_enabled',True) or options.get('max_qcc_calls',0)<=0 or state.get('reference_only') or
            os.getenv('CLIENTREACH_QCC_ENABLED','').lower() in {'0','false','off'}):return {}
    from .company_research import broker_for
    broker=broker_for(state)
    targets=[state['company_target_name']] if state.get('company_target_name') else state.get('company_intent_targets',[])
    sources=list(state.get('source_ids',[]));pending=list(state.get('company_mcp_sources',[]))
    ids=list(state.get('company_ids',[]));receipts=list(state.get('company_receipts',[]));attempts=list(state.get('attempts',[]))
    updates=state.get('company_updates',0)
    for name in targets[:min(2,options['max_qcc_calls'])]:
        result=await broker.execute('qcc_company_lookup',{'name':name,'action':'basic'})
        attempts.append({'channel':'qcc_mcp','entity_name':name,'query':name,'error':result.get('error',''),'source_count':len(result.get('sources',[]))})
        for source in result.get('sources',[]):
            sources.append(source['id'])
            if not primary_matches(source.get('body',''),name):continue
            value,path=primary_object(source['body']);facts=[]
            for key,(field,label) in FIELDS.items():
                item=value.get(key)
                if isinstance(item,str) and item.strip() and len(item)<=1500:
                    facts.append(ResearchFact(field=field,label=label,value=item,source_id=source['id'],quote=f'{path}.{key}: {item}'))
            industry=value.get('国标行业',{})
            if isinstance(industry,dict):
                key=next((key for key in ('小类','中类','大类','门类') if isinstance(industry.get(key),str) and industry[key]),None)
                if key and len(industry[key])<=1500:
                    facts.append(ResearchFact(field='industry',label='国标行业',value=industry[key],source_id=source['id'],quote=f'{path}.国标行业.{key}: {industry[key]}'))
            snapshot=CompanySnapshot(name=name,source_id=source['id'],identity_quote=identity_quote(source['body'],name),facts=facts)
            receipt=await broker.execute('persist_company',{'snapshot':snapshot.model_dump(),'targets':targets})
            if receipt.get('company_id'):
                ids.append(receipt['company_id']);receipts.append(receipt);updates+=receipt.get('accepted_fields',0)
    return {'source_ids':list(dict.fromkeys(sources)),'company_ids':list(dict.fromkeys(ids)),
            'company_receipts':receipts,'company_updates':updates,'attempts':attempts,'company_mcp_sources':list(dict.fromkeys(pending))}
