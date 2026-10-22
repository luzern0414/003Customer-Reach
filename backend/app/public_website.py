"""从实际可见企业网站链接发现补查页；不把外链标签当企业事实或身份认证。"""
import re
from copy import deepcopy
from urllib.parse import urljoin,urlsplit
from lxml import html
from trafilatura.utils import decode_file
from .industry_navigation import visible,WEBSITE_MARKER,NAVIGATION_MARKER,site_family


def website_text(content: bytes, url: str, title: str='') -> str:
    """content为实际HTML、url为最终响应地址、title为实际页面标题可空；保留最多4个网站字段/标题主体原href，空/隐藏/页尾/危险地址返回空，不访问网络。"""
    try:tree=html.fromstring(decode_file(content))
    except (TypeError,ValueError):return ''
    rows=[];seen=set()
    label_pattern=r'公司网址|企业网址|公司网站|企业网站|官方网站|企业官网|公司官网'
    for node in tree.xpath('//a[@href]')[:1200]:
        if not visible(node):continue
        if any(parent.tag=='footer' or re.search(r'footer|copyright|friend[-_]?link',parent.get('class','')+' '+parent.get('id',''),re.I) for parent in node.iterancestors()):continue
        parent=node.getparent()
        clean=deepcopy(node);parent_clean=deepcopy(parent) if parent is not None else None
        for holder in [clean,parent_clean]:
            if holder is None:continue
            for child in list(holder.xpath('.//script|.//style|.//template|.//noscript|.//*[@hidden or @aria-hidden="true"]')):child.drop_tree()
            for child in list(holder.xpath('.//*[@style]')):
                if not visible(child):child.drop_tree()
        text=' '.join(clean.text_content().split())
        context=' '.join(parent_clean.text_content().split()) if parent_clean is not None else ''
        explicit=re.search(label_pattern,text) or (len(context)<=300 and parent_clean is not None and
            len(parent_clean.xpath('.//a[@href]'))==1 and re.search(label_pattern,context))
        legal=re.fullmatch(r'[\u4e00-\u9fffA-Za-z0-9（）()·-]{2,100}(?:有限公司|商行|经营部|工厂)',text)
        if legal and re.sub(r'\s+','',text) not in re.sub(r'\s+','',title):legal=None
        if not explicit and not legal:continue
        raw=node.get('href','').strip()
        try:
            link=urljoin(url,raw);target=urlsplit(link)
            allowed=target.scheme in {'http','https'} and target.hostname and not target.username and not target.password and target.port is None and not target.fragment
        except ValueError:continue
        if not allowed or link==url or link in seen or len(link)>2000:continue
        # 普通登录/分享/跳转链接不会因相邻“公司网站”字段获得许可。
        if re.search(r'/(?:login|signin|oauth|share|redirect)(?:[/.?]|$)',target.path,re.I):continue
        seen.add(link);rows.append('网站入口：'+(explicit.group() if explicit else text)+'\n网站链接：'+link)
        if len(rows)==4:break
    return WEBSITE_MARKER+'\n'+'\n\n'.join(rows) if rows else ''


def website_links(sources: list[dict], leads: list[dict], enabled: list[str]) -> list[dict]:
    """sources为允许正文、leads为已存客户、enabled为启用渠道（均可空）；返回原name或真实来源链绑定的链接，仍需读页/核验。"""
    from .industry_navigation import navigation_owner
    from .source_catalog import reference_channel,matches_channel
    result=[];seen=set()
    for source in sources:
        body=source.get('body','')
        if source.get('kind')!='网页正文' or not any(marker in body for marker in [WEBSITE_MARKER,NAVIGATION_MARKER]):continue
        owners=[lead.get('display_name','') for lead in leads if navigation_owner(lead,source,sources)]
        if not owners:continue
        records=re.findall(r'(?m)^网站入口：([^\n]+)\n网站链接：(https?://[^\s]+)$',body.split(WEBSITE_MARKER,1)[1]) if WEBSITE_MARKER in body else []
        contacts=re.findall(r'(?m)^目录入口：(联系方式|联系我们|公司联系|联系公司|联系商家|联系店铺)\n目录链接：(https?://[^\s]+)$',body.split(NAVIGATION_MARKER,1)[1]) if NAVIGATION_MARKER in body else []
        for label,link in [*contacts,*records]:
            if (label,link) in contacts:
                # 同一平台不等于同一商户；联系导航只读原公司命名空间，不借另一个公司或平台客服入口。
                try:
                    target,origin=urlsplit(link),urlsplit(source['url'])
                    if target.username or target.password or target.fragment or (target.scheme,target.hostname,target.port)!=(origin.scheme,origin.hostname,origin.port):continue
                except ValueError:continue
                family=site_family(origin.hostname or '')
                if family:
                    shop=re.match(r'/(\d+)(?:/|$)',origin.path) if origin.hostname=='shop.jc001.cn' else None
                    if shop:
                        if not target.path.startswith('/'+shop[1]+'/'):continue
                    elif target.path!=origin.path:continue
                elif origin.hostname=='www.yunfale.com':
                    if not target.path.startswith(origin.path):continue
            # 完整企业名链接仅能补该主体的另一个页面；推荐企业不能借页面owner获得许可。
            if re.search(r'(?:有限公司|商行|经营部|工厂)$',label) and re.sub(r'\s+','',label) not in {re.sub(r'\s+','',name) for name in owners}:continue
            if (label,link) in contacts and source.get('channel'):
                channel=source['channel']
                if channel not in enabled or not matches_channel(channel,link):continue
            else:channel=reference_channel(link,enabled)
            if channel and link not in seen:
                seen.add(link);result.append({'url':link,'channel':channel})
    # 每页DOM提取已有限额；此处不能先截断，让已尝试入口挡住后面真实网站或使Broker拒绝它。
    return result


def prioritize_websites(links: list[dict], leads: list[dict], site_target: int, sources: list[dict] | None=None) -> list[dict]:
    """links为已许可链接，leads为已存客户，site_target为来源要求，sources为允许正文可空；按原链接所属客户的缺口排序，不授权限或生成URL。"""
    from .contact_view import contact_view,evidence_sites
    priorities={}
    enabled=list(dict.fromkeys(item['channel'] for item in links))
    bound=[(lead,{item['url'] for item in website_links(sources,[lead],enabled)}) for lead in leads] if sources else []
    for item in links:
        # 多主体必须从真实可见导航重新绑定owner，不能拿A链接给B的跨站缺口加分。
        owners=[lead for lead,urls in bound if item['url'] in urls] if sources else leads if len(leads)==1 else []
        rank=2
        for lead in owners:
            contacts=contact_view(lead.get('facts') or {},lead.get('evidence') or [])
            if not contacts['usable_fields']:rank=0;break
            current=evidence_sites(lead.get('evidence') or [])
            if len(current)<site_target and len(evidence_sites([*(lead.get('evidence') or []),{'url':item['url']}]))>len(current):rank=min(rank,1)
        priorities[item['url']]=rank
    return sorted(links,key=lambda item:priorities[item['url']])
