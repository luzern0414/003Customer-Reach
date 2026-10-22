"""幂等导入已审阅历史研究；数据、日期、来源和摘录类型均保留，不制造Agent工具历史。"""
import hashlib
import json
import re
import shutil
from collections import Counter
from decimal import Decimal, InvalidOperation
from pathlib import Path
from sqlalchemy import select
from .config import ROOT, DATA
from .db import Session, Evidence, Conversation, Message, Setting, now
from .company_models import Company, CompanyFact, ProcurementProject, ProcurementNotice, CompanyRelation, ResearchCompany
from .company_service import stable_key, canonical_field, ensure_company
from .service import ServiceError
from .source_service import bind_company_sources
from .evidence_citations import append_citations


def load_json(path: Path) -> dict:
    """path为现有UTF-8研究文件；返回对象，缺失/坏JSON转为可公开业务错误，不使用远端补造。"""
    try: return json.loads(path.read_text(encoding='utf-8-sig'))
    except (OSError, ValueError) as exc: raise ServiceError('研究资料不可读取：' + path.name, 422) from exc


def import_source(db, dataset: str, source: dict, path: Path) -> str:
    """db为事务、dataset非空命名空间、source含原ID/URL、path为存在原文；幂等归档并返回Evidence ID。"""
    if not path.is_file(): raise ServiceError('来源存档缺失：' + path.name, 422)
    content = path.read_bytes(); digest = hashlib.sha256(content).hexdigest()
    expected = source.get('source_sha256') or source.get('content_sha256')
    if expected and expected != digest: raise ServiceError('来源存档哈希不匹配：' + path.name, 422)
    external_id = source.get('source_id') or source.get('id')
    key = stable_key(dataset, external_id, source['url'], digest)
    if db.get(Evidence, key): return key
    archive = DATA / 'research_sources' / dataset / (digest + path.suffix)
    archive.parent.mkdir(parents=True, exist_ok=True)
    if not archive.exists(): shutil.copyfile(path, archive)
    if path.suffix.lower() == '.pdf':
        from pypdf import PdfReader
        body = '\n\n'.join(page.extract_text() or '' for page in PdfReader(str(path)).pages)
    else: body = content.decode('utf-8-sig')
    row = Evidence(id=key, job_id=None, url=source['url'], title=source.get('title', ''), body=body,
        kind='历史归档正文', channel=source.get('platform', 'disclosure'), content_hash=hashlib.sha256(body.encode()).hexdigest(),
        published_at=source.get('published_date') or source.get('date'),
        source_meta={'dataset': dataset, 'source_id': external_id, 'origin': 'historical_snapshot',
            'evidence_kind': source.get('evidence_kind', '历史公开资料'), 'sha256': digest,
            'hash_object': 'original_pdf' if path.suffix.lower() == '.pdf' else 'archived_text',
            'hash_computed_at': now(), 'original_path': str(path), 'archive_path': str(archive)})
    db.add(row); db.flush(); return row.id


def import_fact(db, company: Company, dataset: str, item: dict, sources: dict, status='verified') -> CompanyFact:
    """db/主体必存在，item为审阅事实，sources为本数据集来源映射；缺引用拒绝，幂等保留原值及口径。"""
    refs = item.get('source_ids') or [item.get('source_id')]
    ids = [sources[r] for r in refs if r in sources]
    if not ids: raise ServiceError('事实缺少可追溯来源：' + item.get('field', ''), 422)
    key = stable_key(dataset, item.get('raw_id'), company.id, item['field'], item.get('as_of'), item.get('value'))
    row = db.scalar(select(CompanyFact).where(CompanyFact.unique_key == key))
    label = item['field']; field = canonical_field(label)
    if field in {'industry', 'business', 'products'} and isinstance(item.get('value'), (int, float)): field = 'detail'
    scope = item.get('entity_scope', '')
    # 多来源原文按明确映射分别保存；旧合并引文不复制到每份文档。
    citations = [{'source_id': sources[e['source_id']], 'quote': e['quote'], 'role': 'value'}
                 for e in item.get('evidence_entries', []) if e.get('source_id') in sources and e.get('quote')]
    if '集团合并' in item.get('note', ''): scope = '集团合并口径'
    elif '子公司单体' in item.get('note', ''): scope = '子公司单体口径'
    elif field == 'headcount' and '控股子公司' in item.get('note', ''): scope = '公司及控股子公司'
    if row:
        # 回填只补引用，不覆盖既有事实/口径或后续研究的逐源引用。
        provenance = row.provenance or {}
        for citation in citations:
            provenance = append_citations(provenance, citation['source_id'], {'value': citation['quote']})
        if citations: row.provenance = provenance
        return row
    numeric = item.get('standard_value', item.get('value'))
    try: numeric = Decimal(str(numeric)) if isinstance(numeric, (int, float, Decimal)) and not isinstance(numeric, bool) else None
    except InvalidOperation: numeric = None
    row = CompanyFact(unique_key=key, company_id=company.id, category=item.get('category', ''), field=field,
        label=label, raw_value=item.get('value'), numeric_value=numeric,
        unit=item.get('standard_unit') or item.get('unit', ''), raw_unit=item.get('unit', ''),
        report_period=item.get('report_period') or item.get('as_of', ''), as_of=item.get('as_of', ''),
        scope=scope, status=status, source_ids=ids,
        quote=item.get('evidence_quote', ''), note=item.get('note', ''),
        provenance={'dataset': dataset, 'raw_id': item.get('raw_id'), 'origin': 'historical_snapshot',
            'source_citations': citations,
            'original_status': item.get('status'), 'publication_date': item.get('publication_date'),
            'contact_validity': item.get('contact_validity') or item.get('contact_state', '')})
    db.add(row)
    if field == 'credit_code' and status == 'verified': company.credit_code = str(item['value'])
    if field == 'short_name' and not company.short_name and status == 'verified': company.short_name = str(item['value'])
    return row


def import_research(db, namespace: str, document: dict) -> dict:
    """db为事务，namespace隔离外部ID、document含已清洗资料；返回主体/来源/历史会话，不触发模型或搜索。"""
    sources = {s['source_id']: import_source(db, namespace, s, Path(s['text_path'])) for s in document['sources']}
    main_name = Counter(r['entity_name'] for r in document['finance']).most_common(1)[0][0]
    companies = {}
    for item in [*document['profiles'], *document['finance']]:
        name = item['entity_name']
        if name not in companies:
            companies[name] = ensure_company(db, name, origin='historical_snapshot', view_scope='group' if name == main_name else 'entity',
                entity_kind='legal' if re.search('有限公司|股份|有限合伙', name) else 'brand',
                visibility='primary' if name == main_name else 'related', research_as_of='2026-10-08')
        company = companies[name]
        import_fact(db, company, namespace, item, sources)
        if name != main_name and item.get('category') in {'母子实体', '子公司关系'} and re.search('母子关系|持股比例', item['field']):
            parent = companies.get(main_name) or ensure_company(db, main_name, view_scope='group', origin='historical_snapshot', research_as_of='2026-10-08')
            key = stable_key(namespace, 'subsidiary', parent.id, company.id, item.get('as_of'))
            if not db.scalar(select(CompanyRelation.id).where(CompanyRelation.unique_key == key)):
                db.add(CompanyRelation(unique_key=key, company_id=parent.id, counterparty_id=company.id, counterparty_name=name,
                    relation_type='subsidiary', report_period=item.get('as_of', ''), source_ids=[sources[item['source_id']]],
                    quote=item['evidence_quote'], note=item.get('note', ''), payload={'ownership_field': item['field'], 'ownership_value': item['value']}))
    parent = companies[main_name]
    # 年报企业信息中的完整业务段落属于实际已归档正文；从连续段落补齐画像而非借用财务“主营收入”。
    financial_sources = {r['source_id'] for r in document['finance'] if r['entity_name'] == main_name}
    for source in sorted(document['sources'], key=lambda s: s.get('published_date') or '', reverse=True):
        if source['source_id'] not in financial_sources: continue
        body = db.get(Evidence, sources[source['source_id']]).body
        match = re.search(r'主要产品与服务项目\s+(.+?)普通股总股本', body, re.S)
        if not match: continue
        raw = match.group(0).removesuffix('普通股总股本').strip()
        description = re.sub(r'\s+', '', match.group(1)).strip()
        peers = [r for r in document['finance'] if r['entity_name'] == main_name and r['source_id'] == source['source_id']]
        as_of = peers[0].get('as_of', '') if peers else ''
        extra = {'field': '主要产品与服务项目', 'value': description.split('，拥有')[0], 'category': '企业业务',
            'source_id': source['source_id'], 'evidence_quote': raw, 'as_of': as_of,
            'raw_id': 'report-business-' + source['source_id'], 'entity_scope': '报告主体主营业务'}
        import_fact(db, parent, namespace, extra, sources)
        series = re.search(r'以(.+?)为主的[一二三四五六七八九十\d]+大?系列', description)
        if series:
            import_fact(db, parent, namespace, {**extra, 'field': '报告产品系列', 'value': series[1], 'raw_id': 'report-products-' + source['source_id']}, sources)
        break
    conv_id = stable_key('historical-conversation', namespace)
    conversation = db.get(Conversation, conv_id)
    if not conversation:
        conversation = Conversation(id=conv_id, title='历史研究 · ' + (parent.short_name or parent.name), profile={})
        db.add(conversation); db.flush()
        db.add(Message(conversation_id=conv_id, role='assistant', content='### 历史研究快照\n\n已导入公开资料归档，研究截至2026-10-08。可查看企业画像、采购信息与上下游；本会话没有伪造的实时工具轨迹。点击继续研究可创建真实任务。'))
    return {'main': parent, 'companies': companies, 'sources': sources, 'conversation_id': conv_id}


def import_history() -> dict:
    """无入参；仅导入项目内明确的四份已审阅资料，重复调用不重复记录，缺文件422且不提交半份数据。"""
    directory = ROOT / '.codex-tmp'
    byd = load_json(directory / 'byd-research/cleaned_byd_data.json')
    hanon = load_json(directory / 'hanon-research/cleaned_hanon.json')
    purchase = load_json(directory / 'byd-procurement-analysis/normalized_procurement.json')
    hp = load_json(directory / 'hanon-procurement/procurement_cleaned.json')
    with Session.begin() as db:
        b = import_research(db, 'byd-20261008', byd)
        h = import_research(db, 'hanon-20261008', hanon)
        # 补充来源独立于旧research ID；来源命名空间只在显式映射后合并。
        supplement = load_json(directory / 'byd-procurement-analysis/supplement.json')
        for source in supplement['sources']:
            b['sources'][source['source_id']] = import_source(db, 'byd-supplement-20261008', source, Path(source['text_path']))
        control = supplement['group_control_evidence']
        control_lines = Path(control['path']).read_text(encoding='utf-8-sig').splitlines()
        for item in control['entity_rows']:
            subsidiary = b['companies'][item['entity']]
            key = stable_key('byd-control', b['main'].id, subsidiary.id, control['as_of'])
            if not db.scalar(select(CompanyRelation.id).where(CompanyRelation.unique_key == key)):
                entity_quote = control_lines[item['line'] - 1]
                db.add(CompanyRelation(unique_key=key, company_id=b['main'].id, counterparty_id=subsidiary.id,
                    counterparty_name=subsidiary.name, relation_type='subsidiary', report_period=control['as_of'],
                    source_ids=[b['sources'][control['source_id']]], quote=control['control_policy']['quote'] + '\n' + entity_quote,
                    note=control['assessment'], payload={'quote_kind': 'multiple_spans', 'policy_lines': control['control_policy']['lines'], 'entity_line': item['line']}))
        project_ids = {}
        for item in purchase['projects']:
            buyer = b['companies'].get(item['buyer']) or ensure_company(db, item['buyer'], origin='historical_snapshot')
            buyer.visibility = 'primary'
            number = item.get('unique_project_key') or item['project_id']
            key = stable_key('byd-project', buyer.id, number)
            project = db.scalar(select(ProcurementProject).where(ProcurementProject.unique_key == key))
            if not project:
                references = [b['sources'][s['source_id']] for s in item['sources']]
                dates = sorted(item.get('dates', []), key=lambda r: r.get('publication_date') or '', reverse=True)
                latest = dates[0] if dates else {}
                payload = {k: item.get(k) for k in ('product', 'category', 'group', 'quantity', 'unit', 'quantity_status', 'model', 'budget', 'candidate_quote', 'delivery', 'purchase_characteristics', 'frequency', 'future_purchase_possibility', 'announcement_project_ids', 'deduplication')}
                payload['specifications'] = [{k: s.get(k) for k in ('parameter', 'raw', 'stage', 'source_id')} for s in item.get('specifications', [])]
                payload['currency_confirmed'] = False
                project = ProcurementProject(unique_key=key, buyer_id=buyer.id, title=item['title'], project_number=number,
                    stage=item.get('stage', ''), published_at=latest.get('publication_date', ''), deadline=latest.get('bid_deadline') or '',
                    payload=payload, source_ids=references, quote=item['sources'][0]['quotations'][0]['quote'])
                db.add(project); db.flush()
            citations = [{'source_id': b['sources'][s['source_id']], 'quote': q['quote'], 'role': 'value'}
                         for s in item['sources'] for q in s.get('quotations', []) if q.get('quote')]
            for citation in citations:
                project.payload = append_citations(project.payload, citation['source_id'], {'value': citation['quote']})
            project_ids[number] = project.id
            # 最终归一资料明确给出了标包别名，不对任意编号做删除后缀式猜并。
            if item.get('uniqueId'): project_ids[item['uniqueId']] = project.id
        for item in purchase['notices']:
            project_id = project_ids.get(item['projectId'])
            if not project_id: raise ServiceError('公告缺少已确认项目关联', 422)
            key = stable_key('byd-notice', project_id, item['sourceId'], item['eventDate'])
            if not db.scalar(select(ProcurementNotice.id).where(ProcurementNotice.unique_key == key)):
                db.add(ProcurementNotice(unique_key=key, project_id=project_id, title=item['product'] + ' · ' + item['stage'],
                    notice_type=item['stage'], published_at=item['eventDate'], platform_published_at=item.get('webpageDate') or '',
                    deadline=item.get('deadline') or '', source_ids=[b['sources'][item['sourceId']]],
                    payload={k: item.get(k) for k in ('quantity', 'unit', 'budget', 'quoteExclusive', 'quoteInclusive', 'candidate', 'specifications', 'quotation', 'note')}))
        # 年报名称/金额/占比同源同口径配对，合计行仅为统计事实。
        fields = hanon['profiles']
        for item in fields:
            match = re.fullmatch(r'(\d{4})年前五(供应商|客户)第(\d+)名', item['field'])
            if not match: continue
            year, kind, rank = match.groups(); name = str(item['value'])
            amount_label = name + ('对应年度采购金额' if kind == '供应商' else '对应年度销售金额')
            amount = next((f for f in fields if f['field'] == amount_label and f['source_id'] == item['source_id']), None)
            share = next((f for f in fields if f['field'] == name + '对应年度占比' and f['source_id'] == item['source_id']), None)
            key = stable_key('hanon-relation', h['main'].id, year, kind, name)
            if not db.scalar(select(CompanyRelation.id).where(CompanyRelation.unique_key == key)):
                db.add(CompanyRelation(unique_key=key, company_id=h['main'].id, counterparty_name=name,
                    relation_type='supplier' if kind == '供应商' else 'customer', rank=int(rank), report_period=year,
                    amount=Decimal(str(amount['value'])) if amount else None, currency='CNY', unit='元',
                    share=Decimal(str(share['value'])) if share else None, scope='集团年度采购额' if kind == '供应商' else '集团年度销售额',
                    source_ids=[h['sources'][item['source_id']]], quote=item['evidence_quote'],
                    note='年报披露无关联关系；具体交易产品、型号、数量与频次未披露。对手方法人身份未单独工商核验。'))
        evidence = {e['id']: e for e in hp['evidence']}
        hp_sources = {}
        for source in hp['sources']:
            existing = next((h['sources'][s['source_id']] for s in hanon['sources'] if s['url'] == source['url']), None)
            hp_sources[source['id']] = existing or import_source(db, 'hanon-procurement-20261008', source, directory / 'hanon-procurement/sources' / source['file'])
        for item in hp['suppliers']:
            if item['kind'] != '年度接受劳务披露，非逐笔招采': continue
            entry = evidence[item['evidence']]
            key = stable_key('hanon-service-supplier', h['main'].id, item['id'])
            if not db.scalar(select(CompanyRelation.id).where(CompanyRelation.unique_key == key)):
                db.add(CompanyRelation(unique_key=key, company_id=h['main'].id, counterparty_name=item['supplier'],
                    relation_type='service_supplier', report_period=item['period'], amount=Decimal(str(item['amount'])),
                    currency='CNY', unit='元', scope=item['kind'], source_ids=[hp_sources[entry['source']]],
                    quote=entry['quote'], note=item['note'], payload={'product': item['product'], 'affiliation': item['relation']}))
        # 外部买方采购品牌设备是应用线索，不能反向变成海能自身采购或直接销售。
        for item in hanon['tenders']:
            if not item.get('buyer') or '项目总投资' in item.get('amount_type', ''): continue
            buyer = ensure_company(db, item['buyer'], visibility='counterparty', entity_kind='unknown', origin='historical_snapshot')
            key = stable_key('hanon-brand-application', buyer.id, item.get('project_key') or item['source_id'])
            if db.scalar(select(ProcurementProject.id).where(ProcurementProject.unique_key == key)): continue
            related = [r for r in hanon['tenders'] if r.get('buyer') == item.get('buyer') and (r.get('project_key') or r['source_id']) == (item.get('project_key') or item['source_id'])]
            source_ids = list(dict.fromkeys(h['sources'][s] for r in related for s in r.get('source_ids', [r['source_id']])))
            db.add(ProcurementProject(unique_key=key, buyer_id=buyer.id, title=item['title'], record_kind='brand_application',
                project_number=item.get('project_id') or '', stage=item.get('announcement_type', ''),
                published_at=item.get('published_date') or '', source_ids=source_ids, quote=item['evidence_quote'],
                payload={'research_company_id': h['main'].id, 'direct_trade': False,
                    'applications': [{k: r.get(k) for k in ('target_entity', 'target_role', 'supplier', 'relationship_evidence', 'amount_raw', 'amount_numeric', 'amount_unit', 'amount_type', 'currency', 'note')} for r in related]}))
        for section, category in [('materials', '采购品类'), ('scale', '采购规模'), ('plans', '建设采购计划')]:
            for item in hp[section]:
                evidence_ids = re.findall(r'E\d+', item.get('evidence', ''))
                entries = [evidence[e] for e in evidence_ids]
                refs = [hp_sources[e['source']] for e in entries]
                if section == 'plans':
                    buyer_name = re.sub(r'（全资子公司）$', '', item['buyer'])
                    buyer = h['companies'].get(buyer_name) or ensure_company(db, buyer_name, origin='historical_snapshot', visibility='related')
                    key = stable_key('hanon-plan', buyer.id, item['id'])
                    if not db.scalar(select(ProcurementProject.id).where(ProcurementProject.unique_key == key)):
                        db.add(ProcurementProject(unique_key=key, buyer_id=buyer.id, title=item['product'], record_kind='plan',
                            stage=item['stage'], published_at=hp['end'], payload={**item, 'record_type': 'investment_plan'},
                            source_ids=refs, quote='\n'.join(e['quote'] for e in entries)))
                    plan = db.scalar(select(ProcurementProject).where(ProcurementProject.unique_key == key))
                    for entry in entries:
                        plan.payload = append_citations(plan.payload, hp_sources[entry['source']], {'value': entry['quote']})
                else:
                    f = {'field': item.get('metric') or item['product'], 'value': item.get('value') if section == 'scale' else item['product'],
                        'unit': item.get('unit') or '', 'as_of': item.get('period') or hp['end'], 'category': category,
                        'source_ids': [e['source'] for e in entries], 'evidence_quote': '\n'.join(e['quote'] for e in entries),
                        'evidence_entries': [{'source_id': e['source'], 'quote': e['quote']} for e in entries],
                        'note': item.get('note', '') + ('；' + item['frequency'] if section == 'materials' else ''),
                        'entity_scope': '集团经营模式' if section == 'materials' else '原披露口径', 'raw_id': item['id']}
                    import_fact(db, h['main'], 'hanon-procurement-20261008', f, hp_sources)
        for item in hp['behaviors']:
            refs = re.findall(r'E\d+', item[3])
            if not refs: continue
            entries = [evidence[e] for e in refs]
            f = {'field': item[0], 'value': item[1], 'category': '采购特征', 'as_of': hp['end'],
                'source_ids': [e['source'] for e in entries], 'evidence_quote': '\n'.join(e['quote'] for e in entries),
                'evidence_entries': [{'source_id': e['source'], 'quote': e['quote']} for e in entries],
                'note': item[4], 'entity_scope': '披露经营规则', 'raw_id': item[0]}
            import_fact(db, h['main'], 'hanon-procurement-20261008', f, hp_sources)
        h['main'].metadata_json = {'coverage': hp['coverage'], 'gaps': ['本轮未找到可核验的企业自身直接招采公告', '具体采购型号、数量、单价和复购频次未公开', '建设采购计划未确认绝对采购日期及成交状态'], 'research_window': [hp['start'], hp['end']], **(h['main'].metadata_json or {})}
        # 这四个已审阅项目是确认图片中的首屏选择；只存真实ID，完整项目集合仍可展开。
        featured = [project_ids[number] for number in ('SZ-05-04A-2026-D-F-E23512', 'SZ-05-04A-2026-D-F-E23492', 'SZ-05-04A-2026-D-F-E10658', 'SZ-05-04A-2026-D-F-E17466') if number in project_ids]
        b['main'].metadata_json = {'gaps': ['需求量不是已购数量', '候选报价不是最终成交', '预算原文未明确币种', '不能由单年项目推算复购概率'], 'research_window': [byd['period_start'], byd['period_end']], 'featured_project_ids': featured, **(b['main'].metadata_json or {})}
        for bundle in (h, b):
            members = [bundle['main']] + [c for c in bundle['companies'].values() if c.visibility == 'primary' and c.id != bundle['main'].id]
            for position, company in enumerate(members):
                key = stable_key(bundle['conversation_id'], company.id)
                if not db.scalar(select(ResearchCompany.id).where(ResearchCompany.unique_key == key)):
                    db.add(ResearchCompany(unique_key=key, company_id=company.id, conversation_id=bundle['conversation_id'],
                        job_id=None, position=position, origin='historical_snapshot'))
        db.flush()
        for company in db.scalars(select(Company)):
            bind_company_sources(db, company.id)
        result = {'company_ids': [h['main'].id, b['main'].id], 'conversation_ids': [h['conversation_id'], b['conversation_id']],
                  'origin': 'historical_snapshot', 'imported_at': now()}
        state = db.get(Setting, 'history_import')
        if state: state.value = result
        else: db.add(Setting(key='history_import', value=result))
    return result
