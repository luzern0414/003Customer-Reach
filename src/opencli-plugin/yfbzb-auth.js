/**
 * opencli yfbzb whoami / opencli yfbzb login
 * 登录检测：控制台 cookie Admin-Token + localStorage YFB-OpenId + /api/system/members。
 * login：打开控制台（未登录时即为登录页），前台等待用户扫码/输入账号，轮询直到登录成功。
 */
import { cli, Strategy } from '@jackwener/opencli/registry';
import { AuthRequiredError, TimeoutError } from '@jackwener/opencli/errors';
import { DOMAIN, CONSOLE_URL, apiGet, ensureSession } from './lib/yfbzb.js';

const COLUMNS = ['logged_in', 'site', 'member_id', 'member_type', 'level', 'is_vip', 'pay_areas', 'login_source'];

async function probeIdentity(page, navigate = true) {
  await ensureSession(page, { navigate });
  const json = await apiGet(page, '/system/members');
  const d = (json && json.data) || {};
  if (!d.memberId && !d.openId) {
    throw new AuthRequiredError(DOMAIN, '乙方宝账号信息为空，视为未登录');
  }
  return {
    logged_in: true,
    site: 'yfbzb',
    member_id: String(d.memberId ?? ''),
    member_type: d.memberType ?? '',
    level: d.level ?? '',
    is_vip: Boolean(d.isMemberVip),
    pay_areas: Array.isArray(d.payAreas) ? d.payAreas.join(',') : '',
    login_source: d.loginSource ?? '',
  };
}

cli({
  site: 'yfbzb',
  name: 'whoami',
  access: 'read',
  description: '检查乙方宝/千里马会员控制台登录状态',
  domain: DOMAIN,
  strategy: Strategy.COOKIE,
  browser: true,
  navigateBefore: false,
  siteSession: 'persistent',
  args: [],
  columns: COLUMNS,
  func: async (page) => probeIdentity(page, true),
});

cli({
  site: 'yfbzb',
  name: 'login',
  access: 'write',
  description: '在 Edge 中打开乙方宝控制台登录页，等待用户完成登录（扫码/账号密码）',
  domain: DOMAIN,
  strategy: Strategy.COOKIE,
  browser: true,
  navigateBefore: false,
  defaultWindowMode: 'foreground',
  siteSession: 'persistent',
  args: [
    { name: 'timeout', type: 'int', default: 600, help: '等待用户登录的最长秒数' },
  ],
  columns: ['status', ...COLUMNS],
  func: async (page, kwargs) => {
    try {
      return { status: 'already_logged_in', ...(await probeIdentity(page, true)) };
    } catch (error) {
      if (!(error instanceof AuthRequiredError)) throw error;
    }
    await page.goto(CONSOLE_URL);
    const timeout = Number(kwargs.timeout) || 600;
    const deadline = Date.now() + timeout * 1000;
    let last = '';
    while (Date.now() < deadline) {
      await page.wait(3);
      try {
        // 登录过程中不要强制跳转，避免打断用户操作
        return { status: 'login_complete', ...(await probeIdentity(page, false)) };
      } catch (error) {
        if (!(error instanceof AuthRequiredError)) throw error;
        last = error.message;
      }
    }
    throw new TimeoutError('yfbzb login', timeout, `请在 Edge 中完成乙方宝登录后重试。最后状态：${last}`);
  },
});
