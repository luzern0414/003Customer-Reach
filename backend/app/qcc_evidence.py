"""企查查 JSON 证据路径与精确企业名；不按正文子串授予结构化字段。"""
import json
import re

NAME_KEYS = {'企业名称', '公司名称', 'name', 'company_name', 'Name'}
FIELD_KEYS = {'name':NAME_KEYS,'credit_code':{'统一社会信用代码','credit_code','CreditCode'},
              'address':{'注册地址','address','Address'},'industry':{'国标行业','industry','行业'},
              'business':{'经营范围','business','经营描述'},'short_name':{'企业简称','short_name'},
              'stock_code':{'股票代码','stock_code'},'phone':{'电话','phone'},'email':{'邮箱','email'},
              'website':{'官网','website'},'headcount':{'人员规模','参保人数','headcount'},'revenue':{'营业收入','revenue'},
              'detail':{'法定代表人','注册资本','实缴资本','成立日期','工商注册号','登记状态','企业类型','登记机关','营业期限','核准日期'}}
PATH_TOKEN = re.compile(r'\.([^\.\[\]:=\s]+)|\[(\d+)\]')


def authorized(source) -> bool:
    meta = source.source_meta or {}
    return source.kind == '授权数据' and source.channel == 'qcc_mcp' and meta.get('origin') == 'qcc_mcp' and meta.get('authorized') is True


def scalar(value) -> str:
    return value if isinstance(value, str) else json.dumps(value, ensure_ascii=False, separators=(',', ':'))


def primary_object(body: str):
    """工商主体只取根对象或已知业务包装；不从股东、名单中的名字授予字段。"""
    try:
        value = json.loads(body)
        path = '$'
        for _ in range(4):
            if not isinstance(value, dict):return {}, ''
            if any(isinstance(value.get(key), str) for key in NAME_KEYS):return value, path
            key = next((key for key in ('data', 'result', 'Result', '企业信息') if isinstance(value.get(key), dict)), None)
            if key is None:break
            value = value[key];path += '.' + key
    except (ValueError, TypeError):pass
    return {}, ''


def primary_matches(body: str, name: str) -> bool:
    value, _ = primary_object(body)
    return any(value.get(key) == name for key in NAME_KEYS)


def field_owned(body: str, name: str, quote: str) -> bool:
    value, path = primary_object(body)
    if not path or not primary_matches(body, name) or not validate_quote(body, quote):return False
    cited_path = re.split(r'\s*[:=]', quote, maxsplit=1)[0]
    leaf = cited_path.removeprefix(path + '.')
    # Nested national industry categories are part of this company's classification.
    return cited_path.startswith(path + '.') and (not re.search(r'[.\[]', leaf) or leaf.startswith(('国标行业.', 'industry.')))


def field_matches(body: str, name: str, quote: str, field: str) -> bool:
    if not field_owned(body,name,quote):return False
    _,path=primary_object(body)
    leaf=re.split(r'\s*[:=]',quote,maxsplit=1)[0].removeprefix(path+'.').split('.')[0]
    return leaf in FIELD_KEYS.get(field,set())


def validate_quote(body: str, quote: str) -> bool:
    """只接受根路径、字典键及有界数组索引；叶子值完整匹配，不支持通配/表达式。"""
    match = re.fullmatch(r'(\$[^:=\s]+)\s*[:=]\s*(.+)', quote or '', re.S)
    if not match:
        return False
    path, cited = match.groups()
    try:
        value = json.loads(body)
        position = 1
        for token in PATH_TOKEN.finditer(path):
            if token.start() != position:
                return False
            value = value[token[1]] if token[1] is not None else value[int(token[2])]
            position = token.end()
        if position != len(path) or isinstance(value, (dict, list)) or value is None:
            return False
        return re.sub(r'\s+', '', scalar(value)) == re.sub(r'\s+', '', cited)
    except (ValueError, TypeError, KeyError, IndexError):
        return False


def identity_quote(body: str, name: str) -> str:
    value,path=primary_object(body)
    for key in NAME_KEYS:
        if value.get(key)==name:return path+'.'+key+': '+name
    return ''
