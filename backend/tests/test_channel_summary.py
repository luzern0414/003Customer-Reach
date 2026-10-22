"""渠道过程结论须来自成功正文和失败账本，不能把摘录、标题或导航当正文。"""
import pytest
from app.answer_summary import read_pages,channel_summary,empty_summary
from app.industry_navigation import NAVIGATION_MARKER

@pytest.mark.parametrize('reverse',[False,True])
def test_failure_and_later_success_are_both_preserved(reverse):
    """reverse表示失败先后顺序；同渠道成功不抹失败，失败也不能抹正文取得事实。"""
    source={'id':'s','kind':'网页正文','title':'隔离标题','url':'https://example.org/','body':'隔离测试公开网页的联系说明。'}
    success={'tool':'fetch_source','channel':'b2b_1688','status':'completed','read_pages':read_pages({'sources':[source]})}
    failure={'tool':'fetch_source','channel':'b2b_1688','status':'unavailable','error':'site_robots_disallowed'}
    operations=[success,failure] if reverse else [failure,success]
    text,mixed=channel_summary(operations)
    assert mixed and '已取得正文，部分页面读取未成功' in text
    assert 'site_robots_disallowed' not in text and '隔离测试公开' not in text

def test_search_excerpt_and_title_only_never_count_as_read_body():
    """无参数；仅标题/URL/派生导航不算正文，正文投影不泄漏原文。"""
    pages=[{'id':'s','kind':'网页正文','title':'隔离标题','url':'https://example.org/','body':'# 隔离标题\nURL: https://example.org/\n'+NAVIGATION_MARKER+'\n目录入口：联系\n目录链接：https://example.org/contact'},
           {'id':'excerpt','kind':'搜索摘录','body':'公开搜索摘录','url':'https://example.org/'}]
    assert read_pages({'sources':pages})==[]
    operations=[{'tool':'search_accounts','channel':'qcc_public','status':'completed','source_count':3},
        {'tool':'fetch_source','channel':'qcc_public','status':'unavailable'},
        {'tool':'fetch_source','channel':'qcc_public','status':'completed','source_count':1,'pages':pages,'read_pages':[]}]
    text,mixed=channel_summary(operations)
    assert not mixed and '有搜索摘录，读取未取得正文' in text
    assert '已读取' not in empty_summary(operations)
