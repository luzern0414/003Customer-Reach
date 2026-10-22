"""招投标企业主页HTML解析：表格转为逐行文本、公告列表保留原文链接、工商信息取标签值对。

只解析公开页面已展示的内容；遮挡值（****、立即查看）保持遮挡，不做补全。
"""
import html as htmllib
import re
from .tender_parse import normalize_date, MASK_RE

BLOCK_TAGS = re.compile(r'</?(?:div|p|li|ul|ol|section|article|header|footer|h[1-6]|br|dd|dt|dl|span class="section-title")[^>]*>', re.I)


def _text(fragment: str) -> str:
    """fragment为HTML片段；去标签、反转义并压缩空白。"""
    return re.sub(r'\s+', ' ', htmllib.unescape(re.sub(r'<[^>]+>', ' ', fragment or ''))).strip()


def html_text(html: str) -> str:
    """html为页面源码；表格行转为“| 单元格 | … |”，块级元素换行，返回可作为证据正文的纯文本。"""
    body = re.sub(r'<(script|style|svg|noscript)[^>]*>.*?</\1>', '', html or '', flags=re.S | re.I)
    body = re.sub(r'<!--.*?-->', '', body, flags=re.S)

    def row(match):
        cells = [_text(cell) for cell in re.findall(r'<t[hd][^>]*>(.*?)</t[hd]>', match.group(0), re.S | re.I)]
        return '\n| ' + ' | '.join(cells) + ' |\n' if cells else '\n'
    body = re.sub(r'<tr[^>]*>.*?</tr>', row, body, flags=re.S | re.I)
    body = BLOCK_TAGS.sub('\n', body)
    lines = [_text(line) if not line.strip().startswith('|') else line.strip() for line in re.sub(r'<[^>]+>', ' ', body).splitlines()]
    text = '\n'.join(htmllib.unescape(line) for line in lines if line)
    return re.sub(r'\n{3,}', '\n\n', text)


def html_title(html: str) -> str:
    """html为页面源码；返回<title>文本。"""
    found = re.search(r'<title[^>]*>(.*?)</title>', html or '', re.S | re.I)
    return _text(found.group(1)) if found else ''


def html_articles(html: str, base: str = '') -> list[dict]:
    """html为企业主页公告列表；返回标题、原文链接与紧随其后的发布日期。"""
    rows = []
    for match in re.finditer(r'<a[^>]+href="([^"]+)"[^>]*title="([^"]+)"[^>]*class="[^"]*news-item-title[^"]*"', html or '', re.I):
        tail = (html or '')[match.end():match.end() + 6000]
        tail = tail.split('news-item-title', 1)[0]
        date = re.search(r'<time[^>]*>(.*?)</time>', tail, re.S | re.I)
        url = match.group(1)
        if url.startswith('/') and base: url = re.match(r'https?://[^/]+', base).group(0) + url
        rows.append({'title': htmllib.unescape(match.group(2)).strip(), 'url': url, 'published_at': normalize_date(_text(date.group(1))) if date else ''})
    return rows


def html_info(html: str) -> dict:
    """html为工商信息页；返回“标签→值”字典，遮挡值剔除，毫秒时间戳不当日期使用。"""
    result = {}
    for label, value in re.findall(r'class="info-label"[^>]*>(.*?)</div>\s*<div[^>]*class="info-value"[^>]*>(.*?)</div>', html or '', re.S | re.I):
        key, val = _text(label), _text(value)
        if key and val and not MASK_RE.search(val) and not re.fullmatch(r'\d{12,13}', val): result[key] = val[:600]
    return result
