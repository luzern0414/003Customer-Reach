"""隔离业务投影验收，不联网、不把虚构公告写入生产。"""
import uuid


def seed(client):
    from app.db import Session, Lead, Evidence, Conversation, Job
    from app.service import lead_view
    name='隔离软件采购单位'+uuid.uuid4().hex[:8]
    sources=[]
    with Session.begin() as db:
        for n, deadline in [(1,'2099-10-16 09:30:00'),(2,'2000-10-16 09:30:00')]:
            body=f'项目名称：知识库开发{n}\n项目编号：TEST-{n}\n预算金额：150.41万元\n最高限价：140万元\n采购需求：提供知识库开发与部署服务，技术规格详见采购文件。\n响应文件提交截止时间：{deadline}\n采购人名称：{name}\n地址：隔离地址\n联系方式：0437-6318701'
            e=Evidence(id=uuid.uuid4().hex, title=f'知识库开发{n}竞争性磋商公告',url=f'https://example.org/{n}',body=body,kind='网页正文',channel='procurement')
            db.add(e);sources.append(e)
        signals=[dict(source_id=e.id,buyer=name,participant_role='buyer',stage='open',deadline=d,intent_score=10,
            quote=e.body,buyer_quote='采购人名称：'+name,deadline_quote='响应文件提交截止时间：'+d) for e,d in zip(sources,['2099-10-16 09:30:00','2000-10-16 09:30:00'])]
        row=Lead(display_name=name,dedupe_key=uuid.uuid4().hex,buyer_role='project_buyer',qualification={'eligible':True,'procurement_signals':signals,'procurement_signal':signals[0]},facts={'name':{'value':name,'verification':'verified'},'procurement':{'value':sources[0].body,'verification':'verified','source_id':sources[0].id}},evidence=[{'field':'procurement','source_id':e.id,'quote':e.body,'url':e.url} for e in sources])
        db.add(row);db.flush()
        conv=Conversation(id=uuid.uuid4().hex,title=name,profile={'products':[{'name':'知识库软件','specifications':'私有部署'}]});db.add(conv)
        other=Conversation(id=uuid.uuid4().hex,title='其他隔离会话');db.add(other)
        db.add(Job(conversation_id=conv.id,client_token=uuid.uuid4().hex,prompt='找软件客户',lead_ids=[row.id],status='completed'))
        return row.id,conv.id,other.id,name


def test_projects_keep_distinct_notices_and_amount_basis(client):
    lead_id,conv,_,_=seed(client)
    data=client.get('/api/leads/'+lead_id).json()
    assert 'acquisition' in data
    p=data['acquisition']['projects']
    assert len(p)==2 and data['acquisition']['open_count']==1
    assert {r['number']['value'] for r in p}=={'TEST-1','TEST-2'}
    assert p[0]['amounts']==[{'label':'预算金额','value':'150.41万元','quote':'预算金额：150.41万元'},{'label':'最高限价','value':'140万元','quote':'最高限价：140万元'}]
    assert '详见采购文件' in p[0]['requirements']['value']
    assert data['acquisition']['research_context']['conversation_id']==conv


def test_conversation_scope_applies_to_rows_and_stats(client):
    lead_id,conv,other,name=seed(client)
    own=client.get('/api/leads',params={'conversation_id':conv,'q':name}).json()
    unrelated=client.get('/api/leads',params={'conversation_id':other,'q':name}).json()
    assert own['total']==1 and own['items'][0]['id']==lead_id
    assert unrelated['total']==0 and sum(unrelated['stats'].values())==0


def test_disputed_procurement_is_not_open_opportunity(client):
    from app.db import Session,Lead
    lead_id,*_=seed(client)
    with Session.begin() as db:
        row=db.get(Lead,lead_id);row.facts={**row.facts,'procurement':{**row.facts['procurement'],'verification':'disputed'}}
    data=client.get('/api/leads/'+lead_id).json()
    assert data['acquisition']['open_count']==0
    assert all(p['status']=='争议' for p in data['acquisition']['projects'])


def test_multi_buyer_page_does_not_borrow_first_project():
    from app.acquisition import notice_projection
    first='项目名称：甲项目\n预算金额：100万元\n采购需求：甲软件\n采购人名称：甲采购单位'
    second='项目名称：乙项目\n预算金额：10万元\n采购需求：乙软件\n采购人名称：乙采购单位'
    record={'buyer':'乙采购单位','quote':second,'source_id':'s1','stage':'historical'}
    row=notice_projection(record,{'body':first+'\n'+second}, {}, '乙采购单位')
    assert row['name']['value']=='乙项目' and row['amounts'][0]['value']=='10万元'
    assert '甲' not in row['requirements']['value']


def test_multiline_requirements_keep_hard_conditions_and_stop_at_section():
    from app.acquisition import notice_projection
    body='项目名称：知识库建设\n采购需求：知识库建设\n1. 必须离线部署\n2. 不得使用外部模型\n二、申请人的资格要求\n1. 依法纳税\n采购人名称：隔离采购单位'
    row=notice_projection({'buyer':'隔离采购单位','quote':body,'stage':'historical'}, {'body':body}, {}, '隔离采购单位')
    assert '必须离线部署' in row['requirements']['value'] and '不得使用外部模型' in row['requirements']['value']
    assert '依法纳税' not in row['requirements']['value']


def test_amount_unit_in_label_is_not_lost():
    from app.acquisition import notice_projection
    body='项目名称：隔离软件采购\n预算金额（元）：1504100\n最高限价（万元）：150.41\n采购人名称：隔离采购单位'
    row=notice_projection({'buyer':'隔离采购单位','quote':body,'stage':'historical'},{'body':body},{},'隔离采购单位')
    assert [a['value'] for a in row['amounts']]==['1504100元','150.41万元']


def test_detail_keeps_requested_product_conversation(client):
    from app.db import Session, Conversation, Job
    lead_id, first, second, _ = seed(client)
    with Session.begin() as db:
        db.get(Conversation, second).profile = {'products': [{'name': '另一产品'}]}
        db.add(Job(conversation_id=second, client_token=uuid.uuid4().hex,
                   prompt='另一产品获客', lead_ids=[lead_id], status='completed', created_at='2099-01-01 00:00:00'))
    data = client.get('/api/leads/'+lead_id, params={'conversation_id': first}).json()
    assert data['acquisition']['research_context']['conversation_id'] == first
    assert data['acquisition']['research_context']['products'][0]['name'] == '知识库软件'
    unrelated = client.post('/api/conversations', json={'title': '未关联对话'}).json()['id']
    assert client.get('/api/leads/'+lead_id, params={'conversation_id': unrelated}).status_code == 409


def test_detail_analysis_is_scoped_to_product_conversation(client):
    from sqlalchemy import select
    from app.db import Session, Job, ToolCall
    lead_id, first, second, _ = seed(client)
    with Session.begin() as db:
        original=db.scalar(select(Job).where(Job.conversation_id==first))
        another=Job(conversation_id=second, client_token=uuid.uuid4().hex,
            prompt='另一产品分析', lead_ids=[lead_id], status='completed')
        db.add(another);db.flush()
        for epoch,job in enumerate([original,another],1):
            db.add(ToolCall(job_id=job.id,operation_id=uuid.uuid4().hex,tool='lead_analysis_result',
                arguments={'lead_id':lead_id},result={'conversation_id':job.conversation_id,
                'job_id':job.id,'analysis_epoch':epoch,'status':'completed'}))
    data=client.get('/api/leads/'+lead_id,params={'conversation_id':first}).json()
    assert data['analysis']['job_id']==original.id
