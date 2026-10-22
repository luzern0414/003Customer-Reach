"""真实联系资料及来源的展示投影；不推断隐去号码、联系人职位或电话可接通性。"""
import re
import json
from urllib.parse import urlparse
from .source_catalog import source_label
import phonenumbers


def phone_info(value: str | None) -> dict:
    """value为公开原号码，可空；离线检查长度并生成RFC3966链接，不改变原值、不补区号、不证明接通。

    中国号码按本项目CN地区解释，显式国际前缀保留；短号、掩码、无法唯一解析的号码无链接。
    """
    if not value:return {'status':'empty','href':''}
    if re.search(r'[*＊…]',value):return {'status':'masked','href':''}
    if len(re.findall(r'\d',value))<10:return {'status':'incomplete','href':''}
    if not re.fullmatch(r'[+\d\s()（）－-]+(?:(?:转|ext\.?|x|#)\s*\d+)?',value,re.I):return {'status':'invalid','href':''}
    raw=re.sub(r'^86(?=[\s-])','+86',value.strip())
    raw=re.sub(r'转\s*(\d+)$',r' ext. \1',raw)
    try:
        number=phonenumbers.parse(raw,'CN')
        if phonenumbers.is_possible_number_with_reason(number)!=phonenumbers.ValidationResult.IS_POSSIBLE:return {'status':'invalid','href':''}
        # 中国号码的通用长度范围还覆盖移动/特殊号码；原文以0开头的固话需用固话规则避免接受9位本地号码。
        if number.country_code==86 and re.match(r'^(?:\+?86[\s-]+)?0',value.strip()) and phonenumbers.is_possible_number_for_type_with_reason(number,phonenumbers.PhoneNumberType.FIXED_LINE)!=phonenumbers.ValidationResult.IS_POSSIBLE:
            return {'status':'invalid','href':''}
        return {'status':'format_valid','href':phonenumbers.format_number(number,phonenumbers.PhoneNumberFormat.RFC3966)}
    except phonenumbers.NumberParseException:return {'status':'invalid','href':''}


def website_link(value: str | None) -> str:
    """value为原文网址或空；只返回HTTP(S)无凭据完整主机链接，坏值返回空，不改写存储原文或验证接通。"""
    if not value or re.search(r'\s',value):return ''
    if not re.match(r'^https?://',value,re.I) and not re.fullmatch(r'(?:www\.)?[A-Za-z0-9.-]+\.[A-Za-z]{2,}(?:[/?#][^\s]*)?',value):return ''
    try:
        url=value if re.match(r'^https?://',value,re.I) else 'https://'+value
        parsed=urlparse(url)
        if parsed.scheme not in {'http','https'} or not parsed.hostname or parsed.username or parsed.password:return ''
        parsed.port
        return url
    except ValueError:return ''


def wechat_valid(value: str | None) -> bool:
    """value为原文微信号/号码或空；完整明文格式返回True，掩码/昵称/未知/同号描述返回False，不推电话号码或账户可添加性。"""
    return bool(value and re.fullmatch(r'(?:[A-Za-z][A-Za-z0-9_-]{5,31}|\d{11})',value) and value.lower() not in {'unknown','wechat','weixin'})


def coexisting_phones(name: str, first: dict, second: dict, sources: dict) -> bool:
    """name为完整主体，两个事实及sources为已校验原文；同号多格式或明确同主体并列联系记录才视为并存。"""
    left=phone_info(first.get('value'));right=phone_info(second.get('value'))
    if not left['href'] or not right['href']:return False
    if left['href']==right['href']:return True
    normalize=lambda value:re.sub(r'\s+','',value or '')
    for key in {first.get('source_id'),second.get('source_id')}:
        source=sources.get(key,{})
        if normalize(name) not in normalize(source.get('title','')):continue
        body=normalize(source.get('body',''))
        values=[re.escape(normalize(x.get('value',''))) for x in [first,second]]
        fixed=[bool(re.search(r'(?:座机电话|固定电话|固话)[：:|]*'+value,body)) for value in values]
        mobile=[bool(re.search(r'(?:手机号码|移动电话|手机)[：:|]*'+value,body)) for value in values]
        if fixed[0] and mobile[1] or fixed[1] and mobile[0]:return True
        uri=urlparse(source.get('url',''))
        if source.get('kind') not in {'网页正文','网页读取'} or not (uri.hostname or '').endswith('.hc23.com'):continue
        # 已实读HC23商户摘要行明确将两号列在完整主体的“地址是…主要提供”记录，不从掩码反推。
        row=re.search(re.escape(name)+r'的地址是[^\n。]{3,500}[,，]([+\d ()-]{10,35})[,，]([+\d ()-]{10,35})[,，]主要提供',source.get('body',''))
        if row and {normalize(row[1]),normalize(row[2])}=={normalize(first.get('value')),normalize(second.get('value'))}:return True
    return False


def contact_view(facts: dict, evidence: list[dict]) -> dict:
    """facts为可空字段映射，evidence为逐字段证据；返回可用入口、缺口、用途和独立来源，无网络或写操作。"""
    facts=facts or {};evidence=evidence or []
    usable=[]
    for field in ['phone','email','website','wechat']:
        fact=facts.get(field,{})
        value=fact.get('value','')
        if not value or fact.get('verification') in {'disputed','inactive'}:continue
        if field=='phone' and not phone_info(value)['href']:continue
        if field=='email' and not re.fullmatch(r'[^\s@]+@[^\s@]+\.[^\s@]+',value):continue
        if field=='website' and not website_link(value):continue
        if field=='wechat' and not wechat_valid(value):continue
        usable.append(field)
    quotes=' '.join(x.get('quote','') for x in evidence if x.get('field') in {'phone','email','wechat'} and
        x.get('source_id')==facts.get(x.get('field'),{}).get('source_id'))
    purpose='用途待核验'
    if re.search('采购单位联系方式|采购人联系方式|采购方联系人',quotes):purpose='采购联系'
    elif re.search('招商|租赁热线',quotes):purpose='招商联系'
    elif re.search('客服|客户服务|售后热线',quotes):purpose='客服/售后'
    elif re.search('业务联系|销售热线|商务合作',quotes):purpose='公开业务联系'
    sources={}
    for item in evidence:
        url=item.get('url','')
        if url and url not in sources:
            sources[url]={key:item.get(key,'') for key in ['url','title','captured_at','channel','kind','source_id']}
            sources[url]['platform']=source_label(url)
    # 有其他可用入口不代表电话/邮箱本身完整；缺口与入口判定共用同一规则，避免表格和导出漏报。
    missing=[field for field in ['phone','email','website','wechat','address','contact_name'] if
             (field in {'phone','email','website','wechat'} and field not in usable) or
             not facts.get(field,{}).get('value') or facts.get(field,{}).get('verification') in {'disputed','inactive'}]
    phone=facts.get('phone',{}).get('value','')
    phone_result=phone_info(phone)
    incomplete_phone=phone_result['status']=='incomplete'
    phone_href=phone_result['href'] if 'phone' in usable else ''
    return {'usable_fields':usable,'status':'有联系入口' if usable else '联系信息待补','purpose':purpose,
        'missing_fields':missing,'phone_incomplete':incomplete_phone,'phone_status':phone_result['status'],'phone_href':phone_href,
        'source_count':len(sources),'site_count':len(evidence_sites(evidence)),
        'sites':evidence_sites(evidence),'sources':list(sources.values())}


def contact_available(value: str | None) -> int:
    """value为SQLite事实JSON或空值；返回0/1用于与展示同口径排序，坏JSON返回0，不推断号码接通。"""
    try:facts=json.loads(value) if value else {}
    except (ValueError,TypeError):return 0
    return int(bool(contact_view(facts,[])['usable_fields'])) if isinstance(facts,dict) else 0


def evidence_sites(evidence: list[dict] | None) -> list[str]:
    """evidence为已校验客户引文，可空；按平台根域去重网站，不将移动站/多个页面称独立站，也不保证独立调查。"""
    sites=set()
    for item in evidence or []:
        host=(urlparse(item.get('url','')).hostname or '').lower()
        parts=host.split('.')
        if len(parts)<2:continue
        # 当前中国企业来源常用com.cn/gov.cn；仅用于来源计数，不作为身份或访问权限判断。
        size=3 if '.'.join(parts[-2:]) in {'com.cn','gov.cn','org.cn','net.cn','co.uk'} else 2
        sites.add('.'.join(parts[-size:]))
    return sorted(sites)
