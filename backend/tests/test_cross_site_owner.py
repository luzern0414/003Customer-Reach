"""异构客户名单的分店与跨站选页验证；仅隔离数据，不冒充真实获客。"""
from app.public_directory import matches_branches
from app.public_website import website_links,prioritize_websites
from app.industry_navigation import WEBSITE_MARKER,NAVIGATION_MARKER

def test_mixed_scopes_keep_known_branch_protection():
    """无参数；异站客户的空scope不能给已知商户其他分店授权，全部未知仍不限制。"""
    own='/subbranch-detail/i-24.html';other='/subbranch-detail/i-26.html'
    scopes=[set(),{own},set()]
    assert not matches_branches('http://www.leanju.com:8080'+other,scopes)
    assert matches_branches('http://www.leanju.com:8080'+own,scopes)
    assert matches_branches('https://example.org'+other,scopes)
    assert matches_branches('http://www.leanju.com:8080'+other,[set(),set()])

def test_link_ranking_uses_actual_owner_not_other_uncontactable_customer():
    """无参数；同主体正文绑定链接，未知owner不借另一个客户根域缺口加分。"""
    name='隔离排序照明有限公司';url='https://owner.example.org/company';external='https://independent.example.com/'
    page={'id':'s','url':url,'title':name,'kind':'网页正文','channel':'official','body':name+'经销灯具。\n'+NAVIGATION_MARKER+'\n目录入口：联系方式\n目录链接：https://owner.example.org/contact\n'+WEBSITE_MARKER+'\n网站入口：公司网站\n网站链接：'+external}
    owner={'display_name':name,'facts':{'phone':{'value':'13500001111'}},'evidence':[{'field':'name','value':name,'url':url,'source_id':'s'}]}
    absent={'display_name':'隔离无联系客户','facts':{},'evidence':[{'field':'name','value':'隔离无联系客户','url':'https://elsewhere.example.net/'}]}
    links=website_links([page],[owner,absent],['official'])
    assert links[0]['url']!=external
    ranked=prioritize_websites(links,[owner,absent],2,[page])
    assert ranked[0]['url']==external
    assert prioritize_websites(links,[{**owner,'facts':{}},absent],2,[page])[0]['url']==links[0]['url']
    unrelated={'url':'https://unbound.example.com/','channel':'official'}
    assert prioritize_websites([unrelated,*links],[owner,absent],2,[page])[0]['url']==external
