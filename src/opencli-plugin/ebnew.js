/**
 * 必联网（ebnew.com）
 *   opencli ebnew search <keyword> [--limit 50]   招标/结果/预告检索（服务端渲染 HTML）
 *   opencli ebnew company <企业名>                 企业库：企业性质、行业、地区、注册资本、经营模式、主营产品
 * Strategy: PUBLIC（GET https://ss.ebnew.com/tradingSearch/index.htm?key=&currentPage=N，每页 10 条；2026-10-08 实测）
 */
import { cli, Strategy } from '@jackwener/opencli/registry';
import { ArgumentError, CommandExecutionError } from '@jackwener/opencli/errors';
import { cleanText, normalizeDate, clampInt } from './lib/common.js';
import { httpText, stripTags, sleep } from './lib/http.js';

const SEARCH = 'https://ss.ebnew.com/tradingSearch/index.htm';
const COMPANY = 'https://ss.ebnew.com/companySearch/index.htm';

function parseTrading(html) {
  const blocks = html.split(/<div class="abstract-box/).slice(1);
  return blocks.map((b) => {
    const tag = cleanText((b.match(/<i class="[^"]*tag-[^"]*"[^>]*>([^<]+)<\/i>/) || [])[1]);
    const a = b.match(/<a[^>]*abstract-title[^>]*href="([^"]+)"[^>]*title="([^"]*)"/) || b.match(/<a[^>]*href="([^"]+)"[^>]*title="([^"]*)"[^>]*abstract-title/);
    const date = normalizeDate((b.match(/发布日期[:：]\s*([0-9-]+)/) || [])[1]);
    const field = (name) => cleanText(stripTags((b.match(new RegExp(`${name}：</span>\\s*<span[^>]*>([\\s\\S]*?)</span>`)) || [])[1]));
    return {
      notice_type: tag,
      title: a ? cleanText(a[2]) : '',
      published_at: date,
      method: field('招标方式'),
      product: field('招标产品').replace(/\$StringUtils.*$/, ''),
      deadline: field('截止时间'),
      region: field('招标地区'),
      url: a ? a[1].replace(/^http:/, 'https:') : '',
    };
  }).filter((r) => r.title);
}

cli({
  site: 'ebnew',
  name: 'search',
  access: 'read',
  description: '必联网招标采购项目检索（预告/公告/变更/结果）',
  domain: 'ss.ebnew.com',
  strategy: Strategy.PUBLIC,
  browser: false,
  example: 'opencli ebnew search "北京航天广通科技有限公司" -f json',
  args: [
    { name: 'query', required: true, positional: true, help: '关键词或企业名' },
    { name: 'limit', type: 'int', default: 50, help: '最多返回条数（每页 10，≤200）' },
  ],
  columns: ['notice_type', 'title', 'published_at', 'method', 'product', 'deadline', 'region', 'total', 'url'],
  func: async (kwargs) => {
    const keyword = cleanText(kwargs.query);
    if (!keyword) throw new ArgumentError('关键词不能为空');
    const limit = clampInt(kwargs.limit, 50, 1, 200);
    const rows = [];
    let total = 0;
    for (let page = 1; rows.length < limit && page <= Math.ceil(limit / 10); page += 1) {
      const { status, text } = await httpText(`${SEARCH}?${new URLSearchParams({ key: keyword, currentPage: String(page) })}`);
      if (status !== 200) throw new CommandExecutionError(`必联网 HTTP ${status}`);
      if (page === 1) total = Number((text.match(/共有\s*(?:<[^>]+>)?\s*(\d+)/) || [])[1] || 0);
      const list = parseTrading(text);
      for (const r of list) {
        rows.push({ ...r, total });
        if (rows.length >= limit) break;
      }
      if (list.length < 10 || (total && rows.length >= total)) break;
      await sleep(1000);
    }
    return rows;
  },
});

cli({
  site: 'ebnew',
  name: 'company',
  access: 'read',
  description: '必联网企业库：企业性质、所属行业、地区、注册资本、经营模式、主营产品',
  domain: 'ss.ebnew.com',
  strategy: Strategy.PUBLIC,
  browser: false,
  example: 'opencli ebnew company "北京航天广通科技有限公司" -f json',
  args: [
    { name: 'query', required: true, positional: true, help: '企业名' },
    { name: 'limit', type: 'int', default: 5, help: '最多返回企业数' },
  ],
  columns: ['name', 'nature', 'industry', 'region', 'reg_capital', 'business_mode', 'main_products', 'url'],
  func: async (kwargs) => {
    const keyword = cleanText(kwargs.query);
    if (!keyword) throw new ArgumentError('企业名不能为空');
    const { status, text } = await httpText(`${COMPANY}?${new URLSearchParams({ key: keyword })}`);
    if (status !== 200) throw new CommandExecutionError(`必联网 HTTP ${status}`);
    const out = [];
    for (const b of text.split(/<div class="abstract-box/).slice(1)) {
      const name = cleanText((b.match(/abstract-title[^>]*title="([^"]+)"/) || [])[1]);
      if (!name) continue;
      const field = (k) => cleanText(stripTags((b.match(new RegExp(`${k}：</span>\\s*<span[^>]*>([\\s\\S]*?)</span>`)) || [])[1]));
      const row = {
        name, nature: field('企业性质'), industry: field('所属行业'), region: field('所属地区'),
        reg_capital: field('注册资本'), business_mode: field('经营模式'), main_products: field('主营产品').slice(0, 200),
        url: ((b.match(/abstract-title[^>]*href="(http[^"]+)"/) || [])[1]) || '',
      };
      if (!row.nature && !row.industry && !row.reg_capital && !row.main_products) continue;
      out.push(row);
      if (out.length >= clampInt(kwargs.limit, 5, 1, 20)) break;
    }
    return out;
  },
});
