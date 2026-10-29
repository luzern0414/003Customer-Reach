"""数据质量：截止时间规范化、线索评分、存量回填与重复单位合并。都可重复执行，重复执行结果不变。"""
import logging
import re
import shutil
from datetime import date, datetime

from sqlalchemy import select

from ..config import DATABASE_URL
from ..db import Company, Fact, Feedback, Followup, JobCompany, Lead, Notice, NoticeParty, Session, now
from .verify import company_name, grounded

log = logging.getLogger(__name__)

_DEADLINE = re.compile(r'(\d{4})\s*[年\-/.]\s*(\d{1,2})\s*[月\-/.]\s*(\d{1,2})\s*日?'
                       r'(?:\s*(上午|下午)?\s*(\d{1,2})\s*[:：时点]\s*(\d{1,2})?)?')


def parse_deadline(text: str) -> str:
    """公告原文里的截止时间（北京时间）→“2026-11-13 09:30”，只有日期时为“2026-11-13”，无法解析为空。"""
    m = _DEADLINE.search(text or '')
    if not m:
        return ''
    try:
        day = date(int(m[1]), int(m[2]), int(m[3]))
    except ValueError:
        return ''
    if not m[5]:
        return day.isoformat()
    hour, minute = int(m[5]), int(m[6] or 0)
    if m[4] == '下午' and hour < 12:
        hour += 12
    if hour > 23 or minute > 59:
        return day.isoformat()
    return f'{day.isoformat()} {hour:02d}:{minute:02d}'


def days_left(deadline_at: str, today: date | None = None) -> int | None:
    """距投标截止的天数：当天截止为 0，已截止为负数；没有截止时间为空。"""
    if not deadline_at:
        return None
    return (date.fromisoformat(deadline_at[:10]) - (today or date.today())).days


# 评分：公告类型基础分 + 截止剩余天数 + 预算 + 联系人 − 公告时效，结果限制在 10–100
KIND_BASE = {'tender': 70, 'intent': 65, 'change': 65, 'candidate': 55, 'award': 50, 'contract': 45}


def score_lead(kind: str, published_on: str, deadline_at: str = '', budget: float | None = None,
               has_contact: bool = False, today: date | None = None) -> int:
    today = today or date.today()
    score = KIND_BASE.get(kind, 40)
    left = days_left(deadline_at, today)
    if left is not None:
        score += 15 if left > 7 else 10 if left >= 3 else 5 if left >= 0 else -20
    if budget:
        score += 10 if budget >= 1_000_000 else 5 if budget >= 100_000 else 0
    if has_contact:
        score += 5
    try:
        score -= (today - date.fromisoformat(published_on)).days // 30 * 5
    except ValueError:
        score -= 60
    return max(10, min(100, score))


def score_notice(notice: Notice | None, today: date | None = None) -> int:
    if not notice:
        return 10
    return score_lead(notice.kind, notice.published_on, notice.deadline_at, notice.budget or notice.amount,
                      bool((notice.quotes or {}).get('contact')), today)


def fill_buyer(db, company: Company, notice: Notice) -> int:
    """采购方：地区取公告地区；电话、地址取核验过的采购人联系方式，并写带原文出处的事实。返回补充的字段数。"""
    filled = 0
    if not company.region and notice.region:
        company.region = notice.region[:100]
        filled += 1
    contact = (notice.quotes or {}).get('contact') or {}
    quote = contact.get('quote', '')
    for field in ('phone', 'address'):
        value = (contact.get(field) or '').strip()
        if value and not getattr(company, field) and grounded(value, quote):
            setattr(company, field, value[:300])
            db.add(Fact(company_id=company.id, field=field, value=value, quote=quote[:1000], source_id=notice.source_id))
            filled += 1
    if filled:
        company.updated_at = now()
    return filled


def rescore_leads(today: date | None = None) -> int:
    """按公告重算全部线索分数（剩余天数随日期变化），返回分数变化的条数。"""
    changed = 0
    with Session.begin() as db:
        rows = db.execute(select(Lead, Notice).join(Notice, Notice.id == Lead.notice_id)).all()
        for lead, notice in rows:
            score = score_notice(notice, today)
            if score != lead.score:
                lead.score = score
                changed += 1
    return changed


def _backup_database() -> None:
    """合并前复制一份数据库文件，保留最近 3 份。"""
    if not DATABASE_URL.startswith('sqlite:///'):
        return
    path = DATABASE_URL.removeprefix('sqlite:///')
    from pathlib import Path
    source = Path(path)
    if not source.exists():
        return
    folder = source.parent / 'backup'
    folder.mkdir(exist_ok=True)
    shutil.copy2(source, folder / f'{source.stem}-{datetime.now():%Y%m%d-%H%M%S}{source.suffix}')
    for old in sorted(folder.glob(f'{source.stem}-*{source.suffix}'))[:-3]:
        old.unlink()


def _merge(db, src: Company, dst: Company) -> dict:
    """把 src 的公告参与方、事实、任务关联与线索迁到 dst，再删除 src。"""
    moved = {'parties': 0, 'facts': 0, 'jobs': 0, 'lead': ''}
    for party in db.scalars(select(NoticeParty).where(NoticeParty.company_id == src.id)):
        if db.scalar(select(NoticeParty).where(NoticeParty.notice_id == party.notice_id, NoticeParty.company_id == dst.id,
                                               NoticeParty.role == party.role)):
            db.delete(party)
        else:
            party.company_id = dst.id
            moved['parties'] += 1
    for fact in db.scalars(select(Fact).where(Fact.company_id == src.id)):
        fact.company_id = dst.id
        moved['facts'] += 1
    for link in db.scalars(select(JobCompany).where(JobCompany.company_id == src.id)):
        if db.get(JobCompany, (link.job_id, dst.id)):
            db.delete(link)
        else:
            db.add(JobCompany(job_id=link.job_id, company_id=dst.id, role=link.role))
            db.delete(link)
            moved['jobs'] += 1
    src_lead = db.scalar(select(Lead).where(Lead.company_id == src.id))
    dst_lead = db.scalar(select(Lead).where(Lead.company_id == dst.id))
    if src_lead and dst_lead:
        # 同一家已有线索：保留 dst 的线索，公告依据取分数高的一条；销售已处理过的状态、负责人不被覆盖
        if (src_lead.score or 0) > (dst_lead.score or 0):
            dst_lead.notice_id, dst_lead.score, dst_lead.match_reason = src_lead.notice_id, src_lead.score, src_lead.match_reason
        if dst_lead.status == 'new' and src_lead.status != 'new':
            dst_lead.status = src_lead.status
        dst_lead.owner = dst_lead.owner or src_lead.owner
        dst_lead.next_followup_at = dst_lead.next_followup_at or src_lead.next_followup_at
        for row in [*db.scalars(select(Followup).where(Followup.lead_id == src_lead.id)),
                    *db.scalars(select(Feedback).where(Feedback.lead_id == src_lead.id))]:
            row.lead_id = dst_lead.id
        db.flush()
        db.delete(src_lead)
        moved['lead'] = 'merged'
    elif src_lead:
        src_lead.company_id = dst.id
        moved['lead'] = 'moved'
    for field in ('region', 'phone', 'address', 'industry', 'legal_person', 'registered_capital', 'credit_code', 'scope'):
        if not getattr(dst, field) and getattr(src, field):
            setattr(dst, field, getattr(src, field))
    db.flush()
    db.delete(src)
    return moved


def backfill() -> dict:
    """存量数据回填：截止时间、采购方地区与联系方式、重复单位合并，最后重算评分。"""
    stats = {'deadlines': 0, 'buyers': 0, 'merged': 0, 'renamed': 0}
    with Session.begin() as db:
        for notice in db.scalars(select(Notice).where(Notice.deadline != '', Notice.deadline_at == '')):
            value = parse_deadline(notice.deadline)
            if value:
                notice.deadline_at = value
                stats['deadlines'] += 1
    with Session.begin() as db:
        rows = db.execute(select(Company, Notice).join(NoticeParty, NoticeParty.company_id == Company.id)
                          .join(Notice, Notice.id == NoticeParty.notice_id).where(NoticeParty.role == 'buyer')
                          .order_by(Notice.published_on.desc())).all()
        for company, notice in rows:
            stats['buyers'] += 1 if fill_buyer(db, company, notice) else 0
    duplicates = []
    with Session() as db:
        for company in db.scalars(select(Company)):
            if company_name(company.name) != company.name:
                duplicates.append(company.id)
    if duplicates:
        _backup_database()
        with Session.begin() as db:
            for company_id in duplicates:
                src = db.get(Company, company_id)
                target = company_name(src.name)
                dst = db.scalar(select(Company).where(Company.name == target))
                if dst:
                    moved = _merge(db, src, dst)
                    stats['merged'] += 1
                    log.info('合并重复单位：%s → %s，参与方 %s、事实 %s、任务 %s、线索 %s', src.name, dst.name,
                             moved['parties'], moved['facts'], moved['jobs'], moved['lead'] or '无')
                else:
                    src.name = target
                    stats['renamed'] += 1
    stats['rescored'] = rescore_leads()
    if any(stats.values()):
        log.info('数据回填：%s', stats)
    return stats
