"""同源公告展示去重的回归；保留底层历史、时间差异与失效反馈。"""
from copy import deepcopy
from app.procurement import procurement_views


def test_same_notice_keeps_complete_quotes_without_changing_history():
    """同源三次提取只呈现一次完整公告，不删除已存档的短片段。"""
    first={'source_id':'real-source','buyer':'学校','participant_role':'buyer',
        'deadline':'2025-06-20 09:30:00','stage':'closed','quote':'照明设备项目招标公告',
        'buyer_quote':'采购人信息 名称：学校 地址：深圳','deadline_quote':'2025年6月20日9：30'}
    second={**first,'stage':'historical','quote':'2025年6月20日9：30','buyer_quote':'名称：学校'}
    qualification={'procurement_signals':[first,second],'procurement_signal':second}
    original=deepcopy(qualification)
    rows=procurement_views(qualification,'2026-10-03 15:00:00')
    assert len(rows)==1 and rows[0]['selected']
    assert rows[0]['buyer_quote']==first['buyer_quote']
    assert qualification==original


def test_distinct_deadlines_remain_and_invalidated_notice_cannot_look_active():
    """同源更正不同截止保留，任一同组失效反馈不能被较长引文掩盖。"""
    first={'source_id':'real-source','buyer':'学校','participant_role':'buyer',
        'deadline':'2027-06-20 09:30:00','stage':'open','intent_score':10,'quote':'照明设备项目原公告'}
    invalid={**first,'verification':'inactive','quote':'失效'}
    changed={**first,'deadline':'2027-07-20 09:30:00'}
    qualification={'procurement_signals':[first,invalid,changed],'procurement_signal':first}
    rows=procurement_views(qualification,'2026-10-03 15:00:00')
    assert len(rows)==2
    assert next(row for row in rows if row['deadline']==first['deadline'])['display_status']=='失效'
