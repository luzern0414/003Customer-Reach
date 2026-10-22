/**
 * opencli yfbzb detail <content_id> [--area 2] [--type zhaobiao] [--fallback-public true]
 *
 * 会员控制台详情（完整字段：采购企业、联系人、电话等）。每次成功读取消耗 1 次会员查看额度。
 * 额度用尽（errType=6）时：status=quota_exhausted，并（默认）回退读取公开 SEO 页（部分字段打码）。
 */
import { cli, Strategy } from '@jackwener/opencli/registry';
import { ArgumentError } from '@jackwener/opencli/errors';
import { cleanText, normalizeDate, extractBuyer, extractWinner, extractAmount, extractContacts, isMasked } from './lib/common.js';
import { DOMAIN, apiGet, consoleDetailUrl, describeDetailError } from './lib/yfbzb.js';

const COLUMNS = ['status', 'content_id', 'title', 'published_at', 'buyer', 'winner', 'amount', 'contacts', 'phones', 'masked', 'source_url', 'note', 'text'];

/** 从详情 JSON 中尽量找出正文与标题（字段名以实测为准，兼容多种命名） */
function pickDetail(data) {
  const flat = [];
  const walk = (v, depth) => {
    if (depth > 3 || v == null) return;
    if (typeof v === 'string') { flat.push(v); return; }
    if (Array.isArray(v)) { v.forEach((x) => walk(x, depth + 1)); return; }
    if (typeof v === 'object') Object.values(v).forEach((x) => walk(x, depth + 1));
  };
  walk(data, 0);
  const title = cleanText(data.title || data.contentTitle || data.noticeTitle || '');
  const htmlCandidates = [data.content, data.contentHtml, data.detail, data.text, data.html].filter((x) => typeof x === 'string');
  const longest = (htmlCandidates.length ? htmlCandidates : flat).sort((a, b) => b.length - a.length)[0] || '';
  return { title, text: cleanText(longest), published: data.updateTime || data.publishTime || data.createTime || '' };
}

function buyerFromTitle(title) {
  const m = cleanText(title).match(/^(.{4,40}?(?:有限责任公司|股份有限公司|有限公司|集团|研究院|研究所|大学|学院|医院|中心|局))/);
  return m ? m[1] : '';
}

async function readPublicPage(page, url) {
  if (!url) return null;
  await page.goto(url);
  await page.wait(3);
  let text = cleanText(await page.evaluate('document.body ? document.body.innerText : ""'));
  // 只保留正文区：“当前位置”之后，到“关注乙方宝服务号/登录之后即可”之前（去掉导航与页脚推荐）
  const start = text.indexOf('当前位置');
  if (start >= 0) text = text.slice(start);
  const end = text.search(/关注乙方宝服务号|登录之后即可享受|招标信息推荐/);
  if (end > 0) text = text.slice(0, end);
  const title = cleanText(await page.evaluate('document.title')).replace(/\s*-\s*乙方宝\s*$/, '');
  return { text, title };
}

cli({
  site: 'yfbzb',
  name: 'detail',
  access: 'read',
  description: '乙方宝会员控制台标讯详情（含联系人/电话；消耗 1 次会员查看额度，额度不足时回退公开页）',
  domain: DOMAIN,
  strategy: Strategy.COOKIE,
  browser: true,
  navigateBefore: false,
  siteSession: 'persistent',
  example: 'opencli yfbzb detail 636513843 --area 2 -f json',
  args: [
    { name: 'content_id', required: true, positional: true, help: 'search 返回的 content_id' },
    { name: 'area', default: '2', help: 'search 返回的 area_id' },
    { name: 'type', default: 'zhaobiao', help: 'zhaobiao|zhongbiao|caigou|nijian' },
    { name: 'public_url', default: '', help: '公开 SEO 页 URL（search 返回的 public_url），额度不足时回退读取' },
    { name: 'fallback_public', default: 'true', help: '额度不足时是否回退读取公开页 true|false' },
  ],
  columns: COLUMNS,
  func: async (page, kwargs) => {
    const contentId = cleanText(kwargs.content_id);
    if (!/^\d+$/.test(contentId)) throw new ArgumentError('content_id 必须是数字');
    const area = cleanText(kwargs.area || '2');
    const type = cleanText(kwargs.type || 'zhaobiao');
    const json = await apiGet(page, '/subZhaobiao/zbDetail', { contentId, pageFrom: type, areaId: area });
    const data = (json && json.data) || {};
    const sourceUrl = consoleDetailUrl(contentId, area, type);

    if (data.errType != null && !data.content && !data.title) {
      const note = describeDetailError(data);
      if (String(kwargs.fallback_public) !== 'false' && kwargs.public_url) {
        const pub = await readPublicPage(page, kwargs.public_url);
        if (pub) {
          const { contacts, phones } = extractContacts(pub.text);
          return [{
            status: Number(data.errType) === 6 ? 'quota_exhausted_public_fallback' : 'denied_public_fallback',
            content_id: contentId,
            title: pub.title,
            published_at: normalizeDate(pub.text),
            buyer: (!isMasked(extractBuyer(pub.text)) && extractBuyer(pub.text)) || buyerFromTitle(pub.title),
            winner: type === 'zhaobiao' ? '' : extractWinner(pub.text),
            amount: extractAmount(pub.text),
            contacts: JSON.stringify(contacts),
            phones: phones.join(','),
            masked: isMasked(pub.text),
            source_url: kwargs.public_url,
            note,
            text: pub.text.slice(0, 8000),
          }];
        }
      }
      return [{
        status: Number(data.errType) === 6 ? 'quota_exhausted' : 'denied',
        content_id: contentId, title: '', published_at: '', buyer: '', winner: '', amount: '',
        contacts: '[]', phones: '', masked: true, source_url: sourceUrl, note, text: '',
      }];
    }

    const d = pickDetail(data);
    const { contacts, phones } = extractContacts(d.text);
    return [{
      status: 'ok',
      content_id: contentId,
      title: d.title,
      published_at: normalizeDate(d.published) || normalizeDate(d.text),
      buyer: extractBuyer(d.text),
      winner: extractWinner(d.text),
      amount: extractAmount(d.text),
      contacts: JSON.stringify(contacts),
      phones: phones.join(','),
      masked: isMasked(d.text),
      source_url: sourceUrl,
      note: '已消耗 1 次会员查看额度',
      text: d.text.slice(0, 8000),
    }];
  },
});
