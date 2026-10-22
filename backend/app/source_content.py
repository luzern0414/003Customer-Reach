"""读取正文质量检查；仅标题/URL的供应商响应不能冒称取得企业正文。"""
import re


def has_content(item: dict) -> bool:
    """item为实际工具来源；返回是否有元数据以外正文，不改变原body、不生成内容；空来源返回False。"""
    title=re.sub(r'\s+','',item.get('title') or '').casefold()
    remaining=[]
    from .industry_navigation import factual_body
    for line in factual_body(item.get('body','') or '').splitlines():
        normalized=re.sub(r'\s+','',line).casefold()
        if not normalized or re.fullmatch(r'[-=*#]+',normalized):continue
        if re.match(r'^url\s*:',line,re.I) or normalized==re.sub(r'\s+','',item.get('url','')).casefold():continue
        heading=re.sub(r'^(?:title:|#{1,6})','',normalized)
        if title and heading==title:continue
        remaining.append(line)
    return bool(remaining)
