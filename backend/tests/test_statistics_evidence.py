"""统计元数据须有原文而非只填非空；仅合成数据，不能当真实营收/员工资料。"""
import pytest
from app.statistics_evidence import valid_statistics


@pytest.mark.parametrize('scope,period,quote',[
    ('集团','2025','2025年度，集团营业收入100万元。'),
    ('公司','2025-12-31','截至2025年12月31日，公司员工人数40人。'),
    ('公司','2025-09','2025年9月，公司员工人数40人。'),
])
def test_quoted_scope_and_period_are_valid(scope,period,quote):
    """年度不补年底日期，中文年月日可对应同精度合法ISO记录。"""
    assert valid_statistics(scope,period,quote)


@pytest.mark.parametrize('scope,period,quote',[
    ('unquoted consolidated group','2025','公司员工人数40人。'),
    ('公司','1900-99-99','公司员工人数40人。'),
    (' ',' ','公司员工人数40人。'),
    ('公司','2025-12-31','2025年度，公司员工人数40人。'),
    ('公司','2025','公司员工人数40人。版权所有2025年。'),
    ('公司','1995','公司成立于1995年，员工人数40人。'),
    ('公司','2025','发布时间：2025年。公司员工人数40人。'),
    ('公司','2025','公司员工人数2025人。'),
    ('公司','2025-12','公司灯具型号2025-12，员工人数40人。'),
])
def test_unquoted_or_nonstatistical_metadata_is_rejected(scope,period,quote):
    """虚构口径、非法/空白日期、补日、成立和页脚年份都不能保存为统计口径。"""
    assert not valid_statistics(scope,period,quote)


@pytest.mark.parametrize('field,value,label',[('headcount','40人','员工人数'),('revenue','100万元','营业收入')])
def test_real_candidate_validator_rejects_invented_metadata(client,field,value,label):
    """直接走实际候选校验，不只测试辅助函数；有效元数据保留原值，伪造元数据拒绝。"""
    from app.service import checked_candidate,ServiceError
    from app.schemas import Candidate,Fact
    body=f'2025年度，隔离公司{label}{value}。'
    source={'s1':{'body':body,'url':'https://example.org/','title':'隔离公司','captured_at':'2026-10-04 08:00:00','kind':'网页正文'}}
    name=Fact(field='name',value='隔离公司',quote=body,source_id='s1')
    fact=Fact(field=field,value=value,quote=body,source_id='s1',scope='隔离公司',effective_date='2025')
    candidate=Candidate(display_name='隔离公司',city='',match_reason='隔离验证',facts=[name,fact])
    clean,_=checked_candidate(candidate,source)
    assert clean[field]['effective_date']=='2025'
    bad=fact.model_copy(update={'scope':'虚构集团口径','effective_date':'1900-99-99'})
    with pytest.raises(ServiceError,match='统计日期和主体口径'):checked_candidate(candidate.model_copy(update={'facts':[name,bad]}),source)
