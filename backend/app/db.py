"""持久化会话、任务、线索和证据；网络请求不占用数据库事务。"""
import os
import uuid
from datetime import datetime, timedelta, timezone
from sqlalchemy import Column, String, Text, Integer, Boolean, JSON, Float, create_engine, event, inspect, text
from sqlalchemy.orm import declarative_base, sessionmaker
from .config import DATA


def now() -> str:
    """返回上海时区当前时间，统一 yyyy-MM-dd HH:mm:ss，无输入与副作用。"""
    return datetime.now(timezone(timedelta(hours=8))).strftime('%Y-%m-%d %H:%M:%S')


def identifier() -> str:
    """生成非空UUID标识，无输入，不包含任何用户信息。"""
    return uuid.uuid4().hex


Base = declarative_base()
engine = create_engine(os.getenv('CLIENTREACH_DATABASE_URL', f'sqlite:///{DATA / "clientreach.db"}'),
                       connect_args={'check_same_thread': False, 'timeout': 20})


@event.listens_for(engine, 'connect')
def sqlite_pragmas(connection, _):
    """配置本地SQLite并发；connection为非空DBAPI连接，第二参数由SQLAlchemy提供，不返回值。"""
    from .contact_view import contact_available
    connection.create_function('contact_available',1,contact_available,deterministic=True)
    cursor = connection.cursor()
    cursor.execute('PRAGMA journal_mode=WAL')
    cursor.execute('PRAGMA foreign_keys=ON')
    cursor.close()


Session = sessionmaker(engine, expire_on_commit=False)


class Conversation(Base):
    """一次获客对话及已提取的公司产品画像。"""
    __tablename__ = 'conversations'
    id = Column(String, primary_key=True, default=identifier)
    title = Column(String, default='新的获客对话')
    profile = Column(JSON, default=dict)
    created_at = Column(String, default=now)
    updated_at = Column(String, default=now)


class Message(Base):
    """用户或Agent消息；附件仅存文件ID，不在日志记录正文。"""
    __tablename__ = 'messages'
    id = Column(Integer, primary_key=True)
    conversation_id = Column(String, index=True)
    role = Column(String)
    content = Column(Text)
    attachment_ids = Column(JSON, default=list)
    created_at = Column(String, default=now)


class Attachment(Base):
    """上传产品资料的原始文件及解析内容，保留提取状态。"""
    __tablename__ = 'attachments'
    id = Column(String, primary_key=True, default=identifier)
    filename = Column(String)
    stored_path = Column(String)
    size = Column(Integer)
    text = Column(Text)
    truncated = Column(Boolean, default=False)
    parse_info = Column(JSON, default=dict)
    created_at = Column(String, default=now)


class Job(Base):
    """数据库任务队列；独立worker领取，暂停与服务中断可恢复。"""
    __tablename__ = 'jobs'
    id = Column(String, primary_key=True, default=identifier)
    conversation_id = Column(String, index=True)
    client_token = Column(String, unique=True)
    prompt = Column(Text)
    attachment_ids = Column(JSON, default=list)
    status = Column(String, default='queued', index=True)
    stage = Column(String, default='等待执行')
    progress = Column(Integer, default=0)
    cancel_requested = Column(Boolean, default=False)
    lead_ids = Column(JSON, default=list)
    error = Column(Text, default='')
    created_at = Column(String, default=now)
    updated_at = Column(String, default=now)
    graph_version = Column(String, default='v2')
    started_at = Column(String, nullable=True)
    finished_at = Column(String, nullable=True)
    elapsed_ms = Column(Integer, default=0)
    clock_at = Column(Float, nullable=True)
    reply_message_id = Column(Integer, nullable=True)
    generation_id = Column(String, default='')
    metrics = Column(JSON, default=dict)
    query_mode = Column(String, default='auto', server_default='auto')
    company_ids = Column(JSON, default=list, server_default='[]')


class JobEvent(Base):
    """可重放的任务进度事件，供SSE和调试查看，不保存敏感原文。"""
    __tablename__ = 'job_events'
    id = Column(Integer, primary_key=True)
    job_id = Column(String, index=True)
    stage = Column(String)
    message = Column(Text)
    level = Column(String, default='info')
    created_at = Column(String, default=now)
    event_type = Column(String, default='stage')
    payload = Column(JSON, default=dict)


class Evidence(Base):
    """真实工具返回的来源正文；Agent只能引用这些来源记录。"""
    __tablename__ = 'evidence'
    id = Column(String, primary_key=True, default=identifier)
    job_id = Column(String, index=True)
    url = Column(Text)
    title = Column(Text)
    body = Column(Text)
    kind = Column(String)
    captured_at = Column(String, default=now)
    channel = Column(String, default='legacy')
    content_hash = Column(String, default='')
    published_at = Column(String, nullable=True)
    expires_at = Column(String, nullable=True)
    source_meta = Column(JSON, default=dict, server_default='{}')


class Lead(Base):
    """候选客户与CRM状态；事实和AI匹配评估分开保存。"""
    __tablename__ = 'leads'
    id = Column(String, primary_key=True, default=identifier)
    dedupe_key = Column(String, unique=True)
    display_name = Column(String, index=True)
    legal_name = Column(String, nullable=True)
    city = Column(String, default='')
    industry = Column(String, default='')
    status = Column(String, default='review', index=True)
    owner = Column(String, default='')
    next_followup = Column(String, default='')
    score = Column(Integer, default=0)
    match_reason = Column(Text, default='')
    matched_products = Column(JSON, default=list)
    facts = Column(JSON, default=dict)
    evidence = Column(JSON, default=list)
    manual_fields = Column(JSON, default=list)
    tags = Column(JSON, default=list)
    archived = Column(Boolean, default=False)
    created_at = Column(String, default=now)
    updated_at = Column(String, default=now)
    buyer_role = Column(String, default='unknown')
    qualification = Column(JSON, default=dict)
    company_id = Column(String, nullable=True, index=True)


class Memory(Base):
    """持久LangGraph Store记录；命名空间隔离偏好、画像及检索绩效，失效不物理删除。"""
    __tablename__ = 'memories'
    id = Column(String, primary_key=True, default=identifier)
    namespace = Column(String, index=True)
    key = Column(String)
    unique_key = Column(String, unique=True)
    value = Column(JSON)
    status = Column(String, default='active')
    created_at = Column(String, default=now)
    updated_at = Column(String, default=now)


class Knowledge(Base):
    """来源可追溯的产品文档块和客户事实；不把模型总结直接当公开事实。"""
    __tablename__ = 'knowledge'
    id = Column(String, primary_key=True, default=identifier)
    unique_key = Column(String, unique=True)
    workspace_id = Column(String, default='local', index=True)
    title = Column(String)
    body = Column(Text)
    kind = Column(String)
    source_id = Column(String, nullable=True)
    source_url = Column(Text, default='')
    entity_id = Column(String, nullable=True)
    status = Column(String, default='active')
    expires_at = Column(String, nullable=True)
    created_at = Column(String, default=now)
    updated_at = Column(String, default=now)


class Feedback(Base):
    """销售纠错或相关性反馈，独立于原始证据；用于角色、知识和渠道优先级。"""
    __tablename__ = 'feedback'
    id = Column(String, primary_key=True, default=identifier)
    lead_id = Column(String, index=True)
    kind = Column(String)
    content = Column(Text, default='')
    created_at = Column(String, default=now)


class ToolCall(Base):
    """稳定操作ID账本：持久工具结果、耗时及失败码，图恢复复用成功操作。"""
    __tablename__ = 'tool_calls'
    id = Column(String, primary_key=True, default=identifier)
    job_id = Column(String, index=True)
    operation_id = Column(String, unique=True)
    tool = Column(String)
    channel = Column(String, default='')
    arguments = Column(JSON)
    result = Column(JSON, nullable=True)
    status = Column(String, default='running')
    elapsed_ms = Column(Integer, default=0)
    attempts = Column(Integer, default=1)
    last_attempt_epoch = Column(Float, default=0)
    retry_after_epoch = Column(Float, default=0)
    created_at = Column(String, default=now)
    updated_at = Column(String, default=now)


class Followup(Base):
    """销售主动添加的跟进记录，与网页采购事实分离。"""
    __tablename__ = 'followups'
    id = Column(Integer, primary_key=True)
    lead_id = Column(String, index=True)
    content = Column(Text)
    kind = Column(String, default='note')
    created_at = Column(String, default=now)


class Setting(Base):
    """非敏感应用设置；API密钥不写此表。"""
    __tablename__ = 'settings'
    key = Column(String, primary_key=True)
    value = Column(JSON)


def serialize(row) -> dict:
    """将非空ORM行投影为字典；仅用于已确定允许返回的模型，空值调用方处理。"""
    return {c.name: getattr(row, c.name) for c in row.__table__.columns}


def initialize() -> None:
    """创建本地初代数据表；不会删除既有表或迁移客户历史数据。"""
    # 旧表先沿用历史增量修复；企业模块由版本化迁移负责，避免create_all掩盖升级缺口。
    company_tables = {'companies', 'company_facts', 'procurement_projects', 'procurement_notices', 'company_relations', 'research_companies','research_datasets', 'source_documents', 'source_fragments', 'entry_source_bindings', 'tender_records', 'tender_relations'}
    legacy_tables = [table for name, table in Base.metadata.tables.items() if name not in company_tables]
    Base.metadata.create_all(engine, tables=legacy_tables)
    # 非破坏性补列，旧客户和日志原样保留；数据库默认值使已有行可直接序列化。
    additions = {
        'tool_calls': {'attempts':'INTEGER DEFAULT 1', 'last_attempt_epoch':'FLOAT DEFAULT 0', 'retry_after_epoch':'FLOAT DEFAULT 0'},
        'attachments': {'parse_info': "JSON DEFAULT '{}'"},
        'jobs': {'graph_version':"VARCHAR DEFAULT 'v1'", 'started_at':'VARCHAR', 'finished_at':'VARCHAR',
                 'elapsed_ms':'INTEGER DEFAULT 0', 'clock_at':'FLOAT', 'reply_message_id':'INTEGER',
                 'generation_id':"VARCHAR DEFAULT ''", 'metrics':"JSON DEFAULT '{}'"},
        'job_events': {'event_type':"VARCHAR DEFAULT 'stage'", 'payload':"JSON DEFAULT '{}'"},
        'evidence': {'channel':"VARCHAR DEFAULT 'legacy'", 'content_hash':"VARCHAR DEFAULT ''", 'published_at':'VARCHAR','expires_at':'VARCHAR'},
        'leads': {'buyer_role':"VARCHAR DEFAULT 'unknown'", 'qualification':"JSON DEFAULT '{}'"},
    }
    with engine.begin() as connection:
        for table, columns in additions.items():
            existing = {x['name'] for x in inspect(connection).get_columns(table)}
            for name, definition in columns.items():
                if name not in existing:
                    connection.execute(text(f'ALTER TABLE {table} ADD COLUMN {name} {definition}'))
        connection.execute(text('CREATE VIRTUAL TABLE IF NOT EXISTS knowledge_fts USING fts5(item_id UNINDEXED, workspace_id UNINDEXED, title, body)'))
        # 老版资料分没有角色资格，先降到待核等级；不替历史记录推断采购方身份。
        connection.execute(text("UPDATE leads SET score=MIN(score,35), qualification='{}' WHERE buyer_role='unknown' AND (qualification IS NULL OR qualification='{}')"))
    from .migrations import upgrade_database
    upgrade_database(engine)
