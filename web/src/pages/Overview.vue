<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { api } from '../api'
import { JOB_STATUS, dateParts } from '../format'
import Charts from '../components/Charts.vue'
import Icon from '../components/Icon.vue'

type KpiKey = 'new_leads' | 'high_leads' | 'won_leads' | 'companies' | 'notices' | 'jobs'
interface Overview {
  kpis: Record<KpiKey | 'awaiting_jobs' | 'failed_jobs', number>
  previous: Partial<Record<KpiKey, number>>
  trend: { date: string; leads: number; notices: number }[]
  lead_status: { status: string; label: string; count: number }[]
  notice_kinds: { kind: string; label: string; count: number }[]
  sites: { site: string; attempts: number; successes: number; adopted: number; rate: number | null }[]
  recent_jobs: { id: string; conversation_id: string; title: string; mode: string; status: keyof typeof JOB_STATUS; created_at: string }[]
}

const router = useRouter()
const RANGES = [{ days: 7, label: '近 7 天' }, { days: 30, label: '近 30 天' }, { days: 90, label: '近 90 天' }, { days: 0, label: '全部' }]
const days = ref(30)
const data = ref<Overview | null>(null)
const error = ref(false)
const loading = ref(true)
const alertClosed = ref(false)
const SITE_NAMES: Record<string, string> = { ccgp: '中国政府采购网', ggzy: '全国公共资源交易平台', bidcenter: '采招网', baidu: '百度企业信息', aiqicha: '爱企查' }
// 石墨主题：主系列深灰，其余取蓝、中灰与浅灰
const PALETTE = ['#3f3f46', '#2563eb', '#a1a1aa', '#15803d', '#d4d4d8', '#e4e4e7']

async function load() {
  loading.value = true
  error.value = false
  try {
    data.value = await api<Overview>(`/overview?days=${days.value}`, { notify: false })
  } catch {
    error.value = true
  } finally {
    loading.value = false
  }
}
watch(days, load)
onMounted(load)

const KPIS: { key: KpiKey; label: string; icon: string; to: string }[] = [
  { key: 'new_leads', label: '新增线索', icon: 'lead', to: '/leads' },
  { key: 'high_leads', label: '高分线索', icon: 'flag', to: '/leads' },
  { key: 'won_leads', label: '已成交', icon: 'check', to: '/leads?status=won' },
  { key: 'companies', label: '新增企业', icon: 'company', to: '/companies' },
  { key: 'notices', label: '已读公告', icon: 'doc', to: '/companies' },
  { key: 'jobs', label: '研究任务', icon: 'workbench', to: '/workbench' },
]
function delta(key: KpiKey) {
  if (!data.value?.previous || !days.value) return null
  const now = data.value.kpis[key], before = data.value.previous?.[key] ?? 0
  return { diff: now - before, before }
}
// 时间范围内每一天都出现在趋势里（无数据记 0），线条连续可比。
const trend = computed(() => {
  const rows = data.value?.trend || []
  if (!rows.length) return []
  const byDate = Object.fromEntries(rows.map((r) => [r.date, r]))
  const end = new Date(rows[rows.length - 1].date)
  const span = days.value || Math.max(7, Math.round((end.getTime() - new Date(rows[0].date).getTime()) / 86400000) + 1)
  return Array.from({ length: span }, (_, i) => {
    const d = new Date(end.getTime() - (span - 1 - i) * 86400000).toISOString().slice(0, 10)
    return byDate[d] || { date: d, leads: 0, notices: 0 }
  })
})
const isEmpty = computed(() => !!data.value && !data.value.kpis.jobs && !data.value.kpis.new_leads && !data.value.kpis.notices)
const firstWaiting = computed(() => data.value?.recent_jobs.find((j) => j.status === 'awaiting_user'))
const firstFailed = computed(() => data.value?.recent_jobs.find((j) => j.status === 'failed'))
const trendTitle = computed(() => {
  const t = data.value?.trend || []
  const leads = t.reduce((a, b) => a + b.leads, 0), notices = t.reduce((a, b) => a + b.notices, 0)
  return `读 ${notices} 篇公告，新增 ${leads} 条线索`
})
</script>

<template>
  <div class="page">
    <div class="page-head">
      <div class="seg page-actions" role="tablist">
        <button v-for="r in RANGES" :key="r.days" type="button" role="tab" :class="{ on: days === r.days }" data-action-id="A-001" @click="days = r.days">{{ r.label }}</button>
      </div>
    </div>

    <div v-if="data && data.kpis.awaiting_jobs && !alertClosed" class="alert-line">
      <Icon name="alert" :size="18" />
      <span class="grow">有 {{ data.kpis.awaiting_jobs }} 个研究在等待你处理</span>
      <RouterLink v-if="firstWaiting" :to="`/c/${firstWaiting.conversation_id}`" data-action-id="A-003">去处理</RouterLink>
      <button type="button" class="link-btn" aria-label="关闭预警" data-action-id="A-005" @click="alertClosed = true"><Icon name="close" :size="16" /></button>
    </div>

    <div v-if="error" class="error-line">无法读取概览数据<el-button size="small" @click="load">重试</el-button></div>
    <template v-else-if="loading && !data">
      <div class="kpis"><div v-for="i in 6" :key="i" class="kpi"><el-skeleton :rows="2" animated /></div></div>
      <div class="card"><el-skeleton :rows="8" animated /></div>
    </template>
    <div v-else-if="isEmpty" class="card empty tall">
      <span class="icon-wrap"><Icon name="radar" :size="28" /></span>
      <div class="empty-title">这段时间还没有研究</div>
      <el-button type="primary" @click="router.push('/workbench')"><Icon name="plus" :size="16" /><span>发起研究</span></el-button>
    </div>
    <template v-else-if="data">
      <div class="kpis">
        <button v-for="k in KPIS" :key="k.key" type="button" class="kpi" data-action-id="A-002" @click="router.push(k.to)">
          <div class="kpi-num">{{ data.kpis[k.key] }}</div>
          <div class="kpi-top"><Icon :name="k.icon" :size="16" class="kpi-icon" /><span class="kpi-label">{{ k.label }}</span></div>
          <div class="kpi-foot">
            <template v-if="delta(k.key)">较上期
              <span :class="delta(k.key)!.diff > 0 ? 'up' : delta(k.key)!.diff < 0 ? 'down' : ''">{{ delta(k.key)!.diff > 0 ? '+' : '' }}{{ delta(k.key)!.diff }}</span>
            </template>
            <template v-else>全部时间</template>
          </div>
        </button>
      </div>

      <div class="row-2">
        <div class="card">
          <div class="card-title"><Icon name="analysis" :size="18" /><span class="grow">{{ trendTitle }}</span></div>
          <Charts v-if="trend.length" type="trend" unit="条" :height="300" :labels="trend.map((t) => t.date)"
                  :series="[{ name: '新增线索', color: '#3f3f46', values: trend.map((t) => t.leads) }, { name: '已读公告', color: '#a1a1aa', values: trend.map((t) => t.notices) }]" />
          <div v-else class="empty">暂无数据</div>
        </div>
        <div class="card">
          <div class="card-title"><Icon name="lead" :size="18" />线索状态</div>
          <Charts v-if="data.lead_status.length" type="donut" unit="条" :labels="data.lead_status.map((s) => s.label)"
                  :values="data.lead_status.map((s) => s.count)" :colors="PALETTE" />
          <div v-else class="empty">暂无线索</div>
          <template v-if="data.notice_kinds.length">
            <div class="card-title sub-title"><Icon name="doc" :size="18" />公告类型</div>
            <Charts type="bars" unit="篇" :labels="data.notice_kinds.map((k) => k.label)" :values="data.notice_kinds.map((k) => k.count)"
                    :colors="data.notice_kinds.map((_, i) => (i === 0 ? '#3f3f46' : '#a1a1aa'))" />
          </template>
        </div>
      </div>

      <div class="row-2">
        <div class="card flush">
          <div class="card-title pad"><Icon name="history" :size="18" /><span class="grow">最近研究</span>
            <RouterLink to="/workbench" class="extra">进入工作台</RouterLink></div>
          <div v-if="!data.recent_jobs.length" class="empty">暂无研究</div>
          <RouterLink v-for="j in data.recent_jobs" :key="j.id" :to="`/c/${j.conversation_id}`" class="job-row" :class="`job-${j.status}`" data-action-id="A-004">
            <span class="job-icon" :class="j.mode"><Icon :name="j.mode === 'company' ? 'company' : 'search'" :size="18" /></span>
            <span class="grow"><span class="job-title">{{ j.title }}</span><span class="cell-sub">{{ j.mode === 'company' ? '查企业' : '找买家' }} · {{ dateParts(j.created_at).date }} {{ dateParts(j.created_at).time }}</span></span>
            <span class="tag" :class="JOB_STATUS[j.status].tone">{{ JOB_STATUS[j.status].label }}</span>
          </RouterLink>
        </div>
        <div class="card">
          <div class="card-title"><Icon name="alert" :size="18" />风险与异常</div>
          <div class="risk">
            <div class="risk-item"><span class="risk-num" :class="{ warn: data.kpis.awaiting_jobs }">{{ data.kpis.awaiting_jobs }}</span><span class="muted">等待处理</span></div>
            <component :is="firstFailed ? 'RouterLink' : 'div'" :to="firstFailed ? `/c/${firstFailed.conversation_id}` : undefined" class="risk-item">
              <span class="risk-num" :class="{ bad: data.kpis.failed_jobs }">{{ data.kpis.failed_jobs }}</span><span class="muted">失败任务</span></component>
          </div>
          <RouterLink v-for="s in data.sites" :key="s.site" to="/sources" class="site-row">
            <span class="grow">{{ SITE_NAMES[s.site] || s.site }}</span>
            <span class="muted small num">{{ s.successes }} / {{ s.attempts }}</span>
            <span class="tag" :class="s.rate !== null && s.rate < 0.5 ? 'danger' : 'ok'">{{ s.rate === null ? '—' : Math.round(s.rate * 100) + '%' }}</span>
          </RouterLink>
        </div>
      </div>
    </template>
  </div>
</template>

<style scoped>
.tall { min-height: 360px; }
.empty-title { font-size: 16px; font-weight: 600; color: var(--ink); }
.sub-title { margin-top: 16px; padding-top: 16px; border-top: 1px solid var(--line); }
.pad { padding: 14px 16px 6px; margin: 0; }
.extra { font-size: 14px; font-weight: 400; }
.job-row { display: flex; align-items: center; gap: 12px; padding: 10px 16px; border-top: 1px solid var(--line); color: var(--ink); transition: background-color .16s ease, border-color .16s ease; }
.job-row.job-running { background: #f8faff; }
.job-row.job-awaiting_user { background: #fffdf7; }
.job-row.job-partial { background: #fffaf5; }
.job-row.job-failed { background: #fffafa; }
.job-row.job-completed:hover, .job-row.job-queued:hover, .job-row.job-paused:hover { background: var(--canvas); }
.job-row:hover { background: var(--canvas); }
.job-icon { display: inline-grid; place-items: center; width: 32px; height: 32px; border-radius: 8px; border: 1px solid var(--line); color: var(--ink-2); flex: none; }
.grow { flex: 1; min-width: 0; display: flex; flex-direction: column; }
.job-title { font-weight: 600; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.risk { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; margin-bottom: 8px; }
.risk-item { display: flex; flex-direction: column; align-items: center; padding: 10px; border: 1px solid var(--line); border-radius: 8px; color: var(--ink); }
.risk-num { font-size: 22px; line-height: 30px; font-weight: 600; font-variant-numeric: tabular-nums; }
.risk-num.warn { color: var(--warn); }
.risk-num.bad { color: var(--danger); }
.site-row { display: flex; align-items: center; gap: 12px; min-height: 40px; border-top: 1px solid var(--line); color: var(--ink); }
.site-row:hover { color: var(--accent); }
.site-row .grow { display: block; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
</style>
