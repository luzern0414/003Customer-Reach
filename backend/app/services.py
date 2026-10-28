"""API 使用的查询与写操作。上下游关系由公告参与方推导：
客户 = 本企业中标/候选的公告的采购人；供应商 = 本企业采购的公告的中标人；竞争对手 = 同一公告中的其他中标/候选人。"""
import hashlib
import io
import re
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from sqlalchemy import func, or_, select
from sqlalchemy.orm import aliased

from . import crawl, llm
from .config import CRAWL_OUT, UPLOADS
from .db import (Attachment, Company, Conversation, CustomSite, DiscoveredSite, Fact, Feedback, Followup, Job, JobCompany, Knowledge, Lead,
                 Message, Notice, NoticeParty, Session, SiteStat, Source, get_settings, now)
from .documents import parse_document
from .research.pipeline import KIND_LABELS
from .research.schemas import MatchAnalysis
from .sites import all_sites, from_custom, known_domain

LEAD_STATUS = {'new': '新线索', 'verifying': '待核验', 'contacted': '已联系', 'following': '持续跟进',
               'won': '已成交', 'invalid': '无效'}
PROFILE_LABELS = {'credit_code': '统一社会信用代码', 'legal_person': '法定代表人', 'registered_capital': '注册资本',
                  'founded_on': '成立日期', 'business_status': '经营状态', 'industry': '行业', 'address': '地址',
                  'website': '官网', 'phone': '电话', 'email': '邮箱', 'scope': '经营范围'}


class NotFound(Exception):
    pass


def _row(obj, *fields) -> dict:
    return {field: getattr(obj, field) for field in fields}


def _get(db, model, key):
    row = db.get(model, key)
    if not row:
        raise NotFound()
    return row


# ---------- 会话与任务 ----------

def conversations() -> list[dict]:
    with Session() as db:
        rows = list(db.scalars(select(Conversation).order_by(Conversation.updated_at.desc()).limit(100)))
        latest = {}
        for job in db.scalars(select(Job).where(Job.conversation_id.in_([c.id for c in rows])).order_by(Job.created_at)):
            latest[job.conversation_id] = job.status
        return [{**_row(c, 'id', 'title', 'updated_at'), 'status': latest.get(c.id, '')} for c in rows]


def create_conversation() -> dict:
    with Session.begin() as db:
        conversation = Conversation()
        db.add(conversation)
        db.flush()
        return _row(conversation, 'id', 'title', 'updated_at')


def job_view(job: Job) -> dict:
    return _row(job, 'id', 'mode', 'status', 'stage', 'metrics', 'handover', 'error', 'reply_message_id',
                'created_at', 'finished_at')


def conversation_detail(conversation_id: str) -> dict:
    with Session() as db:
        conversation = _get(db, Conversation, conversation_id)
        messages = db.scalars(select(Message).where(Message.conversation_id == conversation_id)
                              .order_by(Message.created_at))
        jobs = db.scalars(select(Job).where(Job.conversation_id == conversation_id).order_by(Job.created_at))
        attachments = {}
        result = {**_row(conversation, 'id', 'title', 'updated_at'), 'messages': [], 'jobs': [job_view(j) for j in jobs]}
        for message in messages:
            for aid in message.attachment_ids or []:
                if aid not in attachments and (item := db.get(Attachment, aid)):
                    attachments[aid] = attachment_view(item)
            result['messages'].append({**_row(message, 'id', 'role', 'content', 'job_id', 'created_at'),
                                       'attachments': [attachments[a] for a in message.attachment_ids or [] if a in attachments]})
        return result


def submit(conversation_id: str, content: str, attachment_ids: list[str], mode: str = '', company: str = '') -> dict:
    with Session.begin() as db:
        conversation = _get(db, Conversation, conversation_id)
        busy = db.scalar(select(Job.id).where(Job.conversation_id == conversation_id,
                                              Job.status.in_(['queued', 'running', 'awaiting_user'])))
        if busy:
            raise ValueError('当前对话还有进行中的任务')
        message = Message(conversation_id=conversation_id, role='user', content=content,
                          attachment_ids=[a for a in attachment_ids if db.get(Attachment, a)])
        db.add(message)
        db.flush()
        hints = {k: v for k, v in (('mode_hint', mode), ('company_hint', company)) if v}
        job = Job(conversation_id=conversation_id, message_id=message.id, plan=hints)
        db.add(job)
        conversation.updated_at = now()
        db.flush()
        message.job_id = job.id
        return {'message_id': message.id, 'job': job_view(job)}


def job_detail(job_id: str) -> dict:
    with Session() as db:
        return job_view(_get(db, Job, job_id))


def job_results(job_id: str) -> dict:
    """本次任务产出的企业（目标/买家在前）与线索数。"""
    with Session() as db:
        _get(db, Job, job_id)
        rows = db.execute(select(Company, JobCompany.role).join(JobCompany, JobCompany.company_id == Company.id)
                          .where(JobCompany.job_id == job_id)).all()
        order = {'target': 0, 'buyer': 1, 'related': 2}
        rows.sort(key=lambda r: (order.get(r[1], 3), r[0].name))
        cards = [{**company_card(db, c), 'role': role} for c, role in rows if role != 'related'][:30]
        related = sum(1 for _, role in rows if role == 'related')
        return {'companies': cards, 'related': related}


# ---------- 附件 ----------

def attachment_view(item: Attachment) -> dict:
    return {**_row(item, 'id', 'filename', 'size', 'created_at'), 'meta': item.meta, 'chars': len(item.text)}


def save_attachment(filename: str, content: bytes) -> dict:
    suffix = Path(filename).suffix.lower()
    parsed = parse_document(suffix, content)
    digest = hashlib.sha256(content).hexdigest()
    path = UPLOADS / f'{digest}{suffix}'
    path.write_bytes(content)
    with Session.begin() as db:
        item = Attachment(filename=Path(filename).name[:255], size=len(content), sha256=digest, path=str(path),
                          text=parsed.text, meta=parsed.metadata)
        db.add(item)
        db.flush()
        return {**attachment_view(item), 'text': item.text[:20000]}


def attachment_detail(attachment_id: str) -> dict:
    with Session() as db:
        item = _get(db, Attachment, attachment_id)
        return {**attachment_view(item), 'text': item.text[:20000]}


# ---------- 企业 ----------

def _counts(db, company_id: str) -> dict:
    roles = dict(db.execute(select(NoticeParty.role, func.count()).where(NoticeParty.company_id == company_id)
                            .group_by(NoticeParty.role)).all())
    return {'purchases': roles.get('buyer', 0), 'wins': roles.get('winner', 0) + roles.get('candidate', 0)}


def company_card(db, company: Company) -> dict:
    lead = db.scalar(select(Lead).where(Lead.company_id == company.id))
    rows = db.execute(select(Notice, NoticeParty.role).join(NoticeParty, NoticeParty.notice_id == Notice.id)
                      .where(NoticeParty.company_id == company.id).order_by(Notice.published_on.desc()).limit(20)).all()
    latest = rows[0][0] if rows else None
    # 联系人：本企业作为采购方的公告中已核验的采购联系人（最近一条）。
    contact = next(((n.quotes or {}).get('contact') for n, role in rows if role == 'buyer' and (n.quotes or {}).get('contact')), None)
    return {**_row(company, 'id', 'name', 'industry', 'region', 'business_status', 'registered_capital', 'legal_person',
                   'phone', 'researched_at', 'updated_at'),
            **_counts(db, company.id),
            'scope': company.scope[:120],
            'contact': {'person': contact.get('person', ''), 'phone': contact.get('phone', '')} if contact else None,
            'latest_notice': {'title': latest.title, 'kind': KIND_LABELS.get(latest.kind), 'date': latest.published_on}
            if latest else None,
            'lead': {'id': lead.id, 'status': lead.status, 'score': lead.score} if lead and not lead.archived else None}


def companies(q: str, role: str, page: int, size: int) -> dict:
    with Session() as db:
        query = select(Company)
        if q:
            query = query.where(Company.name.contains(q))
        if role in ('buyer', 'winner'):
            query = query.where(Company.id.in_(select(NoticeParty.company_id).where(NoticeParty.role == role)))
        else:
            # 默认只列有研究产出的企业：被研究过、有采购或有中标记录。
            query = query.where(or_(Company.researched_at.is_not(None),
                                    Company.id.in_(select(NoticeParty.company_id).where(
                                        NoticeParty.role.in_(['buyer', 'winner'])))))
        total = db.scalar(select(func.count()).select_from(query.subquery()))
        rows = db.scalars(query.order_by(Company.updated_at.desc()).offset((page - 1) * size).limit(size))
        return {'total': total, 'items': [company_card(db, c) for c in rows]}


def _notice_view(db, notice: Notice) -> dict:
    parties = db.execute(select(NoticeParty, Company.name).join(Company, Company.id == NoticeParty.company_id)
                         .where(NoticeParty.notice_id == notice.id)).all()
    return {**_row(notice, 'id', 'title', 'kind', 'project_code', 'region', 'published_on', 'deadline', 'budget',
                   'amount', 'items', 'url', 'source_id'),
            'kind_label': KIND_LABELS.get(notice.kind), 'contact': (notice.quotes or {}).get('contact'),
            'quotes': {k: v for k, v in (notice.quotes or {}).items() if k != 'contact'},
            'parties': [{'company_id': p.company_id, 'name': name, 'role': p.role, 'amount': p.amount, 'quote': p.quote}
                        for p, name in parties]}


def _relations(db, company_id: str) -> dict:
    me, other = aliased(NoticeParty), aliased(NoticeParty)
    rows = db.execute(select(me.role, other.role, other.company_id, Company.name, Notice.published_on, other.amount,
                             Notice.amount)
                      .join(other, (other.notice_id == me.notice_id) & (other.company_id != me.company_id))
                      .join(Company, Company.id == other.company_id).join(Notice, Notice.id == me.notice_id)
                      .where(me.company_id == company_id)).all()
    groups = {'customers': {}, 'suppliers': {}, 'competitors': {}}
    for my_role, their_role, cid, name, published, their_amount, notice_amount in rows:
        if my_role in ('winner', 'candidate') and their_role == 'buyer':
            kind, amount = 'customers', notice_amount
        elif my_role == 'buyer' and their_role == 'winner':
            kind, amount = 'suppliers', their_amount or notice_amount
        elif my_role in ('winner', 'candidate') and their_role in ('winner', 'candidate'):
            kind, amount = 'competitors', None
        else:
            continue
        item = groups[kind].setdefault(cid, {'company_id': cid, 'name': name, 'count': 0, 'amount': 0.0, 'last_date': ''})
        item['count'] += 1
        item['amount'] += amount or 0
        item['last_date'] = max(item['last_date'], published or '')
    return {key: sorted(value.values(), key=lambda x: (x['count'], x['amount']), reverse=True)
            for key, value in groups.items()}


def company_detail(company_id: str) -> dict:
    with Session() as db:
        company = _get(db, Company, company_id)
        facts = db.execute(select(Fact, Source.url, Source.title).join(Source, Source.id == Fact.source_id)
                           .where(Fact.company_id == company_id).order_by(Fact.created_at.desc())).all()
        evidence = {}
        for fact, url, title in facts:
            evidence.setdefault(fact.field, {'quote': fact.quote, 'source_id': fact.source_id, 'url': url, 'title': title})
        notices = db.execute(select(Notice, NoticeParty.role).join(NoticeParty, NoticeParty.notice_id == Notice.id)
                             .where(NoticeParty.company_id == company_id).order_by(Notice.published_on.desc())).all()
        purchases = [_notice_view(db, n) for n, role in notices if role == 'buyer']
        wins = [{**_notice_view(db, n), 'role': role} for n, role in notices if role in ('winner', 'candidate')]
        relations = _relations(db, company_id)
        source_ids = {fact.source_id for fact, *_ in facts} | {n.source_id for n, _ in notices}
        sources = db.scalars(select(Source).where(Source.id.in_(source_ids)).order_by(Source.fetched_at.desc()))
        lead = db.scalar(select(Lead).where(Lead.company_id == company_id))
        profile = [{'field': f, 'label': label, 'value': getattr(company, f), 'evidence': evidence.get(f)}
                   for f, label in PROFILE_LABELS.items() if getattr(company, f)]
        items = [n['items'] for n in purchases if n['items']]
        return {
            **_row(company, 'id', 'name', 'short_name', 'industry', 'region', 'address', 'researched_at', 'updated_at'),
            'profile': profile,
            'stats': {'purchases': len(purchases), 'wins': len(wins), 'customers': len(relations['customers']),
                      'suppliers': len(relations['suppliers']), 'competitors': len(relations['competitors']),
                      'budget_total': sum(n['budget'] or n['amount'] or 0 for n in purchases)},
            'purchases': purchases, 'wins': wins, 'relations': relations, 'purchase_items': items[:10],
            'sources': [_row(s, 'id', 'url', 'title', 'site', 'kind', 'fetched_at') for s in sources],
            'lead': {'id': lead.id, 'status': lead.status, 'archived': bool(lead.archived)} if lead else None}


def add_lead_for_company(company_id: str, conversation_id: str = '') -> dict:
    with Session.begin() as db:
        _get(db, Company, company_id)
        lead = db.scalar(select(Lead).where(Lead.company_id == company_id))
        if not lead:
            notice = db.scalar(select(NoticeParty.notice_id).where(NoticeParty.company_id == company_id,
                                                                   NoticeParty.role == 'buyer'))
            lead = Lead(company_id=company_id, notice_id=notice, conversation_id=conversation_id or None)
            db.add(lead)
        lead.archived, lead.updated_at = 0, now()
        db.flush()
        return {'id': lead.id}


# ---------- 线索 ----------

def _lead_query(q: str, status: str, owner: str, start: str, end: str):
    query = select(Lead, Company).join(Company, Company.id == Lead.company_id).where(Lead.archived == 0)
    if q:
        query = query.where(or_(Company.name.contains(q), Lead.match_reason.contains(q)))
    if owner:
        query = query.where(Lead.owner == owner)
    if start:
        query = query.where(Lead.created_at >= start)
    if end:
        query = query.where(Lead.created_at <= end + 'T23:59:59')
    return query, (query.where(Lead.status == status) if status else query)


def _lead_view(db, lead: Lead, company: Company) -> dict:
    notice = db.get(Notice, lead.notice_id) if lead.notice_id else None
    return {**_row(lead, 'id', 'status', 'owner', 'next_followup_at', 'tags', 'score', 'match_reason',
                   'created_at', 'updated_at'),
            'status_label': LEAD_STATUS.get(lead.status), 'company': {'id': company.id, 'name': company.name,
                                                                       'region': company.region},
            'notice': {'id': notice.id, 'title': notice.title, 'kind_label': KIND_LABELS.get(notice.kind),
                       'published_on': notice.published_on, 'deadline': notice.deadline, 'budget': notice.budget,
                       'amount': notice.amount} if notice else None}


def leads(q='', status='', owner='', start='', end='', page=1, size=20) -> dict:
    with Session() as db:
        base, query = _lead_query(q, status, owner, start, end)
        counts = _status_counts(db, base)
        total = db.scalar(select(func.count()).select_from(query.subquery()))
        rows = db.execute(query.order_by(Lead.score.desc(), Lead.updated_at.desc())
                          .offset((page - 1) * size).limit(size)).all()
        owners = sorted({o for o in db.scalars(select(Lead.owner).where(Lead.owner != '')).all()})
        return {'total': total, 'counts': counts, 'owners': owners,
                'items': [_lead_view(db, lead, company) for lead, company in rows]}


def _status_counts(db, base) -> dict:
    sub = base.subquery()
    rows = db.execute(select(sub.c.status, func.count()).group_by(sub.c.status)).all()
    counts = {key: 0 for key in LEAD_STATUS}
    counts.update(dict(rows))
    counts['all'] = sum(counts[key] for key in LEAD_STATUS)
    return counts


def lead_detail(lead_id: str) -> dict:
    with Session() as db:
        lead = _get(db, Lead, lead_id)
        company = db.get(Company, lead.company_id)
        notices = db.scalars(select(Notice).join(NoticeParty, NoticeParty.notice_id == Notice.id)
                             .where(NoticeParty.company_id == company.id, NoticeParty.role == 'buyer')
                             .order_by(Notice.published_on.desc()))
        notice_views = [_notice_view(db, n) for n in notices]
        contacts = [{**n['contact'], 'notice_id': n['id'], 'notice_title': n['title'], 'url': n['url']}
                    for n in notice_views if n.get('contact')]
        return {**_lead_view(db, lead, company), 'analysis': lead.analysis,
                'company': company_card(db, company) | {'address': company.address, 'phone': company.phone},
                'notices': notice_views, 'contacts': contacts,
                'followups': [_row(f, 'id', 'kind', 'content', 'created_at') for f in
                              db.scalars(select(Followup).where(Followup.lead_id == lead_id).order_by(Followup.created_at.desc()))],
                'feedback': [_row(f, 'id', 'kind', 'content', 'created_at') for f in
                             db.scalars(select(Feedback).where(Feedback.lead_id == lead_id).order_by(Feedback.created_at.desc()))]}


def update_lead(lead_id: str, values: dict) -> dict:
    with Session.begin() as db:
        lead = _get(db, Lead, lead_id)
        for key in ('status', 'owner', 'next_followup_at', 'tags', 'archived'):
            if key in values and values[key] is not None:
                if key == 'status' and values[key] not in LEAD_STATUS:
                    raise ValueError('无效的线索状态')
                setattr(lead, key, values[key])
        lead.updated_at = now()
    return lead_detail(lead_id)


def add_followup(lead_id: str, kind: str, content: str) -> dict:
    with Session.begin() as db:
        lead = _get(db, Lead, lead_id)
        db.add(Followup(lead_id=lead_id, kind=kind, content=content))
        lead.updated_at = now()
    return lead_detail(lead_id)


def add_feedback(lead_id: str, kind: str, content: str) -> dict:
    with Session.begin() as db:
        lead = _get(db, Lead, lead_id)
        db.add(Feedback(lead_id=lead_id, kind=kind, content=content))
        if kind == 'not_buyer':
            lead.status = 'invalid'
        company = db.get(Company, lead.company_id)
        if kind in ('not_buyer', 'wrong'):
            # 纠错进入长期知识，后续研究的理解阶段会读到并排除。
            db.add(Knowledge(kind='exclusion', title=company.name,
                             body=f'{company.name}：{"不是买家" if kind == "not_buyer" else "信息有误"}。{content}'))
    return lead_detail(lead_id)


async def analyze_lead(lead_id: str, focus: str) -> dict:
    detail = lead_detail(lead_id)
    settings = get_settings()
    with Session() as db:
        products = [k.body[:1500] for k in db.scalars(select(Knowledge).where(Knowledge.kind == 'product',
                                                                              Knowledge.active == 1).limit(5))]
    our = '\n'.join(filter(None, [settings['company_profile'], *products]))
    if not our:
        raise ValueError('请先在系统设置中填写公司与产品介绍')
    needs = '\n'.join(f'- {n["title"]}（{n["published_on"]}）：{n["items"] or "未披露标的"}' for n in detail['notices'][:8])
    if not needs:
        raise ValueError('该线索还没有已核验的采购公告')
    result = await llm.structured(MatchAnalysis, f'我方产品与能力：\n{our}\n\n客户：{detail["company"]["name"]}\n'
                                  f'客户采购需求（已核验公告）：\n{needs}\n\n分析重点：{focus or "无"}\n\n'
                                  '逐项判断我方产品与客户需求的匹配情况，evidence 引用采购需求原文。')
    with Session.begin() as db:
        _get(db, Lead, lead_id).analysis = {**result.model_dump(), 'analyzed_at': now()}
    return lead_detail(lead_id)


# ---------- 来源、设置、知识 ----------

def source_detail(source_id: str) -> dict:
    with Session() as db:
        source = _get(db, Source, source_id)
        return _row(source, 'id', 'url', 'title', 'site', 'kind', 'status', 'text', 'fetched_at')


def site_stats() -> dict:
    with Session() as db:
        return {row.site: _row(row, 'attempts', 'successes', 'adopted', 'last_status', 'last_at')
                for row in db.scalars(select(SiteStat))}


def knowledge(kind: str = '') -> list[dict]:
    with Session() as db:
        query = select(Knowledge).where(Knowledge.active == 1).order_by(Knowledge.updated_at.desc())
        if kind:
            query = query.where(Knowledge.kind == kind)
        return [_row(k, 'id', 'kind', 'title', 'body', 'hits', 'updated_at') for k in db.scalars(query)]


def add_knowledge(kind: str, title: str, body: str) -> dict:
    with Session.begin() as db:
        item = Knowledge(kind=kind, title=title, body=body)
        db.add(item)
        db.flush()
        return _row(item, 'id', 'kind', 'title', 'body', 'hits', 'updated_at')


def disable_knowledge(item_id: str) -> None:
    with Session.begin() as db:
        _get(db, Knowledge, item_id).active = 0


# ---------- 导出 ----------

def _workbook(title: str, header: list[str], rows: list[list]) -> bytes:
    book = Workbook()
    sheet = book.active
    sheet.title = title[:30]
    sheet.append(header)
    for row in rows:
        sheet.append(row)
    font = 'Microsoft YaHei'
    for cell in sheet[1]:
        cell.font = Font(name=font, bold=True, size=12)
        cell.fill = PatternFill('solid', fgColor='EAF1FB')
        cell.alignment = Alignment(horizontal='center', vertical='center')
    for row in sheet.iter_rows(min_row=2):
        for cell in row:
            cell.font = Font(name=font, size=12)
            cell.alignment = Alignment(vertical='center', wrap_text=True)
    for column in sheet.columns:
        sheet.column_dimensions[column[0].column_letter].width = min(48, max(10, *(len(str(c.value or '')) * 1.6 for c in column[:50])))
    sheet.freeze_panes = 'A2'
    buffer = io.BytesIO()
    book.save(buffer)
    return buffer.getvalue()


def export_leads(**filters) -> bytes:
    data = leads(**filters, page=1, size=5000)
    rows = [[item['company']['name'], item['status_label'], item['score'], item['owner'], item['next_followup_at'],
             (item['notice'] or {}).get('title', ''), (item['notice'] or {}).get('published_on', ''),
             (item['notice'] or {}).get('budget') or (item['notice'] or {}).get('amount') or '',
             item['match_reason'], item['created_at'][:10]] for item in data['items']]
    return _workbook('获客线索', ['客户', '状态', '评分', '负责人', '下次跟进', '采购公告', '发布日期', '金额（元）',
                                 '线索依据', '创建日期'], rows)


def export_company(company_id: str) -> tuple[str, bytes]:
    detail = company_detail(company_id)
    rows = [['工商', item['label'], item['value'], (item['evidence'] or {}).get('url', '')] for item in detail['profile']]
    for label, notices in (('采购', detail['purchases']), ('中标', detail['wins'])):
        rows += [[label, n['published_on'], n['title'], n['url'], n['budget'] or n['amount'] or ''] for n in notices]
    for key, label in (('customers', '客户'), ('suppliers', '供应商'), ('competitors', '竞争对手')):
        rows += [[label, r['name'], f'{r["count"]} 次', r['last_date'], r['amount'] or ''] for r in detail['relations'][key]]
    return detail['name'], _workbook('企业档案', ['类别', '项目', '内容', '来源/日期', '金额（元）'], rows)


# ---------- 概览 ----------

def overview(days: int) -> dict:
    """驾驶舱：时间范围内的线索、企业、公告、研究任务与站点表现。days=0 表示全部。"""
    since = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat() if days else ''
    with Session() as db:
        def count(model, *where):
            query = select(func.count()).select_from(model)
            for clause in where:
                query = query.where(clause)
            return db.scalar(query) or 0

        recent = (lambda column: column >= since) if since else (lambda column: column.is_not(None))

        def kpis_for(window) -> dict:
            live = Lead.archived == 0
            return {
                'new_leads': count(Lead, live, window(Lead.created_at)),
                'high_leads': count(Lead, live, window(Lead.created_at), Lead.score >= 80),
                'won_leads': count(Lead, live, window(Lead.updated_at), Lead.status == 'won'),
                'companies': count(Company, window(Company.created_at)),
                'notices': count(Notice, window(Notice.created_at)),
                'jobs': count(Job, window(Job.created_at), Job.mode.in_(['find_buyers', 'company'])),
            }

        live = Lead.archived == 0
        kpis = {**kpis_for(recent), 'awaiting_jobs': count(Job, Job.status == 'awaiting_user'),
                'failed_jobs': count(Job, recent(Job.created_at), Job.status == 'failed')}
        previous = {}
        if days:
            before = (datetime.now(timezone.utc) - timedelta(days=days * 2)).isoformat()
            previous = kpis_for(lambda column: (column >= before) & (column < since))
        trend: dict[str, dict] = {}
        for column, key, model, extra in ((Lead.created_at, 'leads', Lead, live), (Notice.created_at, 'notices', Notice, None)):
            query = select(func.substr(column, 1, 10), func.count()).select_from(model).where(recent(column))
            if extra is not None:
                query = query.where(extra)
            for day, value in db.execute(query.group_by(func.substr(column, 1, 10))):
                trend.setdefault(day, {'date': day, 'leads': 0, 'notices': 0})[key] = value
        status_rows = db.execute(select(Lead.status, func.count()).where(live, recent(Lead.created_at)).group_by(Lead.status)).all()
        kind_rows = db.execute(select(Notice.kind, func.count()).where(recent(Notice.created_at)).group_by(Notice.kind)).all()
        jobs = db.execute(select(Job, Conversation.title).join(Conversation, Conversation.id == Job.conversation_id)
                          .where(Job.mode.in_(['find_buyers', 'company'])).order_by(Job.created_at.desc()).limit(8)).all()
        sites = [{'site': row.site, 'attempts': row.attempts, 'successes': row.successes, 'adopted': row.adopted,
                  'rate': round(row.successes / row.attempts, 3) if row.attempts else None, 'last_status': row.last_status}
                 for row in db.scalars(select(SiteStat))]
    return {
        'days': days, 'kpis': kpis, 'previous': previous, 'trend': sorted(trend.values(), key=lambda x: x['date']),
        'lead_status': sorted(({'status': s, 'label': LEAD_STATUS.get(s, s), 'count': c} for s, c in status_rows),
                              key=lambda x: -x['count']),
        'notice_kinds': sorted(({'kind': k, 'label': KIND_LABELS.get(k, k), 'count': c} for k, c in kind_rows),
                               key=lambda x: -x['count']),
        'sites': sorted(sites, key=lambda x: -(x['attempts'] or 0)),
        'recent_jobs': [{'id': job.id, 'conversation_id': job.conversation_id, 'title': title, 'mode': job.mode,
                         'status': job.status, 'created_at': job.created_at} for job, title in jobs],
    }


# ---------- 数据源配置 ----------

def _site_values(values: dict) -> dict:
    """校验数据源配置：地址模板必须是 http(s) 且含 {q}；站内搜索填域名；公告链接规则必须是合法正则。"""
    name = (values.get('name') or '').strip()
    mode = values.get('mode') or 'template'
    template = (values.get('template') or '').strip()
    domain = re.sub(r'^https?://', '', (values.get('domain') or '').strip()).strip('/')
    detail = (values.get('detail') or '').strip()
    if not name:
        raise ValueError('请填写站点名称')
    if values.get('kind') not in ('procurement', 'business'):
        raise ValueError('站点类型无效')
    if mode == 'template' and (not re.match(r'^https?://', template) or '{q}' not in template):
        raise ValueError('检索地址需以 http 开头并包含 {q}')
    if mode == 'site_search' and not re.fullmatch(r'[\w.-]+\.[a-z]{2,}', domain, re.I):
        raise ValueError('请填写站点域名，例如 www.example.com')
    if mode not in ('template', 'site_search'):
        raise ValueError('接入方式无效')
    try:
        re.compile(detail or '.')
    except re.error as exc:
        raise ValueError('公告链接规则不是合法的正则表达式') from exc
    return {'name': name[:100], 'kind': values['kind'], 'mode': mode, 'template': template if mode == 'template' else '',
            'domain': domain if mode == 'site_search' else '', 'detail': detail[:300], 'login': int(bool(values.get('login'))),
            'by_company': int(bool(values.get('by_company'))), 'note': (values.get('note') or '').strip()[:200]}


def create_site(values: dict) -> dict:
    data = _site_values(values)
    with Session.begin() as db:
        site_id = 'c' + hashlib.sha1((data['name'] + now()).encode()).hexdigest()[:10]
        db.add(CustomSite(id=site_id, **data))
    return {'id': site_id}


def update_site(site_id: str, values: dict) -> dict:
    data = _site_values(values)
    with Session.begin() as db:
        row = _get(db, CustomSite, site_id)
        for key, value in data.items():
            setattr(row, key, value)
        row.updated_at = now()
    return {'id': site_id}


def delete_site(site_id: str) -> None:
    with Session.begin() as db:
        db.delete(_get(db, CustomSite, site_id))


async def test_site(values: dict, keyword: str) -> dict:
    """用 LuzCrawl 实际检索一次：列表页取得多少公告链接，并读取第一篇公告正文。"""
    data = _site_values(values)
    site = from_custom(CustomSite(id='test', **data))
    profile = get_settings().get('crawl_profile') or await crawl.default_profile()
    folder = await crawl.begin(f'数据源测试 {data["name"]}', CRAWL_OUT)
    started = time.monotonic()
    if site.template:
        page = await crawl.capture(site.search_url(keyword, 90), folder, profile, 3)
    else:
        page = await crawl.search(site.platform, keyword, folder, profile)
    links = [link for link in page.links if site.is_detail(link['url'])]
    result = {'status': page.status, 'error': page.error or ('需要在 Edge 中登录或验证' if page.needs_user else ''),
              'url': page.url, 'links': len(page.links), 'matched': len(links),
              'samples': [{'title': (l.get('text') or '')[:80], 'url': l['url']} for l in links[:5]], 'detail': None}
    if links:
        detail = await crawl.capture(site.detail_url(links[0]['url']), folder, profile, 3)
        result['detail'] = {'status': detail.status, 'title': detail.title, 'chars': len(detail.text),
                            'excerpt': re.sub(r'\s+', ' ', detail.text)[:240]}
    result['elapsed_ms'] = round((time.monotonic() - started) * 1000)
    return result


# ---------- 研究报告 ----------

def job_report(job_id: str) -> dict:
    """一次研究的结果、数据质量、过程与未完成项，全部来自已保存的数据与任务记录。"""
    with Session() as db:
        job = _get(db, Job, job_id)
        plan, metrics = job.plan or {}, job.metrics or {}
        names = {s.id: s.name for s in all_sites().values()}
        sources = select(Source.id).where(Source.job_id == job_id)
        notices = list(db.scalars(select(Notice).where(Notice.source_id.in_(sources))))
        rows = db.execute(select(Company, JobCompany.role).join(JobCompany, JobCompany.company_id == Company.id)
                          .where(JobCompany.job_id == job_id)).all()
        buyers = [c for c, role in rows if role in ('buyer', 'target')]
        leads = {lead.company_id: lead for lead in db.scalars(select(Lead).where(Lead.company_id.in_([c.id for c in buyers])))}

        site_rows: dict[str, dict] = {}
        for item in (plan.get('lists') or {}).values():
            row = site_rows.setdefault(item['site'], {'site': item['site'], 'name': names.get(item['site'], item['site']),
                                                      'searches': 0, 'ok': 0, 'links': 0})
            row['searches'] += 1
            row['ok'] += item['status'] in ('captured', 'partial')
            row['links'] += len(item.get('links') or [])
        read = plan.get('read') or {}
        total = len(notices)
        complete = {key: sum(1 for n in notices if test(n)) for key, test in {
            'budget': lambda n: n.budget is not None or n.amount is not None,
            'deadline': lambda n: bool(n.deadline),
            'items': lambda n: bool(n.items),
            'contact': lambda n: bool((n.quotes or {}).get('contact')),
        }.items()}
        with_facts = set(db.scalars(select(Fact.company_id).where(Fact.company_id.in_([c.id for c in buyers]))))
        profiled = len(with_facts)
        verify = metrics.get('verify') or {}

        top = []
        for company in [c for c, role in rows if role == 'buyer']:
            lead = leads.get(company.id)
            notice = db.get(Notice, lead.notice_id) if lead and lead.notice_id else None
            contact = (notice.quotes or {}).get('contact') if notice else None
            top.append({'company_id': company.id, 'name': company.name, 'lead_id': lead.id if lead else None,
                        'score': lead.score if lead else None, 'status': lead.status if lead else None,
                        'notice': notice.title if notice else '', 'notice_url': notice.url if notice else '',
                        'kind': KIND_LABELS.get(notice.kind) if notice else '', 'items': notice.items if notice else '',
                        'budget': (notice.budget or notice.amount) if notice else None,
                        'deadline': notice.deadline if notice else '', 'published_on': notice.published_on if notice else '',
                        'contact': bool(contact), 'contact_person': (contact or {}).get('person', ''),
                        'contact_phone': (contact or {}).get('phone', ''), 'region': company.region,
                        'profiled': company.id in with_facts})
        records = []
        if job.mode == 'company':
            target = next((c for c, role in rows if role == 'target'), None)
            if target:
                for notice, role in db.execute(select(Notice, NoticeParty.role).join(NoticeParty, NoticeParty.notice_id == Notice.id)
                                               .where(NoticeParty.company_id == target.id).order_by(Notice.published_on.desc())):
                    others = db.execute(select(Company.name, NoticeParty.role).join(NoticeParty, NoticeParty.company_id == Company.id)
                                        .where(NoticeParty.notice_id == notice.id, NoticeParty.company_id != target.id)).all()
                    records.append({'title': notice.title, 'url': notice.url, 'date': notice.published_on,
                                    'role': {'buyer': '采购', 'winner': '中标', 'candidate': '候选'}.get(role, role),
                                    'counterpart': '、'.join(n for n, r in others if r in ('buyer', 'winner'))[:60],
                                    'amount': notice.amount or notice.budget})
        top.sort(key=lambda x: (x['score'] or 0, x['budget'] or 0), reverse=True)

        return {
            'status': job.status, 'mode': job.mode, 'elapsed_ms': metrics.get('elapsed_ms', 0),
            'model_calls': metrics.get('model_calls', 0), 'first_result_ms': metrics.get('first_result_ms'),
            'counts': {'searches': sum(r['searches'] for r in site_rows.values()), 'rounds': plan.get('round', 1), 'candidates': len(plan.get('candidates') or {}),
                       'read': len(read), 'read_failed': sum(1 for v in read.values() if v == 'failed'),
                       'notices': total, 'companies': len(rows), 'buyers': len(buyers),
                       'leads': sum(1 for c in buyers if c.id in leads), 'contacts': complete['contact'], 'profiled': profiled},
            'quality': {'checked': verify.get('checked', 0), 'kept': verify.get('kept', 0),
                        'rate': round(verify['kept'] / verify['checked'], 3) if verify.get('checked') else None,
                        'notice_total': total, 'complete': complete, 'buyers': len(buyers), 'profiled': profiled},
            'sites': sorted(site_rows.values(), key=lambda r: -r['links']),
            'problems': list(dict.fromkeys(plan.get('problems') or [])),
            'top': top[:100], 'records': records[:100],
        }


def discovered_sites(limit: int = 30) -> list[dict]:
    """全网检索中发现、尚未登记的网站，被采用多的在前；附上可直接保存的站点配置。"""
    with Session() as db:
        rows = list(db.scalars(select(DiscoveredSite).where(DiscoveredSite.dismissed == 0)
                               .order_by(DiscoveredSite.adopted.desc(), DiscoveredSite.hits.desc()).limit(limit * 2)))
    result = []
    for row in rows:
        if known_domain(row.sample_url) or len(result) >= limit:
            continue
        result.append({**_row(row, 'domain', 'title', 'sample_url', 'hits', 'adopted', 'last_seen'),
                       'config': {'name': row.title[:30] or row.domain, 'kind': 'procurement', 'mode': 'template',
                                  'template': f'https://cn.bing.com/search?q=site%3A{row.domain}+{{q}}+%E6%8B%9B%E6%A0%87&first={{offset}}',
                                  'detail': re.escape(row.domain), 'note': f'经必应检索 {row.domain} 站内公告'}})
    return result


def dismiss_discovered(domain: str) -> None:
    with Session.begin() as db:
        _get(db, DiscoveredSite, domain).dismissed = 1
