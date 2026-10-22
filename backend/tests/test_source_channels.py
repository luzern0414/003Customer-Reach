"""来源范围、实际规划/工具、联系排序和导出回归；外部数据用明确夹具，不冒充真实平台验收。"""
import asyncio
import json
import uuid
from io import BytesIO
import pytest
from openpyxl import load_workbook
from app.source_catalog import matches_channel,source_rules,requested_channels
from app.contact_view import contact_view
from app.research_tools import ToolBroker
from app.db import Session,Lead,Evidence


@pytest.mark.parametrize('channel,url,valid',[
 ('b2b_1688','https://shop123.1688.com/page/contactinfo.htm',True),
 ('b2b_1688','https://1688.com.attacker.example/company',False),
 ('b2b_1688','https://open.1688.com/api/docs',False),
 ('qcc_public','https://www.qcc.com/firm/fixture.html',True),
 ('qcc_public','https://openapi.qcc.com/dataApi/2001',False),
 ('qcc_public','https://www.yunfale.com/company/fixture',False),
 ('ccgp','https://www.ccgp.gov.cn/cggg/fixture.htm',True),
 ('sz_procurement','https://zfcg.szggzy.com:8084/fixture.html',True),
 ('public_registry','https://amr.sz.gov.cn/fixture.html',True)])
def test_platform_scope(channel,url,valid):
    """channel/url为合成范围用例，valid为预期；不以字符串包含平台名代替实际域名。"""
    assert matches_channel(channel,url) is valid


def job(client):
    """client为隔离HTTP客户端；返回无模型的真实任务ID，仅工具测试使用。"""
    conv=client.post('/api/conversations').json()['id']
    return client.post('/api/conversations/'+conv+'/messages',json={'content':'你好','client_token':uuid.uuid4().hex}).json()['id']


def test_tool_search_cannot_mislabel_another_platform(client,monkeypatch):
    """client/monkeypatch隔离工具与外部响应；真实Broker/schema/存档链保留QCC页，排除其他域和接口文档。"""
    from app import research_tools
    requests=[]
    async def provider(name,args):
        """name/args为真实检索请求；固定外部响应供范围回归，不调用Exa或收费API。"""
        requests.append(args)
        return json.dumps({'results':[
            {'url':'https://www.qcc.com/firm/fixture.html','text':'隔离企业资料，非真实客户','title':'隔离主体'},
            {'url':'https://www.yunfale.com/company/fixture','text':'外站信息','title':'其他黄页'},
            {'url':'https://openapi.qcc.com/dataApi/2001','text':'接口文档','title':'非客户'}]})
    monkeypatch.setattr(research_tools,'call_exa',provider)
    identifier=job(client)
    broker=ToolBroker(identifier,{'enabled_channels':['qcc_public'],'max_searches':2,'max_reads':2},{})
    result=asyncio.run(broker.execute('search_accounts',{'channel':'qcc_public','query':'隔离企业 深圳'}))
    assert len(result['sources'])==1 and result['sources'][0]['channel']=='qcc_public'
    assert 'site:qcc.com' in requests[0]['query']
    wrong=asyncio.run(broker.execute('fetch_source',{'channel':'qcc_public','url':'https://www.yunfale.com/company/fixture'}))
    assert wrong['error']=='source_channel_mismatch'


def test_search_objective_uses_only_current_saved_subject_and_invalidates_old_goal_cache(client,monkeypatch):
    """client隔离库、monkeypatch仅外部搜索；目标变化需新检索，同目标复用，其他会话客户不泄漏。"""
    from app import research_tools
    from app.db import Job,identifier as new_id
    requests=[];name='隔离分店灯饰'+uuid.uuid4().hex[:8];phone='13428788412';job_id=job(client)
    async def provider(tool,args):
        """参数为实际MCP请求；返回合成来源，不伪称网络或客户验证成功。"""
        requests.append(args)
        return json.dumps({'results':[{'url':'https://example.org/'+uuid.uuid4().hex,'title':'合成资料','text':'只用于协议验证。'}]})
    monkeypatch.setattr(research_tools,'call_exa',provider)
    broker=ToolBroker(job_id,{'enabled_channels':['official'],'max_searches':4,'max_reads':0,'max_candidate_searches':4},{})
    args={'channel':'official','query':'深圳 '+name+' 原电话补查'}
    original=asyncio.run(broker.execute('search_accounts',args))
    key=new_id()
    with Session.begin() as db:
        db.add(Lead(id=key,display_name=name,city='深圳',dedupe_key=uuid.uuid4().hex,
            facts={'phone':{'value':phone,'verification':'原文匹配'}},
            evidence=[{'field':'name','url':'http://www.leanju.com:8080/subbranch-detail/i-91.html'}]))
        db.add(Lead(display_name='其他会话隔离客户',city='深圳',dedupe_key=uuid.uuid4().hex,facts={'phone':{'value':'13794469638'}}))
        db.get(Job,job_id).lead_ids=[key]
    enriched=asyncio.run(broker.execute('search_accounts',args))
    assert len(requests)==2 and name in requests[-1]['objective'] and phone in requests[-1]['objective']
    assert '其他门店' in requests[-1]['objective'] and '13794469638' not in requests[-1]['objective']
    assert enriched['search_context_hash']!=original['search_context_hash']
    assert asyncio.run(broker.execute('search_accounts',args))['reused'] and len(requests)==2
    with Session.begin() as db:db.get(Lead,key).facts={'phone':{'value':phone,'verification':'disputed'}}
    changed=asyncio.run(broker.execute('search_accounts',args))
    assert len(requests)==3 and phone not in requests[-1]['objective']
    assert changed['search_context_hash']!=enriched['search_context_hash']


def test_named_platforms_are_in_real_plan(client,monkeypatch):
    """client为隔离API，monkeypatch只替模型规划；用户指定平台必须实际进入图步骤，参考Skill实际加载。"""
    from app import agent
    from app.schemas import ResearchPlan,ResearchStep
    async def planner(state,schema,prompt,label):
        """真实规划参数必须含动态渠道及Skill；模型故意遗漏平台，验证确定性补齐。"""
        assert '掩码' in prompt and 'b2b_1688' in prompt and 'qcc_public' in prompt
        return ResearchPlan(target_roles=['dealer'],steps=[ResearchStep(channel='official',query='深圳灯具经销商',purpose='官网发现')])
    monkeypatch.setattr(agent,'cached_model',planner)
    result=asyncio.run(agent.plan_node({'prompt':'在1688和企查查找深圳灯具经销商',
        'profile':{'region':'深圳','products':[{'name':'吊灯'}]},'options':{'enabled_channels':['official','b2b_1688','qcc_public']}}))
    assert [x['channel'] for x in result['steps']][:2]==['b2b_1688','qcc_public']
    assert requested_channels('查企查查', ['official'])==[]
    guide=source_rules(['qcc_public'])
    assert 'openapi.qcc.com' in guide and 'leanju.com' not in guide


def test_contact_projection_does_not_make_incomplete_numbers_callable():
    """无入参；公开短号/掩码/失效邮箱不成为可用入口，来源和联系用途来自实际引用。"""
    result=contact_view({'phone':{'value':'81762065'},'email':{'value':'sales@example.org','verification':'inactive'}},[])
    assert result['phone_incomplete'] and not result['usable_fields'] and result['status']=='联系信息待补'
    result=contact_view({'phone':{'value':'0755-88803333','source_id':'fixture'}},[
        {'field':'phone','source_id':'fixture','url':'https://www.ccgp.gov.cn/fixture.htm','quote':'采购单位联系方式：0755-88803333','channel':'ccgp'}])
    assert result['purpose']=='采购联系' and result['sources'][0]['platform']=='中国政府采购网'


def test_contactable_buyer_priority_and_export(client):
    """client为隔离API；买家资格先于联系入口，再比分数，邮件/地址/来源与主表一致。"""
    prefix='联系排序隔离-'+uuid.uuid4().hex[:8]
    no_contact=client.post('/api/leads',json={'display_name':prefix+'A','buyer_role':'retailer'}).json()
    contact=client.post('/api/leads',json={'display_name':prefix+'B','buyer_role':'retailer','email':'sales@example.org','website':'https://example.org','contact_name':'隔离联系人','address':'深圳隔离地址'}).json()
    supplier=client.post('/api/leads',json={'display_name':prefix+'C','buyer_role':'manufacturer','phone':'0755-12345678'}).json()
    with Session.begin() as db:
        db.get(Lead,no_contact['id']).score=90
        db.get(Lead,contact['id']).score=10
        db.get(Lead,supplier['id']).score=100
    rows=client.get('/api/leads?q='+prefix).json()['items']
    assert [x['id'] for x in rows]==[contact['id'],no_contact['id'],supplier['id']]
    assert rows[0]['contact_summary']['usable_fields']==['email','website']
    book=load_workbook(BytesIO(client.get('/api/leads/export?q='+prefix).content))
    heads=[x.value for x in book['客户线索'][1]]
    values=[x.value for x in book['客户线索'][2]]
    assert values[heads.index('公开邮箱')]=='sales@example.org'
    assert values[heads.index('联系人')]=='隔离联系人' and values[heads.index('联系网站')]=='https://example.org'
    assert '渠道' in [x.value for x in book['逐字段证据'][1]]


def test_authorized_api_not_exposed_as_public_ready(client):
    """client为隔离API；公开索引能力与未配置授权API分开，不因新增开关伪装收费平台可调用。"""
    rows={x['id']:x for x in client.get('/api/channels').json()}
    assert rows['qcc_public']['mode']=='public_index'
    assert rows['company_api']['status']=='authorization_required'
    assert client.patch('/api/settings',json={'enabled_channels':['company_api']}).status_code==422


def test_city_filter_accepts_suffix_alias_without_rewriting_displayed_city(client):
    """client为隔离API；筛深圳/深圳市均命中两种原值，广州不混入，列表不改原城市。"""
    prefix='城市筛选隔离-'+uuid.uuid4().hex[:8]
    for index,city in enumerate(['深圳','深圳市','广州']):
        assert client.post('/api/leads',json={'display_name':prefix+str(index),'buyer_role':'mall','city':city}).status_code==201
    for city in ['深圳','深圳市']:
        result=client.get('/api/leads',params={'q':prefix,'city':city}).json()
        assert result['total']==2 and {row['city'] for row in result['items']}=={'深圳','深圳市'}


def test_selected_contact_source_is_read_before_unrelated_results(client,monkeypatch):
    """client为隔离API，monkeypatch替网络；已选客户原页优先且保留来源渠道，不被最新泛搜淹没。"""
    from app import agent
    from app.gateway import archive_sources
    from test_export_signals import fixture
    identifier,candidate,sources,job_id=fixture(client)
    original=next(x for x in sources.values() if x['id']!=candidate.procurement_signal.source_id)
    with Session.begin() as db:
        source=db.get(Evidence,original['id']);source.kind='搜索摘录';source.channel='official'
    latest=archive_sources(job_id,[{'url':'https://example.org/unrelated','title':'隔离无关目录','body':'未含客户联系方式的目录'}],'搜索摘录','industry_directory')[0]
    calls=[]
    async def execute(self,name,args):
        """self/name/args为真实读取节点委派；只记录调用以验证预算和顺序，未声称取得公网资料。"""
        calls.append(args);return {'sources':[]}
    monkeypatch.setattr(ToolBroker,'execute',execute)
    asyncio.run(agent.read_node({'job_id':job_id,'options':{'enabled_channels':['official','industry_directory'],'max_reads':4},
        'profile':{},'source_ids':[original['id'],latest['id']],'saved_ids':[identifier],
        'attempts':[{'source_ids':[latest['id']]}],'steps':[{'channel':'industry_directory'}],'cursor':0}))
    assert calls[0]=={'url':original['url'],'channel':'official'}
    assert len(calls)==2


def test_public_contact_sidebar_is_preserved_and_hidden_contact_ignored():
    """无入参；真实HTML联系侧栏保留原文，隐藏号码和脚本不得因补完整率进入公开证据。"""
    from app.public_contacts import contact_blocks
    content='<html><meta charset="utf-8"><main>隔离商行经销吊灯。</main><ul class="cp-contact"><li>电话86 0755 23004025</li><li>地址深圳观澜隔离铺位</li></ul><div class="contact" style="display:none">手机13900000000</div><div class="contact">邮箱sales@example.org<script>phone="13800000000"</script></div></html>'.encode()
    value=contact_blocks(content)
    assert '电话86 0755 23004025' in value and '地址深圳观澜隔离铺位' in value
    assert 'sales@example.org' in value and '13900000000' not in value and '13800000000' not in value


def test_discovery_reads_role_match_before_manufacturer(client,monkeypatch):
    """client为隔离API，monkeypatch禁止网络；有限读预算优先明确经销摘要，不把排序信号直接保存为客户。"""
    from app import agent
    from app.gateway import archive_sources
    conversation=client.post('/api/conversations').json()['id']
    job=client.post(f'/api/conversations/{conversation}/messages',json={'content':'深圳吊灯经销客户','client_token':uuid.uuid4().hex}).json()['id']
    sources=archive_sources(job,[{'url':'https://example.org/factory','title':'厂商','body':'专业灯具生产厂家'},
        {'url':'https://example.org/dealer','title':'经销商','body':'隔离商行经销批发吊灯'}],'搜索摘录','industry_directory')
    calls=[]
    async def execute(self,name,args):
        """self/name/args为真实工具调用参数；记录读取顺序，返回空来源，不伪造网络成功。"""
        calls.append(args);return {'sources':[]}
    monkeypatch.setattr(ToolBroker,'execute',execute)
    asyncio.run(agent.read_node({'job_id':job,'options':{'enabled_channels':['industry_directory'],'max_reads':1},
        'profile':{},'plan':{'target_roles':['dealer']},'source_ids':[x['id'] for x in sources],'saved_ids':[],
        'attempts':[{'source_ids':[x['id'] for x in sources]}],'steps':[{'channel':'industry_directory'}],'cursor':0}))
    assert calls==[{'url':'https://example.org/dealer','channel':'industry_directory'}]


@pytest.mark.parametrize('url,title,body,expected',[
    ('https://example.org/login','企业查询','登录后查看','site_login_required'),
    ('https://example.org/company','登录-隔离查询网','账号登录','site_login_required'),
    ('https://example.org/company','安全验证','请验证您不是机器人','site_verification_required'),
    ('https://example.org/company','隔离商行','深圳隔离商行经销灯具；免费注册 登录 联系我们',''),
    ('https://example.org/company','隔离商行','请完成验证。'+'真实商户正文。'*200,'')])
def test_access_page_detection_does_not_reject_normal_footer(url,title,body,expected):
    """四个参数为明确合成页面用例；登录/验证入口受限，普通网站页脚登录链接不阻止真实正文。"""
    from app.source_access import access_issue
    assert access_issue(url,title,body)==expected


def test_login_fallback_is_not_archived_as_success(client,monkeypatch):
    """client为隔离API，monkeypatch只替外部请求；真实Broker拒绝供应商返回的登录页，旧缓存也不能复用。"""
    import httpx
    from sqlalchemy import select
    from app import research_tools
    from app.db import ToolCall
    from app.gateway import archive_sources
    identifier=job(client);url='https://example.org/company'
    archive_sources(identifier,[{'url':url,'title':'登录-隔离查询网','body':'仅用于隔离登录缓存测试。'*20}],'网页正文','industry_directory')
    original=httpx.AsyncClient
    async def response(request):
        """request为隔离HTTP请求；无可用静态正文，验证正常进入现有供应商读取路径。"""
        return httpx.Response(200,content=b'<html></html>',headers={'Content-Type':'text/html'})
    monkeypatch.setattr(research_tools.httpx,'AsyncClient',lambda **kwargs:original(**kwargs,transport=httpx.MockTransport(response)))
    monkeypatch.setattr(research_tools,'public_url',lambda url:True)
    async def provider(name,args):
        """name/args为真实fallback入参；返回明确登录页面，不冒充客户资料。"""
        return json.dumps({'results':[{'url':url,'title':'登录-隔离查询网','text':'请先登录再查询公司资料'}]})
    monkeypatch.setattr(research_tools,'call_exa',provider)
    broker=ToolBroker(identifier,{'max_reads':1,'max_searches':0,'enabled_channels':['industry_directory']},{})
    result=asyncio.run(broker.execute('fetch_source',{'url':url,'channel':'industry_directory'}))
    assert result['error']=='site_login_required' and result['sources']==[] and not result.get('cached')
    with Session() as db:
        tool=db.scalar(select(ToolCall).where(ToolCall.job_id==identifier,ToolCall.tool=='fetch_source'))
        assert tool.status=='unavailable'
        assert len(list(db.scalars(select(Evidence).where(Evidence.job_id==identifier))))==1


def test_source_site_count_merges_mobile_but_not_other_platforms():
    """无入参；同平台移动/桌面两URL计一个网站，政府三级根域保持，网站数不称事实独立调查数。"""
    from app.contact_view import evidence_sites
    assert evidence_sites([{'url':'http://m.jc001.cn/store'},{'url':'http://shop.jc001.cn/store'},
        {'url':'https://www.1024sj.com/company'},{'url':'https://www.ccgp.gov.cn/notice'}])==['1024sj.com','ccgp.gov.cn','jc001.cn']


@pytest.mark.parametrize('prompt,count',[('找3家深圳买家',1),('至少3个不同网站交叉核验',3),('两个不同网站核对',2),('交叉核验公开电话',2)])
def test_required_sources_do_not_confuse_buyer_count(prompt,count):
    """prompt为本轮要求、count为预期；来源数量与买家数量独立，未明确跨站时不强迫增加搜索。"""
    from app.source_catalog import required_sites
    assert required_sites(prompt)==count


def test_gap_keeps_corroborating_complete_contact_when_requested(client):
    """client为隔离API；已有完整联系资料但只有一站，用户要求跨站时真实gap节点不能提前结束。"""
    from app import agent
    identifier=job(client)
    lead=client.post('/api/leads',json={'display_name':'跨站隔离门店','city':'深圳','buyer_role':'dealer','phone':'0755-12345678','address':'深圳隔离地址'}).json()
    with Session.begin() as db:
        row=db.get(Lead,lead['id']);row.facts={**row.facts,'categories':{'value':'吊灯'}}
        row.evidence=[{'url':'https://example.org/customer','field':'name','quote':'跨站隔离门店'}]
    result=asyncio.run(agent.gap_node({'job_id':identifier,'saved_ids':[lead['id']],'prompt':'通过至少3个不同网站交叉核验',
        'cursor':0,'steps':[{'channel':'official','query':'深圳跨站隔离门店','purpose':'官网核验'}],
        'profile':{'region':'深圳','products':[{'name':'吊灯'}]},'options':{'max_leads':1,'max_searches':4,'max_reads':4,'enabled_channels':['official','industry_directory']},
        'attempts':[{'channel':'official','query':'深圳跨站隔离门店'}],'gaps':[]}))
    assert result['cursor']<len(result['steps']) and '跨站隔离门店' in result['steps'][result['cursor']]['query']
    assert '交叉核验' in result['steps'][result['cursor']]['query']


def test_unknown_purchase_field_does_not_force_procurement_platform():
    """无入参；深圳地区加未知采购字段不是访问采购平台指令，真正平台名称仍确定性执行。"""
    assert requested_channels('深圳灯具商行，未知采购和营收留空',['sz_procurement','industry_directory'])==[]
    assert requested_channels('先查深圳公共资源交易采购公告',['sz_procurement'])==['sz_procurement']


def test_spaced_contact_label_is_valid_but_legal_representative_is_not(client):
    """client为隔离API；空格标签按原文归一匹配，法人字段不能充当联系人身份。"""
    from app.schemas import Fact
    from app.service import checked_candidate,ServiceError
    from app.gateway import archive_sources
    from test_export_signals import fixture
    _,candidate,rows,identifier=fixture(client)
    source=archive_sources(identifier,[{'url':'https://example.net/contact','title':candidate.display_name,
        'body':'联 系 人：隔离先生。法定代表人：隔离法人。'}],'隔离测试')[0]
    rows[source['id']]=source
    field=Fact(field='contact_name',value='隔离先生',quote='联 系 人：隔离先生',source_id=source['id'])
    clean,_=checked_candidate(candidate.model_copy(update={'facts':[*candidate.facts,field]}),rows)
    assert clean['contact_name']['value']=='隔离先生'
    with pytest.raises(ServiceError,match='联系人必须'):
        checked_candidate(candidate.model_copy(update={'facts':[*candidate.facts,field.model_copy(update={'value':'隔离法人','quote':'法定代表人：隔离法人'})]}),rows)


def test_conflicting_values_in_same_batch_keep_alternatives(client):
    """client为隔离API；单次跨站输出的不同电话保留双方证据并标争议，不悄悄选择最后一个值。"""
    from app.schemas import Fact
    from app.gateway import archive_sources
    from app.service import save_candidate
    from test_export_signals import fixture
    lead,candidate,rows,identifier=fixture(client)
    fields=[]
    for index,phone in enumerate(['0755-12345678','0755-87654321']):
        source=archive_sources(identifier,[{'url':f'https://example{index}.org/contact','title':candidate.display_name,'body':'业务电话：'+phone}],'隔离测试')[0]
        rows[source['id']]=source
        fields.append(Fact(field='phone',value=phone,quote=source['body'],source_id=source['id']))
    save_candidate(candidate.model_copy(update={'facts':[*candidate.facts,*fields]}),rows,identifier)
    detail=client.get('/api/leads/'+lead).json()
    assert detail['facts']['phone']['verification']=='disputed'
    assert detail['facts']['phone']['value']=='0755-12345678'
    assert detail['facts']['phone']['alternatives'][0]['value']=='0755-87654321'
    assert 'phone' not in detail['contact_summary']['usable_fields']


def test_candidate_repair_uses_existing_evidence_and_revalidates(client,monkeypatch):
    """client隔离业务，monkeypatch只替格式修复模型；坏引文真实拒绝后，用原证据修复一次并重走Broker校验。"""
    from app import agent
    from app.schemas import Fact,Candidate
    from sqlalchemy import select
    from app.db import ToolCall
    from test_export_signals import fixture
    lead,candidate,sources,identifier=fixture(client)
    base=candidate.facts[0].source_id
    bad=candidate.model_copy(update={'facts':[*candidate.facts,Fact(field='phone',value='0755-00000000',quote='不存在的引文0755-00000000',source_id=base)]})
    repairs=[]
    async def repair(state,schema,prompt,label):
        """state/schema/prompt/label为真实修复输入；返回已校验基础候选，未声称真实外部模型成功。"""
        assert schema is Candidate and '引文未能' in prompt and sources[base]['body'] in prompt
        repairs.append(label);return candidate
    monkeypatch.setattr(agent,'cached_model',repair)
    result=asyncio.run(agent.save_node({'job_id':identifier,'cursor':0,'profile':{'region':'深圳','products':[{'name':'吊灯'}]},
        'options':{'max_leads':1,'enabled_channels':['official']},'source_ids':list(sources),'saved_ids':[],
        'plan':{'target_roles':['retailer']},'candidates':[bad.model_dump()],'gaps':[]}))
    assert result['saved_ids']==[lead] and len(repairs)==1
    with Session() as db:
        states=[x.status for x in db.scalars(select(ToolCall).where(ToolCall.job_id==identifier,ToolCall.tool=='persist_lead'))]
    assert sorted(states)==['completed','rejected']


@pytest.mark.parametrize('value,status,href',[
    ('86 0755 23004025','format_valid','tel:+86-755-2300-4025'),
    ('0755-280019935','invalid',''),('81762065','incomplete',''),('139****5678','masked',''),
    ('13428788412','format_valid','tel:+86-134-2878-8412'),
    ('0755-88377572转2314','format_valid','tel:+86-755-8837-7572;ext=2314')])
def test_phone_link_uses_library_without_changing_original(value,status,href):
    """value/status/href为格式用例；仅验证离线长度及RFC3966，不声称号码接通、不修改证据原值。"""
    from app.contact_view import phone_info
    assert phone_info(value)=={'status':status,'href':href}


def test_project_search_never_substitutes_another_project(client,monkeypatch):
    """client为隔离API、monkeypatch固定供应商响应；指定项目精确过滤，无相关公告不能用别的项目充数。"""
    from app import research_tools
    requests=[]
    async def provider(name,args):
        """name/args为真实检索参数；两条合成公告测试匹配规则，不调用真实采购站。"""
        requests.append(args)
        return json.dumps({'results':[
            {'url':'https://www.szggzy.com/project/wrong','title':'其他项目','text':'编号SZDL2025000999'},
            {'url':'https://www.szggzy.com/project/right','title':'指定照明项目','text':'编号SZDL2025000716，采购单位隔离学校'}]})
    monkeypatch.setattr(research_tools,'call_exa',provider)
    identifier=job(client)
    broker=ToolBroker(identifier,{'enabled_channels':['sz_procurement'],'max_searches':1,'max_reads':1},{})
    result=asyncio.run(broker.execute('search_accounts',{'query':'深圳外国语学校照明项目SZDL2025000716','channel':'sz_procurement'}))
    assert len(result['sources'])==1 and result['sources'][0]['url'].endswith('/right')
    assert 'SZDL2025000716' in requests[0]['objective']


@pytest.mark.parametrize('quote,title,same_name,expected',[
    ('公司经营、代理的有：隔离照明品牌。','公司介绍 - 隔离百明丰商行',True,True),
    ('企业性质：个体经营 - 经销批发','隔离百明丰商行',True,True),
    ('公司经营、代理的有：隔离照明品牌。','行业目录',True,False),
    ('公司经营、代理的有：隔离照明品牌。','隔离百明丰商行',False,False),
    ('其他照明有限公司\n公司经营、代理的有：照明。','隔离百明丰商行',True,False)])
def test_scoped_role_requires_single_subject_and_explicit_role(quote,title,same_name,expected):
    """四个参数为明确结构关联用例；单主体介绍允许，同目录/其他法律主体/无同源名称拒绝。"""
    from app.evidence_role import scoped_role
    value='经销批发' if '企业性质' in quote else '代理'
    assert scoped_role('隔离百明丰商行',value,quote,title,same_name)==expected


def test_directory_table_role_belongs_to_its_section():
    """无入参；授权表头只归该分区中的真实行，不归无表头同名或其他角色分区。"""
    from app.evidence_role import scoped_role
    assert scoped_role('隔离灯饰店','授权店','### 授权店\n| 编号 | 店名 | 地址 |\n| 1 | 隔离灯饰店 | 深圳 |','官方门店目录',False)
    assert not scoped_role('隔离灯饰店','授权店','| 1 | 隔离灯饰店 | 深圳 |','官方门店目录',False)
    assert not scoped_role('隔离灯饰店','授权店','### 授权店\n| 1 | 其他店 | 深圳 |\n### 厂商\n| 2 | 隔离灯饰店 | 深圳 |','官方门店目录',False)


def test_product_article_role_requires_unambiguous_company_intro():
    """无入参；商品标题不含公司名时只允许明确介绍段回指，出现另一法律主体后不能继续归给原商行。"""
    from app.evidence_role import scoped_role
    name='隔离百明丰商行';quote='公司经营、代理的品牌有:'
    assert scoped_role(name,'代理',quote,'筒灯产品介绍',True,name+'成立于2007年，是一家销售企业。\n'+quote)
    assert not scoped_role(name,'代理',quote,'筒灯产品介绍',True,name+'成立于2007年。另有其他灯具有限公司。\n'+quote)
    assert not scoped_role(name,'代理',quote,'筒灯产品介绍',True,'只有页面推荐：'+name+'。\n'+quote)


def test_role_body_proof_does_not_require_duplicate_name_fact(client):
    """client为隔离API；完整名字已在原文介绍段时，不因模型仅选另一站name引用而拒绝真实主体关联。"""
    from app.schemas import Fact
    from app.gateway import archive_sources
    from app.service import checked_candidate
    from test_export_signals import fixture
    _,candidate,rows,identifier=fixture(client)
    quote='公司经营零售门店。'
    source=archive_sources(identifier,[{'url':'https://example.net/product','title':'隔离商品介绍','body':candidate.display_name+'成立于2007年，是一家销售企业。\n'+quote}],'隔离测试')[0]
    rows[source['id']]=source
    facts=[x for x in candidate.facts if x.field!='buyer_role']
    facts.append(Fact(field='buyer_role',value='零售门店',quote=quote,source_id=source['id']))
    clean,_=checked_candidate(candidate.model_copy(update={'facts':facts}),rows)
    assert clean['buyer_role']['source_id']==source['id']


def test_reference_urls_respect_disabled_platform_and_credentials():
    """无入参；用户提供链接不借官网绕过关闭的平台，也不接收嵌入凭据或接口文档。"""
    from app.source_catalog import reference_urls
    assert reference_urls('查https://www.qcc.com/firm/test.html',['official'])==[]
    assert reference_urls('查https://openapi.qcc.com/dataApi/2001',['qcc_public','official'])==[]
    assert reference_urls('查https://user:secret@example.org/info',['official'])==[]
    assert reference_urls('查https://example.org/info。',['official'])==[{'url':'https://example.org/info','channel':'official'}]


def test_user_reference_fetch_creates_only_actual_response_evidence(client,monkeypatch):
    """client隔离HTTP、monkeypatch固定公开HTML；明确链接可读取，但用户链接本身不能生成事实Evidence。"""
    import httpx
    from sqlalchemy import select
    from app import research_tools
    url='https://reference.example.org/company'
    conv=client.post('/api/conversations').json()['id']
    identifier=client.post(f'/api/conversations/{conv}/messages',json={'content':'销售灯具，请查'+url,'client_token':uuid.uuid4().hex}).json()['id']
    with Session() as db:assert not list(db.scalars(select(Evidence).where(Evidence.job_id==identifier)))
    body='参考链接隔离商行经销照明产品，地址深圳，仅用于本地公开链接工具路径验证。'*8
    content=('<html><meta charset="utf-8"><title>隔离公司页</title><article>'+body+'</article></html>').encode()
    original=httpx.AsyncClient
    async def response(request):
        """request为隔离公开读取请求；返回真实HTML形状，未声称源站实际访问成功。"""
        return httpx.Response(200,content=content,headers={'Content-Type':'text/html'})
    monkeypatch.setattr(research_tools.httpx,'AsyncClient',lambda **kwargs:original(**kwargs,transport=httpx.MockTransport(response)))
    monkeypatch.setattr(research_tools,'public_url',lambda url:True)
    broker=ToolBroker(identifier,{'max_reads':1,'max_searches':0,'enabled_channels':['official']},{})
    result=asyncio.run(broker.execute('fetch_source',{'url':url,'channel':'official'}))
    assert not result.get('error') and len(result['sources'])==1
    assert result['sources'][0]['kind']=='网页正文' and '仅用于本地' in result['sources'][0]['body']
