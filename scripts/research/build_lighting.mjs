/** 将 AI 已引用的事实与评估导出成可追溯 Excel，不生成任何缺失业务值。 */
import fs from 'node:fs/promises';
import path from 'node:path';
import { Workbook, SpreadsheetFile } from '@oai/artifact-tool';

const [input, output, archive] = process.argv.slice(2);
if (!input || !output) throw new Error('Usage: node build_lighting.mjs dataset.json output.xlsx [archive-dir]');
const data = JSON.parse(await fs.readFile(input, 'utf8'));
const sources = new Map(data.sources.map(s => [s.id, s]));
const facts = new Map(data.facts.map(f => [`${f.entity_id}:${f.field}`, f]));
const missing = '未找到公开数据';
const previews = path.resolve('.codex-tmp/lighting-previews');
await fs.mkdir(previews, { recursive: true });
await fs.mkdir(path.dirname(path.resolve(output)), { recursive: true });
if (await fs.stat(output).then(() => true).catch(() => false)) throw new Error('Output already exists; do not overwrite a delivered workbook');
const snapshots = new Map();
if (archive) {
  for (const s of data.sources) {
    const saved = await fs.readFile(path.join(archive, `${s.id}.json`), 'utf8').catch(() => null);
    if (saved) snapshots.set(s.id, JSON.parse(saved));
  }
}
const compact = text => String(text ?? '').replace(/\s+/g, '');
const fact = (id, field) => facts.get(`${id}:${field}`);
const value = (id, field) => fact(id, field)?.value ?? missing;
const qualifier = (id, field) => fact(id, field)?.qualifier ?? fact(id, field)?.missing_reason ?? '';
const entitySources = id => [...new Set(data.facts.filter(f => f.entity_id === id).flatMap(f => (f.evidence ?? []).map(e => e.source_id)))];
const snapshotStatus = id => {
  const raw = snapshots.get(id);
  return raw?.status === 'ok' ? '正文归档成功（不代表字段全部匹配）'
    : raw?.status === 'provider_error' ? '回源地址不支持；保留搜索摘录'
    : raw?.status === 'transport_error' ? '服务429限流；主线程复核未完成'
    : sources.get(id)?.fetch_policy === 'search_only' ? '仅公开搜索摘录，不访问受限页面'
    : '子任务曾读取/检索；主线程复核因限流未完成';
};
const matched = (sid, quote) => snapshots.get(sid)?.status === 'ok'
  && compact(snapshots.get(sid).text).includes(compact(quote));
const book = Workbook.create();
const sheets = new Map();
// 先创建全部引用目标，避免写公式时出现临时缺失 sheetId 的警告。
for (const name of ['客户优先级', '客户信息', '灯具与价格', '采购参考', '证据与来源']) {
  sheets.set(name, book.worksheets.add(name));
}
const bodyFont = { name: 'Arial', size: 10, color: '#202A30' };
const metadata = `资料日期 ${data.as_of}；近12月 ${data.recent_start} 至 ${data.recent_end}；未知不估算`;

/** 创建表格；rows 仅允许来源值或明确标注的分析，widths 单位像素。 */
function addSheet(name, title, headers, rows, widths, tableName, headerRow = 6) {
  const sheet = sheets.get(name) ?? book.worksheets.add(name);
  sheets.set(name, sheet);
  sheet.showGridLines = false;
  const endCol = column(headers.length);
  const endRow = headerRow + rows.length;
  const area = sheet.getRange(`A${headerRow}:${endCol}${endRow}`);
  area.values = [headers, ...rows];
  area.format.font = bodyFont;
  area.format.verticalAlignment = 'center';
  area.format.wrapText = true;
  sheet.getRange('A2').values = [[title]];
  sheet.getRange('A2').format.font = { ...bodyFont, size: 14, bold: true };
  sheet.getRange(`A2:${endCol}2`).format.borders = { bottom: { style: 'thin', color: '#B6C3C0' } };
  sheet.getRange('A3').values = [[metadata]];
  sheet.getRange('A3').format.font = { ...bodyFont, color: '#627078' };
  sheet.getRange('A3').format.wrapText = false;
  const table = sheet.tables.add(`A${headerRow}:${endCol}${endRow}`, true, tableName);
  table.style = 'TableStyleLight1';
  table.showFilterButton = true;
  sheet.getRange(`A${headerRow}:${endCol}${headerRow}`).format = {
    fill: '#274E47', font: { ...bodyFont, bold: true, color: '#FFFFFF' },
    horizontalAlignment: 'center', verticalAlignment: 'center', wrapText: true, rowHeight: 36,
  };
  widths.forEach((width, i) => sheet.getRange(`${column(i + 1)}${headerRow}:${column(i + 1)}${endRow}`).format.columnWidthPx = width);
  rows.forEach((row, r) => {
    // 用中文字符宽度近似计算行高，避免为长证据缩小字体或截断正文。
    const lines = Math.max(...row.map((v, c) => {
      const text = v instanceof Date ? '2026-09-30 17:00:00' : String(v ?? '');
      return Math.max(...text.split('\n').map(line => Math.ceil(
        [...line].reduce((n, ch) => n + (/[^\x00-\x7F]/.test(ch) ? 11 : 6), 0) / (widths[c] - 14))));
    }), 1);
    const range = sheet.getRange(`A${headerRow + r + 1}:${endCol}${headerRow + r + 1}`);
    range.format.rowHeightPx = Math.max(34, lines * 17 + 12);
    if (r % 2 === 1) range.format.fill = '#F2F5F5';
  });
  sheet.freezePanes.freezeRows(headerRow);
  sheet.freezePanes.freezeColumns(Math.min(2, headers.length));
  return sheet;
}

/** 将正整数列数转换为 Excel 列标；非正整数不允许传入。 */
function column(n) {
  let result = '';
  while (n > 0) { n -= 1; result = String.fromCharCode(65 + n % 26) + result; n = Math.floor(n / 26); }
  return result;
}

const sorted = [...data.entities].sort((a, b) => a.priority - b.priority);
const rank = addSheet('客户优先级', '深圳灯具获客：研究优先级',
  ['顺序', '网点/线索名称', '区', '主体角色', '优先级性质', '业务号码（原文）', '公开经营品类', '排序理由（AI评估）', '建议下一步（非确认需求）', '营业/资料时效', '研究分组'],
  sorted.map(e => [e.priority, e.name, e.district, e.role, e.tier, value(e.id, 'phone'), value(e.id, 'categories'), e.reason, e.approach, e.operating_status, e.group_id]),
  [55, 240, 70, 170, 235, 220, 300, 380, 380, 340, 165], 'LeadPriorities');
rank.tabColor = '#274E47';
rank.getRange('A4:J4').values = [['网点/线索数', null, '', '官网零售价条目', null, '', '本轮找到目标订单', 0, '研究分组', new Set(sorted.map(e => e.group_id)).size]];
rank.getRange('B4').formulas = [[`=COUNTA('客户信息'!A7:A${6 + sorted.length})`]];
rank.getRange('E4').formulas = [[`=COUNT('灯具与价格'!F7:F${6 + data.products.length})`]];
rank.getRange('A4:J4').format.font = { ...bodyFont, bold: true };
const gapStart = 29;
rank.getRange(`B${gapStart}`).values = [['解读与缺口']];
data.gaps.forEach((text, i) => {
  rank.getRange(`B${gapStart + i + 1}:H${gapStart + i + 1}`).merge();
  rank.getRange(`B${gapStart + i + 1}`).values = [[text]];
  rank.getRange(`B${gapStart + i + 1}:H${gapStart + i + 1}`).format = { font: bodyFont, wrapText: true, rowHeight: 32 };
});

const detail = addSheet('客户信息', '客户主体与公开事实',
  ['客户ID', '名称', '城市', '区', '角色', '行业（经营品类归类）', '公开经营主体', '地址', '业务电话原文', '电话用途/限制', '公开业务邮箱', '主营/品类', '品牌与关系', '具体型号', '规模参考（非员工）', '员工人数', '员工统计日期/口径', '年营收（元）', '营收年度/主体口径', '最近采购', '主要供货公司', '实际采购单价', '补货频次', '官方业务页', '来源ID', '营业/资料时效'],
  sorted.map(e => {
    const industry = e.id === 'C20' ? '照明特种光源经销（非工商行业码）' : e.group_id === 'IKEA_SZ' ? '家居零售/设计服务（经营归类）' : e.role.includes('灯') ? '灯具/灯饰销售（经营归类）' : '家居建材卖场（经营归类）';
    const official = { C01: 'S01', C06: 'S14', C07: 'S11', C08: 'S13', C09: 'S12', C10: 'S12', C11: 'S12', C12: 'S12', C13: 'S12', C17: 'S03', C18: 'S02', C19: 'S02' }[e.id];
    return [e.id, e.name, '深圳', e.district, e.role, industry, value(e.id, 'legal_entity'), value(e.id, 'address'), value(e.id, 'phone'), qualifier(e.id, 'phone'), value(e.id, 'email'), value(e.id, 'categories'), value(e.id, 'brand_relation'), value(e.id, 'models'), value(e.id, 'scale'), missing, '未取得适用本主体的数据', missing, '未取得适用本主体及年度的数据', '近12月未找到公开订单，不代表没有采购', missing, '未取得成交明细；不使用零售价代替', '未取得多笔独立订单，不推断月/季/年频次', official ? sources.get(official).url : '未找到官方业务页', entitySources(e.id).join(', '), e.operating_status];
  }),
  [80, 240, 75, 75, 170, 265, 270, 340, 220, 370, 255, 310, 265, 220, 300, 160, 220, 160, 260, 300, 180, 285, 315, 420, 145, 345], 'BuyerFacts');
detail.getRange('I7:I26').setNumberFormat('@');

const products = addSheet('灯具与价格', '具体灯具：规格与公开价格',
  ['产品ID', '品牌', '商品名称', '型号/货号', '类型', '公开现价（元）', '价格性质', '实际功率（W）', '最大允许功率（W）', '色温（K）', '尺寸', '材质', '场景', '税运/安装条件', 'MOQ', '规格与现售限制', '来源ID', '旧参考价（元）'],
  data.products.map(p => [p.id, p.brand, p.name, p.model ?? missing, p.category, p.price ?? missing, p.price_kind, p.power_w ?? missing, p.max_power_w ?? '不适用/未披露', p.cct_k ?? missing, p.size ?? missing, p.material ?? missing, p.application ?? missing, p.tax_delivery_installation, p.moq ?? missing, p.status, p.source_id, p.historical_price ?? '不适用']),
  [80, 100, 235, 340, 185, 120, 265, 140, 155, 170, 300, 300, 295, 350, 150, 390, 85, 150], 'LightingProducts');
products.getRange('F7:F16').setNumberFormat('"¥"#,##0.00');
products.getRange('H7:I16').setNumberFormat('0.0');
products.getRange('R7:R16').setNumberFormat('"¥"#,##0.00');
products.getRange('B20').values = [['横向对照边界']];
const comparison = [
  ['落地灯', 'ÅRSTID 199元；ISJAKT 499元', '前者灯泡另购，60W是允许上限；后者内置LED 16.5W。只能比较预算，不是同规格竞价。'],
  ['壁灯', 'ANKARSPEL 199元；KABOMBA 399元', '阅读壁灯与IP44浴室灯场景不同，安装件/光源条件不同。'],
  ['当前采购价', '未取得', '所有公开零售价都不是目标客户实际拿货价；没有同SKU、同批量、多供应商成交比较。'],
  ['吸顶灯与吊灯', '型号/规格有部分证据，现价缺失', '2021吊灯目录缺订购码；HFAC1001旧参考1688元及尺寸冲突，不进入现价比较。'],
];
products.getRange('B21:D24').values = comparison;
products.getRange('B21:D24').format = { font: bodyFont, wrapText: true, rowHeight: 72 };

const procurement = addSheet('采购参考', '深圳采购参考：不是目标零售商订单',
  ['事件ID', '采购买方', '项目', '公告日期', '金额性质', '整包金额（元）', '供应商', '目标零售商订单？', '状态与限制', '采购频次', '来源ID'],
  data.procurement.map(e => [e.id, e.buyer ?? missing, e.project, new Date(`${e.date}T00:00:00Z`), e.kind, e.amount, e.supplier ?? missing, '否，仅作为独立工程参考', e.status, missing, e.source_id]),
  [85, 285, 365, 125, 215, 145, 255, 230, 400, 190, 85], 'ProcurementEvents');
procurement.getRange('D7:D10').setNumberFormat('yyyy-mm-dd');
procurement.getRange('F7:F10').setNumberFormat('"¥"#,##0.00');
procurement.getRange('B14').values = [['明细预算上限：不等于成交单价或进货价']];
const caps = data.budget_prices.map(p => [p.project_id, p.item, p.spec, p.quantity, p.unit, p.unit_price_cap, null, p.scope, p.source_id]);
const capRange = procurement.getRange('A17:I23');
capRange.values = [['事件ID', '货品', '规格', '数量', '单位', '含税单价上限（元）', '本行上限计算（元）', '口径与限制', '来源ID'], ...caps];
capRange.format = { font: bodyFont, wrapText: true, rowHeight: 70, verticalAlignment: 'center' };
procurement.getRange('A17:I17').format = { fill: '#705C30', font: { ...bodyFont, bold: true, color: '#FFFFFF' }, rowHeight: 36, wrapText: true };
procurement.tables.add('A17:I23', true, 'BudgetPriceCaps');
procurement.getRange('G18').formulas = [['=D18*F18']];
procurement.getRange('G18:G23').fillDown();
procurement.getRange('F18:G23').setNumberFormat('"¥"#,##0.00');
procurement.getRange('B27').values = [['已排除的历史线索']];
procurement.getRange('B28:D30').values = data.exclusions.map(e => [e.name, e.reason, `${e.source_id}：${e.quote}`]);
procurement.getRange('B28:D30').format = { font: bodyFont, wrapText: true, rowHeight: 95 };

const sourceSheet = addSheet('证据与来源', '公开来源和字段证据',
  ['来源ID', '来源类型', '标题', '公开发布日期', '来源URL', '本次主线程回源', '质量/限制', '抓取时间（上海）'],
  data.sources.map(s => [s.id, s.kind, s.title, s.published_on ? new Date(`${s.published_on}T00:00:00Z`) : s.published_month ?? '未标日期', s.url, snapshotStatus(s.id), s.quality, snapshots.get(s.id)?.captured_at ?? '子任务工具获取，本次复核未完成']),
  [85, 200, 330, 145, 650, 330, 470, 235], 'EvidenceSources');
sourceSheet.getRange('D7:D41').setNumberFormat('yyyy-mm-dd');
const fieldNames = { legal_entity: '公开经营主体', address: '地址', phone: '业务电话', categories: '经营品类', brand_relation: '品牌关系', scale: '经营规模', email: '业务邮箱', models: '产品型号' };
const evidenceRows = [];
for (const f of data.facts) {
  for (const e of f.evidence ?? []) {
    evidenceRows.push([f.entity_id, fieldNames[f.field] ?? f.field, f.value, e.source_id, e.quote, sources.get(e.source_id).url, f.qualifier ?? '', matched(e.source_id, e.quote) ? '正文逐字匹配' : '工具检索/读取引文；本次正文未匹配']);
  }
}
for (const p of data.products) {
  for (const quote of [...p.quotes, ...(p.price_quote ? [p.price_quote] : [])]) {
    evidenceRows.push([p.id, '产品规格/价格', p.name, p.source_id, quote, sources.get(p.source_id).url, p.status, matched(p.source_id, quote) ? '正文逐字匹配' : '子任务回源/检索引文；本次正文未匹配']);
  }
}
sourceSheet.getRange('B44').values = [['字段与产品证据（保持原文，不由模型补充采购事实）']];
sourceSheet.getRange(`A46:H${46 + evidenceRows.length}`).values = [['客户/产品ID', '字段', '值/产品名称', '来源ID', '证据短引文', 'URL', '字段限制', '本次逐字校验'], ...evidenceRows];
sourceSheet.getRange(`A46:H${46 + evidenceRows.length}`).format = { font: bodyFont, wrapText: true, rowHeight: 72, verticalAlignment: 'center' };
sourceSheet.getRange('A46:H46').format = { fill: '#274E47', font: { ...bodyFont, bold: true, color: '#FFFFFF' }, rowHeight: 36 };
sourceSheet.tables.add(`A46:H${46 + evidenceRows.length}`, true, 'FieldEvidence');

book.recalculate();
const summary = await book.inspect({ kind: 'table', range: '客户优先级!A4:J4', tableMaxRows: 1, tableMaxCols: 10 });
console.log(summary.ndjson);
const errors = await book.inspect({ kind: 'match', searchTerm: '#REF!|#DIV/0!|#VALUE!|#NAME\\?|#NUM!|#NULL!|#SPILL!|#CALC!', options: { useRegex: true, maxResults: 20 } });
console.log(errors.ndjson);
const check = procurement.getRange('G18:G23').values.flat();
const expected = data.budget_prices.map(p => p.quantity * p.unit_price_cap);
if (check.some((v, i) => typeof v !== 'number' || Math.abs(v - expected[i]) > 0.000001)) throw new Error('Budget formula check failed');
// 在一次性内存编辑中测试公式重算，恢复原值后再进行最终检查和输出。
procurement.getRange('D18').values = [[1]];
book.recalculate();
if (procurement.getRange('G18').values[0][0] !== data.budget_prices[0].unit_price_cap) throw new Error('Input-change formula check failed');
procurement.getRange('D18').values = [[data.budget_prices[0].quantity]];
book.recalculate();
for (const [name, range] of [['客户优先级', 'A1:H11'], ['客户信息', 'A1:K9'], ['灯具与价格', 'A1:J11'], ['采购参考', 'A1:H10'], ['证据与来源', 'A1:H10']]) {
  const image = await book.render({ sheetName: name, range, scale: 1.3, format: 'png' });
  await fs.writeFile(path.join(previews, `${name}.png`), new Uint8Array(await image.arrayBuffer()));
}
const exported = await SpreadsheetFile.exportXlsx(book);
await exported.save(output);
await fs.rename(`${output}.inspect.ndjson`, path.join(previews, 'export.inspect.ndjson')).catch(() => {});
await fs.writeFile(path.join(previews, 'verification.json'), JSON.stringify({
  output: path.resolve(output), entities: data.entities.length, products: data.products.length,
  groups: new Set(data.entities.map(e => e.group_id)).size, evidence_rows: evidenceRows.length,
  budget_formula_expected: expected, budget_formula_actual: procurement.getRange('G18:G23').values.flat(),
  source_snapshot_ok: [...snapshots.values()].filter(s => s.status === 'ok').length,
  native_excel_application_tested: false,
}, null, 2));
console.log(JSON.stringify({ output: path.resolve(output), sheets: [...sheets.keys()], entities: sorted.length, products: data.products.length }));
