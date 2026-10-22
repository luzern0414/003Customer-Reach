"""已验证商场静态目录的可见正文与店名电话关联；不合成公司名或补区号。"""
import re
from lxml import html
from urllib.parse import urlsplit, urljoin
from trafilatura.utils import decode_file


def is_procurement_list(url: str) -> bool:
    """url为实际来源地址，可空；仅识别已验证HTTPS公告列表路径，查询串/外域/详情页返回False。"""
    uri=urlsplit(url or '')
    return bool(uri.scheme=='https' and uri.netloc=='www.ccgp.gov.cn' and not uri.query and not uri.fragment and
                re.fullmatch(r'/cggg/dfgg/gkzb/(?:index_\d+\.htm)?',uri.path))


def is_branch_list(url: str) -> bool:
    """url为实际来源地址，可空；仅识别乐安居公开分店列表，外域/查询串/详情页返回False。"""
    uri=urlsplit(url or '')
    return bool(uri.scheme in {'http','https'} and re.fullmatch(r'(?:www\.)?leanju\.com(?::8080)?',uri.netloc,re.I)
                and uri.path in {'/subbranch/','/subbranch'} and not uri.query and not uri.fragment)


def branch_key(url: str) -> str:
    """url为实际证据地址；已验证乐安居分店详情返回分店路径，其他来源/查询地址返回空，不推断经营主体。"""
    uri=urlsplit(url or '')
    if uri.scheme not in {'http','https'} or not re.fullmatch(r'(?:www\.)?leanju\.com(?::8080)?',uri.netloc,re.I) or uri.query or uri.fragment:return ''
    return uri.path if re.fullmatch(r'/subbranch-detail/i-\d+\.html',uri.path) else ''


def matches_branches(url: str, scopes: list[set[str]]) -> bool:
    """url为待读真实入口，scopes为满额客户name证据分店key集合；按已知同平台分店筛选，全部未知或其他站点不限制。"""
    key=branch_key(url)
    known=[scope for scope in scopes if scope]
    # 异构名单中的企业官网客户没有商场分店标识，不能使另一客户的已知分店保护失效。
    return not (key and known and not any(key in scope for scope in known))


def branch_directory_text(content: bytes, url: str) -> str:
    """content为真实HTML字节、url为实际分店列表地址；保留可见同站分店href，未知/隐藏链接返回空正文。"""
    if not is_branch_list(url):return ''
    try:tree=html.fromstring(decode_file(content))
    except (ValueError,TypeError):return ''
    uri=urlsplit(url);lines=[];seen=set()
    for anchor in tree.xpath('//a[@href]')[:120]:
        if any(element.get('hidden') is not None or element.get('aria-hidden')=='true' or re.search(r'display\s*:\s*none|visibility\s*:\s*hidden',element.get('style',''),re.I) for element in [anchor,*anchor.iterancestors()]):continue
        link=urljoin(url,anchor.get('href'));target=urlsplit(link)
        if target.scheme not in {'http','https'} or target.netloc.lower()!=uri.netloc.lower() or target.query or target.fragment or not re.fullmatch(r'/subbranch-detail/i-\d+\.html',target.path):continue
        if link in seen:continue
        for element in list(anchor.xpath('.//script|.//style|.//*[@hidden or @aria-hidden="true"]')):element.drop_tree()
        for element in list(anchor.xpath('.//*[@style]')):
            if re.search(r'display\s*:\s*none|visibility\s*:\s*hidden',element.get('style',''),re.I):element.drop_tree()
        label=' '.join((anchor.get('title') or anchor.text_content() or ' '.join(anchor.xpath('.//img/@alt'))).split())[:160]
        if not label:continue
        # 入口记录不是企业事实；分店名称/地址/商户电话必须在后续真实详情重新核验。
        lines.append(f'分店入口：{label}\n分店链接：{link}');seen.add(link)
        if len(lines)>=40:break
    return '\n\n'.join(lines)


def directory_links(body: str, url: str, profile: dict, channel: str) -> list[str]:
    """body/url为本任务目录原文，profile为ICP，channel为原启用渠道；返回实际链接，未知模板/范围不匹配返回空。"""
    if channel=='ccgp':return procurement_links(body,url,profile)
    if channel=='industry_directory':
        from .industry_navigation import navigation_links
        return navigation_links(body,url,profile)
    if channel not in {'mall_directory','directory'} or not is_branch_list(url):return []
    if profile.get('region')!='深圳' or not re.search('灯|照明',' '.join(str(x.get('name','')) for x in profile.get('products',[]))):return []
    uri=urlsplit(url);result=[]
    for link in re.findall(r'(?m)^分店入口：[^\n]+\n分店链接：(https?://[^\s]+)$',body or ''):
        target=urlsplit(link)
        if target.netloc.lower()!=uri.netloc.lower() or target.query or target.fragment or not re.fullmatch(r'/subbranch-detail/i-\d+\.html',target.path):continue
        if link not in result:result.append(link)
    # DOM原采集最多40个分店；聚合层不能先截8条，让已读或别分店入口遮住后续目标。
    return result[:40]


def directory_text(content: bytes, url: str) -> str:
    """content为公开HTML、url为实际响应地址；仅识别已验证乐安居分店结构，未知/隐藏目录返回空。"""
    host=(urlsplit(url).hostname or '').lower()
    if host=='www.ccgp.gov.cn':return procurement_directory_text(content,url)
    if is_branch_list(url):return branch_directory_text(content,url)
    if host not in {'leanju.com','www.leanju.com'} or '/subbranch-detail/' not in urlsplit(url).path:return ''
    # 与主正文同源解码，不能让旧charset令目录补充解析空白而主正文仍显示成功。
    try:tree=html.fromstring(decode_file(content).encode('utf-8'),parser=html.HTMLParser(encoding='utf-8'))
    except (ValueError,TypeError):return ''
    nodes=tree.xpath("//div[contains(concat(' ',normalize-space(@class),' '),' subbranch-det ')]")
    if len(nodes)!=1:return ''
    node=nodes[0]
    if any(element.get('hidden') is not None or element.get('aria-hidden')=='true' or re.search(r'display\s*:\s*none|visibility\s*:\s*hidden',element.get('style',''),re.I) for element in [node,*node.iterancestors()]):return ''
    if not node.xpath(".//div[contains(concat(' ',normalize-space(@class),' '),' de-tit ')][contains(.,'入驻品牌')]"):return ''
    for element in list(node.xpath('.//script|.//style|.//*[@hidden or @aria-hidden="true"]')):element.drop_tree()
    for element in list(node.xpath('.//*[@style]')):
        if re.search(r'display\s*:\s*none|visibility\s*:\s*hidden',element.get('style',''),re.I):element.drop_tree()
    # 保留目录标题、商场地址和原顺序的商户记录，不能只留算法选中的电话长列表而丢分店上下文。
    lines=[line.strip() for text in node.itertext() for line in text.splitlines() if line.strip()]
    body='\n'.join(lines)
    return body if len(body)<=18000 else ''


def mall_listing(name: str, body: str) -> dict:
    """name为原文店名、body为来源完整正文；返回明确分店列表记录，缺标题/连续店名电话则空。"""
    heading=re.search(r'[^\n]{2,40}店\s+入驻品牌',body or '')
    if not heading:return {}
    # 商场介绍/总电话在入驻名单标题之前，不属于租户；只在该列表内部关联店名与Tel。
    lines=[line.strip() for line in body[heading.end():].splitlines() if line.strip()]
    for index,line in enumerate(lines[:-1]):
        if line!=name:continue
        phone=re.fullmatch(r'(?:Tel|电话)[：:]\s*([+\d ()-]{7,30})',lines[index+1],re.I)
        if phone:return {'phone':phone[1].strip()}
    return {}


def mall_city_quote(name: str, city: str, body: str) -> str:
    """name/city为候选原值、body为完整同源目录；仅从单分店介绍取得明确在/位于该市的连续原文。"""
    if not city or not mall_listing(name,body):return ''
    intro=body.split('了解更多',1)[0]
    if '了解更多' not in body:intro=body.split('Tel:',1)[0]
    for line in intro.splitlines():
        if len(line)<=1500 and re.search(r'(?:在|位于)'+re.escape(city)+r'|'+re.escape(city)+r'市',line):
            return line.strip()
    return ''


def mall_address_quote(name: str, value: str, body: str) -> str:
    """name为原商户名、value为地址原值、body为同源目录（均可空）；只接受商户Tel后紧邻独立地址标签。

    商场简介/总地址不能作为独立商户地址；无明确商户地址原文返回空，不补铺位或拼接引文。
    """
    if not mall_listing(name,body):return ''
    heading=re.search(r'[^\n]{2,40}店\s+入驻品牌',body)
    lines=[line.strip() for line in body[heading.end():].splitlines() if line.strip()]
    normalize=lambda text:re.sub(r'\s+','',text or '')
    for index,line in enumerate(lines[:-2]):
        if line!=name or not re.fullmatch(r'(?:Tel|电话)[：:]\s*[+\d ()-]{7,30}',lines[index+1],re.I):continue
        address=re.fullmatch(r'(?:商户|门店|店铺|铺位)地址[：:]\s*(.+)',lines[index+2])
        if address and normalize(value)==normalize(address[1]):return lines[index+2]
    return ''


def procurement_directory_text(content: bytes, url: str) -> str:
    """content为真实列表HTML、url为响应地址；仅保留CCGP已核验静态列表记录与同目录公告href，未知模板返回空。"""
    uri=urlsplit(url)
    if not is_procurement_list(url):return ''
    try:
        decoded=decode_file(content)
        if '\ufffd' in decoded:return ''
        tree=html.fromstring(decoded)
    except (ValueError,TypeError):return ''
    lines=[]
    for node in tree.xpath('//ul[@class="c_list_bid"]/li')[:20]:
        if any(element.get('hidden') is not None or element.get('aria-hidden')=='true' or re.search(r'display\s*:\s*none|visibility\s*:\s*hidden',element.get('style',''),re.I) for element in [node,*node.iterancestors()]):continue
        anchors=node.xpath('./a[@href]')
        if len(anchors)!=1:continue
        anchor=anchors[0];link=urljoin(url,anchor.get('href'));target=urlsplit(link)
        if target.scheme!='https' or target.netloc!='www.ccgp.gov.cn' or target.query or target.fragment or not re.fullmatch(r'/cggg/dfgg/gkzb/\d{6}/t\d{8}_\d+\.htm',target.path):continue
        # 列表只有发现用途；不能把标题、列表采购人标签或平台热线当已确认采购/买方联系。
        title=' '.join((anchor.get('title') or anchor.text_content()).split())
        metadata=' '.join(node.text_content().split())
        lines.append(f'公告标题：{title}\n列表记录：{metadata}\n公告链接：{link}')
    if not lines:return ''
    current=re.search(r'index_(\d+)\.htm$',uri.path)
    page=int(current[1]) if current else 0
    for anchor in tree.xpath('//a[@href]'):
        if not re.fullmatch(r'下一页|下页',anchor.text_content().strip()):continue
        if any(element.get('hidden') is not None or element.get('aria-hidden')=='true' or re.search(r'display\s*:\s*none|visibility\s*:\s*hidden',element.get('style',''),re.I) for element in [anchor,*anchor.iterancestors()]):continue
        link=urljoin(url,anchor.get('href'));target=urlsplit(link)
        match=re.fullmatch(r'/cggg/dfgg/gkzb/index_(\d+)\.htm',target.path)
        # 只保留HTML明确可见的向后页href，不从脚本/页码/日期猜链接，不执行网页脚本。
        if target.scheme=='https' and target.netloc=='www.ccgp.gov.cn' and not target.query and not target.fragment and match and int(match[1])>page:
            lines.append('下一页链接：'+link);break
    return '\n\n'.join(lines)


def announcement_links(body: str, url: str, profile: dict) -> list[str]:
    """body/url为已取得CCGP列表正文，profile为当前地区产品；返回最多2个同目录真实href，字段缺失/不匹配时空。"""
    uri=urlsplit(url)
    if not is_procurement_list(url):return []
    region=profile.get('region','')
    products=' '.join(str(item.get('name','')) for item in profile.get('products',[]))
    if not region or not re.search('灯|照明',products):return []
    result=[]
    for title,record,link in re.findall(r'(?m)^公告标题：([^\n]+)\n列表记录：([^\n]+)\n公告链接：(https://www\.ccgp\.gov\.cn/cggg/dfgg/gkzb/\d{6}/t\d{8}_\d+\.htm)$',body or ''):
        if region not in record or not re.search('灯具|照明|路灯',title) or re.search('显微|医疗|手术|检测',title):continue
        if link not in result:result.append(link)
    return result[:2]


def procurement_links(body: str, url: str, profile: dict) -> list[str]:
    """body/url为真实CCGP列表，profile含地区与产品；按匹配公告、一个原文下一页排序，读取方过滤已尝试项。"""
    matches=announcement_links(body,url,profile)
    uri=urlsplit(url)
    if not is_procurement_list(url):return []
    if not profile.get('region') or not re.search('灯|照明',' '.join(str(x.get('name','')) for x in profile.get('products',[]))):return []
    current=re.search(r'index_(\d+)\.htm$',uri.path);page=int(current[1]) if current else 0
    links=re.findall(r'(?m)^下一页链接：(https://www\.ccgp\.gov\.cn/cggg/dfgg/gkzb/index_(\d+)\.htm)$',body or '')
    return [*matches,*[link for link,index in links if int(index)>page][:1]]
