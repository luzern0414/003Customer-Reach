"""目录原40条边界与真实读取额度分开；第九个入口仍可在过滤后由Broker复核。"""
import asyncio
import uuid
import pytest
from app.industry_navigation import navigation_text
from app.public_directory import directory_text,directory_links


@pytest.mark.parametrize('channel',['industry_directory','mall_directory'])
@pytest.mark.parametrize('full',[False,True])
def test_ninth_directory_entry_survives_attempt_and_subject_filters(client,monkeypatch,channel,full):
    """client隔离库、monkeypatch限单平台窗口场景、channel为模板、full为满额；真实gap/read/Broker缓存验尾入口，不联网、不声明客户核验。"""
    from app import agent
    from app.db import Session,Job,Lead,ToolCall,identifier
    from app.service import save_settings
    from app.gateway import archive_sources
    profile={'region':'深圳','products':[{'name':'吊灯'}]}
    options=save_settings({'enabled_channels':[channel],'max_leads':1,'max_reads':1 if full else 9})
    conv=client.post('/api/conversations').json()['id']
    job=client.post('/api/conversations/'+conv+'/messages',json={'content':'找深圳灯具经销商','client_token':uuid.uuid4().hex}).json()['id']
    base=100000+int(uuid.uuid4().hex[:6],16)
    if channel=='industry_directory':
        parent='https://www.yunfale.com/'
        content=''.join(f'<a href="/company/detail/{base+i}/">深圳隔离灯具公司{i}</a>' for i in range(9))
        body='隔离目录实际可见内容。'*20+'\n'+navigation_text(content.encode(),parent,profile)
        if not full:
            from app import source_catalog
            # 单独验证去重窗口，不让正确的“先给未试平台机会”规则改变本用例目标。
            monkeypatch.setattr(source_catalog,'PUBLIC_ENTRIES',[{'url':parent,'channel':channel,'region':'深圳','products':'灯|照明'}])
    else:
        parent='http://www.leanju.com:8080/subbranch/'
        content=''.join(f'<a href="/subbranch-detail/i-{base+i}.html">隔离分店{i}</a>' for i in range(9))
        body=directory_text(content.encode(),parent)
    links=directory_links(body,parent,profile,channel)
    assert len(links)==9
    source=archive_sources(job,[{'url':parent,'title':'隔离目录','body':body}],'网页正文',channel)[0]
    name='深圳隔离灯具公司8'
    cached=archive_sources(uuid.uuid4().hex,[{'url':links[-1],'title':name,'body':name+'隔离页面正文，不作真实客户证明。'*20}],'网页正文',channel)[0]
    lead_key=identifier()
    with Session.begin() as db:
        row=db.get(Job,job);row.status='running';row.lead_ids=[lead_key] if full else []
        if full:db.add(Lead(id=lead_key,display_name=name,city='深圳',buyer_role='dealer',facts={},evidence=[{'field':'name','value':name,'source_id':cached['id'],'url':cached['url']}]))
        else:
            for url in links[:8]:db.add(ToolCall(job_id=job,operation_id=uuid.uuid4().hex,tool='fetch_source',channel=channel,status='completed',arguments={'url':url,'channel':channel},attempts=1,result={'sources':[]}))
    state={'job_id':job,'profile':profile,'options':options,'saved_ids':[lead_key] if full else [],'source_ids':[source['id']],
        'steps':[{'channel':channel,'query':'隔离查询'}],'cursor':0,'reference_urls':[],'warnings':['provider_rate_limited'],'prompt':'找深圳灯具经销商'}
    update=asyncio.run(agent.gap_node(state))
    assert update['direct_read_target']=={'url':links[-1],'channel':channel}
    output=asyncio.run(agent.read_node({**state,**update}))
    assert output['recent_read_source_ids']==[cached['id']]
    with Session() as db:
        count=sum(row.attempts for row in db.query(ToolCall).filter(ToolCall.job_id==job,ToolCall.tool=='fetch_source'))
        assert count==options['max_reads']
