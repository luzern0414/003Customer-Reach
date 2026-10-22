"""目录路径不是纯导航证明；只扩大真实正文分析，不放宽任何客户保存资格。"""
import asyncio
import uuid
import pytest
from app.industry_navigation import navigation_only,NAVIGATION_MARKER


URL='https://shop.jc001.cn/gc-006001-r1-265/'
PROFILE={'region':'深圳','products':[{'name':'吊灯'}]}


@pytest.mark.parametrize('body,expected',[
    ('灯具企业库\n深圳\n批发商\n深圳隔离照明有限公司',True),
    ('企业目录说明。'*100,True),
    ('深圳隔离照明有限公司是一家从事照明灯具批发经营的企业。',False),
    ('深圳隔离照明有限公司专业生产LED灯具并提供照明安装服务。',False),
    ('深圳隔离照明有限公司位于深圳市，主要产品为室内照明灯具。',False),
    ('目录入口\n'+NAVIGATION_MARKER+'\n目录入口：深圳隔离照明有限公司是一家从事照明灯具批发经营的企业。\n目录链接：https://shop.jc001.cn/1/',True)])
def test_directory_content_gate_does_not_treat_navigation_as_facts(body,expected):
    """body为测试原正文、expected为是否纯导航；介绍只决定分析资格，不证明买家或照明产品匹配。"""
    assert navigation_only(URL,body)==expected
    assert not navigation_only('https://example.org/unknown-directory',body)


def test_actual_extract_save_analyzes_directory_and_drops_pure_navigation_context(client,monkeypatch):
    """client为隔离API、monkeypatch替模型；真实图提取与保存保留多主体校验，不请求公网或模型。"""
    from app import agent
    from app.db import Session,Conversation,Job,identifier
    from app.gateway import archive_sources
    from app.schemas import Candidate,CandidateBatch,Fact
    from app.service import submit,save_settings,checked_candidate,ServiceError
    options=save_settings({'enabled_channels':['industry_directory'],'max_leads':1})
    conversation=identifier()
    with Session.begin() as db:db.add(Conversation(id=conversation,title='隔离目录正文验证'))
    job=submit(conversation,{'content':'自主找深圳灯具经销商','attachment_ids':[],'client_token':uuid.uuid4().hex})
    with Session.begin() as db:db.get(Job,job['id']).status='running'
    name='深圳隔离照明有限公司'
    role_quote=name+'是一家从事照明灯具批发经营的企业。'
    body=role_quote+'\n地址：深圳市隔离测试地址\n'+('隔离验证的产品资料说明。'*20)
    directory=archive_sources(job['id'],[{'url':URL,'title':'深圳灯具企业库','body':body}],'网页正文','industry_directory')[0]
    pure=archive_sources(job['id'],[{'url':'https://www.jc001.cn/','title':'九正建材网','body':'目录说明及导航文字。'*30}],'网页正文','industry_directory')[0]
    observed=[]
    async def model(state,result_type,prompt,label):
        """state/result_type/prompt/label为真实提取请求；只返回测试候选并检查纯导航不占模型上下文。"""
        observed.append(prompt)
        assert '目录说明及导航文字。' not in prompt
        assert role_quote in prompt
        return CandidateBatch(candidates=[Candidate(display_name=name,city='深圳',buyer_role='dealer',match_reason='隔离目录验证',
            facts=[Fact(field='name',value=name,quote=name,source_id='S1'),
                Fact(field='buyer_role',value='批发',quote=role_quote,source_id='S1')])])
    monkeypatch.setattr(agent,'cached_model',model)
    state={'job_id':job['id'],'profile':PROFILE,'options':options,'source_ids':[directory['id'],pure['id']],
        'recent_read_source_ids':[directory['id'],pure['id']],'saved_ids':[],'prompt':'自主找深圳灯具经销商',
        'cursor':0,'plan':{'target_roles':['dealer']}}
    extracted=asyncio.run(agent.extract_node(state))
    assert len(observed)==1 and extracted['candidates'][0]['facts'][0]['source_id']==directory['id']
    saved=asyncio.run(agent.save_node({**state,**extracted}))
    assert len(saved['saved_ids'])==1
    # 目录中其他主体的业务不能拼给原公司；可分析正文不代表角色自动成立。
    other='深圳其他隔离贸易有限公司经营照明灯具批发业务。'
    row={**directory,'body':body+'\n'+other}
    bad=Candidate.model_validate(extracted['candidates'][0]).model_copy(update={'facts':[
        Fact(field='name',value=name,quote=name,source_id=directory['id']),
        Fact(field='buyer_role',value='批发',quote=other,source_id=directory['id'])]})
    with pytest.raises(ServiceError,match='角色原文没有'):
        checked_candidate(bad,{directory['id']:row})


def test_empty_search_and_no_new_read_does_not_reanalyze_all_old_evidence(client,monkeypatch):
    """client为隔离API、monkeypatch禁止模型；实际read→extract无新搜索资料时不重分析旧主体，原Evidence保留。"""
    from app import agent
    from app.gateway import archive_sources
    old=archive_sources(uuid.uuid4().hex,[{'url':'https://example.org/'+uuid.uuid4().hex,'title':'隔离旧公司',
        'body':'深圳隔离照明有限公司是一家从事照明灯具批发经营的企业。'*20}],'网页正文','official')[0]
    state={'job_id':uuid.uuid4().hex,'profile':PROFILE,'options':{'enabled_channels':['official'],'max_reads':2,'max_leads':1},
        'source_ids':[old['id']],'recent_read_source_ids':[old['id']],'attempts':[{'channel':'official','source_ids':[]}],
        'steps':[{'channel':'official'}],'cursor':0,'saved_ids':[],'reference_urls':[],
        'plan':{'target_roles':['dealer']},'prompt':'自主找深圳灯具经销商'}
    async def forbidden(*args,**kwargs):
        """args/kwargs为模型请求（均不应出现）；调用即表明空检索误分析旧资料。"""
        raise AssertionError('空检索不能重新分析旧资料')
    monkeypatch.setattr(agent,'cached_model',forbidden)
    read=asyncio.run(agent.read_node(state))
    assert read['read_empty'] and read['source_ids']==[old['id']]
    assert asyncio.run(agent.extract_node({**state,**read}))['candidates']==[]


@pytest.mark.parametrize('failure',['sdk','generic','budget'])
def test_extract_sdk_timeout_skips_page_without_caching_it_or_downgrading_budget(client,monkeypatch,failure):
    """client隔离DB、monkeypatch仅故障注入、failure为SDK/通用超时/预算；仅确认SDK超时继续，原预算与缓存规则不变。"""
    import httpx
    from openai import APITimeoutError
    from sqlalchemy import select
    from app import agent
    from app.db import Session,JobEvent
    from app.gateway import archive_sources
    from app.schemas import CandidateBatch
    from app.service import ServiceError
    key=uuid.uuid4().hex
    row=archive_sources(key,[{'url':URL,'title':'隔离目录','body':'深圳隔离照明有限公司是一家从事照明灯具批发经营的企业。'*20}],'网页正文','industry_directory')[0]
    state={'job_id':key,'profile':PROFILE,'options':{'enabled_channels':['industry_directory'],'max_leads':1},
        'source_ids':[row['id']],'recent_read_source_ids':[row['id']],'saved_ids':[],
        'plan':{'target_roles':['dealer']},'prompt':'自主找深圳灯具经销商','cursor':0}
    calls=[]
    async def failing(*args,**kwargs):
        """args/kwargs为真实节点模型入参；仅注入错误，不发送外部请求或改预算。"""
        calls.append(1)
        if failure=='sdk':raise APITimeoutError(request=httpx.Request('POST','https://example.org/model-fixture'))
        if failure=='generic':raise TimeoutError('隔离通用超时')
        raise ServiceError('任务模型预算已耗尽')
    monkeypatch.setattr(agent,'cached_model',failing)
    if failure!='sdk':
        with pytest.raises(TimeoutError if failure=='generic' else ServiceError):asyncio.run(agent.extract_node(state))
        return
    output=asyncio.run(agent.extract_node(state))
    assert output['candidates']==[] and output['warnings']==['extract_model_timeout']
    assert 'extraction_hashes' not in output
    with Session() as db:
        event=db.scalar(select(JobEvent).where(JobEvent.job_id==key,JobEvent.event_type=='extract.partial'))
        assert event.payload['error']=='APITimeoutError' and event.payload['parsed_count']==0
    async def success(*args,**kwargs):
        """args/kwargs为随后复核同原文请求；未完成签名必须再次进入分析，不使用失败缓存。"""
        calls.append(1);return CandidateBatch(candidates=[])
    monkeypatch.setattr(agent,'cached_model',success)
    verified=asyncio.run(agent.extract_node({**state,**output}))
    assert len(calls)==2 and verified['extraction_hashes']
