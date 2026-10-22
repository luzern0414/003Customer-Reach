"""回答应区分模型候选提议记录与CRM保存数量，不把保存配额当提取数量。"""
from app.answer_summary import proposal_summary
from app.answer_summary import empty_summary


def test_three_proposals_and_one_saved_are_distinct():
    """一次真实形状提取3条、保存1条时仍保留3候选计数；不传未保存客户名称或事实。"""
    summary=proposal_summary([{'tool':'extract:0','status':'completed','result':{'candidates':[
        {'display_name':'隔离甲'},{'display_name':'隔离乙'},{'display_name':'隔离丙'}]}}],1)
    assert summary['proposed_records']==3 and summary['saved_leads']==1 and summary['nonempty_batches']==1
    assert '隔离甲' not in str(summary)


def test_repeated_proposals_are_records_not_unique_customers_and_failures_excluded():
    """重复输出计记录，不伪装不同公司；失败、修复、保存工具不算新的提议输出。"""
    result={'candidates':[{'display_name':'隔离同名'}]}
    operations=[{'tool':'extract:0','status':'completed','result':result},
        {'tool':'parse_account','status':'completed','result':result},
        {'tool':'extract:1','status':'unavailable','result':result},
        {'tool':'candidate_repair:0','status':'completed','result':result},
        {'tool':'persist_lead','status':'completed','result':result}]
    summary=proposal_summary(operations,1)
    assert summary['proposed_records']==2 and '可重复' in summary['meaning']
    assert proposal_summary([],0)['proposed_records']==0


def test_empty_answer_cannot_promote_page_title_to_verified_customer():
    """零保存输出不得把成功网页/未通过候选当客户；只有已完成读取可进入过程摘要。"""
    answer=empty_summary([
        {'tool':'fetch_source','channel':'mall_directory','status':'completed','source_count':1,'read_pages':[{'title':'未核验主体有限公司','url':'https://www.zhaopin.com/companydetail/test'}]},
        {'tool':'fetch_source','channel':'qcc_public','status':'running','source_count':0},
        {'tool':'search_accounts','channel':'b2b_1688','status':'rate_limited','error':'provider_rate_limited'},
        {'tool':'persist_lead','status':'rejected'}])
    assert '尚无通过完整校验' in answer and '未核验主体有限公司' not in answer
    assert '供应商' in answer and '企查查' not in answer and '未通过校验' in answer
    assert 'zhaopin.com' in answer and '家居商场商户' not in answer and 'mall_directory' not in answer
