/**
 * 插件公共工具：文本清洗、日期归一、字段抽取。
 * 注意：本目录不注册命令（无 cli() 调用），只被各命令文件 import。
 */

export function cleanText(value) {
  if (value == null) return '';
  return String(value)
    .replace(/<[^>]+>/g, '')
    .replace(/&nbsp;/g, ' ')
    .replace(/&lt;/g, '<')
    .replace(/&gt;/g, '>')
    .replace(/&amp;/g, '&')
    .replace(/[ 　\s]+/g, ' ')
    .trim();
}

/** '2026-10-08 16:11:03' | '2026.10.08' | '2026年10月08日' -> '2026-10-08' */
export function normalizeDate(value, now = new Date()) {
  const text = cleanText(value);
  const ymd = (d) => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
  const m = text.match(/(20\d{2})[-./年](\d{1,2})[-./月](\d{1,2})/);
  if (m) return `${m[1]}-${m[2].padStart(2, '0')}-${m[3].padStart(2, '0')}`;
  // 相对时间：刚刚 / N分钟前 / N小时前 / 今天 / 昨天 / N天前
  if (/刚刚|分钟前|小时前|今天/.test(text)) return ymd(now);
  if (/昨天/.test(text)) return ymd(new Date(now.getTime() - 86400000));
  const days = text.match(/(\d+)\s*天前/);
  if (days) return ymd(new Date(now.getTime() - Number(days[1]) * 86400000));
  // 只有月-日：取今年，若晚于今天则视为去年
  const md = text.match(/^(\d{1,2})[-./月](\d{1,2})日?$/);
  if (md) {
    let y = now.getFullYear();
    const cand = new Date(y, Number(md[1]) - 1, Number(md[2]));
    if (cand.getTime() > now.getTime() + 86400000) y -= 1;
    return `${y}-${md[1].padStart(2, '0')}-${md[2].padStart(2, '0')}`;
  }
  return '';
}

const ORG_SUFFIX = '(?:有限责任公司|股份有限公司|有限公司|集团公司|集团|公司|研究院|研究所|研究中心|大学|学院|医院|中心|局|委员会|政府|办公室|学校|总队|支队|大队|厂|院|所|站|部|处|社|馆)';

/** 从摘要/正文中抽取采购单位（采购企业 / 采购人 / 采购单位 / 招标人 / 建设单位） */
export function extractBuyer(text) {
  const t = cleanText(text);
  const re = new RegExp(`(?:采购企业|采购人名称|采购人|采购单位名称|采购单位|招标人|招标单位|建设单位|业主单位)\\s*[:：]\\s*([\\u4e00-\\u9fa5A-Za-z0-9（）()·\\-]{2,40}?${ORG_SUFFIX})`);
  const m = t.match(re);
  return m ? m[1] : '';
}

/** 抽取中标/成交供应商 */
export function extractWinner(text) {
  const t = cleanText(text);
  const re = new RegExp(`(?:中标人|中标单位|中标供应商|成交供应商|中标（成交）供应商|成交人|供应商（乙方）|乙方|中标候选人|第一中标候选人|第[一1]名|供应商名称|名称)\\s*[:：]?\\s*([\\u4e00-\\u9fa5A-Za-z0-9（）()·\\-]{2,40}?${ORG_SUFFIX})`);
  const m = t.match(re);
  return m ? m[1] : '';
}

/**
 * 判断关键词（企业名）在公告中的角色：buyer / winner / candidate / mentioned
 * 依据：关键词前 40 字内出现的角色标记。
 */
export function inferRole(text, keyword, buyer, winner) {
  if (!keyword) return '';
  const t = cleanText(text);
  if (buyer && buyer.includes(keyword)) return 'buyer';
  if (winner && winner.includes(keyword)) return 'winner';
  const idx = t.indexOf(keyword);
  if (idx < 0) return 'related'; // 全文命中但不在摘要中
  const before = t.slice(Math.max(0, idx - 40), idx);
  const near = before.slice(-8);
  // 标签须紧挨企业名（“满足招标人要求 2 某公司”这种评审表文本不算）；摘要已给出别家采购方时不据此判为采购方
  if ((!buyer || buyer.includes(keyword)) && /(采购企业|采购人|采购单位|招标人|招标单位|建设单位|业主(?:单位)?)\s*(?:名称)?\s*[:：]?\s*$/.test(before)) return 'buyer';
  if (/(拟从|拟向|从厂家|向厂家)[^。；;]{0,6}$/.test(before)) return 'winner'; // 直接采购/单一来源：拟从某厂家采购
  if (/(第[二三四五2-9]名|候选人)\s*[:：]?\s*$/.test(near) || /(^|\s)[2-9]\s*$/.test(near)) return 'candidate';
  const otherWinner = winner && !winner.includes(keyword);
  if (!otherWinner && /(中标|成交|供应商|乙方|第[一1]名)[^。；;]{0,20}$/.test(before)) return 'winner';
  if (!otherWinner && /\]\s*$/.test(before) && /^\s*\S{0,30}\s*特此公告/.test(t.slice(idx + keyword.length, idx + keyword.length + 40))) return 'winner';
  if (/(^|\s)1\s*$/.test(near)) return 'candidate'; // 评审排名表第 1 行
  return otherWinner ? 'candidate' : 'mentioned';
}

/** 抽取金额（预算/中标金额），返回原文片段 */
export function extractAmount(text) {
  const t = cleanText(text);
  const m = t.match(/(?:预算金额|采购预算|中标金额|成交金额|中标价|合同金额|最高限价)[^0-9]{0,12}([0-9][0-9,.]*\s*(?:万元|元|万)?)/);
  return m ? m[1].replace(/\s+/g, '') : '';
}

/** 抽取联系人与电话（用于详情页；号码打码时原样返回） */
export function extractContacts(text) {
  const t = cleanText(text);
  const contacts = [];
  const re = /(?:联系人|询价人名称|询价人|项目联系人|采购人联系人)\s*[:：]\s*([一-龥A-Za-z*]{1,10}?)(?=[\s,，;；]|联系|电话|手机|$)[\s,，;；]*(?:(?:联系电话|电话|手机|询价人电话|联系方式)\s*[:：]\s*([0-9*\-—()（） ]{5,25}))?/g;
  let m;
  while ((m = re.exec(t)) && contacts.length < 10) {
    contacts.push({ name: m[1], phone: (m[2] || '').trim() });
  }
  const phones = [...t.matchAll(/(?:联系电话|电话|手机|询价人电话|联系方式)\s*[:：]\s*([0-9*\-—()（） ]{5,25})/g)].map((x) => x[1].trim());
  return { contacts, phones: [...new Set(phones)] };
}

/** 招标代理/项目管理/咨询类机构（不应计为采购方） */
export function isAgency(name) {
  return /招标代理|招标有限|招标集团|招标股份|招标中心|项目管理|工程管理|造价咨询|工程咨询|采购代理|交易中心|采购中心/.test(String(name || ''));
}

export function isMasked(value) {
  return /\*{3,}|点击登录查看/.test(String(value || ''));
}

export function clampInt(value, def, min, max) {
  const n = Number(value);
  if (!Number.isFinite(n)) return def;
  return Math.max(min, Math.min(max, Math.trunc(n)));
}
