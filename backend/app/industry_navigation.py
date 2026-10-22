"""行业目录静态导航：只发现真实可见链接，不提取或推断客户事实。"""
import re
from copy import deepcopy
from urllib.parse import urljoin, urlsplit
from lxml import html
from trafilatura.utils import decode_file

NAVIGATION_POLICY='industry-navigation-19'
NAVIGATION_MARKER='[公开目录导航，仅用于发现页面，不是客户事实]'
WEBSITE_MARKER='[企业网站链接，仅用于发现页面，不是客户事实]'
HOSTS={'www.yunfale.com','www.b2b168.com','www.jc001.cn'}
SITE_FAMILIES={'b2b168.com','jc001.cn'}


def site_family(host: str) -> str:
    """host为实际解析主机，可空；仅已验证平台根域及其真实子域返回平台根域，不按字符串包含匹配。"""
    return next((domain for domain in SITE_FAMILIES if host==domain or host.endswith('.'+domain)),'')


def visible(node) -> bool:
    """node为真实DOM节点；隐藏、脚本或模板节点及其后代返回False，不执行CSS或脚本。"""
    return not any(element.tag in {'script','style','template','noscript'} or
        element.get('hidden') is not None or element.get('aria-hidden','').lower()=='true' or
        re.search(r'display\s*:\s*none|visibility\s*:\s*hidden',element.get('style',''),re.I)
        for element in [node,*node.iterancestors()])


def same_site(url: str, parent: str) -> bool:
    """url为实际href解析结果、parent为响应地址；云发了严格同源，新目录仅注册平台域默认端口，异常/凭据拒绝。"""
    try:
        target,origin=urlsplit(url),urlsplit(parent)
        family=site_family(origin.hostname or '')
        allowed_origin=origin.hostname in HOSTS or bool(family)
        if origin.hostname=='www.yunfale.com' and target.path.startswith('/about/'):return False
        same_origin=target.scheme==origin.scheme and target.hostname==origin.hostname and target.port==origin.port
        # 新目录的分类/商户在子域；仅真实原href同平台根域及默认端口，仍由Broker逐跳检查公网/权限。
        same_family=bool(family and site_family(target.hostname or '')==family and target.port is None and origin.port is None)
        if family=='b2b168.com' and (target.hostname=='info.b2b168.com' or '/shop/supply/' in target.path or
            re.fullmatch(r'/s\d+\.html',target.path) or
            (target.hostname=='www.b2b168.com' and target.path.startswith('/ad/'))):return False
        if family=='jc001.cn' and (target.hostname in {'news.jc001.cn','agent.jc001.cn','supply.jc001.cn','goods.jc001.cn',
            'm.jc001.cn','wx.jc001.cn','mail.jc001.cn','service.jc001.cn','video.jc001.cn'} or
            re.match(r'/(?:article/|ad_go\.php|zt/|job/|goods/)',target.path)):return False
        return bool(allowed_origin and target.scheme in {'http','https'} and (same_origin or same_family) and
            not target.username and not target.password and not target.fragment and len(url)<=2000 and
            not target.path.startswith('/member/'))
    except ValueError:return False


def relevance(label: str, profile: dict) -> int:
    """label为原标签、profile为本轮ICP；只排序读取候选，不将匹配当买家或采购证明；空画像得0。"""
    region=str(profile.get('region') or '')
    products=' '.join(str(item.get('name','')) for item in profile.get('products',[]))
    label=re.sub(r'企业资料可查看','',label).strip()
    if re.search('登录|注册|会员|客服|广告|招商|诚招|加盟|加入|招募|帮助|隐私|条款|留言|发布|求职',label):return -1000
    score=40 if region and region in label else 0
    regional=re.fullmatch(r'(.+?)(?:灯饰|室外照明灯具|室内照明灯具|主流灯具|专门用途灯具|舞台灯具/节日灯)黄页',label)
    if regional and region and region not in regional[1]:score-=40
    if re.fullmatch('企业名录|行业目录|行业分类|企业分类',label):score+=20
    if re.search('企业库|黄页|商户目录',label):score+=14
    if re.search('经销商|零售|门店',label):score+=12
    if re.search('联系方式|联系我们|公司介绍|关于我们',label):score+=10
    if re.search('灯|照明',products) and re.search('灯|照明',label):score+=6
    if re.search('经销|零售|批发|商行|商户|企业|黄页',label):score+=1
    return score


def heading_context(anchor) -> str:
    """anchor为可见实际DOM链接；只取最近小型分类块的唯一可见灯具标题，空/多个标题/大块不关联。"""
    for parent in list(anchor.iterancestors())[:4]:
        if parent.tag in {'html','body'}:break
        if len(' '.join(parent.text_content().split()))>400:continue
        labels=[];explicit=[]
        for node in parent.xpath('./h1|./h2|./h3|./h4|./dt|./strong|./b|./a|./span|./div/a|./div/span'):
            if node is anchor or not visible(node):continue
            clean=deepcopy(node)
            for child in list(clean.xpath('.//script|.//style|.//template|.//noscript|.//*[@hidden or @aria-hidden="true"]')):child.drop_tree()
            for child in list(clean.xpath('.//*[@style]')):
                if not visible(child):child.drop_tree()
            text=' '.join(''.join(clean.itertext()).split())
            if node.tag in {'h1','h2','h3','h4','dt','strong','b'} and 1<len(text)<=24:explicit.append(text)
            if 1<len(text)<=24 and re.search('灯|照明|地板|洁具|吊顶|管材|卫浴|门窗|涂料|瓷砖|橱柜|石材|钢材',text) and not re.search('公司|商行|门店|企业',text):labels.append(text)
        if len(set(explicit))>1:return ''
        labels=list(dict.fromkeys(labels))
        if len(labels)==1:return labels[0]
        if len(labels)>1:return ''
    return ''


def navigation_priority(label: str, context: str, profile: dict) -> int:
    """label/context为实际标签与同分类标题、profile为ICP；类别仅优先读取，不作为客户证据，禁止标签不能被标题抵消。"""
    score=relevance(label,profile)
    if score<=0:return score
    products=' '.join(str(item.get('name','')) for item in profile.get('products',[]))
    region=str(profile.get('region') or '')
    actionable=(region and region in label) or re.search('经销商|零售|门店|企业库|黄页|目录',label)
    return score+(60 if actionable and re.search('灯|照明',products) and re.search('灯|照明',context) else 0)


def relevant_detail(label: str, link: str, parent: str, profile: dict, context: str='') -> bool:
    """label/link/parent为原导航及来源、profile为ICP、context为同DOM小块可见分类（空表示未知）；仅选页、不判买家资格或按编号猜品类。"""
    products=' '.join(str(item.get('name','')) for item in profile.get('products',[]))
    if not re.search('灯|照明',products):return True
    # 地区吻合不抵消明确品类不符；只排目录分类，未知/混合企业身份仍由正文核验。
    category_label=context or label
    categories=re.findall(r'(地板|洁具|吊顶|管材|卫浴|门窗|涂料|瓷砖|橱柜|石材|钢材)(?:企业|企业黄页|黄页|公司黄页)?$',category_label)
    if categories and not re.search('灯|照明',category_label) and not any(category in products for category in categories):return False
    home=re.search('吊灯|壁灯|吸顶灯|家居|家用|室内',products)
    special=re.search('车灯|汽车照明|车用灯|舞台灯|航标灯|交通信号灯|医疗照明|显微照明',label)
    if home and special and special.group() not in products:return False
    uri=urlsplit(link);origin=urlsplit(parent)
    # 首页多个分类都写“深圳”，没有保留下来的明文分类就不能拿地区命中去遍历全部品类。
    if origin.hostname=='shop.jc001.cn' and origin.path=='/' and uri.hostname=='shop.jc001.cn' and re.match(r'/gc-\d+-r\d+-\d+/',uri.path) and label==profile.get('region') and not context:return False
    lighting_directory=origin.hostname=='dengshi.b2b168.com' or '/dengshi/' in origin.path
    if '/company/detail/' in uri.path:return bool(re.search('灯|照明',label))
    b2b_company=(uri.hostname!='www.b2b168.com' and site_family(uri.hostname or '')=='b2b168.com' and uri.path=='/') or bool(uri.hostname=='www.b2b168.com' and re.fullmatch(r'/c168-\d+\.html',uri.path))
    if b2b_company and not lighting_directory:return bool(re.search('灯|照明',label))
    if site_family(uri.hostname or '')=='b2b168.com' and not lighting_directory:
        if not re.search('灯|照明',label) and not re.fullmatch(r'企业黄页|企业名录|企业库|联系方式|联系我们|公司介绍|关于我们',label):return False
    return True


def frontier_allowed(url: str, attempts: list[dict], entries: list[dict], selected: bool) -> bool:
    """url为真实候选链接、attempts为本任务读账本、entries为启用入口、selected表示已有客户；发现阶段单平台4次后先试未读独立平台。"""
    if selected:return True
    def platform(value):
        host=urlsplit(value or '').hostname or ''
        return site_family(host) or host
    platforms={platform(entry['url']) for entry in entries if entry.get('channel')=='industry_directory'}
    target=platform(url)
    if len(platforms)<2 or target not in platforms:return True
    counts={key:sum(item.get('attempts') or 1 for item in attempts if platform(item.get('url'))==key) for key in platforms}
    return counts[target]<4 or not any(key!=target and counts[key]==0 for key in platforms)


def subject_link(url: str, body: str, names: list[str]) -> bool:
    """url为已取得导航链接、body为带真实导航附录的正文、names为已存完整名，可空；标签明确含主体才豁免发现配额，不证明角色或归属。"""
    if not names or NAVIGATION_MARKER not in (body or ''):return False
    normalize=lambda text:re.sub(r'\s+','',text)
    for label,link in re.findall(r'(?m)^目录入口：([^\n]+)\n目录链接：(https?://[^\s]+)',body.split(NAVIGATION_MARKER,1)[1]):
        if link==url and any(normalize(name) in normalize(label) for name in names if name):return True
    return False


def navigation_owner(lead: dict, source: dict, sources: list[dict]) -> bool:
    """lead为已存主体、source为实际网页、sources为本任务允许正文（均可空）；仅返回导航的主体绑定。

    优先原同源name证明；九正单商户页可沿原名称证据所在目录的完整名href、真实页标题/正文及
    同商户通用导航建立最多三跳联系来源链。无链/争议名称/其他主体/其他商户返回False；不生成Fact或别名。
    """
    from .evidence_role import same_subject_page
    name=lead.get('display_name','');previous=lead.get('evidence') or []
    if not name or (lead.get('facts') or {}).get('name',{}).get('verification') in {'disputed','inactive'}:return False
    if same_subject_page(name,previous,{source.get('id',''):source}):return True
    normalize=lambda value:re.sub(r'\s+','',value or '')
    entity=normalize(name)
    rows=[row for row in sources if row.get('kind')=='网页正文']
    anchored={row.get('id') for row in rows if entity in normalize(factual_body(row.get('body',''))) and any(
        cite.get('field')=='name' and normalize(cite.get('value',''))==entity and
        (cite.get('source_id')==row.get('id') or cite.get('url')==row.get('url')) for cite in previous)}
    def bound(page,depth,visited):
        # 数字路径只约束已证明的商户命名空间，不能从编号认定公司身份。
        if depth>3 or page.get('id') in visited:return False
        uri=urlsplit(page.get('url',''))
        shop=re.match(r'/(\d+)(?:/|$)',uri.path) if uri.hostname=='shop.jc001.cn' else None
        title=page.get('title','')
        if not shop or entity not in normalize(title) or entity not in normalize(factual_body(page.get('body',''))) or re.search('目录|名录|列表|分店',title):return False
        # 同完整名字的标题重复子串可用于导航，另一个法律主体标题仍拒绝；不据此授别名或字段归属。
        title_names=re.findall(r'[\u4e00-\u9fffA-Za-z0-9（）()·]{2,80}(?:有限公司|商行|经营部)',title)
        if any(normalize(item) not in entity for item in title_names):return False
        for parent in rows:
            body=parent.get('body','')
            if NAVIGATION_MARKER not in body:continue
            for label,link in re.findall(r'(?m)^目录入口：([^\n]+)\n目录链接：(https?://[^\s]+)',body.split(NAVIGATION_MARKER,1)[1]):
                if link!=page.get('url') or not same_site(link,parent.get('url','')):continue
                if normalize(label)==entity and parent.get('id') in anchored:return True
                if label not in {'公司介绍','关于我们','联系方式','联系我们','公司联系','联系公司','联系商家','联系店铺'}:continue
                origin=urlsplit(parent.get('url',''))
                if (origin.scheme,origin.hostname,origin.port)!=(uri.scheme,uri.hostname,uri.port) or not re.match(r'/'+re.escape(shop[1])+r'(?:/|$)',origin.path):continue
                if bound(parent,depth+1,{*visited,page.get('id')}):return True
        return False
    return bound(source,0,set())


def enrichment_allowed(url: str, source: dict, leads: list[dict], sources: list[dict] | None=None) -> bool:
    """url为原导航、source为原来源、leads为满额客户（可空）、sources为允许正文可空；仅选择补读，不授Fact资格。"""
    if not leads:return True
    target=urlsplit(url);origin=urlsplit(source.get('url',''))
    shop=re.match(r'/(\d+)(?:/|$)',target.path) if target.hostname=='shop.jc001.cn' else None
    yunfale=target.hostname=='www.yunfale.com' and '/company/detail/' in target.path
    b2b=site_family(target.hostname or '')=='b2b168.com' and ((target.hostname!='www.b2b168.com' and target.path=='/') or re.fullmatch(r'/c168-\d+\.html',target.path))
    if not (shop or yunfale or b2b):return True
    if subject_link(url,source.get('body',''),[lead.get('display_name','') for lead in leads]):return True
    owners=[lead for lead in leads if navigation_owner(lead,source,sources or [source])]
    # 已存主体页中的通用“公司介绍”标签可补本商户，不能借单主体标题读它推荐的其他公司。
    if not owners or (target.scheme,target.hostname,target.port)!=(origin.scheme,origin.hostname,origin.port):return False
    if shop:return bool(re.match(r'/'+re.escape(shop[1])+r'(?:/|$)',origin.path))
    if yunfale:return target.path.startswith(origin.path)
    return target.path==origin.path


def navigation_text(content: bytes, url: str, profile: dict) -> str:
    """content为真实HTML字节、url为响应地址、profile为ICP；输出最多40条原href/标签，未知站点或无匹配返回空。"""
    if urlsplit(url).hostname not in HOSTS and not site_family(urlsplit(url).hostname or ''):return ''
    try:tree=html.fromstring(decode_file(content))
    except (ValueError,TypeError):return ''
    entries=[];seen=set()
    for anchor in tree.xpath('//a[@href]')[:1200]:
        if not visible(anchor):continue
        try:link=urljoin(url,anchor.get('href','').strip())
        except ValueError:continue
        if link==url or link in seen or not same_site(link,url):continue
        for element in list(anchor.xpath('.//script|.//style|.//template|.//noscript|.//*[@hidden or @aria-hidden="true"]')):element.drop_tree()
        for element in list(anchor.xpath('.//*[@style]')):
            if not visible(element):element.drop_tree()
        label=' '.join(anchor.text_content().split()) or ' '.join(anchor.xpath('.//img/@alt'))
        label=label.strip()[:160]
        context=heading_context(anchor)
        # 照明场景不遍历首页随机推荐企业；优先真实照明标签，详情正文仍须独立核验产品/地区/买家角色。
        if not relevant_detail(label,link,url,profile,context):continue
        if not label or relevance(label,profile)<=0:continue
        seen.add(link);entries.append((label,link,context))
    entries.sort(key=lambda item:navigation_priority(item[0],item[2],profile),reverse=True)
    records=[f'目录入口：{label}\n目录链接：{link}'+('\n目录分类：'+context if context else '') for label,link,context in entries[:40]]
    return NAVIGATION_MARKER+'\n'+'\n\n'.join(records) if records else ''


def navigation_links(body: str, url: str, profile: dict) -> list[str]:
    """body/url为本任务原文及地址、profile为ICP；返回DOM已采集的最多40个合格原href，去重/主体过滤后由图按原预算选页，不合成链接。"""
    if NAVIGATION_MARKER not in (body or ''):return []
    records=[]
    for label,link,context in re.findall(r'(?m)^目录入口：([^\n]+)\n目录链接：(https?://[^\s]+)(?:\n目录分类：([^\n]+))?$',body.split(NAVIGATION_MARKER,1)[1]):
        if not relevant_detail(label,link,url,profile,context):continue
        if same_site(link,url) and navigation_priority(label,context,profile)>0 and link!=url and link not in [item[1] for item in records]:records.append((label,link,context))
    records.sort(key=lambda item:navigation_priority(item[0],item[2],profile),reverse=True)
    return [link for _,link,_ in records[:40]]


def factual_body(body: str) -> str:
    """body为带导航附录的正文；返回附录前的原正文，导航标签/URL不能进入客户事实提取。"""
    return re.split(re.escape(NAVIGATION_MARKER)+'|'+re.escape(WEBSITE_MARKER),body or '',maxsplit=1)[0].rstrip()


def is_index(url: str) -> bool:
    """url为真实响应地址；只识别已核验主页/企业入口，详情或查询页不跳过客户提取。"""
    uri=urlsplit(url)
    # 已真实读到的行业/企业分类页只负责发现；商户数字详情和商户子域根页仍需事实提取。
    if uri.hostname=='dengju.jc001.cn' and uri.path in {'/','/shop/'}:return True
    if uri.hostname=='shop.jc001.cn' and (uri.path=='/' or re.fullmatch(r'/(?:gc-\d+(?:-r\d+-\d+)*|st-\d+)/?',uri.path)):return True
    paths={'/','/company/'} if uri.hostname=='www.yunfale.com' else {'/'}
    return bool(uri.hostname in HOSTS and uri.path in paths and not uri.query and not uri.fragment)


def navigation_only(url: str, body: str) -> bool:
    """url为实际响应URL、body为已读正文（可空）；仅已知索引且没有完整主体介绍时返回True。

    该判定只省略纯导航的模型分析，不授予客户、角色、地区或联系资格。主体介绍只认原连续文本，
    派生导航附录不参与；详情/未知路径返回False并保留原提取流程，不推断网页未展示的资料。
    """
    if not is_index(url):return False
    text=factual_body(body)
    # 行业分类页也可能有完整公司业务简介，不能仅依据gc/st路径将其全部当成入口元数据。
    description=re.search(r'[\u4e00-\u9fffA-Za-z0-9（）()·]{2,80}(?:有限公司|商行|经营部|灯饰店|照明店)'
        r'[，,\s]*(?:是|成立|位于|专业|主营|主要|经营|从事|经销|零售|代理|批发)[^\n]{12,}',text)
    return not bool(description)
