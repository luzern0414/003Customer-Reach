"""SQLite 数据模型。上下游关系不单独存表，由公告参与方（notice_parties）推导。"""
import uuid
from datetime import datetime, timezone

from sqlalchemy import (JSON, Float, ForeignKey, Integer, String, Text, UniqueConstraint, create_engine, event,
                        inspect, select, text)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker

from .config import DATABASE_URL, DEFAULT_SETTINGS

engine = create_engine(DATABASE_URL, connect_args={'check_same_thread': False, 'timeout': 30})


@event.listens_for(engine, 'connect')
def _pragmas(connection, _):
    cursor = connection.cursor()
    cursor.execute('PRAGMA journal_mode=WAL')
    cursor.execute('PRAGMA foreign_keys=ON')
    cursor.close()


Session = sessionmaker(engine, expire_on_commit=False)


def new_id() -> str:
    return uuid.uuid4().hex


def now() -> str:
    """UTC ISO 时间字符串，精确到秒。"""
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


class Base(DeclarativeBase):
    type_annotation_map = {dict: JSON, list: JSON}


class Setting(Base):
    __tablename__ = 'settings'
    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[dict] = mapped_column(JSON)


class User(Base):
    """登录账号。quota 为可发起研究的次数，NULL 表示不限（管理员）。"""
    __tablename__ = 'users'
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    username: Mapped[str] = mapped_column(String(32), unique=True)
    password_hash: Mapped[str] = mapped_column(String(200))
    is_admin: Mapped[int] = mapped_column(Integer, default=0)
    quota: Mapped[int | None] = mapped_column(Integer, nullable=True)
    used: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[str] = mapped_column(String(32), default=now)
    last_login_at: Mapped[str] = mapped_column(String(32), default='')


class UserSession(Base):
    """登录会话。只保存令牌的 SHA-256，令牌本身只在 Cookie 中。"""
    __tablename__ = 'user_sessions'
    token_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey('users.id', ondelete='CASCADE'), index=True)
    created_at: Mapped[str] = mapped_column(String(32), default=now)
    expires_at: Mapped[str] = mapped_column(String(32))


class Conversation(Base):
    __tablename__ = 'conversations'
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    user_id: Mapped[str | None] = mapped_column(String(32), index=True)
    title: Mapped[str] = mapped_column(String(200), default='新研究')
    created_at: Mapped[str] = mapped_column(String(32), default=now)
    updated_at: Mapped[str] = mapped_column(String(32), default=now)


class Message(Base):
    __tablename__ = 'messages'
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    conversation_id: Mapped[str] = mapped_column(ForeignKey('conversations.id', ondelete='CASCADE'), index=True)
    role: Mapped[str] = mapped_column(String(16))
    content: Mapped[str] = mapped_column(Text, default='')
    attachment_ids: Mapped[list] = mapped_column(JSON, default=list)
    job_id: Mapped[str | None] = mapped_column(String(32), index=True)
    request_id: Mapped[str | None] = mapped_column(String(96), nullable=True, index=True)
    created_at: Mapped[str] = mapped_column(String(32), default=now)


class Attachment(Base):
    __tablename__ = 'attachments'
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    filename: Mapped[str] = mapped_column(String(255))
    size: Mapped[int] = mapped_column(Integer)
    sha256: Mapped[str] = mapped_column(String(64))
    path: Mapped[str] = mapped_column(String(500))
    text: Mapped[str] = mapped_column(Text, default='')
    meta: Mapped[dict] = mapped_column(JSON, default=dict)
    user_id: Mapped[str | None] = mapped_column(String(32), index=True)
    created_at: Mapped[str] = mapped_column(String(32), default=now)


class Job(Base):
    """一次研究任务。status: queued/running/awaiting_user/paused/completed/partial/failed。"""
    __tablename__ = 'jobs'
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    conversation_id: Mapped[str] = mapped_column(ForeignKey('conversations.id', ondelete='CASCADE'), index=True)
    message_id: Mapped[str] = mapped_column(String(32))
    mode: Mapped[str] = mapped_column(String(24), default='')
    status: Mapped[str] = mapped_column(String(24), default='queued', index=True)
    stage: Mapped[str] = mapped_column(String(32), default='queued')
    plan: Mapped[dict] = mapped_column(JSON, default=dict)
    metrics: Mapped[dict] = mapped_column(JSON, default=dict)
    handover: Mapped[dict] = mapped_column(JSON, default=dict)
    crawl_folder: Mapped[str] = mapped_column(String(500), default='')
    reply_message_id: Mapped[str | None] = mapped_column(String(32))
    request_id: Mapped[str | None] = mapped_column(String(96), nullable=True, index=True)
    error: Mapped[str] = mapped_column(Text, default='')
    created_at: Mapped[str] = mapped_column(String(32), default=now)
    started_at: Mapped[str | None] = mapped_column(String(32))
    finished_at: Mapped[str | None] = mapped_column(String(32))


class JobEvent(Base):
    __tablename__ = 'job_events'
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    job_id: Mapped[str] = mapped_column(ForeignKey('jobs.id', ondelete='CASCADE'), index=True)
    type: Mapped[str] = mapped_column(String(48))
    data: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[str] = mapped_column(String(32), default=now)


class Source(Base):
    """LuzCrawl 实际读取到的页面；text 为页面可见正文，folder 指向证据目录。"""
    __tablename__ = 'sources'
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    url: Mapped[str] = mapped_column(String(1000), unique=True)
    title: Mapped[str] = mapped_column(String(500), default='')
    site: Mapped[str] = mapped_column(String(64), default='', index=True)
    kind: Mapped[str] = mapped_column(String(24), default='page')
    status: Mapped[str] = mapped_column(String(24), default='captured')
    text: Mapped[str] = mapped_column(Text, default='')
    folder: Mapped[str] = mapped_column(String(500), default='')
    job_id: Mapped[str | None] = mapped_column(String(32))
    fetched_at: Mapped[str] = mapped_column(String(32), default=now)


class Company(Base):
    __tablename__ = 'companies'
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    name: Mapped[str] = mapped_column(String(200), unique=True)
    short_name: Mapped[str] = mapped_column(String(100), default='')
    credit_code: Mapped[str] = mapped_column(String(32), default='')
    legal_person: Mapped[str] = mapped_column(String(64), default='')
    registered_capital: Mapped[str] = mapped_column(String(64), default='')
    founded_on: Mapped[str] = mapped_column(String(32), default='')
    business_status: Mapped[str] = mapped_column(String(32), default='')
    industry: Mapped[str] = mapped_column(String(100), default='')
    region: Mapped[str] = mapped_column(String(100), default='')
    address: Mapped[str] = mapped_column(String(300), default='')
    website: Mapped[str] = mapped_column(String(300), default='')
    phone: Mapped[str] = mapped_column(String(100), default='')
    email: Mapped[str] = mapped_column(String(100), default='')
    scope: Mapped[str] = mapped_column(Text, default='')
    summary: Mapped[str] = mapped_column(Text, default='')
    researched_at: Mapped[str | None] = mapped_column(String(32))
    created_at: Mapped[str] = mapped_column(String(32), default=now)
    updated_at: Mapped[str] = mapped_column(String(32), default=now)


class Fact(Base):
    """企业字段的原文依据：每个非空企业字段至少对应一条 quote 已在来源正文中核验的事实。"""
    __tablename__ = 'facts'
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    company_id: Mapped[str] = mapped_column(ForeignKey('companies.id', ondelete='CASCADE'), index=True)
    field: Mapped[str] = mapped_column(String(48))
    value: Mapped[str] = mapped_column(Text)
    quote: Mapped[str] = mapped_column(Text)
    source_id: Mapped[str] = mapped_column(ForeignKey('sources.id'))
    created_at: Mapped[str] = mapped_column(String(32), default=now)


class Notice(Base):
    """招投标/采购公告。kind: intent/tender/change/candidate/award/contract/other。金额单位为元。"""
    __tablename__ = 'notices'
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    source_id: Mapped[str] = mapped_column(ForeignKey('sources.id'))
    url: Mapped[str] = mapped_column(String(1000), unique=True)
    title: Mapped[str] = mapped_column(String(500))
    kind: Mapped[str] = mapped_column(String(16), default='other', index=True)
    project_code: Mapped[str] = mapped_column(String(100), default='')
    region: Mapped[str] = mapped_column(String(100), default='')
    published_on: Mapped[str] = mapped_column(String(16), default='', index=True)
    deadline: Mapped[str] = mapped_column(String(32), default='')
    deadline_at: Mapped[str] = mapped_column(String(16), default='', index=True)  # 规范化的截止时间（北京时间）
    budget: Mapped[float | None] = mapped_column(Float)
    amount: Mapped[float | None] = mapped_column(Float)
    items: Mapped[str] = mapped_column(Text, default='')
    quotes: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[str] = mapped_column(String(32), default=now)


class NoticeParty(Base):
    """公告参与方。role: buyer/agent/winner/candidate/bidder。"""
    __tablename__ = 'notice_parties'
    __table_args__ = (UniqueConstraint('notice_id', 'company_id', 'role'),)
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    notice_id: Mapped[str] = mapped_column(ForeignKey('notices.id', ondelete='CASCADE'), index=True)
    company_id: Mapped[str] = mapped_column(ForeignKey('companies.id', ondelete='CASCADE'), index=True)
    role: Mapped[str] = mapped_column(String(16))
    amount: Mapped[float | None] = mapped_column(Float)
    quote: Mapped[str] = mapped_column(Text, default='')


class JobCompany(Base):
    """任务产出的企业，role: target（查企业目标）/buyer（找买家结果）/related。"""
    __tablename__ = 'job_companies'
    job_id: Mapped[str] = mapped_column(ForeignKey('jobs.id', ondelete='CASCADE'), primary_key=True)
    company_id: Mapped[str] = mapped_column(ForeignKey('companies.id', ondelete='CASCADE'), primary_key=True)
    role: Mapped[str] = mapped_column(String(16), default='related')


class Lead(Base):
    """销售线索。status: new/verifying/contacted/following/won/invalid。每家企业至多一条。"""
    __tablename__ = 'leads'
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    company_id: Mapped[str] = mapped_column(ForeignKey('companies.id', ondelete='CASCADE'), unique=True)
    notice_id: Mapped[str | None] = mapped_column(ForeignKey('notices.id', ondelete='SET NULL'))
    conversation_id: Mapped[str | None] = mapped_column(String(32), index=True)
    status: Mapped[str] = mapped_column(String(16), default='new', index=True)
    owner: Mapped[str] = mapped_column(String(64), default='')
    next_followup_at: Mapped[str] = mapped_column(String(32), default='')
    tags: Mapped[list] = mapped_column(JSON, default=list)
    score: Mapped[int] = mapped_column(Integer, default=0)
    match_reason: Mapped[str] = mapped_column(Text, default='')
    analysis: Mapped[dict] = mapped_column(JSON, default=dict)
    archived: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[str] = mapped_column(String(32), default=now)
    updated_at: Mapped[str] = mapped_column(String(32), default=now)


class Followup(Base):
    __tablename__ = 'followups'
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    lead_id: Mapped[str] = mapped_column(ForeignKey('leads.id', ondelete='CASCADE'), index=True)
    kind: Mapped[str] = mapped_column(String(16), default='note')
    content: Mapped[str] = mapped_column(Text)
    created_at: Mapped[str] = mapped_column(String(32), default=now)


class Feedback(Base):
    """纠错反馈。kind: relevant/not_buyer/wrong/stale。"""
    __tablename__ = 'feedback'
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    lead_id: Mapped[str] = mapped_column(ForeignKey('leads.id', ondelete='CASCADE'), index=True)
    kind: Mapped[str] = mapped_column(String(16))
    content: Mapped[str] = mapped_column(Text, default='')
    created_at: Mapped[str] = mapped_column(String(32), default=now)


class Knowledge(Base):
    """长期知识。kind: preference/exclusion/product/experience。"""
    __tablename__ = 'knowledge'
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    kind: Mapped[str] = mapped_column(String(16))
    title: Mapped[str] = mapped_column(String(200), default='')
    body: Mapped[str] = mapped_column(Text)
    active: Mapped[int] = mapped_column(Integer, default=1)
    hits: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[str] = mapped_column(String(32), default=now)
    updated_at: Mapped[str] = mapped_column(String(32), default=now)


class SiteStat(Base):
    """来源经验：各站点的尝试、成功与被采用次数，用于排序与冷却。"""
    __tablename__ = 'site_stats'
    site: Mapped[str] = mapped_column(String(64), primary_key=True)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    successes: Mapped[int] = mapped_column(Integer, default=0)
    adopted: Mapped[int] = mapped_column(Integer, default=0)
    last_status: Mapped[str] = mapped_column(String(24), default='')
    last_at: Mapped[str] = mapped_column(String(32), default='')
    cooldown_until: Mapped[str] = mapped_column(String(32), default='')


class CustomSite(Base):
    """用户新增的数据源。mode: template（自拼检索地址）/ site_search（LuzCrawl 自动定位站内搜索框）。"""
    __tablename__ = 'custom_sites'
    id: Mapped[str] = mapped_column(String(48), primary_key=True)
    name: Mapped[str] = mapped_column(String(100))
    kind: Mapped[str] = mapped_column(String(16), default='procurement')
    mode: Mapped[str] = mapped_column(String(16), default='template')
    template: Mapped[str] = mapped_column(String(1000), default='')
    domain: Mapped[str] = mapped_column(String(200), default='')
    detail: Mapped[str] = mapped_column(String(300), default='')
    login: Mapped[int] = mapped_column(Integer, default=0)
    by_company: Mapped[int] = mapped_column(Integer, default=0)
    note: Mapped[str] = mapped_column(String(200), default='')
    created_at: Mapped[str] = mapped_column(String(32), default=now)
    updated_at: Mapped[str] = mapped_column(String(32), default=now)


class DiscoveredSite(Base):
    """全网检索结果中出现、尚未登记为数据源的网站：命中次数与被采用（读出公告）次数。"""
    __tablename__ = 'discovered_sites'
    domain: Mapped[str] = mapped_column(String(200), primary_key=True)
    title: Mapped[str] = mapped_column(String(200), default='')
    sample_url: Mapped[str] = mapped_column(String(1000), default='')
    hits: Mapped[int] = mapped_column(Integer, default=0)
    adopted: Mapped[int] = mapped_column(Integer, default=0)
    dismissed: Mapped[int] = mapped_column(Integer, default=0)
    first_seen: Mapped[str] = mapped_column(String(32), default=now)
    last_seen: Mapped[str] = mapped_column(String(32), default=now)


def init_db() -> None:
    Base.metadata.create_all(engine)
    # create_all 不会给已有表加列：补上后续新增的列
    for table in ('conversations', 'attachments'):
        if 'user_id' not in {c['name'] for c in inspect(engine).get_columns(table)}:
            with engine.begin() as connection:
                connection.execute(text(f'ALTER TABLE {table} ADD COLUMN user_id VARCHAR(32)'))
                connection.execute(text(f'CREATE INDEX IF NOT EXISTS ix_{table}_user_id ON {table} (user_id)'))
    if 'deadline_at' not in {c['name'] for c in inspect(engine).get_columns('notices')}:
        with engine.begin() as connection:
            connection.execute(text("ALTER TABLE notices ADD COLUMN deadline_at VARCHAR(16) DEFAULT ''"))
            connection.execute(text('CREATE INDEX IF NOT EXISTS ix_notices_deadline_at ON notices (deadline_at)'))
    for table in ('messages', 'jobs'):
        columns = {c['name'] for c in inspect(engine).get_columns(table)}
        if 'request_id' not in columns:
            with engine.begin() as connection:
                connection.execute(text(f'ALTER TABLE {table} ADD COLUMN request_id VARCHAR(96)'))
                connection.execute(text(f'CREATE INDEX IF NOT EXISTS ix_{table}_request_id ON {table} (request_id)'))
    with engine.begin() as connection:
        connection.execute(text('CREATE UNIQUE INDEX IF NOT EXISTS uq_messages_conversation_request '
                                'ON messages (conversation_id, request_id) WHERE request_id IS NOT NULL'))
        connection.execute(text('CREATE UNIQUE INDEX IF NOT EXISTS uq_jobs_conversation_request '
                                'ON jobs (conversation_id, request_id) WHERE request_id IS NOT NULL'))


def get_settings() -> dict:
    with Session() as db:
        stored = {row.key: row.value.get('v') for row in db.scalars(select(Setting))}
    return {**DEFAULT_SETTINGS, **{k: v for k, v in stored.items() if k in DEFAULT_SETTINGS}}


def save_settings(values: dict) -> dict:
    with Session.begin() as db:
        for key, value in values.items():
            if key in DEFAULT_SETTINGS:
                db.merge(Setting(key=key, value={'v': value}))
    return get_settings()
