"""在线公司资料逐字段校验与事务持久化；模型输出从不直接当数据库事实。"""
import re
import time
from datetime import datetime
from decimal import Decimal, InvalidOperation
from sqlalchemy import select, text, func
from .db import Session, Job, Evidence, now
from .company_models import Company, CompanyFact, ProcurementProject, ProcurementNotice, CompanyRelation, ResearchCompany
from .company_service import stable_key, ensure_company, scope_ids
from .company_research_schemas import CompanySnapshot
from .service import ServiceError
from .source_content import has_content
from .statistics_evidence import valid_statistics
from .evidence_citations import append_citations

COMPANY_POLICY = 'company-evidence-6'


def normalize(value) -> str:
    """value可为空或数值；仅统一排版空白和千分位，不修改证据存档、不猜名称或单位。"""
    return re.sub(r'[\s,，]', '', str('' if value is None else value)).casefold()


def decimal_value(value: str | None):
    """value为原文数字字符串可空；完整数字才转Decimal，带单位/范围/未知返回None。"""
    if not value or not re.fullmatch(r'-?\d[\d,]*(?:\.\d+)?', value.strip()): return None
    try: return Decimal(value.replace(',', ''))
    except InvalidOperation: return None


def numeric_evidence(value: str, unit: str, quote: str, metadata: str = '') -> None:
    """value为原数字、unit可空、quote/metadata为已校验连续原文；数值与单位必须对应，缺证据抛ServiceError。"""
    amount = decimal_value(value)
    if amount is None: raise ServiceError('数值不是明确原文数字')
    text = normalize(quote)
    numbers = list(re.finditer(r'(?<![\d.])-?\d+(?:\.\d+)?(?![\d.])', text))
    matches = [m for m in numbers if Decimal(m.group()) == amount]
    if not matches: raise ServiceError('数值没有对应原文，不接受其他数值的子串')
    if not unit: return
    normalized_unit = normalize(unit)
    # 元不能被万元/亿元的子串授权；无紧邻单位时只接受同源明确的单位表头。
    boundary = r'(?!民币)' if unit == '人' else r'(?![万亿兆元台套])'
    adjacent = any(re.match(re.escape(normalized_unit) + boundary, text[m.end():]) for m in matches)
    header = re.search(r'单位[（(：:]*' + re.escape(normalized_unit) + boundary, normalize(metadata))
    people = unit == '人' and re.search('人数', metadata) is not None
    explicit = any(re.match(r'(?:人民币)?[万亿兆]?(?:美元|欧元|元)|人|台|套|%', text[m.end():]) for m in matches)
    if not adjacent and explicit: raise ServiceError('数值紧邻单位与提议单位不一致')
    if not (adjacent or header or people): raise ServiceError('数值单位没有对应原文，不能改变倍率')


def target_matches(name: str, target: str, quote: str) -> bool:
    """name/target为非空原名，quote为连续身份声明；仅完整名或同句明确简称映射通过，未知返回False。"""
    if normalize(name) == normalize(target): return True
    text = normalize(quote)
    # 法人完整名称不能被子串命中；简称需在同一连续声明内绑定这个完整主体。
    if re.search('有限公司|股份公司|集团公司', target): return False
    pattern = re.escape(normalize(name)) + r'[（(]?[^。；;]{0,30}(?:以下简称|公司简称|证券简称|股票简称|简称)[：:为“"\s]*' + re.escape(normalize(target)) + r'(?![\u4e00-\u9fffA-Za-z0-9])'
    return bool(re.search(pattern, text))


def notice_date(value: str, quote: str, kind: str) -> str:
    """value可空日期或上海时间，quote为同源连续日期声明，kind为publication/deadline；不猜时间，失败抛业务错误。"""
    if not value: return ''
    fmt = '%Y-%m-%d %H:%M:%S' if len(value) == 19 else '%Y-%m-%d'
    try: stamp = datetime.strptime(value, fmt)
    except ValueError as exc: raise ServiceError('公告日期格式或日历日期无效') from exc
    label = r'发布|公告日期|公告时间|日期' if kind == 'publication' else r'截止|递交|投标时间'
    # 保留ISO日期与时钟之间的边界，其余排版空白可以忽略；否则03 23会被误当033。
    compact_quote=re.sub(r'\s+','',re.sub(r'(\d{4}-\d{2}-\d{2})\s+(\d{1,2}:)',r'\1T\2',quote))
    if not re.search(label, compact_quote): raise ServiceError('公告日期缺少对应用途标签')
    if kind=='publication' and not re.search('发布时间|公告日期|公告时间|发布日期',quote) and re.search('计划|拟于|文件|下载|获取',quote):
        raise ServiceError('计划发布或文件获取日期不是实际公告发布日期')
    date_pattern = fr'{stamp.year}[-年/.]0?{stamp.month}[-月/.]0?{stamp.day}(?:日)?(?!\d)'
    if not re.search(date_pattern, compact_quote): raise ServiceError('公告日期未在对应原文出现')
    if fmt.endswith('%S'):
        from .procurement import deadline_in_quote
        if not deadline_in_quote(value, compact_quote): raise ServiceError('公告时分秒没有对应原文')
    return value


def original_deadline(body: str) -> tuple[str,str]:
    """body为已归档正文可空；仅提取唯一、带截止用途标签的真实日期，返回日期及连续原文，歧义返回空。

    24:00保留原文，只输出原日期粒度，不推算次日；没有时分秒不补午夜。
    """
    pattern=r'(?:投标|报价|响应文件)?截止(?:时间|日期)?[：:\s]*(?P<y>\d\s*\d\s*\d\s*\d)[年/.-]\s*(?P<m>\d(?:\s*\d)?)[月/.-]\s*(?P<d>\d(?:\s*\d)?)日?(?:\s*(?P<h>\d{1,2}):(?P<minute>\d{2})(?::(?P<second>\d{2}))?)?'
    candidates=[]
    for match in re.finditer(pattern,body or ''):
        parts={key:re.sub(r'\s+','',value) if value else value for key,value in match.groupdict().items()};value=f"{int(parts['y']):04d}-{int(parts['m']):02d}-{int(parts['d']):02d}"
        if parts['h'] is not None and parts['second'] is not None and int(parts['h'])<24:
            value+=f" {int(parts['h']):02d}:{parts['minute']}:{parts['second']}"
        try:notice_date(value,match.group(),'deadline')
        except ServiceError:continue
        candidates.append((value,match.group()))
    return candidates[0] if candidates and len({value for value,quote in candidates})==1 else ('','')


def source_owned(db, company: Company, source: Evidence, domain_only=False) -> bool:
    """db与两个已存在记录必填；全文声明主体或已核验公司网址的同域页面才可归属，不凭相似域名。"""
    from .qcc_evidence import authorized, primary_matches
    if authorized(source):return not domain_only and primary_matches(source.body, company.name)
    if not domain_only and normalize(company.name) in normalize(source.title or '')+normalize(source.body[:12000]):return True
    from urllib.parse import urlparse
    from .contact_view import website_link
    host=(urlparse(source.url).hostname or '').removeprefix('www.')
    sites=db.scalars(select(CompanyFact).where(CompanyFact.company_id==company.id,CompanyFact.field=='website',CompanyFact.status=='verified'))
    for fact in sites:
        if not re.search('公司网址|官方网站|官网',fact.label):continue
        if not re.search('公司网址|官方网站|官网',fact.quote):continue
        url=website_link(str(fact.raw_value or ''))
        official=(urlparse(url).hostname or '').removeprefix('www.') if url else ''
        if official and (host==official or host.endswith('.'+official)):return True
    return False


def cited_source(db, source_id: str, quote: str, allowed: set, allow_history=False) -> Evidence:
    """db为事务、source_id/quote必填、allowed当前任务许可；仅真实全文连续引文可引用，失败抛业务错误。"""
    row = db.get(Evidence, source_id)
    kinds={'网页正文','网页读取','Edge网页正文'} | ({'历史归档正文'} if allow_history else set())
    authorized_qcc = bool(row and row.kind == '授权数据' and row.channel == 'qcc_mcp' and
        isinstance(row.source_meta, dict) and row.source_meta.get('origin') == 'qcc_mcp' and
        row.source_meta.get('authorized') is True)
    if source_id not in allowed or not row or (row.kind not in kinds and not authorized_qcc) or (not authorized_qcc and not has_content({'title':row.title,'body':row.body,'url':row.url})):
        raise ServiceError('字段没有本任务已读全文证据')
    from .industry_navigation import factual_body
    # 引文只容忍PDF/网页排版空白，不能改逗号或英文大小写后假称为原文片段。
    candidate = quote
    if authorized_qcc:
        from .qcc_evidence import validate_quote
        if not quote.startswith('$.'):
            raise ServiceError('授权数据缺少结构化字段路径')
        if not validate_quote(row.body, quote):
            raise ServiceError('授权数据字段路径与值不一致')
        return row
    if re.sub(r'\s+','',candidate) not in re.sub(r'\s+','',factual_body(row.body)): raise ServiceError('字段引文不是连续原文')
    return row


def subject_field(name: str, source: Evidence, quote: str) -> bool:
    """name为完整名、source为已读正文、quote为连续字段引文；只认本主体片段或单主体页，缺归属返回False。"""
    from .evidence_role import competing_subject
    compact = lambda value: re.sub(r'\s+', '', value or '')
    if competing_subject(name, quote): return False
    if compact(name) in compact(quote): return True
    title = source.title or ''
    return compact(name) in compact(title) and not competing_subject(name, title) and not re.search('年报|年度报告|名单|目录|名录|列表', title)


def save_snapshot(job_id: str, snapshot: CompanySnapshot, allowed: set, targets: list[str], relation_id: str | None = None) -> dict:
    """job_id须存在，snapshot为提议、allowed/targets为作用域；relation_id空走主体研究，非空只补已授权关系。

    返回逐项核验回执；无来源/错主体/未授权关系抛ServiceError，事实/引用/绑定随同事务回滚。
    """
    rejected = []; accepted = 0;accepted_refs=[];project_buyers=set()
    with Session.begin() as db:
        # 两个研究任务可同时发现同一事实，先取得短写事务，避免语义去重的查询/插入竞态。
        db.execute(text('BEGIN IMMEDIATE'))
        job = db.get(Job, job_id)
        if not job: raise ServiceError('任务不存在', 404)
        selected = (job.metrics or {}).get('target_company_id')
        relation = db.get(CompanyRelation, relation_id) if relation_id else None
        if relation_id:
            from .relation_service import composite_name
            owners = set(job.company_ids or []) | ({selected} if selected else set())
            fields = (job.metrics or {}).get('requested_fields', [])
            explicit = (job.metrics or {}).get('counterparty_only')
            if not relation or relation.company_id not in owners or not (explicit or {'supplier', 'customer'} & set(fields)):
                raise ServiceError('关系不属于本次上下游补查范围')
            if explicit and relation.id not in (job.metrics or {}).get('counterparty_relation_ids', []):
                raise ServiceError('关系未在本次选择范围内')
            if composite_name(relation.counterparty_name): raise ServiceError('组合主体需要单独核验')
            if not target_matches(snapshot.name, relation.counterparty_name, snapshot.identity_quote):
                raise ServiceError('对手方身份与报告名称不一致')
        identity = cited_source(db, snapshot.source_id, snapshot.identity_quote, allowed, allow_history=True)
        from .qcc_evidence import authorized, field_matches
        if authorized(identity) and not field_matches(identity.body, snapshot.name, snapshot.identity_quote,'name'):
            raise ServiceError('授权数据身份不是响应的主企业')
        name = normalize(snapshot.name)
        if name not in normalize(snapshot.identity_quote): raise ServiceError('企业名称没有身份引文')
        if targets and not any(target_matches(snapshot.name, t, snapshot.identity_quote) for t in targets):
            raise ServiceError('提议主体不属于本次指定研究范围')
        if selected and not relation and db.get(Company, selected).name != snapshot.name: raise ServiceError('补查主体与已选择企业不一致')
        existed = db.scalar(select(Company.id).where(Company.name == snapshot.name))
        if relation and existed:
            # 身份冲突拒绝整份补查，不能把同名另一公司的主营写入既有档案。
            existing = db.get(Company, existed)
            codes = {normalize(f.raw_value) for f in db.scalars(select(CompanyFact).where(CompanyFact.company_id == existed, CompanyFact.field == 'credit_code', CompanyFact.status == 'verified'))}
            if existing.credit_code: codes.add(normalize(existing.credit_code))
            proposed = {normalize(f.value) for f in snapshot.facts if f.field == 'credit_code'}
            if proposed and codes and proposed != codes: raise ServiceError('同名企业信用代码冲突，需重新确认主体')
        company = ensure_company(db, snapshot.name, visibility='primary', origin='agent', research_as_of=now()[:10],
            entity_kind='legal' if re.search('有限公司|股份|有限合伙', snapshot.name) else 'unknown')
        # 被用户明确研究的既有关联主体也应进入查询结果，不能保存成功后仍被primary筛选隐藏。
        if not relation: company.visibility='primary'
        elif not existed: company.visibility='counterparty'
        identity_key=stable_key(company.id,'identity',snapshot.name)
        identity_fact=db.scalar(select(CompanyFact).where(CompanyFact.company_id==company.id,CompanyFact.field=='name',func.json_extract(CompanyFact.raw_value,'$')==snapshot.name))
        if not identity_fact:
            identity_fact=CompanyFact(unique_key=identity_key,company_id=company.id,field='name',label='企业名称',category='企业身份',
                raw_value=snapshot.name,source_ids=[identity.id],quote=snapshot.identity_quote,
                provenance={'origin':'historical_identity_reused' if identity.kind=='历史归档正文' else 'agent','job_id':job_id})
            db.add(identity_fact);db.flush()
        elif identity_fact.status in {'inactive','disputed'}:raise ServiceError('企业身份存在审核限制，不能自动复活')
        else:identity_fact.source_ids=list(dict.fromkeys([*(identity_fact.source_ids or []),identity.id]))
        identity_fact.provenance=append_citations(identity_fact.provenance,identity.id,{'value':snapshot.identity_quote},identity.url)
        accepted_refs.append({'kind':'identity','id':identity_fact.id,'field':'name','source_id':identity.id,'source_ids':identity_fact.source_ids,'url':identity.url,'quote':snapshot.identity_quote})
        for item in snapshot.facts:
            try:
                source = cited_source(db, item.source_id, item.quote, allowed, allow_history=True)
                if normalize(item.value) not in normalize(item.quote): raise ServiceError('字段值未在连续引文出现')
                if not source_owned(db,company,source): raise ServiceError('字段来源未明确归属于该主体')
                if authorized(source) and not field_matches(source.body, company.name, item.quote,item.field):
                    raise ServiceError('授权字段不属于响应的主企业')
                if relation and not subject_field(company.name, source, item.quote):
                    raise ServiceError('对手方字段缺少本主体归属，不能借用主企业资料')
                if item.metadata_quote: cited_source(db, item.source_id, item.metadata_quote, allowed, allow_history=True)
                if item.field in {'phone','email'}:
                    from .contact_owner import public_phone
                    from .contact_owner import buyer_contact
                    from .evidence_role import competing_subject
                    # 集团公告出现买方名称不授予集团页尾号码归属；不向原始网页标题补企业名。
                    owner_title=source.title or ''
                    if competing_subject(snapshot.name,owner_title) and not buyer_contact(snapshot.name,item.value,source.body):
                        raise ServiceError('集团或其他主体页面的联系值不在本企业买方联系块')
                    if not public_phone(snapshot.name,item.value,source.body,owner_title):raise ServiceError('联系值没有明确的本主体归属')
                if item.field in {'headcount','revenue'} and not valid_statistics(item.scope, item.report_period, item.metadata_quote or item.quote):
                    raise ServiceError('统计口径与报告期缺少原文支持')
                if item.field in {'headcount','revenue'}:
                    context = item.quote + item.metadata_quote
                    other_names = db.scalars(select(Company.name).where(Company.id != company.id))
                    if any(normalize(n) in normalize(context) for n in other_names if n != company.name):
                        raise ServiceError('统计引文包含其他主体，不能写为本企业统计值')
                    group_scope = re.search('合并|公司及控股子公司|公司及其子公司|本公司及子公司', item.scope)
                    if not group_scope and name not in normalize(context):
                        raise ServiceError('统计引文未明确本企业或集团合并口径')
                    numeric_evidence(item.value, item.unit, item.quote, item.metadata_quote)
                if item.field == 'short_name' and not target_matches(company.name, item.value, item.quote):
                    raise ServiceError('简称未与完整主体在同一声明中绑定')
                if item.field in {'industry','business','products'} and decimal_value(item.value) is not None: raise ServiceError('行业或主营不能用统计数量代替')
                if item.field=='products' and re.search('产品介绍|宣传片|视频',item.quote) and name not in normalize(item.quote) and name not in normalize(source.title):
                    raise ServiceError('视频或介绍标题未证明本主体产品归属')
                if item.field in {'products','business'} and re.search('本项目|采购货物|采购内容|采购项目|拟采购',item.quote) and not re.search('主营|自主设计|自产|公司生产|主要产品',item.quote):
                    raise ServiceError('采购设备不能作为本企业主营或自产产品')
                if item.field=='products' and re.search('未来.{0,8}(?:将|拓展)|公司将|拟生产|计划拓展|重点拓展',item.quote):
                    raise ServiceError('未来拓展计划不能作为已实现产品能力')
                if item.field == 'industry' and re.search('行业标准|数量|排名', item.quote): raise ServiceError('行业标准数量不是行业分类')
                if item.field == 'revenue' and re.search('对应年度采购金额|对应年度销售金额|供应商采购额|前五客户', item.label): raise ServiceError('对手方交易额不能作本企业营收')
                key = (stable_key('semantic-detail-1',company.id,item.field,item.label,normalize(item.value),item.unit,item.report_period,item.scope)
                    if item.field=='detail' else stable_key('semantic-fact-1',company.id,item.field,normalize(item.value),item.unit,item.report_period,item.scope))
                possible=list(db.scalars(select(CompanyFact).where(CompanyFact.company_id==company.id,CompanyFact.field==item.field,
                    func.coalesce(CompanyFact.report_period,'')==item.report_period,func.coalesce(CompanyFact.unit,'')==item.unit,
                    func.coalesce(CompanyFact.scope,'')==item.scope)))
                if item.field=='detail':possible=[row for row in possible if row.label==item.label]
                # 历史导入JSON数值617与模型文本“617”是同一业务值，不能误建新事实或制造统计冲突。
                numeric=decimal_value(item.value)
                fact=next((row for row in possible if normalize(row.raw_value)==normalize(item.value) or
                    numeric is not None and decimal_value(str(row.raw_value))==numeric),None)
                is_new=not fact
                if not fact:
                    if item.field in {'credit_code','stock_code','headcount','revenue'}:
                        conflicting=list(db.scalars(select(CompanyFact).where(CompanyFact.company_id==company.id,CompanyFact.field==item.field,
                            func.coalesce(CompanyFact.report_period,'')==item.report_period,func.coalesce(CompanyFact.unit,'')==item.unit,
                            func.coalesce(CompanyFact.scope,'')==item.scope,CompanyFact.status=='verified')))
                        if conflicting:
                            for previous in conflicting:
                                previous.status='disputed'
                                alternatives=list((previous.provenance or {}).get('alternatives',[]))
                                alternative={'value':item.value,'source_id':source.id,'quote':item.quote,'job_id':job_id}
                                if alternative not in alternatives:alternatives.append(alternative)
                                previous.provenance={**(previous.provenance or {}),'alternatives':alternatives}
                            raise ServiceError('同一统计口径或身份字段存在不同值，保留争议待核验')
                    fact=CompanyFact(unique_key=key, company_id=company.id, field=item.field, label=item.label,
                        category={'headcount':'经营规模','revenue':'财务数据','phone':'公开联系方式','email':'公开联系方式','website':'公开联系方式','procurement_rule':'采购特征','products':'产品能力'}.get(item.field, '企业资料'),
                        raw_value=item.value, numeric_value=decimal_value(item.value), unit=item.unit, raw_unit=item.unit,
                        report_period=item.report_period, as_of=item.report_period, scope=item.scope,
                        source_ids=[source.id], quote=item.quote, note=item.note,
                        provenance={'origin':'agent','job_id':job_id,'policy':COMPANY_POLICY,'metadata_quote':item.metadata_quote})
                    db.add(fact);db.flush()
                elif fact.status in {'inactive','disputed'}:
                    raise ServiceError('既有字段已失效或存在争议，保留原审核状态')
                else:
                    fact.source_ids=list(dict.fromkeys([*(fact.source_ids or []),source.id]))
                    citations=list((fact.provenance or {}).get('citations',[]))
                    citation={'source_id':source.id,'quote':item.quote,'job_id':job_id}
                    if citation not in citations:citations.append(citation)
                    fact.provenance={**(fact.provenance or {}),'citations':citations,'last_confirmed_job_id':job_id}
                    fact.updated_at=now()
                if item.field == 'short_name' and not company.short_name: company.short_name = item.value
                fact.provenance=append_citations(fact.provenance,source.id,{'value':item.quote,'metadata':item.metadata_quote},source.url)
                if item.field == 'credit_code' and re.fullmatch(r'[A-Z0-9]{18}', item.value): company.credit_code = item.value
                accepted += 1
                accepted_refs.append({'kind':'fact','id':fact.id,'field':item.field,'source_id':source.id,'source_ids':fact.source_ids,'url':source.url,'quote':item.quote,'change':'new' if is_new else 'reconfirmed'})
            except ServiceError as exc: rejected.append(item.label + '：' + str(exc))
        for item in snapshot.relations:
            try:
                source = cited_source(db, item.source_id, item.quote, allowed, allow_history=True)
                if normalize(item.counterparty_name) not in normalize(item.quote): raise ServiceError('对手方未出现在关系引文')
                if name not in normalize(source.title or '') + normalize(source.body[:12000]): raise ServiceError('关系报告不属于该企业')
                if item.metadata_quote: cited_source(db, item.source_id, item.metadata_quote, allowed, allow_history=True)
                context = item.quote + item.metadata_quote
                required = {'supplier':'供应商|采购','customer':'客户|销售','subsidiary':'子公司|持股|控制','service_supplier':'劳务|服务'}[item.relation_type]
                if not re.search(required, context): raise ServiceError('关系类型未有原文支持')
                if item.relation_type == 'subsidiary' and reversed_subsidiary(company.name, item.counterparty_name, item.quote):
                    raise ServiceError('子公司关系方向相反：本企业是对方的下属企业')
                amount = decimal_value(item.amount)
                if item.amount is not None: numeric_evidence(item.amount, item.unit, item.quote, item.metadata_quote)
                if item.share is not None: numeric_evidence(format(item.share, 'g'), '%', item.quote, item.metadata_quote)
                if (amount is not None or item.share is not None) and (not item.report_period or item.report_period[:4] not in context): raise ServiceError('年度交易缺少报告期原文')
                currencies = {'CNY':r'人民币|\bRMB\b|\bCNY\b','USD':r'美元|美金|\bUSD\b|US\$','EUR':r'欧元|\bEUR\b|€'}
                currency = item.currency if item.currency and re.search(currencies[item.currency], context, re.I) else None
                if item.currency and not currency and any(re.search(pattern, context, re.I) for pattern in currencies.values()):
                    raise ServiceError('币种与关系金额的原文不一致')
                # 年度关系行使用独立变量名，不能覆盖补查对手方时传入的父关系relation（否则会把最后一条关系绑定到本企业）。
                key = stable_key('semantic-relation-1',company.id,item.counterparty_name,item.relation_type,item.report_period,item.amount,item.unit,currency,item.share)
                saved_relation=db.scalar(select(CompanyRelation).where(CompanyRelation.company_id==company.id,CompanyRelation.counterparty_name==item.counterparty_name,
                    CompanyRelation.relation_type==item.relation_type,CompanyRelation.report_period==item.report_period,
                    CompanyRelation.amount==amount,CompanyRelation.unit==item.unit,CompanyRelation.currency==currency,CompanyRelation.share==item.share))
                is_new=not saved_relation
                if not saved_relation:
                    counterparty_id = None
                    if item.relation_type == 'subsidiary':
                        if name not in normalize(context): raise ServiceError('子公司关系未明确母公司与子公司双端')
                        subsidiary = ensure_company(db, item.counterparty_name, visibility='related', origin='agent')
                        counterparty_id = subsidiary.id
                    saved_relation=CompanyRelation(unique_key=key, company_id=company.id, counterparty_name=item.counterparty_name,
                        counterparty_id=counterparty_id,
                        relation_type=item.relation_type, report_period=item.report_period, amount=amount, unit=item.unit,
                        currency=currency, share=item.share, scope='年度采购交易' if item.relation_type=='supplier' else '年度销售交易' if item.relation_type=='customer' else '原文关系',
                        source_ids=[source.id], quote=item.quote, note=item.note, payload={'metadata_quote':item.metadata_quote,'policy':COMPANY_POLICY})
                    db.add(saved_relation);db.flush()
                else:saved_relation.source_ids=list(dict.fromkeys([*(saved_relation.source_ids or []),source.id]))
                saved_relation.payload=append_citations(saved_relation.payload,source.id,{'value':item.quote,'metadata':item.metadata_quote},source.url)
                accepted += 1
                accepted_refs.append({'kind':'saved_relation','id':saved_relation.id,'field':item.relation_type,'source_id':source.id,'source_ids':saved_relation.source_ids,'url':source.url,'quote':item.quote,'change':'new' if is_new else 'reconfirmed'})
            except ServiceError as exc: rejected.append(item.counterparty_name + '：' + str(exc))
        for item in snapshot.projects:
            try:
                source = cited_source(db, item.source_id, item.quote, allowed, allow_history=True)
                if item.metadata_quote: cited_source(db, item.source_id, item.metadata_quote, allowed, allow_history=True)
                for span in (item.publication_quote, item.deadline_quote, item.budget_quote, item.buyer_quote, item.quantity_quote, item.project_number_quote):
                    if span: cited_source(db, item.source_id, span, allowed, allow_history=True)
                published = notice_date(item.publication_date, item.publication_quote or item.metadata_quote, 'publication')
                deadline = notice_date(item.deadline, item.deadline_quote or item.metadata_quote, 'deadline')
                if deadline and len(deadline)==10:
                    precise,span=original_deadline(source.body)
                    if precise.startswith(deadline) and len(precise)>len(deadline):
                        deadline=precise;item.deadline_quote=span
                quote = normalize(item.quote)
                buyer_span=item.buyer_quote or item.quote
                if normalize(item.buyer_name) not in normalize(buyer_span) or not re.search('招标人|采购人|采购单位|买方', buyer_span): raise ServiceError('实际买方没有公告角色原文')
                if normalize(item.title) not in normalize(source.body) or item.project_number and normalize(item.project_number) not in normalize(item.project_number_quote or item.quote): raise ServiceError('项目身份没有公告原文')
                buyer = db.scalar(select(Company).where(Company.name == item.buyer_name))
                if item.buyer_name != company.name and (not buyer or buyer.id not in scope_ids(db, company)): raise ServiceError('公告买方不是本企业或已核验子公司')
                buyer = buyer or company
                if item.quantity is not None and normalize(format(item.quantity,'g') + item.unit) not in normalize(item.quantity_quote or item.quote): raise ServiceError('需求数量与单位缺少对应原文')
                budget = decimal_value(item.budget_value)
                budget_span = item.budget_quote or item.quote
                if budget is not None and (normalize(item.budget_value) not in normalize(budget_span) or
                    not re.search('预算|最高限价|限价', budget_span) or not item.budget_unit or normalize(item.budget_unit) not in normalize(budget_span)):
                    raise ServiceError('预算金额、单位或预算用途缺少原文，不允许候选报价反填')
                if item.specifications and normalize(item.specifications) not in normalize(source.body): raise ServiceError('规格不是实际原文')
                number = item.project_number or source.url
                key = stable_key('agent-project', buyer.id, number)
                # 精确买方+原项目号跨历史/实时关联，不删除编号后缀，不靠标题猜合并。
                project = db.scalar(select(ProcurementProject).where(ProcurementProject.buyer_id == buyer.id,
                    ProcurementProject.project_number == item.project_number, ProcurementProject.record_kind == 'procurement')) if item.project_number else None
                if not project: project = db.scalar(select(ProcurementProject).where(ProcurementProject.unique_key == key))
                if project and project.payload.get('duplicate_of'):project=db.get(ProcurementProject,project.payload['duplicate_of'])
                if not project and (deadline or published):
                    # 同买方、原始标题和真实日期可合并跨域转载；缺日期不按相似标题合并不同采购。
                    candidates=db.scalars(select(ProcurementProject).where(ProcurementProject.buyer_id==buyer.id,
                        ProcurementProject.record_kind=='procurement',
                        ProcurementProject.payload['duplicate_of'].as_string().is_(None),
                        ProcurementProject.deadline==deadline if deadline else ProcurementProject.published_at==published))
                    for candidate in candidates:
                        old_title,new_title=normalize(candidate.title),normalize(item.title)
                        same_title=old_title==new_title or min(len(old_title),len(new_title))>=8 and (old_title in new_title or new_title in old_title) and old_title in normalize(source.body)
                        same_number=not candidate.project_number and not item.project_number or candidate.project_number==item.project_number
                        if candidate.project_number and not item.project_number:same_number=normalize(candidate.project_number) in normalize(source.body)
                        if item.project_number and not candidate.project_number:
                            same_number=any(normalize(item.project_number) in normalize(previous.body) for sid in candidate.source_ids if (previous:=db.get(Evidence,sid)))
                        if same_title and same_number and all(candidate.payload.get(field) in (None,'',value) or value in (None,'')
                            for field,value in [('quantity',item.quantity),('unit',item.unit)]):project=candidate;break
                if project and not project.project_number and item.project_number:project.project_number=item.project_number
                stages = {'open':'公开招标','candidate':'候选公示','awarded':'已成交','closed':'已关闭','unknown':'阶段待核'}
                stage_terms = {'open':'招标|采购公告|询价','candidate':'候选','awarded':'中标结果|成交公告|成交结果','closed':'终止|关闭|废标','unknown':'.'}
                if not re.search(stage_terms[item.stage], item.quote + source.title + item.title): raise ServiceError('公告阶段没有对应原文')
                project_is_new=not project
                if not project:
                    project = ProcurementProject(unique_key=key, buyer_id=buyer.id, title=item.title, project_number=item.project_number,
                        stage=stages[item.stage], published_at=published, deadline=deadline, source_ids=[source.id], quote=item.quote,
                        payload={'product':item.product,'quantity':item.quantity,'unit':item.unit,'budget':{'amount':float(budget),'unit':item.budget_unit,'type':'预算','currency_code':None} if budget is not None else None,
                            'specifications':[{'raw':item.specifications}] if item.specifications else [],'currency_confirmed':False})
                    db.add(project); db.flush()
                # 有明确日期的同标题同阶段是一个公告事件；日期未知时只按原URL关联，避免猜转载关系。
                notice_key = stable_key('notice-event', project.id, item.title, item.stage, published or source.url, deadline)
                notice = db.scalar(select(ProcurementNotice).where(ProcurementNotice.unique_key == notice_key))
                if notice and notice.payload.get('duplicate_of'):notice=db.get(ProcurementNotice,notice.payload['duplicate_of'])
                if not notice:
                    existing = list(db.scalars(select(ProcurementNotice).where(ProcurementNotice.project_id == project.id)))
                    for row in existing:
                        urls = [e.url for sid in row.source_ids or [] if (e := db.get(Evidence, sid))]
                        same_stage = row.notice_type == stages[item.stage] or (bool(re.search(stage_terms[item.stage], row.notice_type)) if item.stage != 'unknown' else False)
                        if row.payload.get('duplicate_of'):continue
                        old_title,new_title=normalize(row.title),normalize(item.title)
                        same_title=old_title==new_title or min(len(old_title),len(new_title))>=8 and (old_title in new_title or new_title in old_title) and old_title in normalize(source.body)
                        same_deadline=bool(deadline and row.deadline==deadline and same_title)
                        if same_stage and (source.url in urls or published and row.published_at == published and row.deadline == deadline and row.title == item.title or same_deadline):
                            notice = row; break
                if notice:
                    notice.source_ids = list(dict.fromkeys([*(notice.source_ids or []), source.id]))
                    if published and not notice.published_at: notice.published_at = published
                    if deadline and not notice.deadline: notice.deadline = deadline
                else:
                    notice=ProcurementNotice(unique_key=notice_key, project_id=project.id, title=item.title, notice_type=stages[item.stage],
                        published_at=published, deadline=deadline, source_ids=[source.id],
                        payload={'quote':item.quote,'publication_quote':item.publication_quote,'deadline_quote':item.deadline_quote,'budget_quote':item.budget_quote,'buyer_quote':buyer_span,'quantity_quote':item.quantity_quote})
                    db.add(notice)
                notice.payload=append_citations(notice.payload,source.id,{'value':item.quote,'metadata':item.metadata_quote,
                    'publication':item.publication_quote,'deadline':item.deadline_quote,'budget':item.budget_quote,'buyer':buyer_span,'quantity':item.quantity_quote,'project_number':item.project_number_quote},source.url)
                project.source_ids = list(dict.fromkeys([*(project.source_ids or []), source.id]))
                # 抓取顺序不是公告顺序；只有可比较的公告日期才能更新当前项目状态。
                if published and (not project.published_at or published >= project.published_at):
                    project.stage, project.published_at = stages[item.stage], published
                    if deadline: project.deadline = deadline
                    project.quote = item.quote
                payload = dict(project.payload or {})
                if payload.get('quantity') is None and item.quantity is not None: payload.update(quantity=item.quantity, unit=item.unit)
                if not payload.get('product') and item.product: payload['product'] = item.product
                if not payload.get('budget') and budget is not None: payload['budget'] = {'amount':float(budget),'unit':item.budget_unit,'type':'预算','currency_code':None}
                if not payload.get('specifications') and item.specifications: payload['specifications'] = [{'raw':item.specifications}]
                project.payload, project.updated_at = append_citations(payload,source.id,{'value':item.quote,'metadata':item.metadata_quote,
                    'publication':item.publication_quote,'deadline':item.deadline_quote,'budget':item.budget_quote,'buyer':buyer_span,'quantity':item.quantity_quote,'project_number':item.project_number_quote},source.url), now()
                project_buyers.add(buyer.id)
                accepted += 1
                accepted_refs.append({'kind':'project','id':project.id,'field':'procurement','source_id':source.id,'source_ids':project.source_ids,'url':source.url,'quote':item.quote,'change':'new' if project_is_new else 'reconfirmed'})
            except ServiceError as exc: rejected.append(item.title + '：' + str(exc))
        # 有已核验身份也可形成主体结果，字段缺口和拒绝项清楚标记，不伪称全画像完成。
        company.updated_at = now(); company.research_as_of = now()[:10]
        company.metadata_json = {**(company.metadata_json or {}), 'gaps': list(dict.fromkeys([*snapshot.gaps, *rejected]))[:24], 'last_research_job_id': job_id}
        member_key = stable_key(job.conversation_id, job_id, company.id)
        if not relation and not db.scalar(select(ResearchCompany.id).where(ResearchCompany.unique_key == member_key)):
            db.add(ResearchCompany(unique_key=member_key, company_id=company.id, conversation_id=job.conversation_id, job_id=job_id,
                position=len(job.company_ids or []), origin='agent'))
        if not relation: job.company_ids = list(dict.fromkeys([*(job.company_ids or []), company.id]))
        else:
            # 对手方资料不能绑定到本企业自身（模型把本企业资料当作对手方提交时拒绝）。
            if company.id == relation.company_id: raise ServiceError('对手方资料与本企业为同一主体，未绑定')
            relation.counterparty_id = company.id
            relation.payload = {**(relation.payload or {}), 'identity_binding': {'status': 'verified', 'company_id': company.id,
                'source_id': identity.id, 'identity_quote': snapshot.identity_quote, 'verified_at': now()},
                'profile_research': {'status': 'partial' if rejected else 'verified', 'job_id': job_id, 'updated_at': now()}}
            # 同一交易行的重复来源共享身份绑定，避免首屏去重保留了未绑定的版本。
            peers = db.scalars(select(CompanyRelation).where(CompanyRelation.company_id == relation.company_id,
                CompanyRelation.counterparty_name == relation.counterparty_name, CompanyRelation.relation_type == relation.relation_type,
                CompanyRelation.report_period == relation.report_period))
            for peer in peers:
                if (peer.amount, peer.share, peer.unit, peer.currency) == (relation.amount, relation.share, relation.unit, relation.currency):
                    peer.counterparty_id = company.id
                    peer.payload = {**(peer.payload or {}), 'identity_binding': relation.payload['identity_binding'], 'profile_research': relation.payload['profile_research']}
        db.flush()
        from .source_service import bind_company_sources
        bindings={'documents':0,'fragments':0,'bindings':0}
        # 集团研究可以保存已有归属证据的子公司采购；项目/公告绑定须使用实际买方，不能只绑定集团主档。
        for owner_id in sorted({company.id,*project_buyers}):
            delta=bind_company_sources(db,owner_id)
            for key in bindings:bindings[key]+=delta[key]
        if accepted and not (job.metrics or {}).get('first_verified_result_ms'):
            # 与事实和来源绑定同事务提交；仅身份不能当有效首批结果。
            submitted=(job.metrics or {}).get('submitted_epoch') or time.time()
            job.metrics={**(job.metrics or {}),'first_verified_result_ms':max(1,round((time.time()-submitted)*1000))}
        return {'company_id':company.id,'company_name':company.name,'identity_quote':snapshot.identity_quote,'accepted_fields':accepted,'rejected':rejected,'sources':[],
            'source_bindings':bindings,
            'accepted_refs':accepted_refs,'new_records':sum(item.get('change')=='new' for item in accepted_refs),
            'reconfirmed_records':sum(item.get('change')=='reconfirmed' for item in accepted_refs)}


def reversed_subsidiary(company: str, counterparty: str, quote: str) -> bool:
    """company/counterparty为双方原名、quote为关系引文；原文写明“本企业是对方的（全资/控股/下属）子公司”时返回True。"""
    text = re.sub(r'\s+', '', quote or '')
    own, other = re.sub(r'\s+', '', company or ''), re.sub(r'\s+', '', counterparty or '')
    if not own or not other or own not in text or other not in text: return False
    # 同一句内：本企业 …（≤60字）… 是/为/系 …（≤30字）… 对方 …（≤12字）… 子公司/下属。
    return bool(re.search(re.escape(own) + r'[^。；;]{0,60}?(?:是|为|系|作为)[^。；;]{0,30}?' + re.escape(other) + r'[^。；;]{0,12}(?:子公司|下属|控股|全资)', text))
