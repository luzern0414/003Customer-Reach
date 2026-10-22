"""候选池与保存配额分开；可联系排序不能降低原文/主体校验。"""
import asyncio
import uuid
from sqlalchemy import select
from app.candidate_selection import candidate_priority


def test_short_invalid_and_invented_contacts_do_not_outrank_original_complete_contact():
    """只有本任务连续引文及格式有效入口优先；造值/冲突/短号不靠非空提升顺序。"""
    sources={'s':{'body':'原始电话13900000003；短号81762065；另号13900000004；邮箱sales@example.org'}}
    def candidate(value,quote,field='phone'):
        return {'facts':[{'field':field,'value':value,'quote':quote,'source_id':'s'}]}
    complete=candidate('13900000003','原始电话13900000003')
    short=candidate('81762065','短号81762065')
    invented=candidate('13900000005','造电话13900000005')
    unknown=candidate('13900000003','原始电话13900000003');unknown['facts'][0]['source_id']='absent'
    conflict={'facts':[complete['facts'][0],candidate('13900000004','另号13900000004')['facts'][0]]}
    assert all(candidate_priority(complete,sources)>candidate_priority(item,sources) for item in [short,invented,unknown,conflict])
    assert candidate_priority(candidate('sales@example.org','邮箱sales@example.org','email'),sources)[0]


def test_real_save_chooses_contactable_candidate_and_preserves_one_lead_cap(client):
    """真实save/Broker/persist校验原文，短号先出现也不占唯一名额，不生成第二条客户或超额工具调用。"""
    from app import agent
    from app.db import Session,Conversation,Job,Lead,ToolCall,identifier
    from app.gateway import archive_sources
    from app.service import save_settings,submit
    options=save_settings({'enabled_channels':['official'],'max_leads':1})
    conv=identifier()
    with Session.begin() as db:db.add(Conversation(id=conv,title='隔离候选比较'))
    job=submit(conv,{'content':'找深圳吊灯经销商最多1家','attachment_ids':[],'client_token':uuid.uuid4().hex})
    with Session.begin() as db:db.get(Job,job['id']).status='running'
    records=[('隔离候选甲','81762065'),('隔离候选乙','13900000003')]
    body='\n'.join(f'{name}是经销商，位于深圳隔离路1号，主营吊灯，电话{phone}。' for name,phone in records)
    source=archive_sources(job['id'],[{'url':'https://example.org/'+uuid.uuid4().hex,'title':'隔离候选比较','body':body}],'网页正文','official')[0]
    candidates=[]
    for name,phone in records:
        quote=next(line for line in body.splitlines() if line.startswith(name))
        facts=[{'field':field,'value':value,'quote':quote,'source_id':source['id']} for field,value in
            [('name',name),('buyer_role','经销商'),('phone',phone),('address','深圳隔离路1号'),('categories','吊灯')]]
        candidates.append({'display_name':name,'city':'深圳','buyer_role':'dealer','facts':facts,'matched_products':['吊灯'],'match_reason':'隔离测试原文'})
    state={'job_id':job['id'],'profile':{'region':'深圳','products':[{'name':'吊灯'}]},'options':options,
        'source_ids':[source['id']],'saved_ids':[],'candidates':candidates,'plan':{'target_roles':['dealer']},'cursor':0}
    result=asyncio.run(agent.save_node(state))
    assert len(result['saved_ids'])==1
    with Session() as db:
        lead=db.get(Lead,result['saved_ids'][0])
        assert lead.display_name=='隔离候选乙' and lead.facts['phone']['value']=='13900000003'
        calls=list(db.scalars(select(ToolCall).where(ToolCall.job_id==job['id'],ToolCall.tool=='persist_lead')))
        assert len(calls)==1 and calls[0].status=='completed'
