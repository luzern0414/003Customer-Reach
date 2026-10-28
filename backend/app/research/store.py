"""把核验通过的抽取结果写入数据库。未通过原文核验的字段一律不保存。"""
import re
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session as OrmSession

from ..crawl import Page
from ..db import Company, DiscoveredSite, Fact, JobCompany, Lead, Notice, NoticeParty, Session, SiteStat, Source, now
from .schemas import CompanyExtract, NoticeExtract, Party
from .verify import company_name, grounded, grounded_value, plausible_company

PROFILE_FIELDS = ('credit_code', 'legal_person', 'registered_capital', 'founded_on', 'business_status', 'industry',
                  'address', 'website', 'phone', 'email', 'scope')


def save_source(page: Page, site: str, kind: str, job_id: str) -> str:
    with Session.begin() as db:
        row = db.scalar(select(Source).where(Source.url == page.url))
        if not row:
            row = Source(url=page.url)
            db.add(row)
        row.title, row.site, row.kind, row.status = page.title[:500], site, kind, page.status
        row.text, row.folder, row.job_id, row.fetched_at = page.text, page.folder, job_id, now()
        db.flush()
        return row.id


def upsert_company(db: OrmSession, name: str) -> Company:
    name = company_name(name)
    row = db.scalar(select(Company).where(Company.name == name))
    if not row:
        row = Company(name=name)
        db.add(row)
        db.flush()
    return row


def _date(value: str) -> str:
    match = re.search(r'(20\d{2})[-年./](\d{1,2})[-月./](\d{1,2})', value or '')
    return f'{match[1]}-{int(match[2]):02d}-{int(match[3]):02d}' if match else ''


def _party(db: OrmSession, notice: Notice, party: Party | None, role: str, text: str) -> Company | None:
    if not party or not plausible_company(party.name) or not grounded_value(company_name(party.name), party.quote, text):
        return None
    company = upsert_company(db, party.name)
    exists = db.scalar(select(NoticeParty).where(NoticeParty.notice_id == notice.id,
                                                 NoticeParty.company_id == company.id, NoticeParty.role == role))
    if not exists:
        db.add(NoticeParty(notice_id=notice.id, company_id=company.id, role=role, amount=party.amount,
                           quote=party.quote[:500]))
    return company


def save_notice(extract: NoticeExtract, source_id: str, page: Page, fallback: dict) -> dict:
    """保存一篇公告及参与方，返回 {notice_id, buyer_id, winner_ids, company_ids}。"""
    text = page.text
    code = extract.project_code if grounded(extract.project_code, text) else ''
    with Session.begin() as db:
        notice = db.scalar(select(Notice).where(Notice.url == page.url))
        if not notice and code:
            # 同一公告常被政府采购网与公共资源交易平台同时发布：项目编号与公告类型相同即视为同一篇。
            notice = db.scalar(select(Notice).where(Notice.project_code == code[:100], Notice.kind == extract.kind))
        if not notice:
            notice = Notice(url=page.url)
            db.add(notice)
        notice.source_id = source_id
        notice.title = (extract.title or fallback.get('title') or page.title)[:500]
        notice.kind = extract.kind if extract.kind != 'other' else fallback.get('kind', 'other')
        notice.project_code = code[:100]
        notice.published_on = _date(extract.published_on) or _date(fallback.get('published_on', ''))
        notice.deadline = extract.deadline[:32] if grounded(extract.deadline, text) else ''
        notice.region = extract.region or fallback.get('region', '')
        notice.budget = extract.budget if extract.budget and grounded(extract.budget_quote, text) else None
        notice.amount = extract.amount if extract.amount and grounded(extract.amount_quote, text) else None
        notice.items = extract.items[:500] if grounded(extract.items_quote, text) else ''
        quotes = {key: getattr(extract, key + '_quote') for key in ('budget', 'amount', 'items')
                  if getattr(extract, key + '_quote') and grounded(getattr(extract, key + '_quote'), text)}
        contact = extract.buyer_contact
        if contact and grounded(contact.quote, text):
            quotes['contact'] = {'person': contact.person, 'phone': contact.phone, 'address': contact.address,
                                 'quote': contact.quote}
        notice.quotes = quotes
        db.flush()
        buyer = _party(db, notice, extract.buyer, 'buyer', text)
        agent = _party(db, notice, extract.agent, 'agent', text)
        winners = [c for c in (_party(db, notice, p, 'winner', text) for p in extract.winners) if c]
        candidates = [c for c in (_party(db, notice, p, 'candidate', text) for p in extract.candidates) if c]
        # 核验统计：模型给出的字段数（checked）与通过原文核验后保存的字段数（kept）。
        given = [extract.project_code, extract.deadline, extract.budget, extract.amount, extract.items,
                 extract.buyer_contact and extract.buyer_contact.quote, extract.buyer, extract.agent]
        kept = [notice.project_code, notice.deadline, notice.budget, notice.amount, notice.items,
                quotes.get('contact'), buyer, agent]
        checked = sum(1 for g in given if g) + len(extract.winners) + len(extract.candidates)
        passed = sum(1 for g, k in zip(given, kept) if g and k) + len(winners) + len(candidates)
        return {'notice_id': notice.id, 'buyer_id': buyer.id if buyer else None, 'checked': checked, 'kept': passed,
                'winner_ids': [c.id for c in winners], 'company_ids': [c.id for c in [buyer, *winners, *candidates] if c]}


def provided_fields(extract: CompanyExtract) -> int:
    return sum(1 for field in PROFILE_FIELDS if getattr(extract, field))


def save_profile(company_id: str, extract: CompanyExtract, source_id: str, text: str) -> int:
    """写入核验通过的工商字段与 Fact，返回保存的字段数。"""
    saved = 0
    with Session.begin() as db:
        company = db.get(Company, company_id)
        for field in PROFILE_FIELDS:
            item = getattr(extract, field)
            if not item or not grounded_value(item.value, item.quote, text):
                continue
            setattr(company, field, item.value[:2000] if field == 'scope' else item.value[:300])
            db.add(Fact(company_id=company_id, field=field, value=item.value, quote=item.quote[:1000],
                        source_id=source_id))
            saved += 1
        company.updated_at = now()
    return saved


def link_job(job_id: str, company_id: str, role: str) -> None:
    with Session.begin() as db:
        row = db.get(JobCompany, (job_id, company_id))
        if not row:
            db.add(JobCompany(job_id=job_id, company_id=company_id, role=role))
        elif role == 'target' or (role == 'buyer' and row.role == 'related'):
            row.role = role


def score_lead(kind: str, published_on: str, deadline: str) -> int:
    """正在招标/意向最高；近 90 天的中标、成交说明有持续采购；越新越高。"""
    base = {'intent': 90, 'tender': 85, 'change': 80, 'candidate': 65, 'award': 60, 'contract': 55}.get(kind, 40)
    try:
        age = (date.today() - date.fromisoformat(published_on)).days
    except ValueError:
        age = 365
    return max(10, min(100, base - age // 30 * 5))


def upsert_lead(company_id: str, notice_id: str, conversation_id: str, score: int, reason: str) -> str:
    with Session.begin() as db:
        lead = db.scalar(select(Lead).where(Lead.company_id == company_id))
        if not lead:
            lead = Lead(company_id=company_id, conversation_id=conversation_id, score=0)
            db.add(lead)
        if score >= (lead.score or 0):
            lead.notice_id, lead.score, lead.match_reason = notice_id, score, reason[:500]
        lead.archived, lead.updated_at = 0, now()
        db.flush()
        return lead.id


def record_site(site: str, status: str, adopted: int = 0) -> None:
    with Session.begin() as db:
        row = db.get(SiteStat, site) or SiteStat(site=site)
        db.add(row)
        row.attempts = (row.attempts or 0) + 1
        row.successes = (row.successes or 0) + (status in ('captured', 'partial'))
        row.adopted = (row.adopted or 0) + adopted
        row.last_status, row.last_at = status, now()


def discover(domain: str, title: str, url: str, adopted: int = 0) -> None:
    """记录全网检索发现的网站；adopted 表示从该网站读出了核验通过的公告。"""
    if not domain:
        return
    with Session.begin() as db:
        row = db.get(DiscoveredSite, domain) or DiscoveredSite(domain=domain, title=title[:200], sample_url=url[:1000])
        db.add(row)
        row.hits = (row.hits or 0) + (0 if adopted else 1)
        row.adopted = (row.adopted or 0) + adopted
        row.last_seen = now()
