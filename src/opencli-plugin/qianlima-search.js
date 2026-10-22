/**
 * opencli qianlima search <keyword> [--days 365] [--limit 60] [--title-only false]
 * 千里马招标网全文/标题检索。
 * Strategy: PUBLIC_API —— POST https://search.qianlima.com/api/v1/website/search?...（无需登录，2026-10-08 实测）
 * timeType：2=近一周 3=近一月 5=近三月 1=近一年；numPerPage 最大 20。
 * 返回字段含 tenderees(招标人) / bidder(中标人) / agent(代理) / 金额（部分公告为空）。
 */
import { cli, Strategy } from '@jackwener/opencli/registry';
import { ArgumentError, CommandExecutionError } from '@jackwener/opencli/errors';
import { cleanText, normalizeDate, clampInt, extractBuyer } from './lib/common.js';
import { httpJson, sleep } from './lib/http.js';

const API = 'https://search.qianlima.com/api/v1/website/search';
const PAGE_SIZE = 20;

function daysToTimeType(days) {
  const d = Number(days) || 365;
  if (d <= 7) return '2';
  if (d <= 31) return '3';
  if (d <= 92) return '5';
  return '1';
}

function money(num, unit) {
  if (num == null || num === '') return '';
  return `${num}${unit || ''}`;
}

function names(v) {
  if (!v) return '';
  if (Array.isArray(v)) return v.map((x) => (typeof x === 'string' ? x : x && (x.name || x.companyName) || '')).filter(Boolean).join(';');
  return cleanText(typeof v === 'string' ? v : v.name || '');
}

cli({
  site: 'qianlima',
  name: 'search',
  access: 'read',
  description: '千里马招标网检索（公开接口：招标/中标/预告/变更等，含招标人/中标人/代理/金额字段）',
  domain: 'search.qianlima.com',
  strategy: Strategy.PUBLIC,
  browser: false,
  example: 'opencli qianlima search "北京航天广通科技有限公司" --days 365 -f json',
  args: [
    { name: 'query', required: true, positional: true, help: '关键词或企业名' },
    { name: 'days', type: 'int', default: 365, help: '时间范围：7/30/90/365' },
    { name: 'limit', type: 'int', default: 60, help: '最多返回条数（≤400）' },
    { name: 'title_only', default: 'false', help: 'true=仅标题检索，false=全文检索' },
  ],
  columns: ['content_id', 'notice_type', 'stage', 'title', 'published_at', 'area', 'buyer', 'winner', 'agency', 'budget', 'amount', 'hit', 'total', 'url'],
  func: async (kwargs) => {
    const keyword = cleanText(kwargs.query);
    if (!keyword) throw new ArgumentError('关键词不能为空');
    const limit = clampInt(kwargs.limit, 60, 1, 400);
    const rows = [];
    for (let page = 1; rows.length < limit && page <= Math.ceil(limit / PAGE_SIZE); page += 1) {
      const q = new URLSearchParams({
        filtermode: '1', timeType: daysToTimeType(kwargs.days), areas: '', types: '-1',
        searchMode: String(kwargs.title_only) === 'true' ? '1' : '0', keywords: keyword,
        beginTime: '', endTime: '', isfirst: 'false', currentPage: String(page), numPerPage: String(PAGE_SIZE),
      });
      const { status, json } = await httpJson(`${API}?${q}`, { method: 'POST', headers: { Referer: 'https://search.qianlima.com/', Origin: 'https://search.qianlima.com' } });
      if (status !== 200 || !json || json.code !== 200) {
        if (page === 1) throw new CommandExecutionError(`千里马检索失败：HTTP ${status} code=${json && json.code} ${json && json.msg}`);
        break;
      }
      const data = json.data || {};
      const list = data.data || [];
      for (const it of list) {
        const title = cleanText(it.popTitle || it.showTitle);
        const hit = /在正文中/.test(it.showTitle || '') ? 'content' : 'title';
        rows.push({
          content_id: String(it.contentid || ''),
          notice_type: cleanText(it.noticeSegmentTypeName || it.progName),
          stage: cleanText(it.progressStageName || it.progName),
          title,
          published_at: normalizeDate(it.updateTimeStr || it.updateTime),
          area: cleanText(it.areaName),
          buyer: names(it.tenderees) || extractBuyer(title),
          winner: names(it.bidder),
          agency: names(it.agent),
          budget: money(it.budgetAmountNumber ?? it.tenderAmountNumber, it.tenderAmountUnit),
          amount: money(it.biddingAmountNumber ?? it.bidderAmountNumber, it.bidderAmountUnit),
          hit,
          total: Number(data.rowCount || 0),
          url: cleanText(it.url || it.originUrl),
        });
        if (rows.length >= limit) break;
      }
      if (list.length < PAGE_SIZE) break;
      await sleep(800);
    }
    return rows;
  },
});
