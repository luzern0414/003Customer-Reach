/**
 * opencli ccgp search <keyword> [--days 365] [--type 0] [--limit 40]
 *
 * 中国政府采购网全文检索（search.ccgp.gov.cn/bxsearch），在 Edge 中打开结果页并解析列表。
 * Strategy: DOM_STATE（服务端渲染 HTML 列表）
 * 站点对访问频率敏感：出现“访问过于频繁”页面时返回 CommandExecutionError(code=RATE_LIMITED)，由上层改用 Exa 补充。
 */
import { cli, Strategy } from '@jackwener/opencli/registry';
import { ArgumentError, CommandExecutionError } from '@jackwener/opencli/errors';
import { cleanText, normalizeDate, clampInt } from './lib/common.js';

const SEARCH = 'http://search.ccgp.gov.cn/bxsearch';

function fmt(d) {
  return `${d.getFullYear()}:${String(d.getMonth() + 1).padStart(2, '0')}:${String(d.getDate()).padStart(2, '0')}`;
}

function buildUrl(keyword, days, bidType, pageIndex, fulltext) {
  const end = new Date();
  const start = new Date(Date.now() - days * 86400000);
  const p = new URLSearchParams({
    searchtype: fulltext ? '2' : '1', page_index: String(pageIndex), bidSort: '0', buyerName: '', projectId: '', pinMu: '0',
    bidType: String(bidType), dbselect: 'bidx', kw: keyword, start_time: fmt(start), end_time: fmt(end),
    timeType: '6', displayZone: '', zoneId: '', pppStatus: '0', agentName: '',
  });
  return `${SEARCH}?${p.toString()}`;
}

const PARSE_JS = `(() => {
  const body = document.body ? document.body.innerText : '';
  if (/访问过于频繁|频繁访问/.test(document.title + body)) return { rateLimited: true, rows: [] };
  const totalMatch = body.match(/共找到\\s*(\\d+)\\s*条/);
  const items = [...document.querySelectorAll('ul.vT-srch-result-list-bid li, .vT-srch-result-list li')];
  const rows = items.map(li => {
    const a = li.querySelector('a');
    const span = li.querySelector('span');
    return { title: a ? a.innerText : '', url: a ? a.href : '', meta: span ? span.innerText : '', summary: (li.querySelector('p') || {}).innerText || '' };
  }).filter(r => r.title && r.url);
  return { rateLimited: false, total: totalMatch ? Number(totalMatch[1]) : null, rows };
})()`;

function parseMeta(meta) {
  // 形如：2026.09.30 10:12:33 | 采购人：XX | 代理机构：YY | 公开招标公告 | 北京 | 品目
  const parts = cleanText(meta).split('|').map((s) => s.trim()).filter(Boolean);
  const out = { published_at: '', buyer: '', agency: '', notice_type: '', region: '' };
  for (const part of parts) {
    if (!out.published_at && /20\d{2}[.\-/]\d{1,2}[.\-/]\d{1,2}/.test(part)) out.published_at = normalizeDate(part);
    else if (/^采购人[:：]/.test(part)) out.buyer = part.replace(/^采购人[:：]/, '').trim();
    else if (/^代理机构[:：]/.test(part)) out.agency = part.replace(/^代理机构[:：]/, '').trim();
    else if (/公告|公示|结果/.test(part) && !out.notice_type) out.notice_type = part;
    else if (!out.region && part.length <= 8) out.region = part;
  }
  // 列表里“代理机构”与公告类型之间常无分隔符：'XX有限公司 中标公告'
  const tail = out.agency.match(/^(.*?)\s+(\S*(?:公告|公示))$/);
  if (tail) {
    out.agency = tail[1].trim();
    if (!out.notice_type) out.notice_type = tail[2];
  }
  return out;
}

cli({
  site: 'ccgp',
  name: 'search',
  access: 'read',
  description: '中国政府采购网公告检索（标题/全文含关键词），返回采购人、代理机构、公告类型、日期',
  domain: 'search.ccgp.gov.cn',
  strategy: Strategy.PUBLIC,
  browser: true,
  navigateBefore: false,
  siteSession: 'persistent',
  example: 'opencli ccgp search "北京航天广通科技有限公司" --days 365 -f json',
  args: [
    { name: 'query', required: true, positional: true, help: '关键词或采购人名称' },
    { name: 'days', type: 'int', default: 365, help: '时间范围（天）' },
    { name: 'type', default: '0', help: '公告类型 bidType：0=所有 1=公开招标 7=中标 11=成交 等' },
    { name: 'limit', type: 'int', default: 40, help: '最多返回条数（每页 20 条，≤100）' },
    { name: 'fulltext', default: 'true', help: 'true=全文检索（企业名出现在正文即命中，如中标供应商）false=仅标题' },
  ],
  columns: ['title', 'notice_type', 'published_at', 'buyer', 'agency', 'region', 'summary', 'url'],
  func: async (page, kwargs) => {
    const keyword = cleanText(kwargs.query);
    if (!keyword) throw new ArgumentError('关键词不能为空');
    const days = clampInt(kwargs.days, 365, 1, 3650);
    const limit = clampInt(kwargs.limit, 40, 1, 100);
    const rows = [];
    for (let pageIndex = 1; rows.length < limit && pageIndex <= 5; pageIndex += 1) {
      await page.goto(buildUrl(keyword, days, kwargs.type || '0', pageIndex, String(kwargs.fulltext) !== 'false'));
      await page.wait(3);
      const res = await page.evaluate(PARSE_JS);
      if (res && res.rateLimited) {
        if (rows.length) break;
        throw new CommandExecutionError('RATE_LIMITED: 中国政府采购网提示“访问过于频繁”，请稍后再试（上层会改用 Exa 补充）');
      }
      const list = (res && res.rows) || [];
      for (const r of list) {
        rows.push({ title: cleanText(r.title), ...parseMeta(r.meta), summary: cleanText(r.summary).slice(0, 300), url: r.url });
        if (rows.length >= limit) break;
      }
      if (list.length < 20) break;
      await page.wait(3);
    }
    return rows;
  },
});
