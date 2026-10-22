/**
 * 乙方宝 / 千里马 会员控制台（qiye.qianlima.com/new_qd_yfbsite）共享逻辑。
 *
 * Strategy: COOKIE_API（在已登录的控制台页面上下文中 fetch 同源 API）
 * Contract: internal（站内接口，2026-10-08 实测；接口变更时按 docs/11 的排障步骤更新）
 * Evidence:
 *   - 登录态：cookie `Admin-Token` + localStorage `YFB-OpenId`（JSON：{"<key>":{"openId":"..."}}）
 *   - 搜索：GET /api/search?pageFrom=zhaobiao|zhongbiao|caigou|nijian&keyword=&areaIds=&timeOption=...
 *   - 前期商机：GET /api/subZhaobiao/queryPreProjectInfo?keywords=
 *   - 详情：GET /api/subZhaobiao/zbDetail?contentId=&pageFrom=&areaId=   （消耗会员查看额度）
 *   - 账号：GET /api/system/members
 */
import { AuthRequiredError, CommandExecutionError } from '@jackwener/opencli/errors';
import { cleanText } from './common.js';

export const DOMAIN = 'qiye.qianlima.com';
export const ORIGIN = 'https://qiye.qianlima.com';
export const CONSOLE_URL = `${ORIGIN}/new_qd_yfbsite/#/infoCenter/search`;
export const API_BASE = `${ORIGIN}/new_qd_yfbsite/api`;

/** 控制台 Tab -> pageFrom */
export const NOTICE_TYPES = {
  zhaobiao: '招标',
  zhongbiao: '中标',
  caigou: '采购意向',
  nijian: '拟在建',
  qianqi: '前期商机',
};

/** 天数 -> timeOption（实测：1=近7天 2=近一个月 5=近三个月 3=近六个月 4=更长/一年） */
export function daysToTimeOption(days) {
  const d = Number(days) || 30;
  if (d <= 7) return '1';
  if (d <= 31) return '2';
  if (d <= 92) return '5';
  if (d <= 183) return '3';
  return '4';
}

/** 确保当前 tab 在控制台同源页面上，返回 { openid, hasToken } */
export async function ensureSession(page, { navigate = true } = {}) {
  let href = '.';
  try {
    href = String(await page.evaluate('location.href'));
  } catch {
    href = '.';
  }
  if (navigate && !href.startsWith(ORIGIN)) {
    await page.goto(CONSOLE_URL);
    await page.wait(3);
  }
  const session = await page.evaluate(`(() => {
    let raw = localStorage.getItem('YFB-OpenId') || '';
    let openid = '';
    try {
      const obj = JSON.parse(raw);
      const first = obj && typeof obj === 'object' ? Object.values(obj)[0] : null;
      openid = (first && first.openId) || (typeof obj === 'string' ? obj : '');
    } catch (e) { openid = raw; }
    const hasToken = document.cookie.split('; ').some(c => c.startsWith('Admin-Token=') && c.length > 'Admin-Token='.length);
    return { openid, hasToken, href: location.href };
  })()`);
  if (!session || !session.openid || !session.hasToken) {
    throw new AuthRequiredError(DOMAIN, '乙方宝未登录：请运行 `opencli yfbzb login` 并在 Edge 中完成登录（扫码或账号密码）');
  }
  return session;
}

/** 在页面上下文中调用控制台 API（同源 + cookie） */
export async function apiGet(page, path, params = {}) {
  const session = await ensureSession(page);
  const qs = new URLSearchParams({ ...params, openid: session.openid }).toString();
  const url = `${API_BASE}${path}?${qs}`;
  const res = await page.evaluate(`(async () => {
    try {
      const r = await fetch(${JSON.stringify(url)}, { credentials: 'include', headers: { Accept: 'application/json, text/plain, */*' } });
      const text = await r.text();
      return { status: r.status, text };
    } catch (e) {
      return { status: 0, text: String(e && e.message || e) };
    }
  })()`);
  if (!res || res.status === 0) {
    throw new CommandExecutionError(`乙方宝接口请求失败: ${path} ${res && res.text}`);
  }
  if (res.status === 401 || res.status === 403) {
    throw new AuthRequiredError(DOMAIN, `乙方宝登录已失效（HTTP ${res.status}）`);
  }
  let json;
  try {
    json = JSON.parse(res.text);
  } catch {
    if (/登录|login/i.test(res.text)) throw new AuthRequiredError(DOMAIN, '乙方宝登录已失效（返回登录页）');
    throw new CommandExecutionError(`乙方宝接口返回非 JSON: ${path} HTTP ${res.status}`);
  }
  if (json && (json.code === 401 || json.code === 403 || /未登录|登录失效|请登录/.test(json.msg || ''))) {
    throw new AuthRequiredError(DOMAIN, `乙方宝登录已失效：${json.msg}`);
  }
  return json;
}

/** 控制台详情页 URL */
export function consoleDetailUrl(contentId, areaId, pageFrom = 'zhaobiao') {
  return `${ORIGIN}/new_qd_yfbsite/#/infoCenter/infoDetail/${contentId}/${areaId || '2'}/${pageFrom}`;
}

/** 公开 SEO 详情页（仅招标公告；字段部分打码，不消耗额度） */
export function publicDetailUrl(contentId, updateTime) {
  const d = String(updateTime || '').match(/(20\d{2})-(\d{2})-(\d{2})/);
  if (!d) return '';
  return `https://www.yfbzb.com/inviteBid/detail/${d[1]}${d[2]}${d[3]}_${contentId}.html`;
}

/** zbDetail 的 errType 含义（实测 6 = 当日查看额度已用完） */
export function describeDetailError(data) {
  const t = Number(data && data.errType);
  const map = {
    6: `当日详情查看额度已用完（limitNum=${data && data.limitNum}），需开通/升级会员或次日再试`,
  };
  return map[t] || `详情不可查看（errType=${t}，refuseArea=${cleanText(data && data.refuseArea)}，payLevels=${data && data.payLevels}）`;
}
