"""商户地址只能来自独立记录，商场位置不能继承；本地合成原文，无网络。"""
import asyncio
import uuid
import pytest


def test_mall_address_requires_explicit_merchant_block(client):
    """client隔离库；原文总地址拒绝，明确商户Tel后地址允许，城市仍据原分店简介。"""
    from app.schemas import Candidate,Fact
    from app.service import checked_candidate,ServiceError
    name='隔离灯饰';header='隔离沙井店 入驻品牌';record=name+'\nTel: 13169928365'
    body='作为隔离商场在深圳西部的布点。\n商场地址：深圳隔离路1号\n了解更多\n'+header+'\n灯饰\n'+record
    row={'id':'s','url':'http://www.leanju.com:8080/subbranch-detail/i-91.html','title':'隔离目录',
        'kind':'网页正文','channel':'mall_directory','body':body,'captured_at':'2026-10-04 00:00:00'}
    base=Candidate(display_name=name,city='深圳',buyer_role='retailer',match_reason='合成归属',facts=[
        Fact(field='name',value=name,quote=record,source_id='s'),Fact(field='buyer_role',value='入驻品牌',quote=header,source_id='s'),
        Fact(field='phone',value='13169928365',quote=record,source_id='s')])
    wrong=base.model_copy(update={'facts':[*base.facts,Fact(field='address',value='深圳隔离路1号',quote='商场地址：深圳隔离路1号',source_id='s')]})
    with pytest.raises(ServiceError,match='不能继承商场'):checked_candidate(wrong,{'s':row})
    address='门店地址：深圳隔离路2号铺位'
    good=base.model_copy(update={'facts':[*base.facts,Fact(field='address',value='深圳隔离路2号铺位',quote=address,source_id='s')]})
    assert checked_candidate(good,{'s':{**row,'body':body+'\n'+address}})[0]['address']['value']=='深圳隔离路2号铺位'


def test_invalid_optional_address_and_website_are_omitted_then_fully_rechecked(client,monkeypatch):
    """client隔离库、monkeypatch禁模型；省已拒可选字段后仍走真实Broker验证姓名/城市/角色/电话。"""
    from app import agent
    from app.schemas import Candidate,Fact
    from app.db import Session,Job,Lead
    from app.gateway import archive_sources
    from app.service import save_settings
    name='隔离商户灯饰'+uuid.uuid4().hex[:6];header='隔离沙井店 入驻品牌';record=name+'\nTel: 13169928365'
    body='作为隔离商场在深圳西部的布点。\n商场地址：深圳隔离路1号\n网站：http://\n了解更多\n'+header+'\n灯饰\n'+record
    conv=client.post('/api/conversations').json()['id']
    job=client.post('/api/conversations/'+conv+'/messages',json={'content':'找深圳零售门店','client_token':uuid.uuid4().hex}).json()['id']
    with Session.begin() as db:db.get(Job,job).status='running'
    row=archive_sources(job,[{'url':'http://www.leanju.com:8080/subbranch-detail/i-91.html','title':'合成目录','body':body}],'网页正文','mall_directory')[0]
    candidate=Candidate(display_name=name,city='深圳',buyer_role='retailer',match_reason='合成省略回归',facts=[
        Fact(field=field,value=value,quote=quote,source_id=row['id']) for field,value,quote in [
            ('name',name,record),('buyer_role','入驻品牌',header),('phone','13169928365',record),
            ('address','深圳隔离路1号','商场地址：深圳隔离路1号'),('website','http://','网站：http://')]])
    async def forbidden(*args,**kwargs):raise AssertionError('确定可选字段省略不应发新模型请求')
    monkeypatch.setattr(agent,'cached_model',forbidden)
    result=asyncio.run(agent.save_node({'job_id':job,'profile':{'region':'深圳','products':[{'name':'吊灯'}]},
        'options':save_settings({'enabled_channels':['mall_directory'],'max_leads':1}),'source_ids':[row['id']],
        'saved_ids':[],'candidates':[candidate.model_dump()],'plan':{'target_roles':['retailer']},'cursor':0}))
    assert len(result['saved_ids'])==1
    with Session() as db:
        lead=db.get(Lead,result['saved_ids'][0]);assert 'address' not in lead.facts and 'website' not in lead.facts
        assert lead.facts['phone']['value']=='13169928365'


@pytest.mark.parametrize('wrong_phone',[False,True])
def test_bad_optional_quote_does_not_discard_valid_contact_name_or_weaken_phone_guard(client,monkeypatch,wrong_phone):
    """client隔离API，monkeypatch只替一次修复模型；拒可选类别/网址后重新核验，错误电话仍不落库。"""
    from app import agent
    from app.schemas import Candidate,Fact
    from app.db import Session,Job,Lead
    from app.gateway import archive_sources
    from app.service import save_settings
    name='深圳隔离字段修复照明有限公司'+uuid.uuid4().hex[:6]
    body=name+'经销灯具。\n联系人：李先生\n网站：http://\n联系电话：0755-23004025'
    conv=client.post('/api/conversations').json()['id']
    job=client.post('/api/conversations/'+conv+'/messages',json={'content':'找深圳照明经销商','client_token':uuid.uuid4().hex}).json()['id']
    with Session.begin() as db:db.get(Job,job).status='running'
    row=archive_sources(job,[{'url':'https://example.org/'+job,'title':name,'body':body}],'网页正文','official')[0]
    facts=[Fact(field=field,value=value,quote=quote,source_id=row['id']) for field,value,quote in [
        ('name',name,name),('buyer_role','经销',name+'经销灯具。'),('contact_name','李先生','联系人：李先生'),
        ('website','http://','网站：http://'),('categories','灯具','不存在的灯具主营引用')]]
    if wrong_phone:facts.append(Fact(field='phone',value='13794469638',quote='电话：13794469638',source_id=row['id']))
    candidate=Candidate(display_name=name,city='深圳',buyer_role='dealer',facts=facts,match_reason='隔离字段降级')
    repairs=[]
    async def repair(state,schema,prompt,label):
        """参数为既有有界修复接口；外部模型未修成功，真实省略/核验路径必须处理。"""
        repairs.append(label);return candidate
    monkeypatch.setattr(agent,'cached_model',repair)
    result=asyncio.run(agent.save_node({'job_id':job,'profile':{'region':'深圳','products':[{'name':'吊灯'}]},
        'options':save_settings({'enabled_channels':['official'],'max_leads':1}),'source_ids':[row['id']],
        'saved_ids':[],'candidates':[candidate.model_dump()],'plan':{'target_roles':['dealer']},'cursor':0}))
    assert not repairs
    if wrong_phone:assert not result['saved_ids']
    else:
        with Session() as db:
            lead=db.get(Lead,result['saved_ids'][0])
            assert lead.facts['contact_name']['value']=='李先生' and 'categories' not in lead.facts and 'website' not in lead.facts
