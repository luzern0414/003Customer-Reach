"""原始文档、条目证据片段与强外键绑定；共享报告不共享无上下文的预览。"""
from sqlalchemy import Column, String, Text, Integer, JSON, ForeignKey, CheckConstraint, UniqueConstraint
from .db import Base, identifier, now


class SourceDocument(Base):
    """Evidence的一对一文档版本；原站地址和正文仍由不可变Evidence保存。"""
    __tablename__ = 'source_documents'
    id = Column(String, primary_key=True, default=identifier)
    evidence_id = Column(String, ForeignKey('evidence.id'), nullable=False, unique=True)
    document_kind = Column(String, default='web')
    origin = Column(String, default='agent')
    namespace = Column(String, default='')
    external_id = Column(String, default='')
    content_hash = Column(String, default='')
    created_at = Column(String, default=now)


class SourceFragment(Base):
    """当前文档版本的实际摘录；不能定位的历史整理文本显式保留摘录类型。"""
    __tablename__ = 'source_fragments'
    id = Column(String, primary_key=True, default=identifier)
    unique_key = Column(String, nullable=False, unique=True)
    document_id = Column(String, ForeignKey('source_documents.id'), nullable=False, index=True)
    text = Column(Text, nullable=False)
    quote_kind = Column(String, nullable=False)
    location_status = Column(String, nullable=False)
    char_start = Column(Integer, nullable=True)
    char_end = Column(Integer, nullable=True)
    page_start = Column(Integer, nullable=True)
    page_end = Column(Integer, nullable=True)
    created_at = Column(String, default=now)


class EntrySourceBinding(Base):
    """一个事实/项目/公告/关系关联一个片段；数据库保证只能绑定一种条目。"""
    __tablename__ = 'entry_source_bindings'
    __table_args__ = (
        CheckConstraint('(CASE WHEN fact_id IS NULL THEN 0 ELSE 1 END + CASE WHEN relation_id IS NULL THEN 0 ELSE 1 END + CASE WHEN project_id IS NULL THEN 0 ELSE 1 END + CASE WHEN notice_id IS NULL THEN 0 ELSE 1 END) = 1', name='ck_source_single_entry'),
        UniqueConstraint('fact_id', 'fragment_id', 'role'),
        UniqueConstraint('relation_id', 'fragment_id', 'role'),
        UniqueConstraint('project_id', 'fragment_id', 'role'),
        UniqueConstraint('notice_id', 'fragment_id', 'role'),
    )
    id = Column(String, primary_key=True, default=identifier)
    company_id = Column(String, ForeignKey('companies.id'), nullable=False, index=True)
    fragment_id = Column(String, ForeignKey('source_fragments.id'), nullable=False, index=True)
    fact_id = Column(String, ForeignKey('company_facts.id'), nullable=True, index=True)
    relation_id = Column(String, ForeignKey('company_relations.id'), nullable=True, index=True)
    project_id = Column(String, ForeignKey('procurement_projects.id'), nullable=True, index=True)
    notice_id = Column(String, ForeignKey('procurement_notices.id'), nullable=True, index=True)
    role = Column(String, nullable=False, default='value')
    ordinal = Column(Integer, nullable=False, default=0)
    created_at = Column(String, default=now)
