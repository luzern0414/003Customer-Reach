"""招投标页面解析：只按原文标签判定采购人、中标人与候选人，遮挡或缺失的字段保持为空。"""
import re

# 机构名：非贪婪匹配到第一个机构后缀，避免把标题后续内容并入名称。
ORG = r'[一-龥A-Za-z0-9（）()·]{2,40}?(?:有限责任公司|股份有限公司|有限公司|集团公司|研究院|研究所|大学|学院|医院|中心|广播电视台|电视台|局|公司|集团|厂|五二三台)'
ORG_RE = re.compile(ORG)
AGENCY_RE = re.compile(r'招标代理|招标有限|招标集团|招标股份|招标中心|项目管理|工程管理|造价咨询|工程咨询|咨询集团|咨询有限|采购代理|交易中心|采购中心')
BUYER_LABEL = r'(?:采购人|采购单位|采购企业|招标人|招标单位|询价单位|询价企业|建设单位|业主单位|采购方|需求单位|发布单位)(?:名称|信息)?\s*[:：]\s*'
WINNER_LABEL = (r'(?:确定成交结果单位|成交结果单位|中标（成交）供应商|中标\(成交\)供应商|中标\(成交\)人|中标供应商|成交供应商|'
                r'中标人|中标单位|成交单位|成交人|中选人|中选单位|供应商名称)(?:名称)?\s*[:：]\s*')
CANDIDATE_LABEL = r'(?:第[一二三四五1-5](?:中标|成交)?候选人|(?:中标|成交)候选人)(?:名称)?\s*(?:为)?\s*[:：]?\s*'
AGENCY_LABEL = r'(?:采购代理机构|招标代理机构|代理机构)(?:名称)?\s*[:：]\s*'
AMOUNT_RE = re.compile(r'(?:确定成交报价|中标（成交）金额|中标\(成交\)金额|中标金额|成交金额|中标价|成交价|成交报价|合同金额)\s*[:：]\s*([^\n，。；|]{1,40})')
BUDGET_RE = re.compile(r'(?:预算金额|采购预算|项目预算|最高限价|控制价)\s*[:：]\s*([^\n，。；|]{1,40})')
NUMBER_RE = re.compile(r'(?:项目编号|招标编号|采购编号|询价单编号|项目代码)\s*[:：]\s*([A-Za-z0-9\-_/〔〕\[\]（）()]{4,60})')
DATE_RE = re.compile(r'(20\d{2})[-年./](\d{1,2})[-月./](\d{1,2})')
MASK_RE = re.compile(r'\*{3,}|点击查看|登录查看|会员')
STOP_LINE = re.compile(r'咨询热线|联系人|查看更多|客服电话|版权所有|^#|^\|')


def compact(value: str) -> str:
    """value为任意文本；去除空白后用于主体包含比较，不做相似名合并。"""
    return re.sub(r'\s+', '', value or '')


def clean_name(value: str) -> str:
    """value为表格或标签后的原始名称；去掉序号、遮挡与空白，非机构名返回空串。"""
    value = re.sub(r'^\s*\d+\s+', '', value or '').strip().strip('*').strip()
    if not value or MASK_RE.search(value): return ''
    found = re.fullmatch(r'[一-龥A-Za-z0-9（）()·]{2,60}', value)
    return value if found else ''


def normalize_date(value: str) -> str:
    """value为原文日期片段；返回YYYY-MM-DD，无法识别返回空串，不补当前日期。"""
    found = DATE_RE.search(value or '')
    return f'{found.group(1)}-{int(found.group(2)):02d}-{int(found.group(3)):02d}' if found else ''


def _label_orgs(text: str, label: str, limit: int = 6) -> list[tuple[str, str]]:
    """text为正文、label为标签正则；返回(机构名, 所在原文行)，遮挡值跳过。"""
    result = []
    for found in re.finditer(label + '(' + ORG + ')', text):
        name = clean_name(found.group(1))
        if name and name not in [x[0] for x in result]:
            start = text.rfind('\n', 0, found.start()) + 1
            end = text.find('\n', found.end())
            result.append((name, text[start:end if end > 0 else len(text)].strip()[:300]))
        if len(result) >= limit: break
    return result


def parse_items(text: str, limit: int = 30) -> list[dict]:
    """text为公告正文；识别含名称与数量列的清单表，返回物资名称/规格/数量/单位，未知列留空。"""
    lines = text.splitlines()
    items = []
    header = None
    for line in lines:
        stripped = line.strip()
        cells = [c.strip() for c in stripped.strip('|').split('|')] if stripped.startswith('|') else None
        if cells is None:
            tokens = stripped.split()
            if len(tokens) >= 4 and any(re.search('名称|采购内容|标的', t) for t in tokens) and any('数量' in t for t in tokens):
                header = tokens
            continue
        if all(re.fullmatch(r':?-{2,}:?', c) for c in cells if c): continue
        if any(re.search('名称|采购内容|标的', c) for c in cells) and any('数量' in c for c in cells):
            header = cells; continue
        if not header or len(cells) != len(header): continue
        row = dict(zip(header, cells))
        name_key = next((h for h in header if re.search('物资名称|货物名称|产品名称|标的名称|采购内容|名称', h)), '')
        name = row.get(name_key, '').strip()
        if not name or name in {'-', '/'}: continue
        spec_key = next((h for h in header if re.search('规格|型号|技术参数|参数', h)), '')
        qty_key = next((h for h in header if '数量' in h), '')
        unit_key = next((h for h in header if h == '单位' or h.endswith('单位') and '采购' not in h), '')
        quantity = row.get(qty_key, '').strip()
        items.append({'name': name[:80], 'spec': row.get(spec_key, '').strip()[:160] if spec_key else '',
                      'quantity': quantity if quantity not in {'-', '/'} else '', 'unit': row.get(unit_key, '').strip()[:10] if unit_key else ''})
        if len(items) >= limit: break
    return items


def parse_detail(text: str, company: str, title: str = '') -> dict:
    """text为已读公告正文、company为完整目标名；按标签返回角色与对手方，无法确认时role=mentioned。"""
    body = text or ''
    target = compact(company)
    buyers = _label_orgs(body, BUYER_LABEL, 3)
    # 平台详情页常把采购企业遮挡，但在“招标详情”标题下直接列出发布企业。
    header = re.search(r'招标详情\s*\n+\s*(' + ORG + r')\s*\n', body)
    if header and not buyers and clean_name(header.group(1)):
        buyers = [(clean_name(header.group(1)), header.group(0).strip()[:300])]
    winners = _label_orgs(body, WINNER_LABEL, 6)
    candidates = _label_orgs(body, CANDIDATE_LABEL, 8)
    table_winners, table_candidates, table_number = vertical_parties(body)
    def table_quote(name):
        # 表格引文取“序号”表头到该名称的连续原文，保留列名与取值的对应关系。
        end = body.find(name)
        if end < 0: return name
        head = body.rfind('序号', 0, end)
        return body[head if head >= 0 and end - head < 600 else max(0, end - 200):end + len(name)].strip()
    for name in table_winners:
        if name not in [n for n, _ in winners]: winners.append((name, table_quote(name)))
    for name in table_candidates:
        if name not in [n for n, _ in candidates]: candidates.append((name, table_quote(name)))
    agencies = _label_orgs(body, AGENCY_LABEL, 2)
    buyer = next((name for name, _ in buyers if not AGENCY_RE.search(name)), '')
    agency = agencies[0][0] if agencies else next((name for name, _ in buyers if AGENCY_RE.search(name)), '')
    is_candidate_notice = bool(re.search('候选人', title + body[:300])) and not re.search('结果公告|成交公告|中标公告', title)
    role, quote = 'mentioned', ''
    if buyer and target in compact(buyer):
        role, quote = 'buyer', next(line for name, line in buyers if name == buyer)
    elif any(target in compact(name) for name, _ in winners):
        role = 'candidate' if is_candidate_notice else 'winner'
        quote = next(line for name, line in winners if target in compact(name))
    elif any(target in compact(name) for name, _ in candidates):
        role, quote = 'candidate', next(line for name, line in candidates if target in compact(name))
    elif agency and target in compact(agency):
        role, quote = 'agency', next((line for name, line in agencies if name == agency), '')
    elif title and compact(title).startswith(target) and re.search('采购|询价|招标|比选|竞价|磋商|谈判|遴选', title[len(company):]) and not re.search('中标|成交|候选|提示性', title):
        role, quote, buyer = 'buyer', title, company
    elif title and re.match(re.escape(company) + r'\s*中标', title):
        role, quote = 'winner', title
    if role == 'mentioned' and target in compact(body):
        index = body.find(company)
        quote = body[max(0, index - 80):index + len(company) + 80].strip() if index >= 0 else ''
    amount = AMOUNT_RE.search(body)
    budget = BUDGET_RE.search(body)
    number = NUMBER_RE.search(body)
    published = ''
    for pattern in (r'(?:发布时间|发布日期|公告日期|询价时间|Published)\s*[:：]?\s*([^\n]{8,24})',):
        found = re.search(pattern, body)
        if found: published = normalize_date(found.group(1))
    if not buyer and role == 'winner' and title:
        # “某公司中标某单位……采购”标题只在标签缺失时提供采购人线索。
        after = re.match(re.escape(company) + r'\s*中标\s*(' + ORG + ')', title)
        if after: buyer = clean_name(after.group(1))
    return {'role': role, 'quote': quote[:600], 'buyer': buyer, 'winners': [n for n, _ in winners if target not in compact(n)] if role != 'winner' else [n for n, _ in winners],
            'candidates': [n for n, _ in candidates], 'agency': agency,
            'amount': amount.group(1).strip() if amount and not MASK_RE.search(amount.group(1)) else '',
            'budget': budget.group(1).strip() if budget and not MASK_RE.search(budget.group(1)) else '',
            'project_number': number.group(1) if number and not MASK_RE.search(number.group(1)) else table_number,
            'published_at': published, 'items': parse_items(body)}


def candidate_context(text: str, company: str, limit: int = 12) -> dict:
    """提取具名候选人的报价与业绩披露；合并单元格只在同一完整表头下继承主体。

    历史合同为本公告的业绩披露，不授予客户、供应商或当前成交关系。
    每条引文保持连续原文，续行引文含最近具名主体行。
    """
    result = {'bid': {}, 'disclosed_performance': []}
    header, owner, anchor, header_start, position = [], '', 0, 0, 0
    for raw in (text or '').splitlines(keepends=True):
        start, position = position, position + len(raw)
        line = raw.strip()
        if not line.startswith('|'):
            header, owner = [], ''
            continue
        cells = [c.strip() for c in line.strip('|').split('|')]
        if all(re.fullmatch(r':?-{2,}:?', c) for c in cells if c): continue
        if '中标候选人名称' in cells:
            header, owner = cells, ''
            header_start = start
            continue
        if not header: continue
        name_col = header.index('中标候选人名称')
        if len(cells) == len(header):
            if cells[name_col]:
                owner, anchor = compact(cells[name_col]), start
            row = dict(zip(header, cells))
        elif (len(cells) == len(header) - name_col - 1 and owner
              and cells[0] == '中标候选人业绩' and '类似业绩名称' in header):
            row = dict(zip(header[name_col + 1:], cells))
        else:
            owner = ''
            continue
        if owner != compact(company): continue
        quote = text[anchor:position].strip()
        if len(quote) > 2500: continue
        if '投标报价（元）' in header and not result['bid']:
            price = row.get('投标报价（元）', '')
            if re.fullmatch(r'[\d,]+(?:\.\d+)?', price):
                result['bid'] = {'rank': row.get('中标候选人排序', ''), 'price': price, 'unit': '元',
                                 'quote': text[header_start:position].strip()}
        if '类似业绩名称' in header and row.get('分类') == '中标候选人业绩' and len(result['disclosed_performance']) < limit:
            title = row.get('类似业绩名称', '')
            if title and not MASK_RE.search(title):
                result['disclosed_performance'].append({'title': title, 'signed_at': row.get('合同签订时间', ''),
                    'contract_amount': row.get('合同价格', ''), 'quote': quote, 'basis': '候选人业绩披露'})
    return result


def title_buyer(title: str) -> str:
    """title为中标/候选公告标题；返回标题开头的采购机构名，开头不是机构时返回空串。"""
    head = re.sub(r'^[【\[].*?[】\]]', '', title or '').strip()
    found = re.match(ORG, head)
    return clean_name(found.group(0)) if found else ''


def parse_listing(text: str) -> list[dict]:
    """text为平台企业主页的公告列表；返回标题及紧随其后的日期，导航/联系人区不进入结果。"""
    rows, started, headings = [], False, set()
    for raw in (text or '').splitlines():
        line = raw.strip()
        if not line: continue
        if line.startswith('#') and re.search('招标公告|中标公告|招中标动态|采购公告', line):
            started = True; rows.clear(); headings.add(line.lstrip('#').strip()); continue
        if not started: continue
        if line.startswith('## ') or re.search('^联系人|查看更多', line): break
        if STOP_LINE.search(line) or re.match(r'(?:URL|Published):', line) or line in headings: continue
        if re.fullmatch(r'20\d{2}-\d{2}-\d{2}', line):
            if rows and not rows[-1]['published_at']: rows[-1]['published_at'] = line
            continue
        if 2 <= len(line) <= 160: rows.append({'title': line, 'published_at': ''})
    seen, result = set(), []
    for row in rows:
        if row['title'] in seen: continue
        seen.add(row['title']); result.append(row)
    return result


def parse_partners(text: str) -> dict:
    """text为平台“合作单位/竞争对手”页；返回合作乙方(供应商)、合作甲方(客户)与共同竞标公司(竞争对手)名称及次数。"""
    result = {'supplier': [], 'customer': [], 'competitor': []}
    kind = ''
    for raw in (text or '').splitlines():
        line = raw.strip()
        if not line.startswith('|'):
            continue
        cells = [c.strip() for c in line.strip('|').split('|')]
        if any('合作乙方' in c for c in cells): kind = 'supplier'; continue
        if any('合作甲方' in c for c in cells): kind = 'customer'; continue
        if any('共同竞标' in c for c in cells): kind = 'competitor'; continue
        # “潜在竞争对手”是行业中标排行，并非与本企业同场竞标，不作为竞争对手。
        if any('潜在竞争' in c for c in cells): kind = ''; continue
        if not kind or all(re.fullmatch(r':?-{2,}:?', c) for c in cells if c) or len(cells) < 2: continue
        name = clean_name(cells[0])
        count = re.search(r'\d+', cells[1])
        if name and count: result[kind].append({'name': name, 'count': int(count.group(0)), 'line': line[:200]})
    return result


def parse_supplier_table(text: str) -> list[dict]:
    """text为第三方“供应商列表”页；只读取表头含供应商名称的表格行，返回名称与原文行。"""
    result, active = [], False
    for raw in (text or '').splitlines():
        line = raw.strip()
        if not line.startswith('|'):
            if active and line: active = False
            continue
        cells = [c.strip() for c in line.strip('|').split('|')]
        if any(re.search('供应商(?:企业)?名称', c) for c in cells): active = True; continue
        if not active or all(re.fullmatch(r':?-{2,}:?', c) for c in cells if c) or len(cells) < 2: continue
        name = clean_name(cells[1] if re.fullmatch(r'\d+', cells[0]) else cells[0])
        if name and ORG_RE.fullmatch(name): result.append({'name': name, 'line': line[:200]})
    return result


def parse_win_table(text: str, company: str) -> list[dict]:
    """text为中标业绩汇总页；读取“目标企业中标……”表格行，返回项目、地区、金额范围与采购方线索。"""
    result, target = [], compact(company)
    for raw in (text or '').splitlines():
        line = raw.strip()
        if not line.startswith('|'): continue
        cells = [c.strip() for c in line.strip('|').split('|')]
        index = next((i for i, c in enumerate(cells) if compact(c).startswith(target + '中标')), -1)
        if index < 0: continue
        title = cells[index]
        rest = title[title.find('中标') + 2:]
        result.append({'title': title[:300], 'region': cells[index + 1] if len(cells) > index + 1 else '',
                       'amount': cells[-1] if len(cells) > index + 2 and re.search(r'万|元', cells[-1]) else '',
                       'buyer': title_buyer(rest), 'line': line[:300]})
    return result


VERTICAL_WINNER = re.compile(r'^(?:中选人|中标人|中标单位|成交人|成交单位|成交供应商|中标供应商|中标（成交）供应商|中选单位|供应商名称)$')
VERTICAL_CANDIDATE = re.compile(r'^(?:(?:中标|成交)?候选人(?:名称)?|投标人(?:名称)?|供应商)$')


def vertical_table(text: str) -> list[dict]:
    """text为正文；识别“表头逐行、数据逐行”的纵向表格（表头3–8列且均为短标签），返回行字典列表。"""
    lines = [line.strip() for line in (text or '').splitlines() if line.strip()]
    rows = []
    for start in range(len(lines)):
        for width in range(8, 2, -1):
            header = lines[start:start + width]
            if len(header) < width or header[0] not in {'序号', '排名', '名次'}: continue
            if not all(len(h) <= 12 and not re.search(r'\d', h) for h in header): continue
            if not any(VERTICAL_WINNER.match(h) or VERTICAL_CANDIDATE.match(h) for h in header): continue
            cursor = start + width
            while cursor + width <= len(lines) and re.fullmatch(r'\d{1,2}', lines[cursor]):
                rows.append(dict(zip(header, lines[cursor:cursor + width])))
                cursor += width
            if rows: return rows
    return rows


def vertical_parties(text: str) -> tuple[list[str], list[str], str]:
    """text为正文；从纵向表格、Markdown表格与“: 单元格”块表格取中标/中选人与候选人名称及项目编号，遮挡值跳过。"""
    winners, candidates, number = [], [], ''
    rows = list(vertical_table(text))
    for table in text_tables(text):
        if any(VERTICAL_WINNER.match(h) or VERTICAL_CANDIDATE.match(h) for h in table['header']): rows.extend(table['rows'])
    for row in rows:
        for key, value in row.items():
            name = clean_name(value)
            if VERTICAL_WINNER.match(key) and name: winners.append(name)
            elif VERTICAL_CANDIDATE.match(key) and name: candidates.append(name)
            elif key == '项目编号' and not MASK_RE.search(value): number = number or value
    return list(dict.fromkeys(winners)), list(dict.fromkeys(candidates)), number


def text_tables(text: str) -> list[dict]:
    """text为正文；识别Markdown“| a | b |”表格与Exa“: 单元格”纵向块表格，返回[{header, rows}]，行按表头映射。"""
    tables, lines = [], (text or '').splitlines()
    # Markdown表：首行为表头，分隔行跳过，后续同宽行为数据。
    block = []
    for line in [*lines, '']:
        if line.strip().startswith('|'): block.append([c.strip() for c in line.strip().strip('|').split('|')]); continue
        if len(block) >= 2:
            header, rows = block[0], [r for r in block[1:] if not all(re.fullmatch(r':?-{2,}:?', c) for c in r if c)]
            tables.append({'header': header, 'rows': [dict(zip(header, r)) for r in rows if len(r) == len(header)]})
        block = []
    # 纵向块表：以“: ”开头的连续行为一组，组间空行分隔；首组为表头，同长度后续组为数据行。
    groups, current = [], []
    for line in [*lines, '']:
        stripped = line.strip()
        if stripped.startswith(': ') or stripped == ':': current.append(stripped[2:].strip()); continue
        if stripped: 
            if current: groups.append(current); current = []
            groups.append(None)
            continue
        if current: groups.append(current); current = []
    index = 0
    while index < len(groups):
        header = groups[index]
        if header and len(header) >= 2 and not re.fullmatch(r'\d+', header[0]):
            rows, cursor = [], index + 1
            while cursor < len(groups) and groups[cursor] and len(groups[cursor]) == len(header):
                rows.append(dict(zip(header, groups[cursor]))); cursor += 1
            if rows: tables.append({'header': header, 'rows': rows}); index = cursor; continue
        index += 1
    return tables


def parse_owner_page(text: str, company: str) -> dict:
    """text为建设通“业主”页；返回常合作供应商（次数/累计金额/最近合作）与历史发包记录（项目/中标企业/时间）。"""
    suppliers, projects = [], []
    for table in text_tables(text):
        header = ' '.join(table['header'])
        if '供应商名称' in header:
            for row in table['rows']:
                name = clean_name(row.get('供应商名称', ''))
                if name: suppliers.append({'name': name, 'count': int(re.sub(r'\D', '', row.get('合作次数', '')) or 0),
                                           'amount': row.get('累计总金额（万）', ''), 'latest_at': normalize_date(row.get('最新合作时间', '')),
                                           'line': ' | '.join(row.values())[:300]})
        elif '项目名称' in header and '中标企业' in header:
            for row in table['rows']:
                title = row.get('项目名称', '').strip()
                if not title or title in {'-', '--'}: continue
                projects.append({'title': title, 'published_at': normalize_date(row.get('发包时间', '') or row.get('发布时间', '')),
                                 'winner': clean_name(row.get('中标企业', '')), 'region': row.get('省份', '') or row.get('所在地', ''),
                                 'line': ' | '.join(row.values())[:300]})
    return {'suppliers': suppliers, 'projects': projects}


def parse_info_pairs(text: str) -> dict:
    """text为工商信息片段；从“标签 | 值 | 标签 | 值”表格行或“标签：值”行取工商字段，“--”与遮挡值不取。"""
    labels = ['法定代表人', '法人', '经营状态', '成立时间', '成立日期', '注册资本', '注册资本金', '统一信用代码', '统一社会信用代码', '企业类型',
              '行业', '登记机关', '详细地址', '注册地址', '企业地址', '企业官网', '联系方式', '邮箱', '经营范围', '营业期限', '经营期限']
    result = {}
    for line in (text or '').splitlines():
        stripped = line.strip()
        if stripped.startswith('|'):
            cells = [c.strip() for c in stripped.strip('|').split('|')]
            for i in range(0, len(cells) - 1, 2):
                if cells[i] in labels and cells[i + 1] and cells[i + 1] not in {'--', '-'} and not MASK_RE.search(cells[i + 1]) and '...' not in cells[i + 1]:
                    result.setdefault(cells[i], cells[i + 1][:600])
        else:
            for label, value in re.findall(r'(' + '|'.join(labels) + r')[：:]\s*([^：:]+?)(?=\s+(?:' + '|'.join(labels) + r')[：:]|$)', stripped):
                value = value.strip()
                if value and value not in {'--', '-'} and not MASK_RE.search(value) and '...' not in value: result.setdefault(label, value[:600])
    return result


def parse_shuidi(text: str, company: str) -> list[dict]:
    """text为水滴标讯企业招投标页；按“标题/发布时间/单位角色”三行块返回记录，中标块可带“招采单位：”采购方。"""
    lines = [line.strip() for line in (text or '').splitlines() if line.strip()]
    records = []
    for index, line in enumerate(lines):
        if not line.startswith('发布时间') or index == 0: continue
        title, date = lines[index - 1], normalize_date(line)
        role_line = lines[index + 1] if index + 1 < len(lines) else ''
        role = 'buyer' if role_line.startswith('招采单位') else 'winner' if role_line.startswith('中标单位') else ''
        if not role or len(title) < 4: continue
        budget = re.search(r'预算金额\s*([\d.,]+\s*[万亿]?元)', role_line)
        buyer = ''
        if role == 'winner' and index + 2 < len(lines) and lines[index + 2].startswith('招采单位'):
            buyer = clean_name(re.sub(r'^招采单位[：:]\s*', '', lines[index + 2]))
        records.append({'title': title, 'published_at': date, 'role': role, 'budget': budget.group(1) if budget else '',
                        'buyer': company if role == 'buyer' else buyer, 'notice_type': re.sub(r'^(招采单位|中标单位)\s*|预算金额.*$', '', role_line).strip(),
                        'line': '\n'.join(lines[index - 1:index + (3 if buyer else 2)])})
    return records


def title_key(title: str, company: str = '') -> str:
    """title为公告标题、company为目标企业；去掉企业名前缀、类别标记、括注、标点与公告后缀，跨平台同一公告得到相同键。"""
    value = re.sub(r'[（(]原标题.*?[)）]|【.*?】|\s+', '', title or '')
    value = re.sub(r'[-_|]?(千里马招标网|乙方宝官网|乙方宝|招标网)$', '', value)
    if company: value = value.replace(re.sub(r'\s+', '', company), '', 1) if value.startswith(re.sub(r'\s+', '', company)) else value
    value = re.sub(r'^(关于)?(采购|购买)?', '', value)
    value = re.sub(r'(的)?(招标公告|采购公告|询价单|询价公告|询比价公告|中标结果公告|结果公告|中标公告|成交公告|招标|采购)$', '', value)
    return re.sub(r'[^\w一-龥]', '', value)[:120]
