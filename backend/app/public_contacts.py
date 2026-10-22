"""补充正文算法易遗漏的公开联系区；只保留HTML中实际可见文本，不推断或生成号码。"""
import re
from lxml import html
from trafilatura.utils import decode_file


def contact_blocks(content: bytes) -> str:
    """content为真实公开HTML字节；返回去重联系区原文，隐藏区/脚本/空输入不使用，坏HTML返回空。"""
    if not content:return ''
    # 旧网页常把GBK声明为GB2312；先用已有正文解码器识别，再显式UTF-8解析，避免libxml恢复时悄悄丢联系区。
    try:tree=html.fromstring(decode_file(content).encode('utf-8'),parser=html.HTMLParser(encoding='utf-8'))
    except (ValueError,TypeError):return ''
    selected=tree.xpath("//*[self::div or self::ul or self::table or self::section][contains(translate(@class,'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'contact') or contains(translate(@id,'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'contact') or contains(@class,'lianxi')]")
    result=[]
    for node in selected:
        # 不读取明确隐藏/脚本内容，也不把仅有“联系我们”导航当联系方式。
        parents=[node,*node.iterancestors()]
        if any(x.get('hidden') is not None or x.get('aria-hidden')=='true' or re.search(r'display\s*:\s*none|visibility\s*:\s*hidden',x.get('style',''),re.I) for x in parents):continue
        for element in list(node.xpath('.//script|.//style|.//*[@hidden or @aria-hidden="true"]')):element.drop_tree()
        for element in list(node.xpath('.//*[@style]')):
            if re.search(r'display\s*:\s*none|visibility\s*:\s*hidden',element.get('style',''),re.I):element.drop_tree()
        value=node.text_content().strip()
        if not value or not re.search(r'电话|手机|邮箱|微信|地址|联系人|tel|phone|email|wechat',value,re.I):continue
        if len(value)>4000:value=value[:4000]
        if value not in result and not any(value in previous for previous in result):result.append(value)
        if sum(map(len,result))>=8000:break
    return '\n\n'.join(result)[:8000]
