"""完整主体目录记录里的公开号码可以并列，不能借邻店/掩码/传真或解除已有争议。"""
from app.contact_view import coexisting_phones


def test_verified_hc23_record_keeps_two_full_phones():
    """固定真实模板形状只验证规则，非真实客户；邻主体/掩码/摘要/未知域均拒绝。"""
    name='深圳隔离并列电话商行'
    left={'value':'86-0755-27105866','source_id':'s'}
    right={'value':'13602675387','source_id':'s'}
    row={'url':'https://jz.hc23.com/company/fixture.html','title':name,'kind':'网页正文',
        'body':name+'的地址是深圳某市场,13602675387,86-0755-27105866,主要提供。'}
    assert coexisting_phones(name,left,right,{'s':row})
    assert not coexisting_phones(name,left,right,{'s':{**row,'body':row['body'].replace(name,'深圳别的主体商行')}})
    assert not coexisting_phones(name,left,right,{'s':{**row,'body':row['body'].replace('13602675387','13602....')}})
    assert not coexisting_phones(name,left,right,{'s':{**row,'kind':'搜索摘录'}})
    assert not coexisting_phones(name,left,right,{'s':{**row,'url':'https://example.org/company'}})


def test_phone_pair_projection_preserves_disputed_parent(client):
    """即使新规则识别并列，历史父事实争议仍不生成电话动作，不能绕过人工核验。"""
    from app.contact_view import contact_view
    facts={'phone':{'value':'86-0755-27105866','verification':'disputed',
        'alternatives':[{'value':'13602675387','relation':'additional_contact','verification':'原文匹配'}]}}
    assert not contact_view(facts,[])['usable_fields']


def test_hc23_template_keeps_pair_and_rejects_other_subject(client):
    """Pydantic原文解析/实际校验生成并列入口，掩码字段不推；两电话必须完整存在同主体摘要行。"""
    from app.public_accounts import parse_account
    from app.service import checked_candidate
    name='深圳隔离灯饰店'
    body='| 企 业 名 称：'+name+' 联 系 人：测试先生 员 工 人 数：未知 主 营 产 品：灯饰 水暖 公 司 地 址：深圳某市场 联 系 电 话：86-0755-27105866 移 动 电 话：13602.... |\n本商场是品牌的一级经销商。\n'+name+'的地址是深圳某市场,13602675387,86-0755-27105866,主要提供。'
    source={'id':'s','url':'https://jz.hc23.com/company/123.html','title':name,'body':body,'kind':'网页正文','channel':'industry_directory','captured_at':'2026-10-03 00:00:00'}
    candidate=parse_account(source,'深圳');assert candidate
    clean,_=checked_candidate(candidate,{'s':source})
    assert clean['phone']['verification']!='disputed'
    assert clean['phone']['alternatives'][0]['relation']=='additional_contact'
    assert 'headcount' not in clean and 'email' not in clean
    assert not parse_account({**source,'body':body.replace(name+'的地址是','别的灯饰店的地址是')},'深圳')
    branded={**source,'body':body.replace('本商场是品牌的一级经销商。','本商场销售经营，并是甲牌、乙牌等世界知名品牌的一级经销商。')}
    parsed=parse_account(branded,'深圳');assert parsed
    assert next(item.value for item in parsed.facts if item.field=='brands')=='甲牌、乙牌'
    assert not any(item.field=='supplier' for item in parsed.facts)
