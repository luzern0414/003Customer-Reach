/**
 * 非浏览器命令（browser:false）用的 HTTP 工具：带浏览器 UA、超时、编码处理。
 */
import { CommandExecutionError } from '@jackwener/opencli/errors';

export const UA = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/152.0.0.0 Safari/537.36 Edg/152.0.0.0';

export async function httpText(url, { method = 'GET', body, headers = {}, timeout = 30000, encoding } = {}) {
  const ctrl = new AbortController();
  const timer = setTimeout(() => ctrl.abort(), timeout);
  try {
    const res = await fetch(url, {
      method,
      body,
      headers: { 'User-Agent': UA, Accept: 'text/html,application/json,*/*', 'Accept-Language': 'zh-CN,zh;q=0.9', ...headers },
      signal: ctrl.signal,
      redirect: 'follow',
    });
    const buf = Buffer.from(await res.arrayBuffer());
    let enc = encoding;
    if (!enc) {
      const ct = res.headers.get('content-type') || '';
      const m = ct.match(/charset=([\w-]+)/i) || buf.slice(0, 2000).toString('latin1').match(/charset=["']?([\w-]+)/i);
      enc = m ? m[1].toLowerCase() : 'utf-8';
    }
    const text = new TextDecoder(enc === 'gb2312' ? 'gbk' : enc).decode(buf);
    return { status: res.status, text, url: res.url };
  } catch (e) {
    throw new CommandExecutionError(`请求失败 ${url}: ${e && e.message || e}`);
  } finally {
    clearTimeout(timer);
  }
}

export async function httpJson(url, opts = {}) {
  const r = await httpText(url, { ...opts, headers: { Accept: 'application/json, text/plain, */*', ...(opts.headers || {}) } });
  try {
    return { status: r.status, json: JSON.parse(r.text) };
  } catch {
    throw new CommandExecutionError(`返回非 JSON（HTTP ${r.status}）: ${url}\n${r.text.slice(0, 200)}`);
  }
}

export function stripTags(html) {
  return String(html || '')
    .replace(/<script[\s\S]*?<\/script>|<style[\s\S]*?<\/style>/gi, ' ')
    .replace(/<[^>]+>/g, ' ')
    .replace(/&nbsp;/g, ' ')
    .replace(/&lt;/g, '<').replace(/&gt;/g, '>').replace(/&amp;/g, '&').replace(/&quot;/g, '"')
    .replace(/\s+/g, ' ')
    .trim();
}

export function sleep(ms) {
  return new Promise((r) => setTimeout(r, ms));
}
