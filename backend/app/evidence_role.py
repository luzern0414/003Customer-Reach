"""补充明确页面主体或目录表头的角色关联；不以企业名后缀或普通销售经营范围推断买家。"""
import re

# 角色规则升级后重验旧提取/保存操作，不能复用旧版拒绝或通过记录。
ROLE_POLICY='role-policy-17'
BUYER_NAME_PREFIX=r'(?P<role>采购人|采购方|招标人)(?:(?:信息)?[：:\s]*名\s*称[：:][ \t]*|[：:][ \t]*)'


def buyer_identity(name: str, quote: str) -> bool:
    """只接受明确买方标签紧邻原名；允许公告的“名 称”排版，不跨其他字段或主体。"""
    if not name or not quote:return False
    return bool(re.search(BUYER_NAME_PREFIX+r'\s*'
        +re.escape(name)+r'(?=$|[\s，。；;|])',quote))


def role_location(value: str, quote: str) -> bool:
    """value为场所角色原词、quote为同句原文，均可空；仅作为所在地宾语且无身份谓词时返回True。

    不将位于某市场的企业当市场运营方；明确是一家位于某地的市场仍可继续身份校验。
    """
    text=re.sub(r'\s+','',quote or '');role=re.sub(r'\s+','',value or '')
    if not role:return False
    for match in re.finditer(r'(?:位于|位置在|坐落于|地处|地址[:：])[^。；;，,\n]*?'+re.escape(role),text):
        prefix=text[:match.end()-len(role)]
        if not re.search(r'是(?:一家|一个)?|作为|打造|建成|经营|管理|市场类型|市场类别',prefix):return True
    return False


def role_denied(value: str, quote: str) -> bool:
    """value为原文角色字串、quote为关联片段（均可空）；否定紧邻该角色时返回True，不把其他句的否定套到角色上。"""
    text=re.sub(r'\s+','',quote or '');role=re.sub(r'\s+','',value or '')
    if not role:return True
    denied=any(not re.search('但|而是|只|仅|转为|改为',match[1]) for match in re.finditer(
        r'(?:不是|并非|不属于|不从事|未从事|不经营|不开展|未开展|不提供|没有)([^。；;，,]{0,25}?)'+re.escape(role),text))
    return denied or bool(re.search(re.escape(role)+r'(?:业务|经营)?(?:不是|并非|不属于)(?:本公司|本企业|本店)',text))


def competing_subject(name: str, quote: str) -> bool:
    """name为完整主体、quote为连续引文（可空）；剩余片段有另一法律主体时返回True，不猜实体别名。"""
    text=re.sub(r'\s+','',quote or '').replace(re.sub(r'\s+','',name or ''),'')
    return bool(re.search(r'[\u4e00-\u9fffA-Za-z0-9]{2,}(?:有限公司|商行|经营部)',text))


def same_subject_page(name: str, previous: list[dict], sources: dict) -> bool:
    """name为完整主体、previous为旧name引文、sources仅含本轮name来源；同单主体页面返回True。

    空值/目录标题/其他法律主体/不同来源返回False。这里只确认主体一致，不确认两个地址一致。
    """
    normalize=lambda value:re.sub(r'\s+','',value or '')
    if not name:return False
    for key,source in sources.items():
        title=normalize(source.get('title',''));entity=normalize(name)
        if entity not in title:continue
        rest=title.replace(entity,'')
        if re.search('目录|名录|列表|分店|门店|[\u4e00-\u9fffA-Za-z0-9]{2,}(?:有限公司|商行|经营部)',rest):continue
        if any(item.get('field')=='name' and normalize(item.get('value',''))==entity and
            (item.get('source_id')==key or item.get('url') and item.get('url')==source.get('url')) for item in previous):return True
    return False


def scoped_role(name: str, value: str, quote: str, title: str, same_source_name: bool, body: str='') -> bool:
    """name/value/quote/title来自已校验事实，same_source_name为同源name证据，body可空实际正文；返回明确结构关联。

    支持单主体页面的本公司介绍、企业性质字段，以及目录明确角色标题下的表格行；其他主体或模糊销售描述拒绝。
    """
    normalize=lambda text:re.sub(r'\s+','',text or '')
    if role_denied(value,quote):return False
    if normalize(value) not in normalize(quote).replace(normalize(name),''):return False
    if value=='入驻品牌' and same_source_name and value in quote:
        from .public_directory import mall_listing
        return bool(mall_listing(name,body))
    # 通用网站标题不否定正文的直接身份句；逗号分主语/谓语，不能让完整主体明确“是商场”被拆掉。
    sentence=re.split(r'[。\n；;]',quote.strip(),maxsplit=1)[0]
    if same_source_name and body and len(sentence)<=700 and sentence.startswith(name) and normalize(body).count(normalize(sentence))==1 and not competing_subject(name,sentence):
        tail=sentence[len(name):]
        action=re.match(r'[，,\s]*是(?:位于|位置在|坐落于|地处|服务|面向|供应|提供|负责)',tail)
        if not action and re.fullmatch(r'[，,\s]*是[^。\n；;]{0,200}'+re.escape(value)+r'(?:之一)?',tail) and not role_location(value,tail):return True
    rest_title=normalize(title).replace(normalize(name),'')
    directory_title=bool(re.search('目录|名录|列表',rest_title))
    owner=normalize(name) in normalize(title) and not directory_title and not re.search(r'[\u4e00-\u9fffA-Za-z0-9]{2,}(?:有限公司|商行|经营部)',rest_title)
    if same_source_name and not owner and body and not directory_title:
        # 商品文章的标题可能只有产品名；公司介绍段落中的“公司”必须回指最近、明确的完整主体。
        content=normalize(body);fragment=normalize(quote)
        if fragment and content.count(fragment)==1:
            location=content.find(fragment)
            # 长引文可能从主体名字开始；定位公司代词，再向前找主体，而不是在引文开始前找。
            pronoun=re.search(r'(?:本公司|公司|我司|本商行|本店)(?:经营|经销|代理|零售)',fragment)
            subject_end=location+pronoun.start() if pronoun else location
            anchor=content.rfind(normalize(name),0,subject_end)
            between=content[anchor+len(normalize(name)):subject_end] if anchor>=0 else ''
            owner=bool(anchor>=0 and len(between)<1000 and re.search('成立|位于|是一家|简介|介绍|从事',between) and
                not re.search(r'[\u4e00-\u9fffA-Za-z0-9]{2,}(?:有限公司|商行|经营部)',between))
    if same_source_name and owner:
        # 引文包含另一个法律主体时，不借“公司”代词把它的业务归给页面主体。
        remaining=normalize(quote).replace(normalize(name),'')
        competing=re.search(r'[\u4e00-\u9fffA-Za-z0-9]{2,}(?:有限公司|商行|经营部)',remaining)
        if not competing:
            # 完整主体开头的短介绍块可延续到紧邻主营/专业介绍句；目录分区、其他主体或否定不授予关联。
            block=quote.strip()
            anchor=re.match(re.escape(name)+r'(?:位于|位置在|成立|是一家|专业从事)',block)
            if anchor and len(block)<=700 and not re.search(r'(?m)^\s*#|推荐企业|相关企业|其他商户|招聘职位|企业列表',block):
                pieces=re.split(r'[。\n；;]',block)
                continued=[piece.strip() for piece in pieces[1:] if piece.strip()]
                if (not body or normalize(body).count(normalize(block))==1) and any(
                    re.match(r'主营|主要经营|专业从事|聚焦|从事',piece) and normalize(value) in normalize(piece) for piece in continued):return True
            intro=re.match(r'\s*'+re.escape(name)+r'(?:位于|位置在|成立|是一家|专业从事)[^\n。；;]{0,700}',quote)
            # 同一句明确以完整主体开头的介绍可跨逗号关联角色；目录/其他法律主体仍由owner/competing拒绝。
            if intro and normalize(value) in normalize(intro.group()).replace(normalize(name),'') and not role_location(value,normalize(intro.group()).replace(normalize(name),'')):return True
            for match in re.finditer(r'(?:^|[\n。；;])\s*(?:本公司|公司|我司|本商行|本店)[^\n。；;]{0,100}',quote):
                if normalize(value) in normalize(match.group()):return True
            if re.search(r'(?:企\s*业\s*性\s*质|企\s*业\s*类\s*型|经\s*营\s*模\s*式|经\s*营\s*类\s*型|市\s*场\s*类\s*型|市\s*场\s*类\s*别)[\s:：|]*(?:(?:个体经营|私营企业|有限责任公司)[\s—|\-]+)?'+re.escape(value),quote):return True
            # 单主体商场介绍的“本商场”也是明确回指；长品牌清单仍须在同句且没有另一法律主体。
            for match in re.finditer(r'本商场[^\n。；;]{0,400}',quote):
                if normalize(value) in normalize(match.group()):return True
    # 目录不是单一企业页面；必须有明确角色标题、真实表格结构及包含完整名字的该行。
    if value in {'采购人','采购方','招标人'} and buyer_identity(name,quote):return True
    lines=quote.splitlines();heading=''
    for line in lines:
        plain=re.sub(r'^\s*#{1,6}\s*','',line).strip()
        if re.fullmatch(r'授权店|专卖店|经销商|零售门店|门店',plain):heading=plain
        elif re.match(r'^\s*#',line):heading=''
        if '|' in line and normalize(name) in normalize(line) and normalize(value) in normalize(heading):return True
    return False
