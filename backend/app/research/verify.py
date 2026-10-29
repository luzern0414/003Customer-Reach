"""原文核验：quote 必须出现在来源正文中（忽略空白与全半角差异），名称必须出现在 quote 中。"""
import re
import unicodedata

_SPACE = re.compile(r'\s+')


def norm(text: str) -> str:
    return _SPACE.sub('', unicodedata.normalize('NFKC', text or ''))


def company_name(name: str) -> str:
    """统一企业名：去空白，括号统一为全角，去掉首尾标点与“本级”后缀。"""
    value = _SPACE.sub('', name or '').replace('(', '（').replace(')', '）').strip('：:，,。；;')
    # 政府采购中的“本级”指单位本部，与单位本身是同一采购人
    return re.sub(r'（?本级）?$', '', value)


def grounded(quote: str, text: str) -> bool:
    quote = norm(quote)
    return len(quote) >= 2 and quote in norm(text)


def grounded_value(value: str, quote: str, text: str) -> bool:
    return bool(value) and grounded(quote, text) and norm(value) in norm(quote)


def plausible_company(name: str) -> bool:
    """排除个人、占位符与过短的名称。"""
    name = company_name(name)
    if len(re.findall(r'[一-鿿]', name)) < 2:
        return False
    return len(name) >= 4 and not re.search(r'[*＊×]{2}|详见|见公告|^无$|个人|^某|某单位|某公司|匿名', name)
