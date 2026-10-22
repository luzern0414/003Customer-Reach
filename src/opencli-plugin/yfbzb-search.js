/**
 * opencli yfbzb search <keyword> [--type zhaobiao|zhongbiao|caigou|nijian|qianqi] [--days 365] [--area ''] [--limit 60]
 *
 * 通过会员控制台搜索接口获取标讯列表。列表摘要不消耗详情额度。
 * 输入企业名时，摘要中的“采购企业/招标人/中标人”会被抽取为 buyer / winner。
 */
import { cli, Strategy } from '@jackwener/opencli/registry';
import { ArgumentError, CommandExecutionError } from '@jackwener/opencli/errors';
import { cleanText, normalizeDate, extractBuyer, extractWinner, extractAmount, inferRole, isAgency, clampInt } from './lib/common.js';
import { DOMAIN, CONSOLE_URL, NOTICE_TYPES, apiGet, daysToTimeOption, consoleDetailUrl, publicDetailUrl } from './lib/yfbzb.js';

const PAGE_SIZE = 30;

function buildParams(type, keyword, timeOption, area, pageNum) {
  const common = {
    pageSize: String(PAGE_SIZE),
    pageNum: String(pageNum),
    queryType: '',
    offSet: '',
    viewMonitor: 'false',
    areaIds: area,
    filterCondition: '1',
  };
  if (type === 'caigou') {
    return { path: '/search', params: { ...common, pageFrom: 'caigou', keyword, keywords: '', purchaseTimeType: '-1', searchType: '1' } };
  }
  if (type === 'nijian') {
    return { path: '/search', params: { ...common, pageFrom: 'nijian', keyword, timeOption, stages: '全部', types: '1000', defTimeFlag: '0' } };
  }
  if (type === 'qianqi') {
    return { path: '/subZhaobiao/queryPreProjectInfo', params: { ...common, keywords: keyword, timeOption, nature: '', defTimeFlag: '0' } };
  }
  return {
    path: '/search',
    params: { ...common, pageFrom: type, keyword, keywords: '', timeOption, searchType: '1', nature: '', defTimeFlag: '0' },
  };
}

function toRow(item, type, keyword) {
  const title = cleanText(item.title);
  const summary = cleanText(item.content);
  const contentId = String(item.contentId ?? item.id ?? '');
  const areaId = String(item.areaId ?? item.provinceId ?? '');
  const published = cleanText(item.updateTime || item.updateDate || item.publishTime || '');
  let buyer = extractBuyer(summary);
  // 标题形如 “XX有限公司采购YY招标公告”
  if (!buyer) {
    const m = title.match(/^(.{4,40}?(?:有限公司|集团|研究院|研究所|大学|学院|医院|中心|局))/);
    if (m) buyer = m[1];
  }
  let agency = '';
  if (buyer && isAgency(buyer)) {
    agency = buyer;
    buyer = '';
  }
  let winner = extractWinner(summary);
  if (winner && buyer && winner === buyer) winner = '';
  const role = inferRole(`${title} ${summary}`, keyword, buyer, winner);
  let finalRole = role;
  if (finalRole === 'winner' && /候选人/.test(cleanText(item.type))) finalRole = 'candidate';
  if (finalRole === 'winner' && !winner) winner = keyword;
  return {
    content_id: contentId,
    notice_type: cleanText(item.type) || NOTICE_TYPES[type] || type,
    title,
    area: cleanText(item.areaName),
    area_id: areaId,
    published_at: normalizeDate(published) || published,
    buyer,
    winner,
    agency,
    amount: extractAmount(summary) || cleanText(item.extractBudget || ''),
    role: finalRole,
    summary: summary.slice(0, 300),
    url: consoleDetailUrl(contentId, areaId, type === 'qianqi' ? 'zhaobiao' : type),
    public_url: type === 'zhaobiao' ? publicDetailUrl(contentId, item.updateTime) : '',
  };
}

cli({
  site: 'yfbzb',
  name: 'search',
  access: 'read',
  description: '乙方宝/千里马会员控制台标讯搜索（招标/中标/采购意向/拟在建/前期商机），列表不消耗详情额度',
  domain: DOMAIN,
  strategy: Strategy.COOKIE,
  browser: true,
  navigateBefore: false,
  siteSession: 'persistent',
  example: 'opencli yfbzb search "北京航天广通科技有限公司" --type zhaobiao --days 365 -f json',
  args: [
    { name: 'query', required: true, positional: true, help: '关键词或企业名' },
    { name: 'type', default: 'zhaobiao', help: 'zhaobiao|zhongbiao|caigou|nijian|qianqi' },
    { name: 'days', type: 'int', default: 365, help: '时间范围（天）：7/30/90/180/365' },
    { name: 'area', default: '', help: '地区 areaIds（逗号分隔，空=账号可见全部地区；北京=2）' },
    { name: 'limit', type: 'int', default: 60, help: '最多返回条数（≤300）' },
  ],
  columns: ['content_id', 'notice_type', 'title', 'area', 'area_id', 'published_at', 'buyer', 'winner', 'agency', 'amount', 'role', 'summary', 'url', 'public_url'],
  func: async (page, kwargs) => {
    const keyword = cleanText(kwargs.query);
    if (!keyword) throw new ArgumentError('关键词不能为空');
    const type = cleanText(kwargs.type || 'zhaobiao');
    if (!NOTICE_TYPES[type]) throw new ArgumentError(`不支持的类型 ${type}，可选：${Object.keys(NOTICE_TYPES).join('|')}`);
    const limit = clampInt(kwargs.limit, 60, 1, 300);
    const timeOption = daysToTimeOption(kwargs.days);
    const area = cleanText(kwargs.area || '');

    const rows = [];
    const seen = new Set();
    let total = null;
    for (let pageNum = 1; rows.length < limit && pageNum <= Math.ceil(limit / PAGE_SIZE) + 1; pageNum += 1) {
      const { path, params } = buildParams(type, keyword, timeOption, area, pageNum);
      let json = await apiGet(page, path, params);
      // 控制台刚加载/路由切换时偶发返回空列表：第一页为空则等待重试，第二次重试前重新加载控制台
      const isEmpty = (j) => j.code === 200 && !((j.data || {}).resultList || (j.data || {}).list || []).length;
      for (let attempt = 1; pageNum === 1 && attempt <= 2 && isEmpty(json); attempt += 1) {
        if (attempt === 2) await page.goto(CONSOLE_URL);
        await page.wait(attempt === 2 ? 4 : 2);
        json = await apiGet(page, path, params);
      }
      if (json.code !== 200) {
        if (pageNum === 1) throw new CommandExecutionError(`乙方宝搜索失败：code=${json.code} msg=${json.msg}`);
        break;
      }
      const data = json.data || {};
      total = data.count ?? total;
      const list = data.resultList || data.list || [];
      if (!list.length) break;
      for (const item of list) {
        const row = toRow(item, type, keyword);
        if (!row.content_id || seen.has(row.content_id)) continue;
        seen.add(row.content_id);
        rows.push(row);
        if (rows.length >= limit) break;
      }
      if (list.length < PAGE_SIZE) break;
      await page.wait(1.5); // 翻页间隔，保持会话稳定
    }
    return rows;
  },
});
