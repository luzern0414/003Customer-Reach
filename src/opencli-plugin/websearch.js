/**
 * opencli websearch baidu|sogou <query> [--limit 10]
 *
 * 中文网页检索兜底：Exa 限流或不可用时，在 Edge 中打开百度/搜狗结果页并解析自然结果。
 * Strategy: PUBLIC + DOM 解析；广告（推广）结果剔除；出现安全验证页返回 VERIFICATION_REQUIRED，不尝试绕过。
 * 百度自然结果的真实地址在 mu 属性；搜狗只给跳转链接（/link?url=），真实地址由上层解析跳转页取得。
 */
import { cli, Strategy } from '@jackwener/opencli/registry';
import { ArgumentError, CommandExecutionError } from '@jackwener/opencli/errors';
import { cleanText, normalizeDate, clampInt } from './lib/common.js';

const ENGINES = {
  baidu: {
    url: (q, n) => `https://www.baidu.com/s?wd=${encodeURIComponent(q)}&rn=${Math.min(50, n + 5)}&ie=utf-8`,
    parse: `(() => {
      const body = document.body ? document.body.innerText.slice(0, 400) : '';
      if (/安全验证|百度安全验证|网络不给力/.test(document.title + body) || /wappass\.baidu\.com/.test(location.href)) return { blocked: true, rows: [] };
      const rows = [];
      for (const el of document.querySelectorAll('#content_left > div')) {
        const cls = el.className || '';
        if (/ec_|tuiguang|result-op-ad/.test(cls) || el.querySelector('[data-tuiguang], .ec-tuiguang')) continue;
        const a = el.querySelector('h3 a');
        if (!a) continue;
        const url = el.getAttribute('mu') || '';
        const abs = el.querySelector('.c-abstract, [class*="content-right"], .c-span-last, [class*="summary"]');
        const date = el.querySelector('.c-color-gray2, [class*="time"]');
        rows.push({ title: a.innerText, url: url || a.href, redirect: url ? '' : a.href, snippet: abs ? abs.innerText : '', date: date ? date.innerText : '' });
      }
      return { blocked: false, rows };
    })()`,
  },
  sogou: {
    url: (q) => `https://www.sogou.com/web?query=${encodeURIComponent(q)}`,
    parse: `(() => {
      const body = document.body ? document.body.innerText.slice(0, 400) : '';
      if (/验证码|安全验证|请输入验证码/.test(document.title + body) || /antispider/.test(location.href)) return { blocked: true, rows: [] };
      const rows = [];
      for (const el of document.querySelectorAll('.vrwrap, .rb')) {
        if (el.querySelector('.biz_rb, [class*="ad-"]')) continue;
        const a = el.querySelector('h3 a');
        if (!a) continue;
        const cite = el.querySelector('cite, .citeurl, [class*="cite"]');
        const abs = el.querySelector('.ft, .space-txt, .star-wiki, [class*="text-layout"], p');
        rows.push({ title: a.innerText, url: a.href, redirect: /sogou\.com\/link/.test(a.href) ? a.href : '', snippet: abs ? abs.innerText : '', date: cite ? cite.innerText : '' });
      }
      return { blocked: false, rows };
    })()`,
  },
};

cli({
  site: 'websearch',
  name: 'run',
  access: 'read',
  description: '中文网页检索兜底（百度/搜狗自然结果，剔除推广），返回标题、地址、摘要、日期',
  domain: 'www.baidu.com',
  strategy: Strategy.PUBLIC,
  browser: true,
  navigateBefore: false,
  example: 'opencli websearch run baidu "北京航天广通科技有限公司 招标" --limit 10 -f json',
  args: [
    { name: 'engine', required: true, positional: true, help: 'baidu | sogou' },
    { name: 'query', required: true, positional: true, help: '检索词' },
    { name: 'limit', type: 'int', default: 10, help: '最多返回条数（≤30）' },
  ],
  columns: ['engine', 'title', 'url', 'redirect', 'snippet', 'published_at'],
  func: async (page, kwargs) => {
    const engine = ENGINES[String(kwargs.engine || '').toLowerCase()];
    if (!engine) throw new ArgumentError('engine 只能是 baidu 或 sogou');
    const query = cleanText(kwargs.query);
    if (!query) throw new ArgumentError('检索词不能为空');
    const limit = clampInt(kwargs.limit, 10, 1, 30);
    await page.goto(engine.url(query, limit));
    await page.wait(2);
    const res = await page.evaluate(engine.parse);
    if (res && res.blocked) throw new CommandExecutionError('VERIFICATION_REQUIRED: 搜索引擎要求安全验证，本次检索未取得结果');
    const seen = new Set();
    const rows = [];
    for (const r of (res && res.rows) || []) {
      const title = cleanText(r.title);
      const url = String(r.url || '');
      if (!title || !/^https?:\/\//.test(url) || seen.has(url)) continue;
      seen.add(url);
      rows.push({ engine: String(kwargs.engine).toLowerCase(), title, url, redirect: String(r.redirect || ''),
        snippet: cleanText(r.snippet).slice(0, 400), published_at: normalizeDate(r.date) });
      if (rows.length >= limit) break;
    }
    return rows;
  },
});
