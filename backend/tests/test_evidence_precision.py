"""明确主体、短来源编号与分段采购原文回归；全部企业与公告为隔离测试，不请求外网。"""
import pytest
from app.evidence_context import evidence_context,target_names,source_aliases,resolve_sources
from app.evidence_role import scoped_role
from app.procurement import deadline_in_quote


def test_explicit_target_name_exists_without_saved_lead():
    """无入参；指定名字来自当前要求和真实资料交集，不扩大到国际部/集团，不要求先有CRM客户。"""
    rows=[{'title':'深圳外国语学校国际部','body':'深圳外国语学校采购资料'},
        {'title':'深圳市宝安区百明丰五金电器商行','body':'经销资料'}]
    assert target_names('请核验深圳外国语学校的采购信息',rows,'深圳')==['深圳外国语学校']
    assert target_names('找深圳照明经销商',rows,'深圳')==[]
    assert target_names('我们是深圳市宝安区百明丰五金电器商行，销售灯具，请寻找深圳客户',rows,'深圳','深圳市宝安区百明丰五金电器商行')==[]
    assert target_names('我们是深圳市宝安区百明丰五金电器商行，销售灯具，请寻找深圳客户',rows,'深圳')==[]


def test_target_evidence_is_not_evicted_by_unrelated_fresh_results():
    """无入参；已有指定主体证据优先于五条新无关目录，仍保留当前主体新源。"""
    rows=[{'id':'known','url':'https://example.org/known','title':'目标商行','kind':'网页正文','body':'深圳目标商行经销灯具'}]
    rows.extend({'id':str(index),'url':'https://example.net/'+str(index),'title':'其他厂商','kind':'搜索摘录','body':'深圳其他厂商生产灯具'} for index in range(6))
    result=evidence_context(rows,['目标商行'],'深圳',[x['id'] for x in rows],[str(i) for i in range(6)])
    assert result[0]['id']=='known'


def test_alias_mapping_is_exact_for_facts_and_procurement():
    """无入参；短编号只映射本批真实来源，S99不猜来源，事实/公告均恢复完整ID。"""
    from app.schemas import Candidate
    shown,mapping=source_aliases([{'id':'actual-full-id','url':'https://example.org','body':'原文'}])
    assert shown[0]['id']=='S1' and mapping=={'S1':'actual-full-id'}
    candidate=Candidate(display_name='隔离企业',city='',buyer_role='unknown',match_reason='隔离映射',facts=[{'field':'name','value':'隔离企业','quote':'隔离企业','source_id':'S1'}],
        procurement_signal={'source_id':'S1','buyer':'隔离企业','participant_role':'buyer','stage':'historical','quote':'隔离采购公告'})
    resolved=resolve_sources(candidate,mapping)
    assert resolved.facts[0].source_id==resolved.procurement_signal.source_id=='actual-full-id'
    assert resolve_sources(candidate.model_copy(update={'facts':[candidate.facts[0].model_copy(update={'source_id':'S99'})]}),mapping).facts[0].source_id=='S99'


def test_intro_anchor_inside_long_quote_is_valid():
    """无入参；长引文从名字开始也要识别公司回指，夹入其他公司则拒绝。"""
    text='深圳隔离商行成立于2007年，是一家销售企业。\n公司经营、代理的品牌有：隔离品牌。'
    assert scoped_role('深圳隔离商行','代理',text,'筒灯产品',True,text)
    assert not scoped_role('深圳隔离商行','代理',text.replace('公司经营','其他公司有限公司。\n公司经营'),'筒灯产品',True,text.replace('公司经营','其他公司有限公司。\n公司经营'))


def test_procurement_multiline_buyer_does_not_accept_agency_or_name_prefix():
    """无入参；采购人名称可换行，代理/国际部不能作为学校本体的采购人证据。"""
    assert scoped_role('深圳隔离学校','采购人','采购人信息\n名称：深圳隔离学校\n地址：深圳','公告',True)
    assert not scoped_role('深圳隔离学校','采购人','采购代理机构信息\n名称：深圳隔离学校\n地址：深圳','公告',True)
    assert not scoped_role('深圳隔离学校','采购人','采购人信息\n名称：深圳隔离学校国际部\n地址：深圳','公告',True)


@pytest.mark.parametrize('value,quote,valid',[
    ('2025-06-20 09:30:00','并于2025年6月20日9：30（北京时间）前递交投标文件。',True),
    ('2025-06-20 19:30:00','2025年6月20日9：30前递交。',False),
    ('2025-06-20 00:00:00','2025年6月20日截止。',False)])
def test_deadline_requires_real_date_and_time(value,quote,valid):
    """value为规范时间、quote为原文、valid为预期；不能把日期补成猜测午夜或改时分。"""
    assert deadline_in_quote(value,quote)==valid


def test_phone_landline_and_mobile_on_same_company_card_are_not_conflicting(client):
    """client为隔离API；同公司卡片明确并列座机/手机可保留两个入口，失效反馈同时关闭操作。"""
    from test_export_signals import fixture
    from app.gateway import archive_sources
    from app.schemas import Fact
    from app.service import save_candidate
    from io import BytesIO
    from openpyxl import load_workbook
    lead,candidate,rows,job=fixture(client)
    body='公司名称：'+candidate.display_name+'\n座机电话：0755-23032205\n手机号码：15813848553'
    source=archive_sources(job,[{'url':'https://example.net/contact-card','title':candidate.display_name,'body':body}],'隔离测试')[0]
    rows[source['id']]=source
    fields=[Fact(field='phone',value=value,quote=body,source_id=source['id']) for value in ['0755-23032205','15813848553']]
    save_candidate(candidate.model_copy(update={'facts':[*candidate.facts,*fields]}),rows,job)
    detail=client.get('/api/leads/'+lead).json()
    assert detail['facts']['phone']['verification']!='disputed'
    assert detail['facts']['phone']['alternatives'][0]['contact_href']=='tel:+86-158-1384-8553'
    assert 'phone' in detail['contact_summary']['usable_fields']
    book=load_workbook(BytesIO(client.get('/api/leads/export?q='+candidate.display_name).content))
    assert any(row[8]=='其他公开号码' for row in book['事实与口径'].iter_rows(min_row=2,values_only=True))
    client.post('/api/leads/'+lead+'/feedback',json={'kind':'stale'})
    detail=client.get('/api/leads/'+lead).json()
    assert not detail['facts']['phone']['contact_href']
    assert not detail['facts']['phone']['alternatives'][0]['contact_href']


def test_procurement_phone_belongs_to_buyer_not_agency_or_platform():
    """无入参；同一公告中的平台热线和代理电话不能挂买方，完整买方名称不能以前缀代替国际部。"""
    from app.contact_owner import buyer_contact
    body='平台热线400-810-1996\n采购人信息\n名称：深圳隔离学校\n联系方式：0755-12345678\n采购代理机构信息\n名称：隔离代理公司\n电话：0755-87654321'
    assert buyer_contact('深圳隔离学校','0755-12345678',body)
    assert not buyer_contact('深圳隔离学校','0755-87654321',body)
    assert not buyer_contact('深圳隔离学校','400-810-1996',body)
    assert not buyer_contact('深圳隔离学校','0755-12345678',body.replace('深圳隔离学校\n','深圳隔离学校国际部\n'))


def test_contact_label_must_point_to_the_actual_name():
    """无入参；同一长引文的其他联系人不能证明法人身份，空格标签和采购联系方式则可原文绑定。"""
    from app.contact_owner import contact_identity
    assert contact_identity('董正伟 先生','联 系 人：董正伟 先生')
    assert contact_identity('杨工','联系方式：杨工 0755-12345678')
    assert not contact_identity('隔离法人','联系人：隔离销售；法定代表人：隔离法人')


@pytest.mark.parametrize('quote,valid',[
    ('- 联系人：\n- 隔离女士（）',True),
    ('- 联 系 人：\r\n  * 隔离女士（）',True),
    ('业务联系人：\n+ 隔离女士',True),
    ('联系人：\n- 法定代表人：隔离女士',False),
    ('联系人：\n- 隔离销售\n- 法定代表人：隔离女士',False),
    ('联系人：\n- 备注\n- 隔离女士',False),
    ('法人代表：\n- 隔离女士',False)])
def test_adjacent_markdown_contact_value_does_not_cross_other_fields(quote,valid):
    """quote为模拟真实工具两行列表、valid为预期；仅紧邻联系值可接受，不把其他字段或法人套成联系人。"""
    from app.contact_owner import contact_identity
    assert contact_identity('隔离女士',quote)==valid
    assert not contact_identity('',quote)
    assert not contact_identity('隔离女士','')


def test_markdown_contact_survives_full_persistence_without_quote_rewrite(client):
    """client为隔离API；完整persist接受紧邻业务联系标签，不授采购岗位、不修改Evidence连续引文。"""
    from test_export_signals import fixture
    from app.gateway import archive_sources
    from app.schemas import Fact
    from app.service import save_candidate
    lead,candidate,rows,job=fixture(client)
    quote='- 联系人：\n- 隔离女士（）'
    body='公司名称：'+candidate.display_name+'\n'+quote
    source=archive_sources(job,[{'url':'https://example.net/markdown-contact','title':candidate.display_name,'body':body}],'隔离测试','official')[0]
    rows[source['id']]=source
    fact=Fact(field='contact_name',value='隔离女士',quote=quote,source_id=source['id'])
    save_candidate(candidate.model_copy(update={'facts':[*candidate.facts,fact]}),rows,job)
    detail=client.get('/api/leads/'+lead).json()
    assert detail['facts']['contact_name']['value']=='隔离女士'
    assert any(item['field']=='contact_name' and item['quote']==quote for item in detail['evidence'])
    assert not detail['facts'].get('contact_position')


def test_same_source_separate_procurement_quotes_save_and_feedback_remains(client):
    """client为隔离API；相距较远的项目/买方/截止各自匹配，不能因短引文布局漏掉真实公告或绕过纠错。"""
    from test_export_signals import fixture
    from app.gateway import archive_sources
    from app.service import save_candidate,ServiceError
    lead,candidate,rows,job=fixture(client)
    project='隔离照明采购项目编号 TEST20991231'
    buyer='采购人信息\n名称：'+candidate.display_name+'\n地址：深圳'
    deadline='投标截止：2099年12月31日18：00'
    source=archive_sources(job,[{'url':'https://example.net/split','title':'隔离采购公告','body':project+'\n'+deadline+'\n'+'无关公开说明。'*600+'\n'+buyer}],'隔离测试','procurement')[0]
    rows[source['id']]=source
    signal=candidate.procurement_signal.model_copy(update={'source_id':source['id'],'quote':project,'buyer_quote':buyer,'deadline_quote':deadline})
    updated=candidate.model_copy(update={'procurement_signal':signal})
    save_candidate(updated,rows,job)
    detail=client.get('/api/leads/'+lead).json()
    assert detail['qualification']['signal_score']==10
    assert detail['procurement_signals'][0]['buyer_quote']==buyer
    assert {x['quote'] for x in detail['evidence'] if x['source_id']==source['id']}=={project,buyer,deadline}
    client.post('/api/leads/'+lead+'/feedback',json={'kind':'incorrect'})
    with pytest.raises(ServiceError,match='用户标记'):
        save_candidate(updated.model_copy(update={'procurement_signal':signal.model_copy(update={'quote':deadline})}),rows,job)
