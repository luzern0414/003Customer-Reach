import type { JobStatus, LeadStatus } from './types'

export const LEAD_STATUS: Record<LeadStatus, { label: string; tone: string }> = {
  new: { label: '新线索', tone: 'brand' },
  verifying: { label: '待核验', tone: 'warn' },
  contacted: { label: '已联系', tone: 'teal' },
  following: { label: '持续跟进', tone: 'purple' },
  won: { label: '已成交', tone: 'ok' },
  invalid: { label: '无效', tone: 'grey' },
}

export const JOB_STATUS: Record<JobStatus, { label: string; tone: string }> = {
  queued: { label: '排队中', tone: 'grey' },
  running: { label: '运行中', tone: 'brand' },
  awaiting_user: { label: '等待处理', tone: 'warn' },
  awaiting_input: { label: '等待补充', tone: 'warn' },
  replanning: { label: '重新规划', tone: 'brand' },
  paused: { label: '已暂停', tone: 'grey' },
  completed: { label: '完成', tone: 'ok' },
  partial: { label: '部分完成', tone: 'signal' },
  failed: { label: '失败', tone: 'danger' },
}

export const KIND_TONE: Record<string, string> = {
  intent: 'signal', tender: 'signal', change: 'warn', candidate: 'purple', award: 'teal', contract: 'teal', other: 'grey',
}

export const FOLLOWUP_KIND: Record<string, string> = { note: '笔记', call: '电话', email: '邮件', visit: '拜访' }
export const FEEDBACK_KIND: Record<string, string> = { relevant: '相关客户', not_buyer: '不是买家', wrong: '信息有误', stale: '信息失效' }

/** 金额（元）显示为“38.00 万元”或“9,800 元”；空值为“—”。 */
export function money(value: number | null | undefined): string {
  if (value === null || value === undefined) return '—'
  if (value >= 10000) return `${(value / 10000).toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })} 万元`
  return `${value.toLocaleString('zh-CN')} 元`
}

/** UTC ISO → 本地 “YYYY-MM-DD” 与 “HH:mm”。 */
export function dateParts(iso: string | null | undefined): { date: string; time: string } {
  if (!iso) return { date: '—', time: '' }
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return { date: iso.slice(0, 10), time: '' }
  const pad = (n: number) => String(n).padStart(2, '0')
  return { date: `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`, time: `${pad(d.getHours())}:${pad(d.getMinutes())}` }
}

export function day(iso: string | null | undefined): string {
  return dateParts(iso).date
}

export function duration(ms: number | undefined): string {
  if (!ms) return '0 秒'
  const s = Math.round(ms / 1000)
  return s < 60 ? `${s} 秒` : `${Math.floor(s / 60)} 分 ${s % 60} 秒`
}

/** 会话分组：今天、昨天、更早。 */
export function dayGroup(iso: string): string {
  const today = dateParts(new Date().toISOString()).date
  const yesterday = dateParts(new Date(Date.now() - 86400000).toISOString()).date
  const date = dateParts(iso).date
  return date === today ? '今天' : date === yesterday ? '昨天' : '更早'
}

/** 公告原文里的截止时间（2026年11月17日 09点30分 等）统一成 2026-11-17 09:30。 */
export function deadline(text: string | null | undefined): string {
  if (!text) return ''
  const m = text.match(/(\d{4})\s*[年\-/.]\s*(\d{1,2})\s*[月\-/.]\s*(\d{1,2})\s*日?(?:\s*(\d{1,2})\s*[:：时点]\s*(\d{1,2})?)?/)
  if (!m) return text
  const pad = (v: string) => v.padStart(2, '0')
  const date = `${m[1]}-${pad(m[2])}-${pad(m[3])}`
  return m[4] ? `${date} ${pad(m[4])}:${pad(m[5] || '0')}` : date
}

/** 金额（元）→ 万元数字“475.10”，用于表头已写单位的列；空值为“—”。 */
export function wan(value: number | null | undefined): string {
  if (value === null || value === undefined) return '—'
  return (value / 10000).toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

/** 截止时间：短格式“11-13 09:30”（跨年带年份）与剩余天数；7 天内提醒，3 天内紧急。 */
export function due(text: string | null | undefined): { short: string; left: number | null; label: string; tone: '' | 'warn' | 'danger' } {
  const full = deadline(text)
  const m = full.match(/^(\d{4})-(\d{2})-(\d{2})(?: (\d{2}:\d{2}))?$/)
  if (!m) return { short: full, left: null, label: '', tone: '' }
  const now = new Date()
  const today = new Date(now.getFullYear(), now.getMonth(), now.getDate()).getTime()
  const left = Math.round((new Date(Number(m[1]), Number(m[2]) - 1, Number(m[3])).getTime() - today) / 86400000)
  const short = `${Number(m[1]) === now.getFullYear() ? '' : `${m[1]}-`}${m[2]}-${m[3]}${m[4] ? ` ${m[4]}` : ''}`
  const label = left < 0 ? '已截止' : left === 0 ? '今天截止' : `剩 ${left} 天`
  return { short, left, label, tone: left < 0 ? '' : left <= 3 ? 'danger' : left <= 7 ? 'warn' : '' }
}

/** 日期“2026-10-23”→“10-23”（跨年保留年份）。 */
export function monthDay(text: string | null | undefined): string {
  if (!text) return '—'
  const m = text.match(/^(\d{4})-(\d{2})-(\d{2})/)
  if (!m) return text
  return Number(m[1]) === new Date().getFullYear() ? `${m[2]}-${m[3]}` : `${m[1]}-${m[2]}-${m[3]}`
}

/** 任务问题里的系统报错原文（EPERM、堆栈等）换成用户能看懂的一句话。 */
export function plainProblem(text: string): string {
  return text.replace(/[:：]\s*[^：:]*?(EPERM|EBUSY|ENOENT|Error|rename|Traceback|errno|\bat\s+\w+).*$/i, '：读取失败，继续研究时会重试')
}

/** 状态语气 → 小圆点类名。 */
export const TONE_DOT: Record<string, string> = { ok: 'ok', signal: 'warn', warn: 'warn', danger: 'danger', brand: 'run', teal: 'ok', purple: '', grey: '' }
