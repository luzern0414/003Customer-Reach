"""具体企业页的原始主标题；不从网址或查询词合成公司名。"""
import re
from copy import deepcopy
from urllib.parse import urlsplit
from lxml import html
from trafilatura.utils import decode_file
from .industry_navigation import visible


def subject_title(content: bytes, url: str) -> str:
    """content为实际HTML、url为最终地址；仅已读八方具体企业模板的唯一可见法人标题，其他/多主体返回空。"""
    uri=urlsplit(url)
    if uri.hostname!='www.b2b168.com' or not re.fullmatch(r'/c168-\d+\.html',uri.path):return ''
    try:tree=html.fromstring(decode_file(content))
    except (ValueError,TypeError):return ''
    names=[]
    for node in tree.xpath('//h1|//h2|//h3'):
        if not visible(node):continue
        if any(parent.tag=='footer' or re.search(r'footer|copyright|friend[-_]?link',parent.get('class','')+' '+parent.get('id',''),re.I) for parent in node.iterancestors()):continue
        clean=deepcopy(node)
        for child in list(clean.xpath('.//script|.//style|.//template|.//noscript|.//*[@hidden or @aria-hidden="true"]')):child.drop_tree()
        for child in list(clean.xpath('.//*[@style]')):
            if not visible(child):child.drop_tree()
        text=' '.join(clean.text_content().split())
        if re.search('版权所有|友情链接|推荐企业|相关企业',text):continue
        if re.fullmatch(r'[\u4e00-\u9fffA-Za-z0-9（）()·-]{2,100}(?:有限公司|商行|经营部|工厂)',text):names.append(text)
    names=list(dict.fromkeys(names))
    if not names:
        # 已实读旧企业模板没有企业h1；两个同一内容块的可见栏目标题必须指向同一完整主体。
        sections=[]
        for section_id,suffix in [('gsjj','简介'),('jbzl','基本资料')]:
            nodes=tree.xpath('//ul[@id=$key]',key=section_id)
            if len(nodes)!=1 or not visible(nodes[0]):return ''
            node=nodes[0]
            if node.xpath('.//script|.//style|.//*[@hidden or @aria-hidden="true"]'):return ''
            text=' '.join(node.text_content().split())
            match=re.fullmatch(r'([\u4e00-\u9fffA-Za-z0-9（）()·-]{2,100}(?:有限公司|商行|经营部|工厂))'+suffix,text)
            if not match:return ''
            sections.append((match.group(1),node.getparent()))
        if sections[0][0]==sections[1][0] and sections[0][1] is sections[1][1] and 'Cright' in (sections[0][1].get('class','').split()):
            return sections[0][0]
    return names[0] if len(names)==1 else ''
