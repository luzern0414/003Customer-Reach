"""指定页复核不得因资料缺口发额外搜索或导航；真实公网另由项目Agent验证。"""
import asyncio
import uuid


def test_explicit_scope_does_not_limit_open_discovery():
    """只限制有链接且当前明确限页的消息；开放跨渠道找客户保持原行为。"""
    from app.source_scope import reference_only
    refs=[{'url':'https://example.org/review','channel':'official'}]
    assert reference_only('仅复核这个已读取的公开页面',refs)
    assert reference_only('不得搜索其他页面',refs)
    assert reference_only('仅复核此已读取目录，不要搜索，不读取其他网页，不沿外链。',refs)
    assert reference_only('只复核以下4个页面与成都宏天智电子有限公司的相关信息，不扩展搜索：https://example.org/review',refs)
    assert reference_only('不读取其他网页',refs)
    assert not reference_only('先查这个页面，再通过其他渠道补查',refs)
    assert not reference_only('不要搜索其他页面',[])


def test_explicit_page_review_then_explanation_still_fetches():
    """明确网页复核授权不被后续“解释”抢路由；解释/翻译指令本身不授权网络读取。"""
    from app.conversation import mode
    assert mode('我们销售灯具。仅复核以下页面：https://example.org/a 。解释未通过的原因，不得搜索其他页面。')=='research'
    assert mode('请解释这句话：仅复核以下页面 https://example.org/a')=='chat'
    assert mode('翻译：仅复核以下页面 https://example.org/a')=='chat'


def test_reference_read_and_gap_do_not_expand(client,monkeypatch):
    """真实read/gap与隔离账本：只执行未读指定页，失败亦终止，不跟门户或搜索摘录。"""
    from app.agent import read_node,gap_node
    from app.db import Session,Conversation,Job,identifier
    from app.service import submit,save_settings
    from app.research_tools import ToolBroker
    options=save_settings({'enabled_channels':['official'],'max_reads':4,'max_leads':1})
    conv=identifier()
    with Session.begin() as db:db.add(Conversation(id=conv,title='隔离限页复核'))
    job=submit(conv,{'content':'我们销售灯具，仅复核这个页面 https://example.org/review','attachment_ids':[],'client_token':uuid.uuid4().hex})
    with Session.begin() as db:db.get(Job,job['id']).status='running'
    refs=[{'url':'https://example.org/review','channel':'official'}]
    state={'job_id':job['id'],'prompt':'仅复核这个页面','profile':{'region':'深圳','products':[{'name':'灯具'}]},'options':options,
        'reference_only':True,'reference_urls':refs,'steps':[{'channel':'official','query':'指定页'}],'cursor':0,
        'source_ids':[],'saved_ids':[],'attempts':[],'plan':{'target_roles':['retailer']}}
    seen=[]
    async def fetch(self,name,args):
        """只记录实际选择参数，模拟受限以检验缺口不能扩大范围。"""
        seen.append((name,args));return {'sources':[],'error':'site_access_restricted'}
    monkeypatch.setattr(ToolBroker,'execute',fetch)
    pending=asyncio.run(gap_node(state))
    assert pending['direct_read_pending']
    read=asyncio.run(read_node({**state,**pending}))
    assert seen==[('fetch_source',refs[0])]
    done=asyncio.run(gap_node({**state,**pending,**read}))
    assert not done['direct_read_pending'] and done['cursor']==len(state['steps'])
    disabled=asyncio.run(gap_node({**state,'reference_urls':[{**refs[0],'channel':'qcc_public'}]}))
    assert not disabled['direct_read_pending']


def test_evidence_repair_keeps_original_product_match(client,monkeypatch):
    """真实save/persist：修复引文时模型不能改产品列表，原产品仍经服务校验。"""
    from app import agent
    from app.db import Session,Conversation,Job,Lead,identifier
    from app.gateway import archive_sources
    from app.service import submit,save_settings
    from app.schemas import Candidate
    options=save_settings({'enabled_channels':['official'],'max_leads':1})
    conv=identifier()
    with Session.begin() as db:db.add(Conversation(id=conv,title='隔离修复产品范围'))
    job=submit(conv,{'content':'我们销售吊灯，找深圳零售门店','attachment_ids':[],'client_token':uuid.uuid4().hex})
    with Session.begin() as db:db.get(Job,job['id']).status='running'
    name='隔离灯饰店'+uuid.uuid4().hex[:6]
    body=name+'在深圳零售灯具。地址：深圳隔离路1号。'
    source=archive_sources(job['id'],[{'url':'https://example.org/'+uuid.uuid4().hex,'title':name,'body':body}],'网页正文','official')[0]
    good=Candidate(display_name=name,city='深圳',buyer_role='retailer',match_reason='原文零售，产品待核',matched_products=['吊灯'],
        facts=[{'field':field,'value':value,'quote':body,'source_id':source['id']} for field,value in [('name',name),('buyer_role','零售'),('address','深圳隔离路1号')]])
    bad=good.model_copy(deep=True)
    bad.facts[-1].quote='不在网页中的地址：深圳隔离路1号'
    async def repair(*args,**kwargs):return good.model_copy(update={'matched_products':['模型新增产品']})
    monkeypatch.setattr(agent,'cached_model',repair)
    state={'job_id':job['id'],'prompt':'找深圳零售门店','profile':{'region':'深圳','products':[{'name':'吊灯'}]},
        'options':options,'source_ids':[source['id']],'saved_ids':[],'candidates':[bad.model_dump()],
        'plan':{'target_roles':['retailer']},'cursor':0}
    result=asyncio.run(agent.save_node(state))
    assert len(result['saved_ids'])==1
    with Session() as db:assert db.get(Lead,result['saved_ids'][0]).matched_products==['吊灯']
