/**
 * opencli chinabidding search <keyword> [--limit 60]
 * 中国采购与招标网（www.chinabidding.com.cn / chinabidding.cn）站内检索。
 * Strategy: PUBLIC_API —— GET /sdbxinfo/<token>/datax/json/info_search?keyword=&page=&rp=（无需登录，2026-10-08 实测）
 * 详情页（/zbgg/xxx.html）正文需要登录（免费注册）后可见；列表给出标题、类型、日期、地区。
 */
import { cli, Strategy } from '@jackwener/opencli/registry';
import { ArgumentError, CommandExecutionError } from '@jackwener/opencli/errors';
import { cleanText, normalizeDate, clampInt } from './lib/common.js';
import { httpJson, sleep } from './lib/http.js';

const API = 'https://www.chinabidding.com.cn/sdbxinfo/313035392e302e7379675f62616e64/datax/json/info_search';
const DETAIL_BASE = 'https://www.chinabidding.cn';
const TYPE_LABEL = { ZBGG: '招标公告', ZBGS: '中标公示', ZBYG: '招标预告', BGGG: '变更公告', CGXX: '采购信息', NZJ: '拟在建', XMXX: '项目信息' };
const PAGE_SIZE = 15;

cli({
  site: 'chinabidding',
  name: 'search',
  access: 'read',
  description: '中国采购与招标网检索（公开接口，标题/日期/类型/地区；正文需登录）',
  domain: 'www.chinabidding.com.cn',
  strategy: Strategy.PUBLIC,
  browser: false,
  example: 'opencli chinabidding search "北京航天广通科技有限公司" --limit 60 -f json',
  args: [
    { name: 'query', required: true, positional: true, help: '关键词或企业名' },
    { name: 'limit', type: 'int', default: 60, help: '最多返回条数（≤300）' },
  ],
  columns: ['notice_id', 'notice_type', 'title', 'published_at', 'area_id', 'total', 'url'],
  func: async (kwargs) => {
    const keyword = cleanText(kwargs.query);
    if (!keyword) throw new ArgumentError('关键词不能为空');
    const limit = clampInt(kwargs.limit, 60, 1, 300);
    const rows = [];
    let total = 0;
    for (let page = 1; rows.length < limit && page <= Math.ceil(limit / PAGE_SIZE); page += 1) {
      const q = new URLSearchParams({ keyword, page: String(page), rp: String(PAGE_SIZE), device: 'zbdt001', cpcode: 'zbdt001' });
      const { status, json } = await httpJson(`${API}?${q}`, { headers: { Referer: 'https://www.chinabidding.com.cn/search' } });
      if (status !== 200) throw new CommandExecutionError(`中国采购与招标网接口 HTTP ${status}`);
      total = Number(json.total || total);
      const list = json.relatedList || [];
      for (const it of list) {
        const code = cleanText(it.table_name2 || it.table_name);
        rows.push({
          notice_id: String(it.id || ''),
          notice_type: TYPE_LABEL[code] || code,
          title: cleanText(it.title),
          published_at: normalizeDate(it.publish_date),
          area_id: String(it.area_id || ''),
          total,
          url: it.url ? `${DETAIL_BASE}${it.url}` : '',
        });
        if (rows.length >= limit) break;
      }
      if (list.length < PAGE_SIZE) break;
      await sleep(800);
    }
    return rows;
  },
});
