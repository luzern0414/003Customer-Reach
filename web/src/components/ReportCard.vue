<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { get } from '../api'
import { JOB_STATUS, LEAD_STATUS, deadline, duration, money } from '../format'
import type { JobStatus, LeadStatus } from '../types'
import Icon from './Icon.vue'

interface Report {
  status: JobStatus
  mode: string
  elapsed_ms: number
  model_calls: number
  first_result_ms: number | null
  counts: Record<'searches' | 'rounds' | 'candidates' | 'read' | 'read_failed' | 'notices' | 'companies' | 'buyers' | 'leads' | 'contacts' | 'profiled', number>
  quality: { checked: number; kept: number; rate: number | null; notice_total: number; complete: Record<'budget' | 'deadline' | 'items' | 'contact', number>; buyers: number; profiled: number }
  sites: { site: string; name: string; searches: number; ok: number; links: number }[]
  problems: string[]
  top: { company_id: string; name: string; lead_id: string | null; score: number | null; status: LeadStatus | null; notice: string; notice_url: string; kind: string; items: string; budget: number | null; deadline: string; published_on: string; contact: boolean; contact_person: string; contact_phone: string; region: string; profiled: boolean }[]
  records: { title: string; url: string; date: string; role: string; counterpart: string; amount: number | null }[]
}

const props = defineProps<{ jobId: string; version?: number }>()
const report = ref<Report | null>(null)
const failed = ref(false)

watch(() => [props.jobId, props.version], async () => {
  failed.value = false
  try { report.value = await get<Report>(`/jobs/${props.jobId}/report`) } catch { failed.value = true }
}, { immediate: true })

const buyersMode = computed(() => report.value?.mode !== 'company')
const stats = computed(() => {
  const c = report.value?.counts
  if (!c) return []
  return buyersMode.value
    ? [{ label: '新增线索', value: c.leads, icon: 'lead' }, { label: '采购方', value: c.buyers, icon: 'customers' },
       { label: '核验公告', value: c.notices, icon: 'doc' }, { label: '取得联系人', value: c.contacts, icon: 'phone' },
       { label: '补充工商', value: c.profiled, icon: 'company' }, { label: '涉及企业', value: c.companies, icon: 'link' }]
    : [{ label: '核验公告', value: c.notices, icon: 'doc' }, { label: '涉及企业', value: c.companies, icon: 'link' },
       { label: '检索次数', value: c.searches, icon: 'search' }, { label: '阅读原文', value: c.read, icon: 'note' }]
})
const completeness = computed(() => {
  const q = report.value?.quality
  if (!q || !q.notice_total) return []
  return [
    { label: '预算或金额', n: q.complete.budget }, { label: '截止时间', n: q.complete.deadline },
    { label: '采购标的', n: q.complete.items }, { label: '联系人', n: q.complete.contact },
  ].map((x) => ({ ...x, total: q.notice_total, pct: Math.round((x.n / q.notice_total) * 100) }))
})
const resultCount = computed(() => (buyersMode.value ? report.value?.top.length : report.value?.records.length) || 0)
const rate = computed(() => (report.value?.quality.rate === null || report.value?.quality.rate === undefined ? null : Math.round(report.value.quality.rate * 100)))
const rateTone = computed(() => (rate.value === null ? 'grey' : rate.value >= 85 ? 'ok' : rate.value >= 60 ? 'signal' : 'danger'))
</script>

<template>
  <section v-if="report" class="report">
    <header class="r-head">
      <span class="r-title"><Icon name="analysis" :size="18" />研究报告</span>
      <span class="tag" :class="JOB_STATUS[report.status].tone">{{ JOB_STATUS[report.status].label }}</span>
      <span class="r-meta">总用时 {{ duration(report.elapsed_ms) }}<template v-if="report.first_result_ms"> · 首批结果 {{ duration(report.first_result_ms) }}</template> · 模型调用 {{ report.model_calls }} 次</span>
    </header>

    <div class="r-stats">
      <div v-for="s in stats" :key="s.label" class="r-stat">
        <span class="r-stat-icon"><Icon :name="s.icon" :size="16" /></span>
        <span class="r-num">{{ s.value }}</span><span class="r-label">{{ s.label }}</span>
      </div>
    </div>

    <div class="r-grid">
      <div class="r-block">
        <div class="r-sub">数据质量</div>
        <div class="rate">
          <span class="rate-num" :class="rateTone">{{ rate === null ? '—' : rate + '%' }}</span>
          <span class="rate-text">原文核验通过率<br><span class="muted">{{ report.quality.kept }} / {{ report.quality.checked }} 个字段逐字对上原文</span></span>
        </div>
        <div v-for="c in completeness" :key="c.label" class="bar-row">
          <span class="bar-label">{{ c.label }}</span>
          <span class="bar-track"><span class="bar-fill" :style="{ width: c.pct + '%' }" /></span>
          <span class="bar-value num">{{ c.n }} / {{ c.total }}</span>
        </div>
        <div v-if="buyersMode && report.quality.buyers" class="bar-row">
          <span class="bar-label">工商信息</span>
          <span class="bar-track"><span class="bar-fill alt" :style="{ width: Math.round((report.quality.profiled / report.quality.buyers) * 100) + '%' }" /></span>
          <span class="bar-value num">{{ report.quality.profiled }} / {{ report.quality.buyers }}</span>
        </div>
      </div>
      <div class="r-block">
        <div class="r-sub">检索过程</div>
        <div v-for="s in report.sites" :key="s.site" class="site-row">
          <span class="site-name">{{ s.name }}</span>
          <span class="muted num">检索 {{ s.searches }} 次 · {{ s.links }} 条</span>
          <span class="tag" :class="s.ok === s.searches ? 'ok' : s.ok ? 'signal' : 'danger'">{{ s.ok === s.searches ? '正常' : s.ok ? '部分' : '失败' }}</span>
        </div>
        <div class="site-row"><span class="site-name fixed">筛选与阅读</span><span class="grow" />
          <span class="muted num">{{ report.counts.rounds }} 轮 · 候选 {{ report.counts.candidates }} · 阅读 {{ report.counts.read }} 篇</span>
          <span class="tag" :class="report.counts.read_failed ? 'warn' : 'ok'">{{ report.counts.read_failed ? `${report.counts.read_failed} 篇未读到` : '全部读到' }}</span></div>
        <div v-if="report.problems.length" class="problems">
          <div v-for="p in report.problems.slice(0, 4)" :key="p" class="problem"><Icon name="alert" :size="14" /><span>{{ p }}</span></div>
          <div v-if="report.problems.length > 4" class="muted small">另有 {{ report.problems.length - 4 }} 项</div>
        </div>
      </div>
    </div>

    <div v-if="resultCount" class="r-result">
      <div class="r-result-head">
        <span class="r-sub">{{ buyersMode ? '采购单位清单' : '采购与中标记录' }}</span>
        <span class="muted num">{{ resultCount }} 条</span>
        <span class="r-actions" v-if="buyersMode && report.counts.leads">
          <RouterLink to="/leads" class="el-button el-button--primary el-button--small"><Icon name="lead" :size="14" /><span>查看全部线索</span></RouterLink>
          <a href="/api/leads/export" class="el-button el-button--small"><Icon name="download" :size="14" /><span>导出</span></a>
        </span>
      </div>
    <div v-if="buyersMode && report.top.length" class="r-table">
      <table>
        <thead><tr><th>采购单位</th><th>采购内容</th><th>预算 / 金额</th><th>截止时间</th><th>联系人</th><th>评分</th></tr></thead>
        <tbody>
          <tr v-for="t in report.top" :key="t.company_id">
            <td class="left">
              <RouterLink :to="t.lead_id ? `/leads/${t.lead_id}` : `/companies/${t.company_id}`" class="unit">{{ t.name }}</RouterLink>
              <div class="sub">{{ [t.region, t.published_on].filter(Boolean).join(' · ') }}</div>
            </td>
            <td class="left">
              <a v-if="t.notice_url" :href="t.notice_url" target="_blank" rel="noopener" class="notice"><span v-if="t.kind" class="tag signal">{{ t.kind }}</span>{{ t.items || t.notice || '—' }}</a>
              <span v-else>—</span>
            </td>
            <td class="num strong">{{ money(t.budget) }}</td>
            <td class="num">{{ deadline(t.deadline) || '—' }}</td>
            <td><template v-if="t.contact"><div>{{ t.contact_person || '—' }}</div><div class="sub num">{{ t.contact_phone }}</div></template><span v-else>—</span></td>
            <td><span v-if="t.score !== null" class="tag" :class="t.status ? LEAD_STATUS[t.status].tone : 'grey'">{{ t.score }}</span><template v-else>—</template></td>
          </tr>
        </tbody>
      </table>
    </div>
    <div v-else-if="!buyersMode && report.records.length" class="r-table">
      <table>
        <thead><tr><th>日期</th><th>公告</th><th>角色</th><th>对方</th><th>金额</th></tr></thead>
        <tbody>
          <tr v-for="r in report.records" :key="r.url">
            <td class="num">{{ r.date || '—' }}</td>
            <td class="left"><a :href="r.url" target="_blank" rel="noopener" class="notice">{{ r.title }}</a></td>
            <td><span class="tag" :class="r.role === '中标' ? 'ok' : r.role === '采购' ? 'signal' : 'purple'">{{ r.role }}</span></td>
            <td class="left">{{ r.counterpart || '—' }}</td>
            <td class="num strong">{{ money(r.amount) }}</td>
          </tr>
        </tbody>
      </table>
    </div>

    </div>
  </section>
  <div v-else-if="failed" class="muted small">研究报告读取失败</div>
</template>

<style scoped>
.report { border: 1px solid var(--line); border-radius: 12px; background: #fff; overflow: hidden; }
.r-head { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; padding: 12px 16px; background: var(--brand-tint); }
.r-title { display: inline-flex; align-items: center; gap: 6px; font-size: 17px; font-weight: 600; color: var(--brand-press); }
.r-meta { margin-left: auto; font-size: 13px; color: var(--ink-2); }
.r-stats { display: grid; background: #fff; grid-template-columns: repeat(auto-fit, minmax(110px, 1fr)); border-bottom: 1px solid var(--line-2); }
.r-stat { display: flex; flex-direction: column; align-items: center; gap: 2px; padding: 12px 8px; border-right: 1px solid var(--line-2); }
.r-stat:last-child { border-right: 0; }
.r-stat-icon { color: var(--brand-press); }
.r-num { font-size: 24px; line-height: 32px; font-weight: 600; font-variant-numeric: tabular-nums; }
.r-label { font-size: 13px; color: var(--ink-3); }
.r-grid { display: grid; grid-template-columns: minmax(0, 1fr) minmax(0, 1fr); }
.r-block { padding: 14px 16px; display: flex; flex-direction: column; gap: 8px; min-width: 0; }
.r-block + .r-block { border-left: 1px solid var(--line-2); }
.r-sub { font-size: 15px; font-weight: 600; }
.rate { display: flex; align-items: center; gap: 12px; }
.rate-num { font-size: 30px; line-height: 38px; font-weight: 600; font-variant-numeric: tabular-nums; }
.rate-num.ok { color: var(--ok); }
.rate-num.signal { color: var(--signal); }
.rate-num.danger { color: var(--danger); }
.rate-text { font-size: 14px; line-height: 20px; }
.bar-row { display: grid; grid-template-columns: 84px minmax(0, 1fr) 56px; gap: 10px; align-items: center; font-size: 14px; }
.bar-label { color: var(--ink-2); }
.bar-track { height: 8px; border-radius: 4px; background: #f2f3f5; overflow: hidden; }
.bar-fill { display: block; height: 100%; border-radius: 4px; background: var(--brand); }
.bar-fill.alt { background: #13c2c2; }
.bar-value { text-align: right; color: var(--ink-2); }
.site-row { display: flex; align-items: center; gap: 8px; font-size: 14px; min-height: 30px; }
.site-name { flex: 1; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.site-name.fixed { flex: none; }
.site-row .grow { flex: 1; }
.problems { display: flex; flex-direction: column; gap: 4px; padding: 8px 10px; border-radius: 8px; background: var(--warn-tint); }
.problem { display: flex; gap: 6px; align-items: flex-start; font-size: 13px; color: var(--warn); word-break: break-all; }
.problem .icon { margin-top: 3px; }
.strong { font-weight: 600; }
.r-result { border-top: 1px solid var(--line-2); }
.r-result-head { display: flex; align-items: center; gap: 8px; padding: 10px 16px; }
.r-actions { margin-left: auto; display: flex; gap: 8px; }
.r-actions a { text-decoration: none; }
.r-table { overflow: auto; max-height: 560px; border-top: 1px solid var(--line-2); }
.r-table table { width: 100%; border-collapse: collapse; font-size: 14px; }
.r-table th { position: sticky; top: 0; z-index: 1; background: #f7f8fa; font-weight: 600; text-align: center; padding: 8px 10px; white-space: nowrap; color: var(--ink); }
.r-table tr:first-child td { border-top: 0; }
.r-table td { padding: 10px; border-top: 1px solid var(--line-2); text-align: center; vertical-align: middle; }
.r-table td.left { text-align: left; }
.r-table .num { white-space: nowrap; }
.r-table .unit { font-weight: 600; color: var(--ink); display: inline-block; min-width: 9em; }
.r-table .unit:hover, .r-table .notice:hover { color: var(--brand); }
.r-table .notice { color: var(--ink-2); display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden; min-width: 200px; }
.r-table .notice .tag { margin-right: 4px; }
.r-table .sub { font-size: 13px; color: var(--ink-3); }
@media (max-width: 760px) {
  .r-grid { grid-template-columns: minmax(0, 1fr); }
  .r-block + .r-block { border-left: 0; border-top: 1px solid var(--line-2); }
  .r-meta { margin-left: 0; width: 100%; }
  .r-result-head { flex-wrap: wrap; }
  .r-actions { margin-left: 0; width: 100%; }
  .r-stats { grid-template-columns: repeat(3, minmax(0, 1fr)); }
  .r-stat:nth-child(3n) { border-right: 0; }
}
</style>
