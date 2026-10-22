"""文档与条目证据正规化服务；同事务幂等绑定，不请求网络、不重写原Evidence。"""
import hashlib
import json
import re
from decimal import Decimal
from urllib.parse import urlsplit
from sqlalchemy import select, or_
from sqlalchemy.orm import Session as DatabaseSession
from .db import Evidence, Session
from .company_models import Company, CompanyFact, CompanyRelation, ProcurementProject, ProcurementNotice
from .source_models import SourceDocument, SourceFragment, EntrySourceBinding
from .service import ServiceError


def _key(*parts):
    return hashlib.sha256(json.dumps(parts, ensure_ascii=False, default=str).encode()).hexdigest()


def _span(body, quote, cache, source_id):
    # 只忽略排版空白；逗号、大小写、数值等正文字符不得为匹配而改写。
    start = body.find(quote)
    if start >= 0:
        return (start, start + len(quote)) if body.find(quote, start + 1) < 0 else None
    compact = re.sub(r'\s+', '', quote)
    if not compact:
        return None
    if source_id not in cache:
        characters = [(i, char) for i, char in enumerate(body) if not char.isspace()]
        cache[source_id] = (''.join(char for _, char in characters), [i for i, _ in characters])
    folded, positions = cache[source_id]
    start = folded.find(compact)
    if start < 0 or folded.find(compact, start + 1) >= 0:
        return None
    return positions[start], positions[start + len(compact) - 1] + 1


def _relation_row(body, entry):
    if entry.relation_type not in {'supplier', 'customer'}:
        return None
    # 旧表格摘录包含人工表头；仅同一真实行具名且数值全部吻合才回填该原始行。
    terms = [entry.counterparty_name]
    numbers = [value for value in (entry.amount, entry.share) if value is not None]
    matches = []
    offset = 0
    for line in body.splitlines(keepends=True):
        compact = re.sub(r'\s+', '', line)
        if all(re.sub(r'\s+', '', term) in compact for term in terms) and all(
            format(Decimal(str(value)), ',.2f') in compact or format(Decimal(str(value)), '.2f') in compact
            for value in numbers
        ):
            text = line.strip()
            if text and len(text) <= 1200:
                start = offset + line.index(text)
                matches.append((start, start + len(text)))
        offset += len(line)
    return matches[0] if len(matches) == 1 else None


def _excerpts(entry, kind):
    payload = (entry.provenance or {}) if kind == 'fact' else (entry.payload or {})
    citations = [*(payload.get('source_citations') or []), *(payload.get('citations') or [])]
    values = []
    covered = set()
    explicit_sources = {source_id for citation in payload.get('source_citations') or [] if isinstance(citation, dict)
                        for source_id in (citation.get('source_ids') or [citation.get('source_id')])}
    legacy_ids = list(dict.fromkeys(entry.source_ids or []))
    legacy_unlocated = len(legacy_ids) == 1
    for citation in citations:
        if isinstance(citation, dict) and citation.get('quote'):
            ids = citation.get('source_ids') or [citation.get('source_id')]
            role = citation.get('role', 'value')
            values.append((citation['quote'], role, ids, len(set(ids)) == 1))
            covered.update((role, source_id) for source_id in ids)
    if getattr(entry, 'quote', ''):
        values.append((entry.quote, 'value', [s for s in legacy_ids if s not in explicit_sources and ('value', s) not in covered], legacy_unlocated))
    # 日期、统计表头、预算和买方引文独立保存，不把多段原文拼作一个连续片段。
    for field, role in [('quote', 'value'), ('metadata_quote', 'metadata'), ('buyer_quote', 'buyer'),
                        ('publication_quote', 'publication'), ('deadline_quote', 'deadline'), ('budget_quote', 'budget')]:
        if payload.get(field):
            # 显式来源卡片已完整表达本次片段；缺metadata表示本次没有，不能继承旧来源。
            references = legacy_ids if role == 'value' else legacy_ids[:1]
            values.append((payload[field], role, [s for s in references if s not in explicit_sources and (role, s) not in covered], legacy_unlocated))
    quotation = payload.get('quotation')
    if isinstance(quotation, str) and quotation:
        values.append((quotation, 'value', [s for s in legacy_ids if s not in explicit_sources and ('value', s) not in covered], legacy_unlocated))
    elif isinstance(quotation, list):
        for item in quotation:
            text = item.get('quote') if isinstance(item, dict) else item
            if isinstance(text, str) and text:
                values.append((text, 'value', [s for s in legacy_ids if s not in explicit_sources and ('value', s) not in covered], legacy_unlocated))
    return values


def bind_company_sources(db: DatabaseSession, company_id: str) -> dict[str, int]:
    """将已保存条目关联至文档和独立片段，参与调用者事务且不提交。

    参数：db为当前SQLAlchemy事务会话，不能为空；company_id为已存在企业ID，空/不存在抛404。
    返回：本次新增documents/fragments/bindings数量，重复调用均为0。
    异常：外键/数据库错误向上传播，整体随调用者回滚；未知引用不生成伪造文档。
    """
    db.flush()
    if not company_id or not db.get(Company, company_id):
        raise ServiceError('企业不存在', 404)
    facts = list(db.scalars(select(CompanyFact).where(CompanyFact.company_id == company_id)))
    relations = list(db.scalars(select(CompanyRelation).where(CompanyRelation.company_id == company_id)))
    projects = list(db.scalars(select(ProcurementProject).where(ProcurementProject.buyer_id == company_id)))
    notices = list(db.scalars(select(ProcurementNotice).where(ProcurementNotice.project_id.in_([p.id for p in projects])))) if projects else []
    entries = [('fact', r) for r in facts] + [('relation', r) for r in relations] + [('project', r) for r in projects] + [('notice', r) for r in notices]
    ids = {s for _, row in entries for s in row.source_ids or []}
    evidence = {row.id: row for row in db.scalars(select(Evidence).where(Evidence.id.in_(ids)))} if ids else {}
    documents = {row.evidence_id: row for row in db.scalars(select(SourceDocument).where(SourceDocument.evidence_id.in_(ids)))} if ids else {}
    result = {'documents': 0, 'fragments': 0, 'bindings': 0}
    for source_id, source in evidence.items():
        if source_id in documents:
            continue
        meta = source.source_meta or {}
        document = SourceDocument(id=_key('document', source_id), evidence_id=source_id,
            document_kind='pdf' if re.search(r'\.pdf(?:[?#]|$)', source.url or '', re.I) else 'web',
            origin=meta.get('origin', 'agent'), namespace=meta.get('dataset', ''),
            external_id=str(meta.get('source_id') or ''), content_hash=source.content_hash or '')
        db.add(document); documents[source_id] = document; result['documents'] += 1
    db.flush()
    fragment_cache = {row.unique_key: row for row in db.scalars(select(SourceFragment).where(SourceFragment.document_id.in_([d.id for d in documents.values()])))} if documents else {}
    binding_ids = set(db.scalars(select(EntrySourceBinding.id).where(EntrySourceBinding.company_id == company_id)))
    span_cache = {}
    for kind, entry in entries:
        excerpts = _excerpts(entry, kind)
        for ordinal, (quote, role, references, allow_unlocated) in enumerate(excerpts):
            if not isinstance(quote, str) or not quote.strip():
                continue
            references = list(dict.fromkeys(s for s in references if s in evidence and s in (entry.source_ids or [])))
            for source_id in references:
                source = evidence[source_id]
                body = source.body or ''
                span = _span(body, quote, span_cache, source_id)
                if kind == 'relation' and role == 'value':
                    row_span = _relation_row(body, entry)
                    # 宽表引文也只展示当前交易行；连续行必须位于原引文内，不能越界借用。
                    if row_span and (not span or span[0] <= row_span[0] and row_span[1] <= span[1]):
                        span = row_span
                # 来源未明确的合并摘录不能复制到多个文档；只绑定各文档能独立定位的片段。
                if not span and not allow_unlocated:
                    continue
                text = body[span[0]:span[1]] if span else quote.strip()
                quote_kind = 'continuous' if span else 'historical_excerpt' if source.source_meta and source.source_meta.get('origin') == 'historical_snapshot' else 'unlocated_excerpt'
                page_start = page_end = None
                if span:
                    markers = list(re.finditer(r'===== PDF PAGE (\d+) =====', body))
                    before = [m for m in markers if m.end() <= span[0]]
                    end_before = [m for m in markers if m.end() <= span[1]]
                    if before and end_before:
                        page_start = int(before[-1][1]); page_end = int(end_before[-1][1])
                key = _key(documents[source_id].id, text, quote_kind, span)
                fragment = fragment_cache.get(key)
                if not fragment:
                    fragment = SourceFragment(id=key, unique_key=key, document_id=documents[source_id].id,
                        text=text, quote_kind=quote_kind, location_status='located' if span else 'unlocated',
                        char_start=span[0] if span else None, char_end=span[1] if span else None,
                        page_start=page_start, page_end=page_end)
                    db.add(fragment); fragment_cache[key] = fragment; result['fragments'] += 1
                binding_id = _key(kind, entry.id, fragment.id, role)
                if binding_id not in binding_ids:
                    db.flush()
                    db.add(EntrySourceBinding(id=binding_id, company_id=company_id, fragment_id=fragment.id,
                        **{kind + '_id': entry.id}, role=role, ordinal=ordinal))
                    binding_ids.add(binding_id); result['bindings'] += 1
    db.flush()
    return result


def entry_references(db: DatabaseSession, entries: dict[str, list[str]]) -> dict[str, list[dict]]:
    """批量投影当前条目证据，不读取或返回整份正文。

    参数：db为有效读取会话；entries为fact/relation/project/notice到条目ID列表，空列表返回空字典。
    返回：以条目ID索引的片段列表，摘录最多800字符；完整片段可显式单独读取。
    异常：数据库异常向上传播；空原站URL不补造，页码未知保持null。
    """
    conditions = [getattr(EntrySourceBinding, kind + '_id').in_(ids) for kind, ids in entries.items() if ids]
    if not conditions:
        return {}
    rows = db.execute(select(EntrySourceBinding, SourceFragment, SourceDocument, Evidence)
        .join(SourceFragment, EntrySourceBinding.fragment_id == SourceFragment.id)
        .join(SourceDocument, SourceFragment.document_id == SourceDocument.id)
        .join(Evidence, SourceDocument.evidence_id == Evidence.id)
        .where(or_(*conditions)).order_by(EntrySourceBinding.ordinal, EntrySourceBinding.id))
    result = {}
    for binding, fragment, document, source in rows:
        entry_id = next(getattr(binding, kind + '_id') for kind in ('fact', 'relation', 'project', 'notice') if getattr(binding, kind + '_id'))
        url = source.url or ''
        try:
            parsed = urlsplit(url)
            valid_url = parsed.scheme in {'http', 'https'} and bool(parsed.netloc) and not parsed.username and not parsed.password and not re.search(r'\s', url)
        except ValueError:
            valid_url = False
        result.setdefault(entry_id, []).append({'id': fragment.id, 'binding_id': binding.id,
            'document_id': document.id, 'source_id': source.id, 'title': source.title or '',
            'url': url if valid_url else '', 'source_url': url if valid_url else '',
            'page_url': url.split('#')[0] + '#page=' + str(fragment.page_start) if valid_url and document.document_kind == 'pdf' and fragment.page_start else '',
            'published_at': source.published_at, 'captured_at': source.captured_at,
            'text': fragment.text[:800], 'truncated': len(fragment.text) > 800,
            'quote_kind': fragment.quote_kind, 'location_status': fragment.location_status,
            'page_start': fragment.page_start, 'page_end': fragment.page_end, 'role': binding.role})
    return result


def fragment_detail(fragment_id: str) -> dict:
    """读取显式选定的片段，不默认返回原文档全文。

    参数：fragment_id为持久片段ID，空或不存在抛404。返回：该片段完整原值与定位类型。
    异常：数据库错误向上传播；不返回本地路径/内部元数据。
    """
    with Session() as db:
        row = db.get(SourceFragment, fragment_id)
        if not row:
            raise ServiceError('证据片段不存在', 404)
        return {'id': row.id, 'text': row.text, 'quote_kind': row.quote_kind, 'page_start': row.page_start, 'page_end': row.page_end}


def company_document(company_id: str, source_id: str) -> dict:
    """投影一份来源文档在当前企业的条目证据，替代默认全文预览。

    参数：company_id为持久企业ID，source_id为Evidence ID，均必填；无企业或无关联来源抛404。
    返回：来源元信息及该企业事实/关系/项目/公告的精简条目，不返回文档正文。
    异常：数据库错误向上传播；不能用其他企业的引用解锁来源。
    """
    from .company_service import company_detail
    detail = company_detail(company_id)
    source = next((s for s in detail['sources'] if s['id'] == source_id), None)
    if not source:
        raise ServiceError('企业未关联此来源', 404)
    entries = []
    rows = [('fact', r) for r in detail['facts']] + [('relation', r) for r in detail['relations']] + [('project', r) for r in detail['projects']]
    rows += [('notice', n) for p in detail['projects'] for n in p['notices']]
    for kind, row in rows:
        references = [r for r in row['evidence_refs'] if r['source_id'] == source_id]
        if source_id in row['source_ids']:
            entries.append({**{key: row[key] for key in ('record_kind', 'relation_type', 'amount', 'share', 'unit', 'raw_unit', 'currency', 'scope', 'buyer_name', 'stage', 'temporal_status', 'deadline') if key in row},
                'kind': kind, 'id': row['id'], 'title': row.get('label') or row.get('counterparty_name') or row.get('title'),
                'value': row.get('raw_value'), 'period': row.get('report_period') or row.get('published_at') or '',
                'payload': {key: row.get('payload', {}).get(key) for key in ('budget', 'quantity', 'unit') if key in row.get('payload', {})},
                'evidence_refs': references})
    with Session() as db:
        from .company_models import TenderRecord,TenderRelation
        evidence=db.get(Evidence,source_id)
        for record in db.scalars(select(TenderRecord).where(TenderRecord.company_id==company_id,TenderRecord.evidence_id==source_id)):
            quote=record.quote or ''
            refs=[{'id':record.id,'source_id':source_id,'text':quote,'quote_kind':'excerpt','truncated':False,
                'title':source['title'],'url':source['url']}] if evidence and quote and quote in evidence.body else []
            scope='候选/备选成交，非最终中标，不自动确认客户关系' if record.role=='candidate' else '公开招投标公告；不代表已确认订单'
            entries.append({'kind':'notice','id':record.id,'title':record.title,'published_at':record.published_at,
                'period':record.published_at,'scope':scope,'source_ids':[source_id],'evidence_refs':refs})
        for relation in db.scalars(select(TenderRelation).where(TenderRelation.company_id==company_id,TenderRelation.evidence_id==source_id)):
            quote=relation.quote or ''
            refs=[{'id':relation.id,'source_id':source_id,'text':quote,'quote_kind':'excerpt','truncated':False,
                'title':source['title'],'url':source['url']}] if evidence and quote and quote in evidence.body else []
            basis={'records':'公开招投标公告','platform_stats':'平台合作统计','third_party_list':'第三方名录'}.get(relation.basis,'公开来源')
            entries.append({'kind':'relation','id':relation.id,'title':relation.counterparty_name,
                'relation_type':relation.relation_type,'period':relation.latest_at or '',
                'scope':basis+'口径；次数不代表交易金额，不自动确认订单',
                'source_ids':[source_id],'evidence_refs':refs})
    return {'source': source, 'entries': entries}
