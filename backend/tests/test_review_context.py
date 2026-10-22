"""指定页原文复核使用实际成功工具正文，不把只有回答标题误当读取未取得正文。"""
from app.answer_summary import review_context
from app.industry_navigation import NAVIGATION_MARKER


def test_only_current_requested_successful_bodies_reach_review_after_redirect():
    """原请求与最终URL可不同；不选其他任务/未指定页/失败/假正文，导航不是复核事实。"""
    source={'id':'s','url':'https://example.org/final','title':'隔离实际公司','kind':'网页正文',
        'body':'隔离实际公司专业生产灯具。\n'+NAVIGATION_MARKER+'\n目录入口：其他客户\n目录链接：https://example.org/other'}
    operations=[{'tool':'fetch_source','status':'completed','arguments':{'url':'http://example.org/original'},'result':{'sources':[source]}},
        {'tool':'fetch_source','status':'completed','arguments':{'url':'https://example.org/unrequested'},'result':{'sources':[dict(source,id='other')]}},
        {'tool':'fetch_source','status':'unavailable','arguments':{'url':'http://example.org/original'},'result':{'sources':[dict(source,id='failed')]}}]
    context=review_context(operations,['http://example.org/original'])
    assert len(context)==1 and context[0]['url']=='https://example.org/final'
    assert context[0]['body']=='隔离实际公司专业生产灯具。' and not context[0]['truncated']
    assert '其他客户' not in str(context)


def test_body_budget_is_fair_and_title_only_is_not_original_content():
    """每页公平分预算并明确截断，不把第二页丢掉或把标题/URL当正文。"""
    operations=[];urls=[]
    for index in range(2):
        url='https://example.org/'+str(index);urls.append(url)
        operations.append({'tool':'fetch_source','status':'completed','arguments':{'url':url},'result':{'sources':[
            {'id':str(index),'url':url,'title':'隔离页','kind':'网页正文','body':'实际公司介绍。'*100}]}})
    context=review_context(operations,urls,limit=100)
    assert len(context)==2 and sum(len(item['body']) for item in context)==100
    assert all(item['truncated'] for item in context)
    only={'tool':'fetch_source','status':'completed','arguments':{'url':urls[0]},'result':{'sources':[
        {'id':'empty','url':urls[0],'title':'隔离页','kind':'网页读取','body':'# 隔离页\nURL: '+urls[0]}]}}
    assert not review_context([only],urls)


def test_final_response_url_review_keeps_actual_body_without_reading_unrelated_sources():
    """最终地址可由用户明确引用；只保留该成功响应原文，不接受失败或同次返回的无关地址。"""
    final='https://example.org/final'
    source={'id':'s','url':final,'title':'原文复核','kind':'网页正文','body':'实际目录中的公开产品类别。'}
    operation={'tool':'fetch_source','status':'completed','arguments':{'url':'http://example.org/original'},
        'result':{'sources':[source,{**source,'id':'other','url':'https://example.org/other'}]}}
    context=review_context([operation],[final])
    assert len(context)==1 and context[0]['id']=='s' and context[0]['body']==source['body']
    assert not review_context([{**operation,'status':'unavailable'}],[final])
    assert not review_context([operation],['https://example.net/final'])
