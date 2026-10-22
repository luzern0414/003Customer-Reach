"""同名商户不同分店不可串号，原修复器换name来源也不能越过分店绑定。"""
import asyncio
import uuid
import pytest


def fixtures(client):
    """client为隔离API；返回同名两分店的连续原文与候选，只用于本地校验。"""
    from app.db import Session,Job
    from app.gateway import archive_sources
    from app.schemas import Candidate,Fact
    conv=client.post('/api/conversations').json()['id']
    job=client.post('/api/conversations/'+conv+'/messages',json={'content':'找深圳灯具零售商','client_token':uuid.uuid4().hex}).json()['id']
    with Session.begin() as db:db.get(Job,job).status='running'
    name='隔离同名灯饰';rows=[];candidates=[]
    for number,phone in [('91','13169928365'),('92','13794469638')]:
        heading='隔离'+number+'店 入驻品牌';record=name+'\nTel: '+phone
        body='作为隔离商场在深圳的布点。\n了解更多\n'+heading+'\n灯饰\n'+record
        row=archive_sources(job,[{'url':'http://www.leanju.com:8080/subbranch-detail/i-'+number+'.html',
            'title':'合成商场','body':body}],'网页正文','mall_directory')[0]
        rows.append(row)
        candidates.append(Candidate(display_name=name,city='深圳',buyer_role='retailer',match_reason='合成分店边界',facts=[
            Fact(field='name',value=name,quote=record,source_id=row['id']),Fact(field='buyer_role',value='入驻品牌',quote=heading,source_id=row['id']),
            Fact(field='phone',value=phone,quote=record,source_id=row['id'])]))
    return job,{row['id']:row for row in rows},candidates


def test_split_branch_names_and_contact_source_cannot_be_spliced(client):
    """client隔离库；旧店name搭新店phone或同批两分店name均拒绝，不借修复名称把电话错误合并。"""
    from app.service import checked_candidate,ServiceError
    job,rows,candidates=fixtures(client)
    wrong=candidates[0].model_copy(update={'facts':[candidates[0].facts[0],candidates[0].facts[1],candidates[1].facts[2]]})
    with pytest.raises(ServiceError,match='分店证据不一致'):checked_candidate(wrong,rows)
    two=candidates[0].model_copy(update={'facts':[*candidates[0].facts,candidates[1].facts[0]]})
    with pytest.raises(ServiceError,match='分店证据不一致'):checked_candidate(two,rows)


def test_same_name_different_branch_keeps_two_records_and_phone_values(client):
    """client隔离库；真实save生成两个门店ID，同分店补查仍复用原ID，不把不同号码标同店争议。"""
    from app.service import save_candidate
    from app.db import Session,Lead
    job,rows,candidates=fixtures(client)
    first=save_candidate(candidates[0],rows,job);second=save_candidate(candidates[1],rows,job)
    assert first['id']!=second['id']
    assert save_candidate(candidates[0],rows,job)['id']==first['id']
    with Session() as db:
        assert db.get(Lead,first['id']).facts['phone']['value']=='13169928365'
        assert db.get(Lead,second['id']).facts['phone']['value']=='13794469638'
        assert db.get(Lead,first['id']).facts['phone']['verification']!='disputed'


def test_full_quota_cannot_add_another_branch_using_same_name(client):
    """client隔离库；真实Broker在满额时不同分店拒绝，同分店补全仍允许，不能只凭同名占原记录。"""
    from app.research_tools import ToolBroker
    from app.service import save_candidate
    from app.db import Session,Job
    job,rows,candidates=fixtures(client);first=save_candidate(candidates[0],rows,job)
    with Session.begin() as db:db.get(Job,job).lead_ids=[first['id']]
    broker=ToolBroker(job,{'max_leads':1,'enabled_channels':['mall_directory']},{'region':'深圳','products':[{'name':'吊灯'}]})
    broker.allowed_sources.update(rows)
    denied=asyncio.run(broker.execute('persist_lead',{'candidate':candidates[1].model_dump()}))
    assert denied['error']=='branch_identity_conflict'
    assert asyncio.run(broker.execute('persist_lead',{'candidate':candidates[0].model_dump()}))['id']==first['id']


def test_archived_legacy_branch_is_not_recreated_after_fingerprint_upgrade(client):
    """client隔离库；旧指纹归档记录仍由原分店证据识别，策略升级不能产生新ID复活。"""
    from app.db import Session,Lead,identifier
    from app.service import save_candidate,ServiceError
    job,rows,candidates=fixtures(client);row=next(iter(rows.values()))
    with Session.begin() as db:db.add(Lead(id=identifier(),display_name=candidates[0].display_name,city='深圳',dedupe_key=uuid.uuid4().hex,
        archived=True,evidence=[{'field':'name','url':row['url']}]))
    with pytest.raises(ServiceError,match='已归档'):save_candidate(candidates[0],rows,job)


def market_fixture(client):
    """client隔离API；返回两根域同原市场名/地址，城市两种行政写法，不代表真实客户。"""
    from app.gateway import archive_sources
    from app.schemas import Candidate,Fact
    conv=client.post('/api/conversations').json()['id']
    job=client.post('/api/conversations/'+conv+'/messages',json={'content':'找深圳灯饰市场','client_token':uuid.uuid4().hex}).json()['id']
    name='深圳隔离行政后缀灯饰城';address='广东深圳市福田区'
    rows=archive_sources(job,[{'url':'https://example.'+host+'/fixture/'+uuid.uuid4().hex,'title':name,
        'body':name+'\n市场类型：灯具市场\n地址：'+address} for host in ['org','net']],'网页正文','mall_directory')
    candidates=[Candidate(display_name=name,city=city,buyer_role='mall',match_reason='隔离去重验证',facts=[
        Fact(field='name',value=name,quote=name,source_id=row['id']),
        Fact(field='buyer_role',value='灯具市场',quote='市场类型：灯具市场',source_id=row['id']),
        Fact(field='address',value=address,quote='地址：'+address,source_id=row['id'])]) for row,city in zip(rows,['深圳市','深圳'])]
    return job,{row['id']:row for row in rows},candidates


def test_city_suffix_dedupe_preserves_original_city_and_cross_site_evidence(client):
    """client隔离库；实际save/Broker两城市写法复用ID，满额仍能补第二站，原城市和来源保持。"""
    from app.service import save_candidate
    from app.db import Session,Job,Lead
    from app.research_tools import ToolBroker
    job,rows,candidates=market_fixture(client)
    first=save_candidate(candidates[0],rows,job)
    with Session.begin() as db:db.get(Job,job).lead_ids=[first['id']]
    broker=ToolBroker(job,{'max_leads':1,'enabled_channels':['mall_directory']},{'region':'深圳','products':[{'name':'吊灯'}]})
    broker.allowed_sources.update(rows)
    second=asyncio.run(broker.execute('persist_lead',{'candidate':candidates[1].model_dump()}))
    assert second['id']==first['id']
    with Session() as db:
        lead=db.get(Lead,first['id'])
        assert lead.city=='深圳市' and len({item['url'] for item in lead.evidence})==2
        assert db.query(Lead).filter(Lead.display_name==candidates[0].display_name).count()==1


def test_city_suffix_cannot_revive_archived_market_with_legacy_fingerprint(client):
    """client隔离库；旧城市后缀及旧指纹归档记录仍拒新自动保存，不清原事实。"""
    from app.db import Session,Lead
    from app.service import save_candidate,ServiceError
    job,rows,candidates=market_fixture(client)
    first=save_candidate(candidates[0],rows,job)
    with Session.begin() as db:
        lead=db.get(Lead,first['id']);lead.archived=True;lead.dedupe_key=uuid.uuid4().hex
    with pytest.raises(ServiceError,match='已归档'):save_candidate(candidates[1],rows,job)
