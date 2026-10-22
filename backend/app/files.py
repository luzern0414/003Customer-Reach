"""产品附件持久化与预览；日志不记录产品原文，响应不包含磁盘路径。"""
from pathlib import Path
from .config import DATA
from .db import Session, Attachment, identifier
from .document_parser import parse_document, ALLOWED
from .observability import logger
from .service import ServiceError

LOG = logger('documents')


def attachment_meta(row: Attachment) -> dict:
    """row须为存在的附件；返回文件元信息，旧文件缺少解析元信息时为空字典。"""
    return {'id': row.id, 'filename': row.filename, 'size': row.size,
            'characters': len(row.text or ''), 'truncated': row.truncated,
            'parse': row.parse_info or {}, 'created_at': row.created_at}


def attachment_detail(attachment_id: str) -> dict:
    """attachment_id须非空；返回保存的解析文本与元信息，不存在抛404。"""
    with Session() as db:
        row = db.get(Attachment, attachment_id)
        if not row:
            raise ServiceError('附件不存在', 404)
        return {**attachment_meta(row), 'text': row.text}


def save_attachment(filename: str, content: bytes) -> dict:
    """filename非空、content为<=10MB文件；解析并保存，返回元信息，内容错误抛4xx。"""
    name = Path(filename.replace('\\', '/')).name
    suffix = Path(name).suffix.lower()
    parsed = parse_document(suffix, content)
    upload_id = identifier()
    directory = DATA / 'uploads'
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f'{upload_id}{suffix}'
    path.write_bytes(content)
    with Session.begin() as db:
        row = Attachment(id=upload_id, filename=name, stored_path=str(path), size=len(content),
                         text=parsed.text, truncated=parsed.truncated, parse_info=parsed.metadata)
        db.add(row)
        db.flush()
        result = attachment_meta(row)
    LOG.info('attachment_parsed', extra={'details': {'attachment_id': upload_id,
        'format': suffix, 'characters': result['characters'], 'truncated': parsed.truncated,
        'elapsed_ms': parsed.metadata['elapsed_ms'], 'warning_count': len(parsed.metadata['warnings'])}})
    return result
