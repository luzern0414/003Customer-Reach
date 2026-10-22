"""实际read节点只按检索信号优先读页，排序不产生客户事实。"""
import asyncio
import uuid
import pytest


@pytest.mark.parametrize('role,title,body',[
    ('dealer','深圳隔离灯具经销商','公开业务邮箱 sales@example.org'),
    ('retailer','深圳隔离零售门店','公开业务电话0755-23004025'),
    ('mall','深圳隔离灯饰城','入驻商户名录'),
    ('manufacturer','深圳隔离灯饰厂','生产加工灯具')])
def test_read_priority_includes_title_region_and_target_role(client,monkeypatch,role,title,body):
    """四种目标在1页预算内优先对应标题；client隔离库、monkeypatch替网络，其他参数是合成检索信号。"""
    from app import agent
    from app.gateway import archive_sources
    from app.research_tools import ToolBroker
    conv=client.post('/api/conversations').json()['id']
    job=client.post('/api/conversations/'+conv+'/messages',json={'content':'找深圳灯具客户','client_token':uuid.uuid4().hex}).json()['id']
    sources=archive_sources(job,[
        {'url':'https://example.org/generic','title':'泛照明资料','body':'照明服务介绍'},
        {'url':'https://example.org/foreign','title':title.replace('深圳','外地'),'body':'角色资料，没有目标地区'},
        {'url':'https://example.org/local','title':title,'body':body}], '搜索摘录','industry_directory')
    seen=[]
    async def execute(self,name,args):seen.append((name,args));return {'sources':[]}
    monkeypatch.setattr(ToolBroker,'execute',execute)
    state={'job_id':job,'profile':{'region':'深圳','products':[{'name':'灯具'}]},'options':{'enabled_channels':['industry_directory'],'max_reads':1},
        'plan':{'target_roles':[role]},'source_ids':[item['id'] for item in sources],'saved_ids':[],
        'attempts':[{'source_ids':[item['id'] for item in sources]}],'steps':[{'channel':'industry_directory'}],'cursor':0}
    result=asyncio.run(agent.read_node(state))
    assert seen==[('fetch_source',{'url':'https://example.org/local','channel':'industry_directory'})]
    assert result['recent_read_source_ids']==[]
