/** 只读复核导出的 workbook，并渲染明细区域；不修改交付文件。 */
import fs from 'node:fs/promises';
import path from 'node:path';
import { FileBlob, Workbook, SpreadsheetFile } from '@oai/artifact-tool';
const [file, input] = process.argv.slice(2);
if (!file || !input) throw new Error('Usage: verify_lighting.mjs workbook.xlsx dataset.json');
const dataset = JSON.parse(await fs.readFile(input, 'utf8'));
const workbook = await SpreadsheetFile.importXlsx(await FileBlob.load(file));
workbook.recalculate();
const detail = workbook.worksheets.getItem('客户信息');
const rows = detail.getRange('A7:Z26').values;
const expected = [...dataset.entities].sort((a, b) => a.priority - b.priority);
const facts = new Map(dataset.facts.map(f => [`${f.entity_id}:${f.field}`, f.value]));
for (let i = 0; i < expected.length; i++) {
  if (rows[i][0] !== expected[i].id || rows[i][1] !== expected[i].name) throw new Error('Client identity lost on export');
  if (rows[i][8] !== facts.get(`${expected[i].id}:phone`)) throw new Error('Business number changed or masked');
  if (rows[i][15] !== '未找到公开数据' || rows[i][17] !== '未找到公开数据') throw new Error('Missing metric converted to a fabricated value');
}
const prices = workbook.worksheets.getItem('灯具与价格').getRange('F7:F16').values.flat();
dataset.products.forEach((p, i) => {
  if (prices[i] !== (p.price ?? '未找到公开数据')) throw new Error('Price type/value changed');
});
const formulas = workbook.worksheets.getItem('采购参考').getRange('G18:G23').formulas;
if (formulas.some(row => !row[0]?.startsWith('='))) throw new Error('Budget formulas were not preserved');
const inspection = await workbook.inspect({ kind: 'match', searchTerm: '#REF!|#DIV/0!|#VALUE!|#NAME\\?|#NUM!|#NULL!|#SPILL!|#CALC!', options: { useRegex: true, maxResults: 20 } });
console.log(inspection.ndjson);
const previewDir = path.resolve('.codex-tmp/lighting-previews');
for (const [name, range, label] of [['采购参考', 'A14:I30', '预算与排除'], ['证据与来源', 'A44:H53', '字段证据'], ['灯具与价格', 'B20:D24', '价格可比性']]) {
  const preview = await workbook.render({ sheetName: name, range, scale: 1.2, format: 'png' });
  await fs.writeFile(path.join(previewDir, `${label}.png`), new Uint8Array(await preview.arrayBuffer()));
}
const report = { exported_file_read_back: true, client_rows: rows.length, business_numbers_exact: true,
  missing_metrics_preserved: true, public_price_rows: prices.filter(p => typeof p === 'number').length,
  budget_formulas_preserved: formulas.length, native_excel_tested: false };
await fs.writeFile(path.join(previewDir, 'readback.json'), JSON.stringify(report, null, 2));
console.log(JSON.stringify(report));
