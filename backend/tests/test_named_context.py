"""明确续查复用该客户已存来源；不把新发现、排除语句或限页任务扩大为旧客户研究。"""
import asyncio
import uuid
import pytest


@pytest.mark.parametrize('mode',['followup','discovery','denied','reference','seller','disputed','extended_name'])
def test_named_followup_loads_only_owned_sources_and_respects_scope(client,monkeypatch,mode):
    """client隔离API、monkeypatch禁规划模型，mode为当前授权边界；执行真实context/plan/DB。"""
    from app import agent
    from app.db import Session,Job,Lead,identifier,Conversation
    from app.service import save_settings
    from app.gateway import archive_sources
    options=save_settings({'enabled_channels':['industry_directory'],'max_leads':1})
    conv=client.post('/api/conversations').json()['id']
    name='深圳隔离续查照明有限公司'+uuid.uuid4().hex[:6]
    with Session.begin() as db:db.get(Conversation,conv).profile={'products':[{'name':'吊灯'}],'region':'深圳','company_name':name if mode=='seller' else None}
    prompt='补查已保存客户'+name+'的公开联系方式'
    if mode=='discovery':prompt='我们销售吊灯，寻找深圳经销商，排除'+name
    if mode=='denied':prompt='不要补查'+name+'的公开联系方式'
    if mode=='reference':prompt='仅复核这个页面 http://shop.jc001.cn/9146/ 的'+name+'资料'
    if mode=='extended_name':prompt='补查'+name+'制造集团的公开联系方式'
    job=client.post('/api/conversations/'+conv+'/messages',json={'content':prompt,'client_token':uuid.uuid4().hex}).json()['id']
    body=name+'经销灯具。\n[公开目录导航，仅用于发现页面，不是客户事实]\n目录入口：联系方式\n目录链接：http://shop.jc001.cn/9146/contact.html'
    source=archive_sources(job,[{'url':'http://shop.jc001.cn/9146/','title':name,'body':body}],'网页正文','industry_directory')[0]
    other=archive_sources(job,[{'url':'https://example.org/unreferenced','title':'其他页面','body':'非客户实际引文来源。'*30}],'网页正文','industry_directory')[0]
    key=identifier()
    with Session.begin() as db:db.add(Lead(id=key,display_name=name,buyer_role='dealer',city='深圳',dedupe_key=uuid.uuid4().hex,
        facts={'name':{'value':name,'verification':'disputed' if mode=='disputed' else '原文匹配'}},
        evidence=[{'field':'name','value':name,'source_id':source['id'],'url':source['url']}]))
    state={'job_id':job,'conversation_id':conv,'intent':'research','prompt':prompt,'options':options,'metrics':{},'saved_ids':[],'source_ids':[]}
    loaded=asyncio.run(agent.load_context(state))
    with Session() as db:saved_ids=db.get(Job,job).lead_ids
    if mode=='followup':
        assert loaded['saved_ids']==[key] and saved_ids==[key] and loaded['source_ids']==[source['id']]
        assert other['id'] not in loaded['source_ids']
        async def forbidden(*args,**kwargs):raise AssertionError('明确既有主体不应重复规划模型')
        monkeypatch.setattr(agent,'cached_model',forbidden)
        planned=asyncio.run(agent.plan_node({**state,**loaded}))
        assert planned['direct_read_pending'] and planned['metrics']['plan_reused']
    else:
        assert not loaded['saved_ids'] and not loaded['source_ids'] and not saved_ids
