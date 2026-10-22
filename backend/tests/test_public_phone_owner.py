"""普通网页电话归属回归；合成号码不是实际销售联系资料。"""
import pytest
from app.contact_owner import public_phone


@pytest.mark.parametrize('channel,title',[
    ('industry_directory','深圳合成甲灯饰有限公司'),
    ('industry_directory','深圳企业目录'),
    ('official','深圳合成甲灯饰有限公司')])
def test_checked_candidate_rejects_platform_phone(client,channel,title):
    """client为隔离库；channel/title为合成来源，真实准入拒绝平台电话而非仅解析器拒绝。"""
    from app.schemas import Candidate
    from app.service import checked_candidate,ServiceError
    name='深圳合成甲灯饰有限公司'
    intro=name+'在深圳经营灯具零售。'
    contact='平台服务中心电话：0755-00000000'
    row={'body':intro+'\n深圳合成乙灯饰有限公司经营灯具零售。\n'+contact,
        'title':title,'url':'https://example.org/fixture','captured_at':'2026-10-04 00:00:00','kind':'网页正文','channel':channel}
    candidate=Candidate(display_name=name,city='深圳',buyer_role='retailer',match_reason='隔离归属测试',facts=[
        {'field':'name','value':name,'quote':intro,'source_id':'s'},
        {'field':'buyer_role','value':'零售','quote':intro,'source_id':'s'},
        {'field':'phone','value':'0755-00000000','quote':contact,'source_id':'s'}])
    with pytest.raises(ServiceError,match='电话未与该客户主体'):checked_candidate(candidate,{'s':row})


def test_public_phone_blocks_and_single_owner():
    """无参数；明确企业块可接受，页脚平台/其他企业拒绝，后续明确客户块仍可恢复关联。"""
    name='深圳合成甲灯饰有限公司';phone='0755-00000000'
    assert public_phone(name,phone,name+'\n联系方式\n电话：'+phone)
    assert public_phone(name,phone,'联系方式\n电话：'+phone,name)
    assert not public_phone(name,phone,name+'\n深圳合成乙灯饰有限公司\n电话：'+phone,name)
    assert not public_phone(name,phone,name+'\n网站客服\n电话：'+phone,name)
    assert public_phone(name,phone,'平台服务热线\n'+name+'\n业务电话：'+phone,name)
