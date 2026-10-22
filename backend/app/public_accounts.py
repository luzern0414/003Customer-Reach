"""已实测公开公司模板的确定性原文提取；不补人数日期、采购、号码或公司别名。"""
import re
from urllib.parse import urlsplit
from .schemas import Candidate,Fact
PARSER_POLICY='public-account-6'


def supports_template(source: dict) -> bool:
    """source为已取得来源；仅接受已核验云发了/HC23公司或乐安居分店完整网页，摘要/未知域返回False。"""
    from .procurement_accounts import supports_procurement
    if supports_procurement(source):return True
    uri=urlsplit(source.get('url',''))
    page=(uri.hostname in {'www.yunfale.com','yunfale.com'} and bool(re.fullmatch(r'/company/detail/\d+/',uri.path))) or ((uri.hostname or '').endswith('.hc23.com') and bool(re.fullmatch(r'/company/\d+\.html',uri.path)))
    from .public_directory import branch_key
    body=source.get('body','')
    mall=bool(branch_key(source.get('url','')) and re.search(r'[^\n]{2,40}店\s+入驻品牌',body) and re.search(r'(?m)^[ \t]*(灯饰|灯具|照明)[ \t]*$',body))
    return bool(page or mall) and source.get('kind') in {'网页正文','网页读取'}


def parse_accounts(source: dict, region: str, products: list[dict], roles: list[str] | None=None) -> list[Candidate]:
    """source为实际正文、region为目标城市，products可空，roles可空沿用原商户解析；返回原文候选批次。

    公司模板复用parse_account，灯具商户仍要求同记录完整号码；商场目标只取已验证分店直接身份句，不借租户号码。
    不联网、不写库、不补地址/法律名/产品匹配或采购；后续persist仍需完整校验。
    """
    from .public_directory import branch_key,mall_listing,mall_city_quote
    from .procurement_accounts import supports_procurement,parse_procurement
    if supports_procurement(source):return parse_procurement(source,region,products,roles)
    if not branch_key(source.get('url','')):
        candidate=parse_account(source,region)
        return [candidate] if candidate and (not roles or candidate.buyer_role in roles) else []
    if not supports_template(source) or not source.get('id') or not region or not re.search('灯|照明',' '.join(str(item.get('name','')) for item in products)):return []
    body=source.get('body','')
    heading=re.search(r'[^\n]{2,40}店\s+入驻品牌',body)
    if not heading or len(re.findall(r'[^\n]{2,40}店\s+入驻品牌',body))!=1:return []
    result=[]
    if roles and not {'mall','retailer'}.intersection(roles):return []
    if roles and 'mall' in roles:
        # 原场所名必须出现在同分店简介，不能由品牌+目录简称拼接；仅解析已有直接身份句。
        intro=body.split('了解更多',1)[0] if '了解更多' in body else body[:heading.start()]
        branch_name=heading[0].split('入驻品牌',1)[0].strip()
        from .evidence_role import scoped_role
        for match in re.finditer(r'(?m)^(?P<name>乐安居[^\n，,。；;]{2,40}店)[，,\t ]*是[^\n。；;]{0,200}?(?P<role>商场|卖场|家居城)(?:之一)?(?=[。\n；;]|$)',intro):
            name=match['name'];quote=match[0];role=match['role']
            if not name.endswith(branch_name) or region not in quote or not scoped_role(name,role,quote,source.get('title',''),True,body):continue
            facts=[Fact(field='name',value=name,quote=quote,source_id=source['id']),
                Fact(field='buyer_role',value=role,quote=quote,source_id=source['id'])]
            category=re.search(r'(?m)^[ \t]*(灯饰|灯具|照明)[ \t]*$',body[heading.end():])
            if category:
                start=heading.end()+category.start();end=body.find('\n',heading.end()+category.end()+1)
                category_quote=body[start:end if end>=0 else len(body)].strip()
                if len(category_quote)>=3:facts.append(Fact(field='categories',value=category[1],quote=category_quote,source_id=source['id'],scope='分店入驻商户商品分区；不是直接经营或采购确认'))
            result.append(Candidate(display_name=name,city=region,buyer_role='mall',facts=facts,matched_products=[],
                match_reason='原分店介绍直接声明商场定位；运营工商主体、业务联系及采购待核验。'))
        if 'retailer' not in roles:return result
    from .contact_view import phone_info
    categories=list(re.finditer(r'(?m)^[ \t]*(灯饰|灯具|照明)[ \t]*$',body))
    records=list(re.finditer(r'(?m)^(?P<name>[^\n]{2,100})\n[ \t]*(?:Tel|电话)[：:][ \t]*(?P<phone>[+\d ()-]{7,30})[ \t]*$',body))
    numbers={}
    for record in records:
        if record.start()>=heading.end():numbers.setdefault(record['name'].strip(),set()).add(record['phone'].strip())
    seen=set()
    for record in records:
        if record.start()<heading.end():continue
        name=record['name'].strip();phone=record['phone'].strip()
        if name in seen or name in {'灯饰','灯具','照明'} or len(numbers.get(name,set()))!=1:continue
        # 只有最近商品分区明确为灯具才进入灯具候选，其他分区的厨电/家具不能继承旧灯饰标题。
        previous=[item for item in categories if heading.end()<=item.start()<record.start()]
        if not previous:continue
        category=previous[-1]
        between=body[category.end():record.start()]
        if any(line.strip() and not re.match(r'(?:Tel|电话)[：:]',line.strip()) and not mall_listing(line.strip(),body) for line in between.splitlines()):continue
        if mall_listing(name,body).get('phone')!=phone or phone_info(phone)['status']!='format_valid':continue
        if not mall_city_quote(name,region,body):continue
        facts=[Fact(field='name',value=name,quote=record[0],source_id=source['id']),
            Fact(field='buyer_role',value='入驻品牌',quote=heading[0],source_id=source['id']),
            Fact(field='phone',value=phone,quote=record[0],source_id=source['id'],scope='原分店入驻记录；未验证电话接通或采购岗位')]
        category_quote=body[category.start():record.end()]
        if len(category_quote)<=1500:facts.append(Fact(field='categories',value=category[1],quote=category_quote,source_id=source['id']))
        result.append(Candidate(display_name=name,city=region,buyer_role='retailer',facts=facts,matched_products=[],
            match_reason='分店公开灯具分区入驻记录及同商户电话；具体产品、营业时效和采购待核验。'))
        seen.add(name)
        if len(result)>=8:break
    return result


def parse_account(source: dict, region: str) -> Candidate | None:
    """source为真实完整正文、region为当前目标城市；返回逐字段Pydantic候选，任一身份/角色/电话关联不足则None。

    不联网、不写库；来源ID必须存在，所有quote保留原文字串。可选主营仅取明确标签，未知数据省略。
    """
    if not supports_template(source) or not source.get('id') or not region:return None
    body=source.get('body','');title=source.get('title','').removesuffix('_云发了网').strip()
    if not re.fullmatch(r'[\u4e00-\u9fffA-Za-z0-9（）()·]{2,100}(?:有限公司|商行|经营部|灯饰店)',title):return None
    if (urlsplit(source['url']).hostname or '').endswith('.hc23.com'):
        entity=re.search(r'企\s*业\s*名\s*称[：:]\s*'+re.escape(title),body)
        role=re.search(r'本商场[^\n。]{1,380}一级经销商',body)
        numbers=re.search(re.escape(title)+r'的地址是[^\n。]{3,500}[,，]([+\d ()-]{10,35})[,，]([+\d ()-]{10,35})[,，]主要提供',body)
        if not entity or not role or not numbers:return None
        card=re.split(r'\||企\s*业\s*名\s*称',body[entity.end():],maxsplit=1)[0][:1500]
        address=re.search(r'公\s*司\s*地\s*址[：:]\s*(.{3,200}?)\s*联\s*系\s*电\s*话[：:]',card)
        if not address or region not in address[1]:return None
        from .source_access import access_issue
        if access_issue(source['url'],title,body):return None
        facts=[Fact(field='name',value=title,quote=entity[0],source_id=source['id']),
            Fact(field='buyer_role',value='一级经销商',quote=role[0],source_id=source['id']),
            Fact(field='address',value=address[1].strip(),quote=address[0],source_id=source['id'])]
        for value in [numbers[1],numbers[2]]:
            facts.append(Fact(field='phone',value=value.strip(),quote=numbers[0],source_id=source['id'],scope='同主体记录并列公开号码；未验证接通或号码类型'))
        categories=re.search(r'主\s*营\s*产\s*品[：:]\s*(.{2,200}?)\s*公\s*司\s*地\s*址',card)
        contact=re.search(r'联\s*系\s*人[：:]\s*([\u4e00-\u9fff]{2,12}(?:先生|女士)?)\s+员\s*工\s*人\s*数',card)
        if categories:facts.append(Fact(field='categories',value=categories[1].strip(),quote=categories[0],source_id=source['id']))
        if contact:facts.append(Fact(field='contact_name',value=contact[1],quote=contact[0],source_id=source['id']))
        brands=re.search(r'并是(.{2,300}?)等世界知名品牌',role[0])
        if brands:facts.append(Fact(field='brands',value=brands[1].strip(),quote=role[0],source_id=source['id'],scope='原页一级经销商自述；不是已确认供货或采购记录'))
        reason='原页明确一级经销商及并列联系记录；'
        if '生产与销售为一体' in body:reason+='原页亦自述生产与销售混合；'
        return Candidate(display_name=title,city=region,buyer_role='dealer',facts=facts,matched_products=[],
            match_reason=reason+'经营时效、具体产品和采购待核验。')
    intro=re.search(re.escape(title)+r'(?:位置在|位于)[^\n。]{3,700}',body)
    if not intro:return None
    tail=body[intro.end():]
    section=re.search(r'(?m)^\s*联系人[\s:：]',tail)
    if not section:return None
    contact=re.split('网站指南|网站服务|相关企业|推荐公司|公司频道|免费注册',tail[section.start():],maxsplit=1)[0][:700]
    # 只解析主体介绍后的联系区，不取页头平台热线或页尾其他企业联系方式。
    phone=re.search(r'电话\s*([+\d ()（）-]{10,45})',contact)
    address=re.search(r'地址\s*([^\r\n]{3,180})',contact)
    if not intro or '经销批发' not in intro[0] or not phone or not address or region not in address[1]:return None
    from .source_access import access_issue
    if access_issue(source['url'],title,body):return None
    facts=[Fact(field='name',value=title,quote=title,source_id=source['id']),
        Fact(field='buyer_role',value='经销批发',quote=intro[0],source_id=source['id']),
        Fact(field='phone',value=phone[1].strip(),quote=phone[0].strip(),source_id=source['id'],scope='页面公开电话；未验证接通'),
        Fact(field='address',value=address[1].strip(),quote=address[0].strip(),source_id=source['id'])]
    categories=re.search(r'主营[：:]\s*([^\r\n]{2,200})',body)
    if categories:facts.append(Fact(field='categories',value=categories[1].strip(),quote=categories[0].strip(),source_id=source['id']))
    return Candidate(display_name=title,city=region,buyer_role='dealer',facts=facts,matched_products=[],
        match_reason='原页明确经销批发角色与公开电话；具体产品适配、采购和资料更新时间待核验。')
