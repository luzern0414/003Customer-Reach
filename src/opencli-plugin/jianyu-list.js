/**
 * opencli jianyu list <keyword> [--scope title,content] [--limit 50]
 *
 * 剑鱼标讯搜索结果页 DOM 解析（内置 `jianyu search` 走的 /jyapi 接口已改为加密返回 antiEncrypt，实测为空）。
 * Strategy: DOM_STATE —— 打开 /jylab/supsearch/index.html?keywords=&selectType=，解析 .search-result-item。
 * 摘要中常含“发布企业/联系人/联系电话”（未登录可见部分）；列表隐藏区含 采购单位/中标单位/代理机构/预算。
 */
import { cli, Strategy } from '@jackwener/opencli/registry';
import { ArgumentError, AuthRequiredError } from '@jackwener/opencli/errors';
import { cleanText, normalizeDate, clampInt, extractContacts } from './lib/common.js';

const ENTRY = 'https://www.jianyu360.cn/jylab/supsearch/index.html';

const PARSE = `(() => {
  const body = document.body ? document.body.innerText : '';
  if (/请在下图依次点击|请完成验证|图形验证码/.test(body)) return { challenge: true, rows: [] };
  const items = [...document.querySelectorAll('.search-result-item')].filter(e => e.querySelector('.a-i-left'));
  const rows = items.map(it => {
    const fields = {};
    it.querySelectorAll('.l-d-item > span').forEach(sp => {
      const lab = sp.querySelector('.l-d-item-label');
      if (!lab) return;
      const k = lab.innerText.replace(/[：:\\s]/g, '');
      const v = sp.innerText.replace(lab.innerText, '').replace(/获取更多/g, '').trim();
      if (k && v) fields[k] = v;
    });
    const idEl = it.querySelector('[dataid]');
    return {
      title: (it.querySelector('.a-i-left') || {}).innerText || '',
      time: (it.querySelector('.time-text') || {}).innerText || '',
      summary: (it.querySelector('.a-i-detail') || {}).innerText || '',
      tags: [...it.querySelectorAll('.tags .tag')].map(t => t.innerText.trim()).filter(Boolean),
      dataid: idEl ? idEl.getAttribute('dataid') : '',
      fields,
    };
  });
  const totalMatch = body.match(/(?:共|找到|为您找到)[^0-9]{0,8}([0-9,]+)\\s*条/);
  return { challenge: false, total: totalMatch ? Number(totalMatch[1].replace(/,/g, '')) : null, rows };
})()`;

function pick(fields, keys) {
  for (const k of keys) {
    const v = fields[k];
    if (v && !/登录即可|NaN/.test(v)) return cleanText(v);
  }
  return '';
}

cli({
  site: 'jianyu',
  name: 'list',
  access: 'read',
  description: '剑鱼标讯搜索结果页解析（标题/日期/地区/类型/采购单位/中标单位/摘要中的联系人电话）',
  domain: 'www.jianyu360.cn',
  strategy: Strategy.COOKIE,
  browser: true,
  navigateBefore: false,
  siteSession: 'persistent',
  example: 'opencli jianyu list "北京航天广通科技有限公司" -f json',
  args: [
    { name: 'query', required: true, positional: true, help: '关键词或企业名' },
    { name: 'scope', default: 'title,content', help: '搜索范围 selectType：title|title,content|buyer|winner 等' },
    { name: 'limit', type: 'int', default: 50, help: '最多返回条数（每页 50，≤200）' },
  ],
  columns: ['notice_id', 'notice_type', 'title', 'published_at', 'region', 'buyer', 'winner', 'agency', 'budget', 'contacts', 'phones', 'summary', 'url'],
  func: async (page, kwargs) => {
    const keyword = cleanText(kwargs.query);
    if (!keyword) throw new ArgumentError('关键词不能为空');
    const limit = clampInt(kwargs.limit, 50, 1, 200);
    const q = new URLSearchParams({ keywords: keyword, selectType: kwargs.scope || 'title,content', searchGroup: '1' });
    await page.goto(`${ENTRY}?${q}`);
    const rows = [];
    const seen = new Set();
    for (let p = 1; rows.length < limit && p <= Math.ceil(limit / 50); p += 1) {
      let res = null;
      for (let i = 0; i < 6; i += 1) { // 等待列表渲染
        await page.wait(2);
        res = await page.evaluate(PARSE);
        if (res && (res.challenge || res.rows.length)) break;
      }
      if (res && res.challenge) throw new AuthRequiredError('jianyu360.cn', '剑鱼出现人机验证：请在 Edge 中完成验证（或 opencli jianyu login 登录）后重试');
      const list = (res && res.rows) || [];
      for (const r of list) {
        const id = r.dataid || r.title;
        if (seen.has(id)) continue;
        seen.add(id);
        const tags = r.tags || [];
        const { contacts, phones } = extractContacts(r.summary);
        const pubCompany = (cleanText(r.summary).match(/发布企业\s*([一-龥A-Za-z0-9（）()]{4,40}?(?:有限公司|研究院|研究所|大学|学院|医院|中心|局))/) || [])[1] || '';
        const phoneInline = [...cleanText(r.summary).matchAll(/联系电话\s*([0-9]{7,12})/g)].map((m) => m[1]);
        const nameInline = [...cleanText(r.summary).matchAll(/联系人\s*([一-龥]{2,4}?)(?=联系电话|联系方式|电话|手机|\s|$)/g)].map((m) => m[1]);
        rows.push({
          notice_id: r.dataid || '',
          notice_type: tags.find((t) => /公告|询价|成交|中标|招标|预告|结果|采购|变更|合同|意向|拟建/.test(t)) || '',
          title: cleanText(r.title).replace(/^\d+\.\s*/, ''),
          published_at: normalizeDate(r.time) || cleanText(r.time),
          region: tags.find((t) => /[省市区县]|北京|上海|天津|重庆/.test(t) && !/公告/.test(t)) || '',
          buyer: pick(r.fields, ['采购单位', '招标单位', '业主单位']) || pubCompany,
          winner: pick(r.fields, ['中标单位', '中标企业', '成交单位', '中标人']),
          agency: pick(r.fields, ['代理机构', '招标代理机构']),
          budget: pick(r.fields, ['预算金额', '中标金额']),
          contacts: JSON.stringify(contacts.length ? contacts : nameInline.map((n, i) => ({ name: n, phone: phoneInline[i] || '' }))),
          phones: [...new Set([...phones, ...phoneInline])].join(','),
          summary: cleanText(r.summary).slice(0, 300),
          url: r.dataid ? `https://www.jianyu360.cn/nologin/content/${r.dataid}.html` : '',
        });
        if (rows.length >= limit) break;
      }
      if (list.length < 50 || rows.length >= limit) break;
      // 翻页：点击“下一页”
      const moved = await page.evaluate(`(() => { const n = [...document.querySelectorAll('button,a,li,span')].find(e => /^(下一页|>)$/.test((e.innerText||'').trim()) && !e.disabled && !/disabled/.test(e.className)); if (!n) return false; n.click(); return true; })()`);
      if (!moved) break;
    }
    return rows;
  },
});
