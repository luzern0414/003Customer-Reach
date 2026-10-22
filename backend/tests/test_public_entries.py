"""没有用户URL、检索无结果时仍可按ICP读取公开目录，不制造证据或绕过关闭渠道。"""
import uuid
import asyncio
import pytest
from app.source_catalog import public_entries
from app.evidence_context import evidence_excerpt


def test_entries_follow_region_product_and_enabled_channel():
    """目录是范围受限的读取入口，成都/非灯具/关闭渠道不误送深圳灯饰名单。"""
    profile={'region':'深圳','products':[{'name':'LED筒灯'}]}
    assert public_entries(profile,['mall_directory'],'mall_directory')
    assert not public_entries(profile,['official'],'mall_directory')
    assert not public_entries({**profile,'region':'成都'},['mall_directory'])
    assert not public_entries({**profile,'products':[{'name':'办公软件'}]},['mall_directory'])
    assert all(x['channel']=='directory' for x in public_entries(profile,['directory'],'directory'))
    assert not public_entries(profile,['qcc_public'],'qcc_public')
    assert public_entries(profile,['ccgp'],'ccgp')
    assert not any('ccgp.gov.cn' in x['url'] for x in public_entries(profile,['directory'],'directory'))


def test_new_discovery_keeps_lighting_section_without_known_customer():
    """首次找门店没有name锚点，也必须保留目录实际中段的灯饰记录。"""
    body='沙井店 入驻品牌\n介绍\n'+('厨电\n无关电器\nTel: 12345678\n'*180)+'灯饰\n隔离灯饰\nTel: 13169928365\n'+('家具\n沙发\n'*150)
    excerpt=evidence_excerpt(body,[],3500)
    assert '灯饰\n隔离灯饰\nTel: 13169928365' in excerpt


def test_fallback_entry_roles_do_not_replace_explicit_procurement_or_user_permission():
    """角色只筛自动目录兜底，不把未知来源硬拒，不撤销选定采购步骤或Broker原许可。"""
    profile={'region':'深圳','products':[{'name':'吊灯'}]}
    enabled=['mall_directory','industry_directory','brand_directory','ccgp']
    markets=public_entries(profile,enabled,roles=['mall'])
    assert markets and all(entry['channel'] not in {'ccgp','brand_directory'} for entry in markets)
    assert any(entry['channel']=='industry_directory' for entry in markets)
    retailers=public_entries(profile,enabled,roles=['retailer'])
    assert any(entry['channel']=='brand_directory' for entry in retailers) and not any(entry['channel']=='ccgp' for entry in retailers)
    assert public_entries(profile,enabled,'ccgp',['mall'])
    assert any(entry['channel']=='ccgp' for entry in public_entries(profile,enabled,roles=['project_buyer']))


def test_limited_market_fallback_does_not_spend_read_budget_on_procurement_and_retail_entries(client):
    """client隔离库；所有适用入口已试时结束，不改读公告或零售网点凑市场线索。"""
    from app.agent import gap_node
    from app.service import save_settings
    profile={'region':'深圳','products':[{'name':'吊灯'}]}
    options=save_settings({'enabled_channels':['mall_directory','brand_directory','ccgp'],'max_reads':12})
    attempted=[entry['url'] for entry in public_entries(profile,options['enabled_channels'],roles=['mall'])]
    state={'job_id':uuid.uuid4().hex,'cursor':0,'steps':[{'channel':'mall_directory'}],
        'options':options,'profile':profile,'plan':{'target_roles':['mall']},'warnings':['provider_rate_limited'],
        'saved_ids':[],'attempts':[],'source_ids':[],'prompt':'寻找深圳灯饰市场运营方',
        'reference_urls':[],'read_attempted_urls':attempted}
    result=asyncio.run(gap_node(state))
    assert not result['direct_read_pending'] and result['cursor']==len(result['steps'])


def test_search_limit_routes_to_unread_public_directory(client):
    """隔离库验证限流不封锁目录；已读入口和零预算不得导致无限回路。"""
    from app.agent import gap_node
    from app.service import save_settings
    options=save_settings({'enabled_channels':['b2b_1688','mall_directory'],'max_reads':2})
    state={'job_id':uuid.uuid4().hex,'cursor':0,'steps':[{'channel':'b2b_1688'}],
        'options':options,'profile':{'region':'深圳','products':[{'name':'LED吊灯'}]},
        'warnings':['provider_rate_limited'],'saved_ids':[],'attempts':[{'channel':'b2b_1688'}],
        'prompt':'自主找深圳灯具零售买家','reference_urls':[]}
    result=asyncio.run(gap_node(state))
    assert result['direct_read_pending']
    assert result['steps'][result['cursor']]['channel']=='mall_directory'
    used=[entry['url'] for entry in public_entries(state['profile'],options['enabled_channels'])]
    assert not asyncio.run(gap_node({**state,'read_attempted_urls':used}))['direct_read_pending']
    assert not asyncio.run(gap_node({**state,'options':{**options,'max_reads':0}}))['direct_read_pending']


def test_saved_customer_does_not_block_directory_fallback(client,monkeypatch):
    """已有客户未达数量时继续未读目录；实际read选链，无外部成功替身。"""
    from app.agent import gap_node,read_node
    from app.db import Session,Lead,Conversation,identifier
    from app.service import submit,save_settings
    from app.research_tools import ToolBroker
    from app.gateway import archive_sources
    profile={'region':'深圳','products':[{'name':'LED吊灯'}]}
    options=save_settings({'enabled_channels':['mall_directory'],'max_reads':3,'max_leads':2})
    conversation=identifier();lead=identifier()
    with Session.begin() as db:
        db.add(Conversation(id=conversation,title='隔离已有客户目录补查'))
        db.add(Lead(id=lead,display_name='隔离已有门店',city='深圳',dedupe_key=uuid.uuid4().hex))
    job=submit(conversation,{'content':'找深圳灯饰零售门店','attachment_ids':[],'client_token':uuid.uuid4().hex})
    source=archive_sources(job['id'],[{'url':'https://example.org/'+job['id'],'title':'隔离目录','body':'隔离目录验证内容。'*50}],'网页正文','mall_directory')[0]
    state={'job_id':job['id'],'cursor':0,'steps':[{'channel':'mall_directory'}],
        'options':options,'profile':profile,'warnings':['provider_rate_limited'],'saved_ids':[lead],
        'attempts':[],'source_ids':[source['id']],'prompt':'找深圳灯饰零售门店','reference_urls':[]}
    update=asyncio.run(gap_node(state));assert update['direct_read_pending']
    seen=[]
    async def execute(self,name,args):
        """仅记录图选取的URL；返回无来源，不冒充真实HTTP成功。"""
        assert name=='fetch_source';seen.append(args);return {'sources':[]}
    monkeypatch.setattr(ToolBroker,'execute',execute)
    result=asyncio.run(read_node({**state,**update}))
    assert len(seen)==1 and seen[0]['url'] in {item['url'] for item in public_entries(profile,options['enabled_channels'])}
    assert seen[0]['url'] in result['read_attempted_urls']


def test_graph_reads_registered_entry_without_search_or_user_link(client,monkeypatch):
    """client为隔离库；mock只断网，真实图read与Broker校验运行，读取前Evidence不存在、预算0不读。"""
    from app.db import Session,Conversation,Job,Evidence,identifier
    from app.service import submit,save_settings,ServiceError
    from app.research_tools import ToolBroker
    from app.agent import read_node
    profile={'region':'深圳','products':[{'name':'LED筒灯'}]}
    options=save_settings({'enabled_channels':['mall_directory'],'max_reads':2})
    conversation=identifier()
    with Session.begin() as db:db.add(Conversation(id=conversation,title='隔离自主入口验证'))
    job=submit(conversation,{'content':'找深圳灯饰零售门店','attachment_ids':[],'client_token':uuid.uuid4().hex})
    with Session.begin() as db:db.get(Job,job['id']).status='running'
    seen=[]
    real_fetch=ToolBroker.fetch
    async def fetch(self,args):
        """self为实际Broker，args为图选择入口；断网代替返回空来源，不能伪造真实外部成功。"""
        assert args['url'] in self.reference_urls
        seen.append(args)
        return {'sources':[]}
    monkeypatch.setattr(ToolBroker,'fetch',fetch)
    state={'job_id':job['id'],'options':options,'profile':profile,'steps':[{'channel':'mall_directory'}],
        'cursor':0,'attempts':[{'error':'provider_rate_limited','source_ids':[]}],'source_ids':[],
        'reference_urls':[],'saved_ids':[],'plan':{'target_roles':['retailer']}}
    with Session() as db:assert db.query(Evidence).filter(Evidence.job_id==job['id']).count()==0
    asyncio.run(read_node(state))
    assert seen and all(item['channel']=='mall_directory' for item in seen)
    with Session() as db:assert db.query(Evidence).filter(Evidence.job_id==job['id']).count()==0
    seen.clear()
    asyncio.run(read_node({**state,'options':{**options,'max_reads':0}}))
    assert not seen
    broker=ToolBroker(job['id'],options,profile)
    with pytest.raises(ServiceError,match='url_not_discovered'):
        # 还原实际fetch的前置读取许可，只测试未知入口，不向外网发送请求。
        asyncio.run(real_fetch(broker,{'url':'https://example.org/unregistered','channel':'mall_directory'}))
