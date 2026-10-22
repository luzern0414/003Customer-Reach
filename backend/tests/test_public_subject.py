"""企业页主标题来自真实可见DOM，不能由网址编号、查询条件或隐藏标题补主体。"""
from app.public_subject import subject_title
from app.evidence_role import scoped_role


def test_unique_visible_legal_heading_is_subject_not_platform_title():
    """已读具体模板保留唯一法人标题；多主体/隐藏/目录不修改原标题。"""
    url='https://www.b2b168.com/c168-123.html'
    content='<h1>隔离原文照明有限公司</h1><h2>公司介绍</h2><h3 hidden>其他隐藏有限公司</h3>'
    assert subject_title(content.encode(),url)=='隔离原文照明有限公司'
    assert not subject_title((content+'<h2>竞争实体有限公司</h2>').encode(),url)
    assert not subject_title('<h1 hidden>隔离原文照明有限公司</h1>'.encode(),url)
    assert not subject_title('<h1><span hidden>隐藏</span>隔离原文照明有限公司</h1>'.encode(),url).startswith('隐藏')
    assert not subject_title(content.encode(),'https://www.b2b168.com/dengshi/')
    assert not subject_title(content.encode(),'https://example.org/c168-123.html')
    assert not subject_title('<footer><h1>平台运营有限公司</h1></footer>'.encode(),url)


def test_business_mode_requires_single_subject_and_same_source_name():
    """经营模式字段可证明声明角色，但主体/同源姓名缺失仍拒绝，不能从公司后缀推制造。"""
    name='隔离原文照明有限公司';quote='经营模式：生产加工'
    assert scoped_role(name,'生产加工',quote,name,True,body=name+'\n'+quote)
    assert scoped_role(name,'生产加工','经营模式\n生产加工',name,True,body=name+'\n经营模式\n生产加工')
    assert not scoped_role(name,'生产加工','经营模式：不是生产加工',name,True,body=name+'\n经营模式：不是生产加工')
    assert not scoped_role(name,'生产加工',quote,'其他主体有限公司',True,body='其他主体有限公司\n'+quote)
    assert not scoped_role(name,'生产加工',quote,name,False,body=name+'\n'+quote)
    assert not scoped_role(name,'生产加工',quote+'其他主体有限公司',name,True,body=name+'\n'+quote)
    assert scoped_role(name,'经销批发','企业性质：个体经营 - 经销批发',name,True)
    assert not scoped_role(name,'经销批发','企业性质：个体经营 - 不是经销批发',name,True)
    assert scoped_role(name,'生产加工','| 企业类型 | 生产加工 | 公司注册地 | 深圳 |',name,True)
    assert not scoped_role(name,'生产加工','| 企业类型 | 不是生产加工 |',name,True)


def test_legacy_company_sections_require_matching_visible_owner():
    """实读旧模板栏目双重关联；竞争/隐藏/跨块/单栏不得修补平台标题。"""
    url='https://www.b2b168.com/c168-123.html'
    markup='<h1>八方资源网</h1><div class="Cright"><ul id="gsjj">隔离照明有限公司简介</ul><ul id="jbzl">隔离照明有限公司基本资料</ul></div>'
    assert subject_title(markup.encode(),url)=='隔离照明有限公司'
    assert not subject_title(markup.replace('有限公司基本资料','商行基本资料').encode(),url)
    assert not subject_title(markup.replace('id="jbzl"','hidden id="jbzl"').encode(),url)
    assert not subject_title(markup.replace('<ul id="jbzl">','</div><div class="Cright"><ul id="jbzl">').encode(),url)
    assert not subject_title(markup.replace('id="gsjj"','id="other"').encode(),url)
