<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { get } from '../api'
import { JOB_STATUS, TONE_DOT, due, duration, monthDay, plainProblem, splitPurchaseItems, wan } from '../format'
import type { CompanyCard, JobStatus, LeadStatus } from '../types'
import Icon from './Icon.vue'

interface Buyer {
  company_id: string; name: string; lead_id: string | null; score: number | null; status: LeadStatus | null; notice: string; notice_url: string
  kind: string; items: string; budget: number | null; deadline: string; published_on: string; contact: boolean; contact_person: string
  contact_phone: string; region: string; profiled: boolean
}
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
  top: Buyer[]
  records: { title: string; url: string; date: string; role: string; counterpart: string; amount: number | null }[]
  columns?: string[]
  rows?: SearchRow[]
  path?: { stage: string; label?: string; status: string; elapsed_ms?: number; count?: number; error?: string }[]
  sources?: string[]
}
interface SearchRow {
  status: string; title: string; url: string; language: string; published_on: string; points: string[]; summary?: string; quote?: string
}

const props = defineProps<{ jobId: string; version?: number }>()
const report = ref<Report | null>(null)
const industry = ref<Record<string, string>>({})
const failed = ref(false)
const showAll = ref(false)
const showMore = ref(false)
const sort = ref<{ key: 'budget' | 'deadline' | ''; desc: boolean }>({ key: '', desc: true })
const FIRST = 20

watch(() => [props.jobId, props.version], async () => {
  failed.value = false
  try {
    const [data, results] = await Promise.all([
      get<Report>(`/jobs/${props.jobId}/report`),
      get<{ companies: CompanyCard[] }>(`/jobs/${props.jobId}/results`).catch(() => ({ companies: [] })),
    ])
    report.value = data
    industry.value = Object.fromEntries(results.companies.filter((c) => c.industry).map((c) => [c.id, c.industry]))
  } catch { failed.value = true }
}, { immediate: true })

const buyersMode = computed(() => report.value?.mode === 'find_buyers')
const searchMode = computed(() => report.value?.mode === 'search')
const stats = computed(() => {
  const c = report.value?.counts
  if (!c) return []
  const rate = report.value?.quality.rate
  const verified = { label: '原文核验通过', value: rate === null || rate === undefined ? '—' : `${Math.round(rate * 100)}%` }
  if (searchMode.value) return [{ label: '搜索次数', value: c.searches }, { label: '候选来源', value: c.candidates },
    { label: '读取原文', value: c.read }, { label: '核验结果', value: report.value?.rows?.length || 0 }]
  return buyersMode.value
    ? [{ label: '新增线索', value: c.leads }, { label: '采购方', value: c.buyers }, { label: '核验公告', value: c.notices },
       { label: '取得联系人', value: c.contacts }, { label: '补充工商', value: c.profiled }, { label: '涉及企业', value: c.companies }, verified]
    : [{ label: '核验公告', value: c.notices }, { label: '涉及企业', value: c.companies }, { label: '检索次数', value: c.searches },
       { label: '阅读原文', value: c.read }, verified]
})
const completeness = computed(() => {
  const q = report.value?.quality
  if (!q) return []
  const rows = q.notice_total ? [
    { label: '预算或金额', n: q.complete.budget, total: q.notice_total }, { label: '截止时间', n: q.complete.deadline, total: q.notice_total },
    { label: '采购标的', n: q.complete.items, total: q.notice_total }, { label: '联系人', n: q.complete.contact, total: q.notice_total },
  ] : []
  if (buyersMode.value && q.buyers) rows.push({ label: '工商信息', n: q.profiled, total: q.buyers })
  return rows.map((x) => ({ ...x, pct: Math.round((x.n / x.total) * 100) }))
})

// 每行取值相同的列不单独占列，在表头写一次
const sameKind = computed(() => { const s = new Set(report.value?.top.map((t) => t.kind)); return s.size === 1 ? [...s][0] : '' })
const sameScore = computed(() => { const s = new Set(report.value?.top.map((t) => t.score)); return s.size === 1 ? [...s][0] : null })
const summary = computed(() => [sameKind.value && `均为${sameKind.value}`, sameScore.value !== null && `评分均为 ${sameScore.value}`].filter(Boolean).join(' · '))

const buyers = computed(() => {
  const rows = (report.value?.top || []).map((t) => ({ ...t, due: due(t.deadline), industry: industry.value[t.company_id] || '' }))
  const { key, desc } = sort.value
  if (key === 'budget') rows.sort((a, b) => ((a.budget ?? -1) - (b.budget ?? -1)) * (desc ? -1 : 1))
  if (key === 'deadline') rows.sort((a, b) => ((a.due.left ?? 9999) - (b.due.left ?? 9999)) * (desc ? -1 : 1))
  return rows
})
const shown = computed(() => (showAll.value ? buyers.value : buyers.value.slice(0, FIRST)))
function sortBy(key: 'budget' | 'deadline') {
  sort.value = sort.value.key === key ? { key, desc: !sort.value.desc } : { key, desc: key === 'budget' }
}
const problems = computed(() => (report.value?.problems || []).map(plainProblem))
const statusDot = computed(() => (report.value ? TONE_DOT[JOB_STATUS[report.value.status].tone] : ''))
function host(url: string): string {
  try { return new URL(url).hostname }
  catch { return url }
}
</script>

<template>
  <section v-if="report" class="report">
    <header class="r-head">
      <span class="r-title">{{ searchMode ? '全网搜索结果' : '研究报告' }}</span>
      <span class="r-state"><span class="dot" :class="statusDot" />{{ JOB_STATUS[report.status].label }}</span>
      <span class="r-meta">用时 <b class="num">{{ duration(report.elapsed_ms) }}</b><template v-if="report.first_result_ms"> · 首批结果 <b class="num">{{ duration(report.first_result_ms) }}</b></template> · 模型调用 <b class="num">{{ report.model_calls }}</b> 次</span>
    </header>

    <div class="r-stats" :style="{ gridTemplateColumns: `repeat(${stats.length}, minmax(0, 1fr))` }">
      <div v-for="s in stats" :key="s.label" class="r-stat"><span class="r-num num">{{ s.value }}</span><span class="r-label">{{ s.label }}</span></div>
    </div>

    <div class="r-bar">
      <span class="r-sub">{{ searchMode ? '核验结果表' : buyersMode ? '采购单位清单' : '采购与中标记录' }}</span>
      <span class="r-caption">{{ searchMode ? `${report.rows?.length || 0} 条` : buyersMode ? `${report.top.length} 家` : `${report.records.length} 条` }}<template v-if="buyersMode && summary"> · {{ summary }}</template></span>
      <span class="grow" />
      <template v-if="buyersMode && report.counts.leads">
        <a href="/api/leads/export" class="el-button"><Icon name="download" :size="16" /><span>导出</span></a>
        <RouterLink to="/leads" class="el-button el-button--primary"><Icon name="lead" :size="16" /><span>打开线索管理</span></RouterLink>
      </template>
    </div>

    <table v-if="buyersMode && report.top.length" class="grid buyers" data-pagination="none">
      <colgroup><col class="c-unit"><col><col class="c-money"><col class="c-day"><col class="c-due"><col class="c-contact"><col class="c-src"></colgroup>
      <thead><tr>
        <th>采购单位</th><th>采购标的</th>
        <th class="sortable" :class="{ on: sort.key === 'budget', asc: sort.key === 'budget' && !sort.desc }" @click="sortBy('budget')">预算（万元）</th>
        <th>发布</th>
        <th class="sortable" :class="{ on: sort.key === 'deadline', asc: sort.key === 'deadline' && !sort.desc }" @click="sortBy('deadline')">投标截止</th>
        <th>联系人</th><th>原文</th>
      </tr></thead>
      <tbody>
        <tr v-for="t in shown" :key="t.company_id">
          <td class="l"><span class="unit">
            <RouterLink :to="t.lead_id ? `/leads/${t.lead_id}` : `/companies/${t.company_id}`" class="name" :title="t.name">{{ t.name }}</RouterLink>
            <span v-if="t.industry" class="tag plain ind" :title="t.industry">{{ t.industry }}</span>
          </span></td>
          <td class="l"><span class="clip" :title="t.items || t.notice"><span v-if="!sameKind && t.kind" class="tag plain">{{ t.kind }}</span><ul v-if="splitPurchaseItems(t.items || t.notice).length" class="purchase-list"><li v-for="line in splitPurchaseItems(t.items || t.notice)" :key="line">{{ line }}</li></ul><span v-else>—</span></span></td>
          <td class="r num strong">{{ wan(t.budget) }}</td>
          <td class="c num muted">{{ monthDay(t.published_on) }}</td>
          <td class="c"><span v-if="t.due.short" class="due"><span class="num">{{ t.due.short }}</span><span class="due-left" :class="t.due.tone">{{ t.due.label }}</span></span><span v-else class="muted">—</span></td>
          <td class="l"><span v-if="t.contact_person || t.contact_phone" class="contact"><span v-if="t.contact_person" class="who" :title="t.contact_person">{{ t.contact_person }}</span><span class="num phone">{{ t.contact_phone }}</span></span><span v-else class="muted">—</span></td>
          <td class="c"><a v-if="t.notice_url" :href="t.notice_url" target="_blank" rel="noopener" class="src"><Icon name="external" :size="14" />原文</a><span v-else class="muted">—</span></td>
        </tr>
      </tbody>
    </table>

    <!-- 手机：每家一张卡 -->
    <div v-if="buyersMode && report.top.length" class="m-list">
      <RouterLink v-for="t in shown" :key="t.company_id" :to="t.lead_id ? `/leads/${t.lead_id}` : `/companies/${t.company_id}`" class="m-card">
        <div class="m-row"><span class="name">{{ t.name }}</span><b class="num">{{ t.budget === null ? '—' : `${wan(t.budget)} 万元` }}</b></div>
        <div class="m-items" :title="t.items || t.notice"><ul v-if="splitPurchaseItems(t.items || t.notice).length" class="purchase-list"><li v-for="line in splitPurchaseItems(t.items || t.notice)" :key="line">{{ line }}</li></ul><span v-else>—</span></div>
        <div class="m-row"><span v-if="t.due.short" class="due"><span class="num muted">截止 {{ t.due.short }}</span><span class="due-left" :class="t.due.tone">{{ t.due.label }}</span></span><span class="num muted">{{ t.contact_phone }}</span></div>
      </RouterLink>
    </div>
    <button v-if="buyersMode && buyers.length > FIRST" type="button" class="more-rows" @click="showAll = !showAll">
      <Icon name="down" :size="16" :class="{ flip: showAll }" />{{ showAll ? '收起' : `显示其余 ${buyers.length - FIRST} 家` }}</button>

    <div v-if="!buyersMode && report.records.length" class="table-scroll">
    <table class="grid" data-pagination="none">
      <colgroup><col class="c-day"><col><col class="c-role"><col class="c-party"><col class="c-money"></colgroup>
      <thead><tr><th>日期</th><th>公告</th><th>角色</th><th>对方</th><th>金额（万元）</th></tr></thead>
      <tbody>
        <tr v-for="r in report.records" :key="r.url">
          <td class="c num muted">{{ monthDay(r.date) }}</td>
          <td class="l"><a :href="r.url" target="_blank" rel="noopener" class="clip notice" :title="r.title">{{ r.title }}</a></td>
          <td class="c"><span class="tag" :class="r.role === '中标' ? 'ok' : r.role === '采购' ? 'warn' : 'purple'">{{ r.role }}</span></td>
          <td class="l"><span class="clip" :title="r.counterpart">{{ r.counterpart || '—' }}</span></td>
          <td class="r num strong">{{ wan(r.amount) }}</td>
        </tr>
      </tbody>
    </table>
    </div>

    <div v-if="searchMode" class="table-scroll search-results">
      <table class="grid search-grid" data-pagination="none">
        <colgroup><col><col class="c-src"><col class="c-lang"><col class="c-day"><col class="c-points"><col class="c-src"></colgroup>
        <thead><tr><th>标题</th><th>来源</th><th>语言</th><th>日期</th><th>要点</th><th>原文</th></tr></thead>
        <tbody>
          <tr v-for="row in (report.rows || [])" :key="row.url">
            <td class="l"><a :href="row.url" target="_blank" rel="noopener" class="clip notice" :title="row.summary || row.title">{{ row.title }}</a></td>
            <td class="c"><a :href="row.url" target="_blank" rel="noopener" class="src" :title="row.url"><Icon name="external" :size="14" />{{ host(row.url) }}</a></td>
            <td class="c"><span class="tag" :class="row.language === 'en' ? 'brand' : row.language === 'zh' ? 'teal' : 'grey'">{{ row.language }}</span></td>
            <td class="c num muted c-day">{{ row.published_on || '—' }}</td>
            <td class="l"><span class="clip" :title="row.summary || row.quote"><ul v-if="row.points?.length" class="purchase-list"><li v-for="point in row.points.slice(0, 3)" :key="point">{{ point }}</li></ul><span v-else>—</span></span></td>
            <td class="c"><a :href="row.url" target="_blank" rel="noopener" class="src" :title="row.quote || ''"><Icon name="external" :size="14" />打开</a></td>
          </tr>
        </tbody>
      </table>
    </div>

    <div v-if="!searchMode" class="r-more">
      <button type="button" class="r-more-head" :aria-expanded="showMore" @click="showMore = !showMore">
        <Icon name="chevron" :size="16" :class="{ open: showMore }" /><span class="r-sub">检索过程与数据质量</span>
        <span class="r-caption num">{{ report.sites.length }} 个网站 · 检索 {{ report.counts.searches }} 次 · 候选 {{ report.counts.candidates }} 条 · 阅读 {{ report.counts.read }} 篇<template v-if="report.counts.read_failed"> · {{ report.counts.read_failed }} 篇未读到</template></span>
      </button>
      <div v-if="showMore && !searchMode" class="r-more-body">
        <div class="quality">
          <div v-for="c in completeness" :key="c.label" class="bar-row">
            <span class="muted">{{ c.label }}</span>
            <span class="track"><span class="track-bar" :style="{ width: c.pct + '%' }" /></span>
            <span class="num muted">{{ c.n }} / {{ c.total }}</span>
          </div>
          <div class="muted small num">{{ report.quality.kept }} / {{ report.quality.checked }} 个字段逐字对上原文 · {{ report.counts.rounds }} 轮</div>
        </div>
        <div class="sites">
          <div v-for="s in report.sites" :key="s.site" class="site">
            <span class="site-name" :title="s.name">{{ s.name }}</span>
            <span class="num small muted">{{ s.searches }} 次 · {{ s.links }} 条</span>
            <span class="dot" :class="s.ok === s.searches ? 'ok' : s.ok ? 'warn' : 'danger'" :title="s.ok === s.searches ? '正常' : s.ok ? '部分失败' : '失败'" />
          </div>
        </div>
      </div>
      <div v-for="p in problems" :key="p" class="problem"><Icon name="alert" :size="16" /><span>{{ p }}</span></div>
    </div>
  </section>
  <div v-else-if="failed" class="muted small">研究报告读取失败</div>
</template>

<style scoped>
.report { border: 1px solid var(--line); border-radius: 12px; background: var(--surface); overflow: hidden; }
.r-head { display: flex; align-items: center; gap: 12px; flex-wrap: wrap; min-height: 48px; padding: 0 16px; border-bottom: 1px solid var(--line); }
.r-title { font-size: 16px; font-weight: 600; }
.r-state { display: inline-flex; align-items: center; gap: 6px; font-weight: 600; }
.r-meta { margin-left: auto; font-size: 12px; color: var(--ink-3); }
.r-meta b { font-weight: 600; color: var(--ink-2); }
.r-stats { display: grid; border-bottom: 1px solid var(--line); }
.r-stat { display: flex; flex-direction: column; gap: 2px; padding: 12px 16px; border-right: 1px solid var(--line); min-width: 0; }
.r-stat:last-child { border-right: 0; }
.r-num { font-size: 22px; line-height: 30px; font-weight: 600; }
.r-label { color: var(--ink-3); white-space: nowrap; }
.r-bar { display: flex; align-items: center; gap: 10px; min-height: 52px; padding: 8px 16px; flex-wrap: wrap; }
.r-bar a { text-decoration: none; }
.r-bar .el-button + .el-button { margin-left: 0; }
.r-sub { font-size: 16px; font-weight: 600; }
.r-caption { font-size: 12px; color: var(--ink-3); }
.grid { width: 100%; table-layout: fixed; border-collapse: collapse; }
.grid col.c-unit { width: 20%; }
.grid col.c-money { width: 112px; }
.grid col.c-day { width: 120px; }
.grid col.c-due { width: 184px; }
.grid col.c-contact { width: 216px; }
.grid col.c-src { width: 88px; }
.grid col.c-role { width: 96px; }
.grid col.c-party { width: 24%; }
.grid col.c-lang { width: 88px; }
.grid col.c-points { width: 240px; }
.grid th { height: 40px; padding: 0 16px; background: var(--canvas); border-top: 1px solid var(--line); border-bottom: 1px solid var(--line); color: var(--ink-2); font-weight: 600; text-align: center; white-space: nowrap; }
.grid th.sortable { cursor: pointer; user-select: none; }
.grid th.sortable::after { content: ''; display: inline-block; margin-left: 6px; vertical-align: 2px; border: 4px solid transparent; border-top: 5px solid var(--ink-3); border-bottom: 0; }
.grid th.sortable.on::after { border-top-color: var(--ink); }
.grid th.sortable.asc::after { border-top: 0; border-bottom: 5px solid var(--ink); vertical-align: 3px; }
.grid td { height: 44px; padding: 0 16px; border-bottom: 1px solid var(--line); color: var(--ink-2); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.grid td.c-day { min-width: 120px; }
.grid tbody tr:hover td { background: var(--canvas); }
.grid td.l { text-align: left; }
.grid td.c { text-align: center; }
.grid td.r { text-align: right; padding-right: 24px; }
.strong { font-weight: 600; color: var(--ink); }
/* 单位类型标签放不下时整体换到被裁掉的第二行，不挤压名称 */
.unit { display: flex; flex-wrap: wrap; align-items: center; column-gap: 8px; height: 22px; overflow: hidden; min-width: 0; }
.name { font-weight: 600; color: var(--ink); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; flex: 0 0 auto; max-width: 100%; }
a.name:hover { color: var(--accent); }
.ind { flex: none; max-width: 10em; overflow: hidden; text-overflow: ellipsis; display: inline-block; line-height: 22px; }
.clip { display: block; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; min-width: 0; }
.clip .tag { margin-right: 6px; vertical-align: 1px; }
.notice { color: var(--ink-2); }
.notice:hover { color: var(--accent); }
.contact { display: flex; gap: 8px; overflow: hidden; }
.who { color: var(--ink); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; max-width: 7em; }
.src { display: inline-flex; align-items: center; gap: 4px; }
.table-scroll { width: 100%; overflow-x: auto; }
.search-grid { min-width: 880px; }
.search-grid td.c-day { min-width: 120px; }
.purchase-list { display: flex; flex-direction: column; gap: 1px; margin: 0; padding: 0; list-style: none; line-height: 20px; }
.purchase-list li { position: relative; overflow: hidden; padding-left: 12px; text-overflow: ellipsis; white-space: nowrap; }
.purchase-list li::before { content: ''; position: absolute; top: 8px; left: 1px; width: 5px; height: 5px; border-radius: 50%; background: var(--accent); }
.more-rows { display: flex; align-items: center; justify-content: center; gap: 6px; width: 100%; height: 40px; border: 0; border-bottom: 1px solid var(--line); background: none; color: var(--ink-2); font: inherit; cursor: pointer; }
.more-rows:hover { background: var(--canvas); color: var(--ink); }
.flip { transform: rotate(180deg); }
.r-more-head { display: flex; align-items: center; gap: 8px; width: 100%; min-height: 44px; padding: 0 16px; border: 0; background: none; font: inherit; color: var(--ink); text-align: left; cursor: pointer; flex-wrap: wrap; }
.r-more-head .icon { color: var(--ink-3); transition: transform .15s; }
.r-more-head .icon.open { transform: rotate(90deg); }
.r-more-body { display: grid; grid-template-columns: 360px minmax(0, 1fr); border-top: 1px solid var(--line); }
.quality { display: flex; flex-direction: column; gap: 6px; padding: 12px 16px; border-right: 1px solid var(--line); }
.bar-row { display: grid; grid-template-columns: 80px minmax(0, 1fr) 52px; gap: 10px; align-items: center; }
.bar-row .num { text-align: right; }
.track { height: 4px; border-radius: 4px; background: var(--subtle); overflow: hidden; }
.track-bar { display: block; height: 100%; background: var(--ink-2); }
.sites { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 2px 24px; padding: 12px 16px; align-content: start; }
.site { display: flex; align-items: center; gap: 8px; height: 32px; }
.site-name { flex: 1; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.problem { display: flex; align-items: flex-start; gap: 8px; margin: 0 16px 12px; padding: 8px 12px; border-radius: 8px; background: var(--warn-tint); color: var(--warn); word-break: break-all; }
.problem .icon { margin-top: 3px; }
.m-list { display: none; }
@media (max-width: 1199px) {
  .sites { grid-template-columns: repeat(2, minmax(0, 1fr)); }
}
@media (max-width: 900px) {
  .grid col.c-contact { width: 150px; }
  .grid:not(.search-grid) col.c-src, .grid:not(.search-grid) th:last-child, .grid:not(.search-grid) td:last-child { display: none; }
  .r-more-body { grid-template-columns: minmax(0, 1fr); }
  .quality { border-right: 0; border-bottom: 1px solid var(--line); }
}
@media (max-width: 760px) {
  .r-meta { margin-left: 0; width: 100%; padding-bottom: 8px; }
  .r-stats { grid-template-columns: repeat(4, minmax(0, 1fr)) !important; }
  .r-stat { padding: 8px 10px; border-bottom: 1px solid var(--line); }
  .r-stat:nth-child(4n) { border-right: 0; }
  .r-num { font-size: 18px; line-height: 26px; }
  .r-label { font-size: 12px; }
  .grid.buyers { display: none; }
  .grid col.c-party { width: 30%; }
  .m-list { display: flex; flex-direction: column; border-top: 1px solid var(--line); }
  .m-card { display: flex; flex-direction: column; gap: 4px; padding: 10px 16px; border-bottom: 1px solid var(--line); color: var(--ink); }
  .m-row { display: flex; justify-content: space-between; align-items: center; gap: 8px; }
  .m-items { color: var(--ink-2); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .sites { grid-template-columns: minmax(0, 1fr); }
}
</style>
