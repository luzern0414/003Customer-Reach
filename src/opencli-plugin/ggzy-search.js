/**
 * opencli ggzy search <keyword> [--days 90] [--classify 00] [--timeout 300] [--limit 60]
 *
 * 全国公共资源交易平台（www.ggzy.gov.cn/deal/dealList.html）。
 * 页面是 Vue 应用，查询接口 POST /information/pubTradingInfo/getTradList；服务端返回 code=829 时页面弹出图形验证码。
 * Strategy: UI_SELECTOR + INTERCEPT —— 在真实页面中填写关键词与时间、点击“搜索”，拦截页面自身的 getTradList 响应。
 * 弹出验证码时：窗口切到前台，等待用户在 Edge 中输入验证码并确认，随后自动继续读取（不做自动识别）。
 */
import { cli, Strategy } from '@jackwener/opencli/registry';
import { ArgumentError, CommandExecutionError, TimeoutError } from '@jackwener/opencli/errors';
import { cleanText, normalizeDate, clampInt } from './lib/common.js';

// 注意：不带查询参数直接 GET dealList.html 会返回 405
const LIST = 'https://www.ggzy.gov.cn/deal/dealList.html?HEADER_DEAL_TYPE=02';

const VM = `[...document.querySelectorAll('*')].find(e => e.__vue__).__vue__.$root`;

function fmt(d) {
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
}

/** 读取当前页状态：records / ttlrow / loading / 是否弹出验证码 */
const STATE = `(() => {
  const vm = ${VM};
  const m = document.getElementById('verifyCodeModal');
  const modal = !!m && getComputedStyle(m).display !== 'none';
  return { loading: !!vm.loading, ttlrow: vm.ttlrow, page: vm.currentPage, ttlpage: vm.ttlpage, captcha: modal || (!!vm.captchaToken && !vm.records.length), records: JSON.parse(JSON.stringify(vm.records || [])) };
})()`;

async function waitRecords(page, timeoutSec) {
  const deadline = Date.now() + timeoutSec * 1000;
  let sawCaptcha = false;
  while (Date.now() < deadline) {
    await page.wait(2);
    const st = await page.evaluate(STATE);
    if (st.captcha) { sawCaptcha = true; continue; } // 等待用户在 Edge 中输入验证码
    if (!st.loading && st.ttlrow >= 0 && (st.records.length || st.ttlrow === 0)) return st;
  }
  throw new TimeoutError('ggzy search', timeoutSec, sawCaptcha ? '请在 Edge 的全国公共资源交易平台页面输入验证码并确认' : 'ggzy 未返回结果');
}

cli({
  site: 'ggzy',
  name: 'search',
  access: 'read',
  description: '全国公共资源交易平台交易公开检索（出现验证码时等待用户在 Edge 中输入）',
  domain: 'www.ggzy.gov.cn',
  strategy: Strategy.PUBLIC,
  browser: true,
  navigateBefore: false,
  defaultWindowMode: 'foreground',
  siteSession: 'persistent',
  example: 'opencli ggzy search "北京航天广通科技有限公司" --days 90 -f json',
  args: [
    { name: 'query', required: true, positional: true, help: '关键词或企业名' },
    { name: 'days', type: 'int', default: 90, help: '时间范围（天，平台最长支持约三个月/自定义区间）' },
    { name: 'classify', default: '00', help: '业务类型 DEAL_CLASSIFY：00=全部 01=工程建设 02=政府采购 03=土地 04=国有产权' },
    { name: 'timeout', type: 'int', default: 300, help: '等待用户输入验证码的最长秒数' },
    { name: 'limit', type: 'int', default: 60, help: '最多返回条数' },
  ],
  columns: ['title', 'published_at', 'region', 'platform', 'classify', 'stage', 'url'],
  func: async (page, kwargs) => {
    const keyword = cleanText(kwargs.query);
    if (!keyword) throw new ArgumentError('关键词不能为空');
    const limit = clampInt(kwargs.limit, 60, 1, 200);
    const timeoutSec = clampInt(kwargs.timeout, 300, 30, 1800);
    const end = new Date();
    const begin = new Date(Date.now() - clampInt(kwargs.days, 90, 1, 365) * 86400000);
    await page.goto(LIST);
    await page.wait(4);
    const ok = await page.evaluate(`(() => ({ title: document.title, vue: [...document.querySelectorAll('*')].some(e => e.__vue__) }))()`);
    if (!ok.vue) throw new CommandExecutionError(`ggzy 页面不可用：${ok.title}（稍后重试；上层会改用 Exa 补充）`);
    await page.evaluate(`(() => {
      const vm = ${VM};
      vm.myFindTxt = ${JSON.stringify(keyword)};
      vm.myDealClassify = ${JSON.stringify(String(kwargs.classify || '00'))};
      vm.myDealStage = vm.myDealClassify === '00' ? '0000' : vm.myDealClassify + '00';
      vm.myDealTime = '06';
      vm.timeBegin = '${fmt(begin)}';
      vm.timeEnd = '${fmt(end)}';
      vm.records = []; vm.ttlrow = -1;
      vm.cmd_find();
      return true;
    })()`);
    const rows = [];
    let st = await waitRecords(page, timeoutSec);
    for (let p = 1; ; p += 1) {
      for (const r of st.records) {
        rows.push({
          title: cleanText(r.title),
          published_at: normalizeDate(r.publishTime),
          region: cleanText([r.provinceText, r.cityText].filter(Boolean).join('-')),
          platform: cleanText(r.transactionSourcesPlatformText),
          classify: cleanText(r.businessTypeText),
          stage: cleanText(r.informationTypeText),
          url: r.url ? `https://www.ggzy.gov.cn${r.url}` : '',
        });
        if (rows.length >= limit) return rows;
      }
      if (!st.ttlpage || p >= st.ttlpage) break;
      await page.evaluate(`(() => { const vm = ${VM}; vm.records = []; vm.ttlrow = -1; vm.currentPage = ${p + 1}; vm.getList(); return true; })()`);
      st = await waitRecords(page, timeoutSec);
    }
    return rows;
  },
});
