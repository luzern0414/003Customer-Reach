/**
 * opencli yfbzb public <keyword> [--type zhaobiao|zhongbiao] [--limit 60]
 * 乙方宝公开搜索页（www.yfbzb.com/search/invitedBidSearch | winBidSearch），无需登录，服务端渲染表格。
 * 作为会员控制台（yfbzb search）的免登录补充；字段：标题、公告类型、地区、发布时间、公开详情链接。
 */
import { cli, Strategy } from '@jackwener/opencli/registry';
import { ArgumentError, CommandExecutionError } from '@jackwener/opencli/errors';
import { cleanText, normalizeDate, clampInt, extractBuyer } from './lib/common.js';
import { httpText, stripTags, sleep } from './lib/http.js';

const PATHS = { zhaobiao: '/search/invitedBidSearch' };

function parseRows(html) {
  const tbody = (html.match(/<tbody>([\s\S]*?)<\/tbody>/) || [])[1] || '';
  return [...tbody.matchAll(/<tr[^>]*>([\s\S]*?)<\/tr>/g)].map((m) => {
    const tds = [...m[1].matchAll(/<td[^>]*>([\s\S]*?)<\/td>/g)].map((x) => x[1]);
    const a = (tds[0] || '').match(/href="([^"]+)"[^>]*>([\s\S]*?)<\/a>/);
    if (!a) return null;
    const href = a[1].startsWith('http') ? a[1] : `https://www.yfbzb.com${a[1]}`;
    return {
      content_id: (href.match(/_(\d+)\.html/) || [])[1] || '',
      title: cleanText(stripTags(a[2])),
      notice_type: cleanText(stripTags(tds[1])),
      area: cleanText(stripTags(tds[2])),
      published_at: normalizeDate(stripTags(tds[3])),
      url: href,
    };
  }).filter(Boolean);
}

cli({
  site: 'yfbzb',
  name: 'public',
  access: 'read',
  description: '乙方宝公开搜索页（免登录，招标列表）',
  domain: 'www.yfbzb.com',
  strategy: Strategy.PUBLIC,
  browser: false,
  example: 'opencli yfbzb public "北京航天广通科技有限公司" --type zhaobiao -f json',
  args: [
    { name: 'query', required: true, positional: true, help: '关键词或企业名' },
    { name: 'type', default: 'zhaobiao', help: '仅支持 zhaobiao（中标页为前端异步加载，请用 yfbzb search --type zhongbiao 或 qianlima search）' },
    { name: 'limit', type: 'int', default: 60, help: '最多返回条数（每页 30，≤300）' },
  ],
  columns: ['content_id', 'notice_type', 'title', 'area', 'published_at', 'buyer', 'total', 'url'],
  func: async (kwargs) => {
    const keyword = cleanText(kwargs.query);
    if (!keyword) throw new ArgumentError('关键词不能为空');
    const type = PATHS[kwargs.type] ? kwargs.type : 'zhaobiao';
    const limit = clampInt(kwargs.limit, 60, 1, 300);
    const rows = [];
    let total = 0;
    for (let page = 1; rows.length < limit && page <= Math.ceil(limit / 30); page += 1) {
      const q = new URLSearchParams({
        type: '0', defaultSearch: 'false', keyword, pageNo: String(page), pageSize: '30',
        noticeType: type === 'zhaobiao' ? '3' : '', invitedBidType: '3', timeType: '5', searchType: '2', searchMode: '1',
      });
      const { status, text } = await httpText(`https://www.yfbzb.com${PATHS[type]}?${q}`);
      if (status !== 200) throw new CommandExecutionError(`乙方宝公开搜索 HTTP ${status}`);
      if (page === 1) total = Number((stripTags(text).match(/相关的[^0-9]{0,12}(\d+)\s*条/) || [])[1] || 0);
      const list = parseRows(text);
      for (const r of list) {
        rows.push({ ...r, buyer: extractBuyer(r.title) || (r.title.match(/^(.{4,40}?(?:有限公司|研究院|研究所|大学|学院|医院|中心|局))/) || [])[1] || '', total });
        if (rows.length >= limit) break;
      }
      if (list.length < 30) break;
      await sleep(1000);
    }
    return rows;
  },
});
