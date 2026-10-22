"""公开联系方式主体归属校验；平台、其他企业与买方号码不能混为一体。"""
import re


def public_phone(name: str, value: str, body: str, title: str='', *, position: int | None=None) -> bool:
    """name为完整客户名，value为原联系值，body为实际正文，title可空；返回可证明的主体关联。

    position可空（扫描全部出现位置），非空仅核服务器定位的归一化正文位置；空值、平台/其他主体返回False，
    不推用途或接通状态。用于微信时调用方须先核微信标签，不把号码格式或同值当微信证据。
    """
    from .evidence_role import competing_subject
    normalize=lambda text:re.sub(r'\s+','',text or '')
    entity=normalize(name);number=normalize(value)
    if not entity or not number:return False
    text=normalize(body)
    platform=re.compile(r'平台(?:客服|服务|热线|联系|微信)|网站(?:客服|服务|热线|联系|微信)|技术支持|建站(?:服务|咨询)|本站(?:客服|联系|微信)|投诉举报|举报电话')
    for match in re.finditer(re.escape(number),text):
        if position is not None and match.start()!=position:continue
        # 以最近明确主体或平台联系标题划定块；单一网页标题不能覆盖后续平台页脚。
        before=text[max(0,match.start()-1000):match.start()]
        anchor=before.rfind(entity)
        denied=list(platform.finditer(before))
        if denied and denied[-1].start()>anchor:continue
        if anchor>=0 and not competing_subject(name,before[anchor:]):return True
        rest=normalize(title).replace(entity,'')
        if entity in normalize(title) and not re.search('目录|名录|列表|分店',rest) and not competing_subject(name,rest) and not competing_subject(name,before) and not denied:
            return True
    return False


def wechat_position(value: str, quote: str) -> int | None:
    """value为原联系值、quote为原引用（可空）；返回归一化引文中明确微信标签对应的位置，无标签/掩码返回None。"""
    from .contact_view import wechat_valid
    if not wechat_valid(value):return None
    fragment=re.sub(r'\s+','',quote or '')
    tagged=re.search(r'(?:微信(?:号码|号)?|WeChat(?:ID)?)[：:|]*(?:[-*+•])?(?P<value>'+re.escape(value)+r')(?![A-Za-z0-9_-])',fragment,re.I)
    return tagged.start('value') if tagged else None


def public_wechat(name: str, value: str, quote: str, body: str, title: str='') -> bool:
    """name为完整主体、value为原微信值、quote为连续引用、body为正文、title可空；明确标签和同主体联系块成立才True。

    空值、掩码、仅电话标签、同号推断或全部出现位置均未证明本主体时返回False；不补手机、不调用微信。
    """
    position=wechat_position(value,quote)
    if position is None:return False
    normalize=lambda text:re.sub(r'\s+','',text or '')
    fragment=normalize(quote);text=normalize(body)
    if not fragment or fragment not in text:return False
    # 只核引用中微信标签对应的位置，不能借正文其他位置的同值电话为平台微信授归属。
    return any(public_phone(name,value,body,title,position=match.start()+position)
        for match in re.finditer(re.escape(fragment),text))


def contact_identity(value: str, quote: str) -> bool:
    """value为原联系人名称、quote为连续引文，均可空；返回姓名是否紧跟公开联系标签，空值返回False。

    仅识别标签紧邻的单行Markdown列表换行，不修改保存引文、不跨法人等其他字段授予联系身份。
    公开业务联系不等于采购岗位；此函数不证明主体归属或号码有效性，不抛业务异常。
    """
    normalize=lambda text:re.sub(r'\s+','',text or '')
    if not normalize(value) or not quote:return False
    # Trafilatura会将标签和值转换成相邻列表项；只忽略这个明确结构，不能吞掉中间业务字段。
    text=re.sub(r'((?:联\s*系\s*人|联\s*系\s*方\s*式|contact.?name)[：:|]+)[ \t]*\r?\n[ \t]*[-*+•][ \t]+',r'\1',quote,flags=re.I)
    return bool(re.search(r'(?:联系人|业务联系人|采购联系人|联系方式|contact.?name)[：:|]*'+re.escape(normalize(value)),normalize(text),re.I))


def buyer_contact(name: str, value: str, body: str) -> bool:
    """name为完整买方、value为原联系值、body为公告原文；仅接受实际采购人信息块内该主体的值。

    无明确买方块或值只在代理/平台位置时返回False，不推断采购岗位、不生成联系方式。
    """
    marker=re.compile(r'采购人信息|招标人信息|采购单位信息|采购方信息|采购人名称[：:]|采购人[：:]|招标人[：:]|采购单位[：:]|采购代理机构(?:信息)?|政府集中采购机构|集中采购机构|项目联系方式|系统技术支持|纪检|监督部门|版权所有|Copyright|网站地图',re.I)
    headings=list(marker.finditer(body or ''))
    if not headings:return False
    pattern=r'\s*'.join(re.escape(char) for char in re.sub(r'\s+','',value or ''))
    if not pattern:return False
    for occurrence in re.finditer(pattern,body):
        previous=[item for item in headings if item.end()<=occurrence.start()]
        if not previous:continue
        heading=previous[-1]
        if not re.match('采购人|招标人|采购单位|采购方',heading.group()):continue
        block=body[heading.end():occurrence.start()]
        if re.search(re.escape(name)+r'(?=$|[\s，。；;|])',block):return True
    return False
