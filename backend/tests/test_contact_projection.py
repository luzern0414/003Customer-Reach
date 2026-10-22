"""联系入口与待补字段必须同口径；仅隔离合成值，不作为真实客户数据。"""
import pytest
from app.contact_view import contact_view


@pytest.mark.parametrize('field,value',[('phone','82345678'),('phone','138****0000'),
                                      ('email','not-an-email'),('website','javascript:alert(1)')])
def test_invalid_contact_remains_missing_with_another_valid_entry(field,value):
    """有有效邮箱/电话不掩盖另一字段格式缺口，原值仍完整保留，不补号或改写。"""
    facts={'phone':{'value':'13900000000'},'email':{'value':'sales@example.org'},field:{'value':value}}
    result=contact_view(facts,[])
    assert result['status']=='有联系入口'
    assert field not in result['usable_fields'] and field in result['missing_fields']
    assert facts[field]['value']==value


@pytest.mark.parametrize('state',['disputed','inactive'])
def test_contact_and_person_feedback_remains_missing(state):
    """失效/争议邮箱与联系人即使非空也必须显示缺口，正常电话不受影响。"""
    facts={'phone':{'value':'13900000000'},'email':{'value':'sales@example.org','verification':state},
           'contact_name':{'value':'界面验证联系人','verification':state}}
    result=contact_view(facts,[])
    assert result['usable_fields']==['phone']
    assert {'email','contact_name'}<=set(result['missing_fields'])


def test_sites_and_pages_are_distinct_and_no_task_pages_are_added():
    """只数客户证据；同站多页/移动站合并，空证据为零，不把本轮全部网页计入客户。"""
    evidence=[{'url':'https://example.com.cn/about'},{'url':'https://m.example.com.cn/contact'},
              {'url':'https://example.com.cn/about'},{'url':'https://other.org/company'}]
    result=contact_view({},evidence)
    assert result['source_count']==3 and result['site_count']==2
    assert result['sites']==['example.com.cn','other.org']
    assert contact_view({},[])['site_count']==0
