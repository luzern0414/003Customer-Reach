"""已归档 MCP 标准采购人信息块的原文提取；复用 Candidate 与原保存门禁。"""
import re
from urllib.parse import urlparse
from datetime import datetime
from .schemas import Candidate,Fact,ProcurementSignal
from .evidence_role import BUYER_NAME_PREFIX

BUYER=re.compile(BUYER_NAME_PREFIX+r'\s*'
    r'(?P<name>[^\n：:，。；;|]{2,200})(?=\n|$)')
BOUNDARY=re.compile(r'采购代理机构|招标代理|代理机构信息|项目联系方式|监督部门|系统技术支持|版权所有|Copyright',re.I)


def submission_deadline(body):
    """只取明确响应/投标文件提交期限；其他期限和冲突日期保持未知，返回时间及连续原文。"""
    deadlines=[]
    for match in re.finditer(r'(?m)(?P<label>[^：:\n。；;，]*(?:截止(?:时间)?|开标时间))[：:][^\n。；;]*',body):
        label=match['label']
        if re.search('保证金|获取|报名|询问|质疑|答疑|下载',label):continue
        direct=re.search(r'(?:提交|递交).{0,8}(?:响应|投标)文件|(?:响应|投标)文件.{0,8}(?:提交|递交)|(?:投标|响应|提交|递交)截止|开标时间',label)
        previous=[line.strip() for line in body[:match.start()].splitlines() if line.strip()]
        heading=previous[-1] if previous else ''
        section=re.fullmatch(r'[\s#一二三四五六七八九十\d、.．]*?(?:响应文件提交|投标文件递交|提交响应文件|提交投标文件)',heading)
        if not direct and not (re.fullmatch(r'\s*截止时间\s*',label) and section):continue
        stamp=re.search(r'(\d{4})[-年/](\d{1,2})[-月/](\d{1,2})日?\s*(\d{1,2})[:：](\d{2})(?:[:：](\d{2}))?',match[0])
        if not stamp:continue
        try:parsed=datetime(*[int(value or 0) for value in stamp.groups()])
        except ValueError:continue
        deadlines.append((parsed.strftime('%Y-%m-%d %H:%M:%S'),match[0]))
    return deadlines[0] if deadlines and len({value for value,_ in deadlines})==1 else ('','')


def supports_procurement(source):
    meta=source.get('source_meta') or {}
    from .bidresearch_mcp import DOMAINS
    host=(urlparse(source.get('url','')).hostname or '').lower()
    known_public_page=any(host==domain or host.endswith('.'+domain) for family in ('ggzy','ebnew') for domain in DOMAINS[family])
    return bool(source.get('kind') in {'网页正文','网页读取'} and source.get('channel')=='procurement'
        and ((meta.get('origin')=='bidresearch_mcp' and meta.get('detail_status') in {'public','masked'})
             or (known_public_page and meta.get('origin')!='bidresearch_mcp'))
        and BUYER.search(source.get('body','')))


def parse_procurement(source,region,products,roles):
    if not supports_procurement(source) or not source.get('id') or roles and 'project_buyer' not in roles:return []
    from .bidresearch_mcp import substantive_match,procurement_keywords,software_service_profile,software_service_match
    from .evidence_role import buyer_identity
    body=source['body'];title=source.get('title','')
    keywords=list(dict.fromkeys(word for p in products for word in procurement_keywords(p.get('name',''),[p])))
    if not keywords or not substantive_match(title,body,keywords):return []
    if software_service_profile({'products':products}) and not software_service_match(title,body):return []
    buyers=list(BUYER.finditer(body))
    # 多买方/不完整姓名留给现有模型分析，不把联系人或代理姓名当客户。
    if len(buyers)!=1:return []
    buyer=buyers[0];name=buyer['name'].strip();buyer_quote=buyer[0].rstrip()
    if not buyer_identity(name,buyer_quote) or re.search(r'[*＊×]|暂无|未公开|详见|采购代理',name):return []
    tail=body[buyer.end():];end=BOUNDARY.search(tail)
    block=tail[:end.start()] if end else tail[:1000]
    field=lambda label:re.search(r'(?m)^[ \t]*(?:'+label+r')[：:][ \t]*([^\n]{2,200})',block)
    address=field(r'地\s*址');phone=field(r'联系\s*方式|联系\s*电话|电\s*话')
    city=region if region and region not in {'全国','中国','不限'} else ''
    if city and (not address or city not in address[1]):return []
    sid=source['id'];facts=[Fact(field='name',value=name,quote=buyer_quote,source_id=sid),
        Fact(field='buyer_role',value=buyer['role'],quote=buyer_quote,source_id=sid)]
    if address and not re.search(r'[*＊×]',address[1]):
        facts.append(Fact(field='address',value=address[1].strip(),quote=address[0],source_id=sid))
    if phone:
        from .contact_view import phone_info
        value=phone[1].strip()
        if phone_info(value)['status']=='format_valid':
            facts.append(Fact(field='phone',value=value,quote=phone[0],source_id=sid,
                scope='采购人信息块公开电话；未验证接通或采购岗位'))
    project=re.search(r'项目编号|项目名称|采购需求|采购内容',body[:buyer.start()])
    summary=body[project.start():min(buyer.start(),project.start()+1200)].strip() if project else ''
    if not summary:return []
    facts.append(Fact(field='procurement',value=summary,quote=summary,source_id=sid,
        scope='本公告原文；预算不是成交额，公告不代表已确认订单'))
    deadline,deadline_quote=submission_deadline(body[:buyer.start()])
    stage='awarded' if re.search('中标|成交结果|合同公告',title) else 'closed' if re.search('终止|废标|流标',title) else 'historical'
    from .procurement import closed_notice
    if stage!='awarded' and closed_notice(title,body):stage='closed'
    if deadline and stage not in {'awarded','closed'} and not re.search('更正|变更',title):stage='open'
    signal=ProcurementSignal(source_id=sid,buyer=name,participant_role='buyer',stage=stage,deadline=deadline,
        quote=summary,buyer_quote=buyer_quote,deadline_quote=deadline_quote)
    return [Candidate(display_name=name,city=city,buyer_role='project_buyer',facts=facts,
        matched_products=[],match_reason='原公告明确采购人及软件/服务需求；具体适配、资格和采购进度待核验。',procurement_signal=signal)]
