<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus/es/components/message/index'
import { ApiError, api, post } from '../api'
import type { CompanyDetail, Evidence, Notice } from '../types'
import { KIND_TONE, LEAD_STATUS, dateParts, money } from '../format'
import Icon from '../components/Icon.vue'
import SourceDialog from '../components/SourceDialog.vue'

const route = useRoute()
const router = useRouter()
const company = ref<CompanyDetail | null>(null)
const state = ref<'loading' | 'missing' | 'error' | 'ok'>('loading')
const tab = ref<'purchases' | 'wins' | 'customers' | 'suppliers' | 'competitors'>('wins')
const source = ref<{ id: string | null; quote?: string }>({ id: null })
const busy = ref('')

async function load() {
  state.value = 'loading'
  try {
    company.value = await api<CompanyDetail>(`/companies/${route.params.id}`, { notify: false })
    const s = company.value.stats
    tab.value = s.purchases >= s.wins ? (s.purchases ? 'purchases' : 'wins') : 'wins'
    state.value = 'ok'
  } catch (error) {
    state.value = error instanceof ApiError && error.status === 404 ? 'missing' : 'error'
  }
}
watch(() => route.params.id, load, { immediate: true })

const profile = computed(() => Object.fromEntries((company.value?.profile || []).map((p) => [p.field, p])))
const FACTS = [
  { field: 'legal_person', label: '法定代表人' }, { field: 'registered_capital', label: '注册资本' },
  { field: 'founded_on', label: '成立日期' }, { field: 'credit_code', label: '统一社会信用代码' },
]
const DETAILS = [
  { field: 'address', label: '地址' }, { field: 'website', label: '官网' }, { field: 'phone', label: '电话' },
  { field: 'email', label: '邮箱' }, { field: 'scope', label: '经营范围' },
]
const TABS = computed(() => company.value ? [
  { key: 'purchases', label: '采购记录', icon: 'cart', count: company.value.stats.purchases },
  { key: 'wins', label: '中标记录', icon: 'trophy', count: company.value.stats.wins },
  { key: 'customers', label: '客户', icon: 'customers', count: company.value.stats.customers },
  { key: 'suppliers', label: '供应商', icon: 'supplier', count: company.value.stats.suppliers },
  { key: 'competitors', label: '竞争对手', icon: 'rival', count: company.value.stats.competitors },
] as const : [])
const hasFacts = computed(() => FACTS.some((f) => profile.value[f.field]))
const details = computed(() => DETAILS.filter((d) => profile.value[d.field]))
const notices = computed(() => (tab.value === 'purchases' ? company.value?.purchases : company.value?.wins) || [])
const relations = computed(() => (['customers', 'suppliers', 'competitors'].includes(tab.value) ? company.value?.relations[tab.value as 'customers'] : []) || [])
const partyNames = (n: Notice, roles: string[]) => n.parties.filter((p) => roles.includes(p.role)).map((p) => p.name).join('、') || '—'
const open = (e: Evidence | null | undefined) => { if (e) source.value = { id: e.source_id, quote: e.quote } }

async function research() {
  busy.value = 'research'
  try {
    const result = await post<{ conversation_id: string }>(`/companies/${company.value!.id}/research`, {})
    router.push(`/c/${result.conversation_id}`)
  } finally {
    busy.value = ''
  }
}
async function addLead() {
  busy.value = 'lead'
  try {
    const lead = await post<{ id: string }>(`/companies/${company.value!.id}/lead`, {})
    company.value!.lead = { id: lead.id, status: 'new', archived: false }
    ElMessage.success('已加入线索')
  } finally {
    busy.value = ''
  }
}
</script>

<template>
  <div class="page">
    <div v-if="state === 'loading'" class="card"><el-skeleton :rows="10" animated /></div>
    <div v-else-if="state === 'missing'" class="card empty"><span class="icon-wrap"><Icon name="company" :size="28" /></span><div>这家企业不存在或已被删除</div>
      <el-button @click="router.push('/companies')">返回企业档案</el-button></div>
    <div v-else-if="state === 'error'" class="error-line">无法读取企业信息<el-button size="small" @click="load">重试</el-button></div>
    <template v-else-if="company">
      <RouterLink to="/companies" class="crumb"><Icon name="back" :size="16" />企业档案</RouterLink>

      <section class="card identity">
        <div class="id-main">
          <span class="logo"><Icon name="company" :size="30" /></span>
          <div class="id-text">
            <h1 class="name">{{ company.name }}</h1>
            <div class="id-tags">
              <span v-if="profile.business_status" class="tag ok">{{ profile.business_status.value }}</span>
              <span v-if="company.industry" class="tag grey">{{ company.industry }}</span>
              <span v-if="company.region" class="tag grey"><Icon name="pin" :size="14" />{{ company.region }}</span>
              <span v-if="company.lead && !company.lead.archived" class="tag" :class="LEAD_STATUS[company.lead.status].tone">线索 · {{ LEAD_STATUS[company.lead.status].label }}</span>
            </div>
          </div>
          <div class="page-actions">
            <el-button type="primary" :loading="busy === 'research'" data-action-id="A-205" @click="research"><Icon name="refresh" :size="16" /><span>继续研究</span></el-button>
            <el-button v-if="company.lead && !company.lead.archived" data-action-id="A-213" @click="router.push(`/leads/${company.lead.id}`)"><Icon name="lead" :size="16" /><span>查看线索</span></el-button>
            <el-button v-else :loading="busy === 'lead'" data-action-id="A-206" @click="addLead"><Icon name="plus" :size="16" /><span>加入线索</span></el-button>
            <a :href="`/api/companies/${company.id}/export`" class="el-button" data-action-id="A-207"><Icon name="download" :size="16" /><span>导出</span></a>
          </div>
        </div>
        <div v-if="hasFacts" class="facts">
          <div v-for="f in FACTS" :key="f.field" class="fact">
            <span class="fact-label">{{ f.label }}</span>
            <span class="fact-value">{{ profile[f.field]?.value || '—' }}
              <button v-if="profile[f.field]?.evidence" type="button" class="evid" title="查看原文依据" aria-label="查看原文依据" data-action-id="A-208"
                      @click="open(profile[f.field].evidence)"><Icon name="doc" :size="14" /></button></span>
          </div>
        </div>
        <div v-else class="facts none"><Icon name="doc" :size="16" />尚未核对工商信息
          <button type="button" class="link-btn" data-action-id="A-205" @click="research">继续研究</button></div>
        <div class="stats" role="tablist">
          <button v-for="t in TABS" :key="t.key" type="button" role="tab" class="stat" :class="{ on: tab === t.key }"
                  :data-action-id="['customers', 'suppliers', 'competitors'].includes(t.key) ? 'A-210' : undefined" @click="tab = t.key">
            <span class="stat-icon"><Icon :name="t.icon" :size="18" /></span>
            <span class="stat-num">{{ t.count }}</span><span class="stat-label">{{ t.label }}</span>
          </button>
        </div>
      </section>

      <div class="row-2 top">
        <section class="card flush">
          <template v-if="tab === 'purchases' || tab === 'wins'">
            <el-table :data="notices" :empty-text="tab === 'purchases' ? '还没有采购记录' : '还没有中标记录'">
              <el-table-column label="日期" width="116" align="center"><template #default="{ row }">{{ row.published_on || '—' }}</template></el-table-column>
              <el-table-column label="公告" min-width="300" header-align="center">
                <template #default="{ row }">
                  <button type="button" class="link-btn notice-title" data-action-id="A-209" @click="source = { id: row.source_id }">{{ row.title }}</button>
                  <div class="cell-sub">{{ tab === 'purchases' ? `中标方：${partyNames(row, ['winner'])}` : `采购方：${partyNames(row, ['buyer'])}` }}</div>
                </template>
              </el-table-column>
              <el-table-column label="类型" width="110" align="center">
                <template #default="{ row }"><span class="tag" :class="tab === 'wins' ? (row.role === 'winner' ? 'ok' : 'purple') : KIND_TONE[row.kind]">{{ tab === 'wins' ? (row.role === 'winner' ? '中标' : '候选') : row.kind_label }}</span></template>
              </el-table-column>
              <el-table-column :label="tab === 'purchases' ? '预算 / 金额' : '金额'" width="140" align="center">
                <template #default="{ row }"><span class="num amount">{{ money(tab === 'purchases' ? (row.budget ?? row.amount) : row.amount) }}</span></template>
              </el-table-column>
            </el-table>
          </template>
          <el-table v-else :data="relations" :empty-text="`还没有${TABS.find((t) => t.key === tab)?.label}`">
            <el-table-column label="企业" min-width="260" header-align="center">
              <template #default="{ row }"><RouterLink :to="`/companies/${row.company_id}`" class="cell-main" data-action-id="A-211">{{ row.name }}</RouterLink></template>
            </el-table-column>
            <el-table-column label="合作次数" width="110" align="center"><template #default="{ row }"><span class="num">{{ row.count }}</span></template></el-table-column>
            <el-table-column label="金额合计" width="150" align="center"><template #default="{ row }"><span class="num amount">{{ row.amount ? money(row.amount) : '—' }}</span></template></el-table-column>
            <el-table-column label="最近日期" width="120" align="center"><template #default="{ row }">{{ row.last_date || '—' }}</template></el-table-column>
          </el-table>
        </section>

        <div class="stack">
          <section v-if="details.length" class="card">
            <div class="card-title"><Icon name="doc" :size="18" />工商信息</div>
            <dl class="details">
              <template v-for="d in details" :key="d.field">
                <dt>{{ d.label }}</dt>
                <dd :class="{ clamp: d.field === 'scope' }">{{ profile[d.field]?.value || '—' }}
                  <button v-if="profile[d.field]?.evidence" type="button" class="evid" title="查看原文依据" aria-label="查看原文依据" data-action-id="A-208"
                          @click="open(profile[d.field].evidence)"><Icon name="doc" :size="14" /></button></dd>
              </template>
            </dl>
          </section>
          <section class="card">
            <div class="card-title"><Icon name="source" :size="18" /><span class="grow">来源</span><span class="extra">{{ company.sources.length }} 个页面</span></div>
            <div v-if="!company.sources.length" class="muted">还没有来源</div>
            <button v-for="s in company.sources.slice(0, 8)" :key="s.id" type="button" class="src-row" @click="source = { id: s.id }">
              <Icon name="external" :size="14" /><span class="grow">{{ s.title || s.url }}</span><span class="muted small">{{ dateParts(s.fetched_at).date }}</span>
            </button>
          </section>
        </div>
      </div>
    </template>
    <SourceDialog :source-id="source.id" :quote="source.quote" @close="source = { id: null }" />
  </div>
</template>

<style scoped>
.crumb { display: inline-flex; align-items: center; gap: 4px; color: var(--ink-3); width: fit-content; }
.identity { padding: 16px 16px 0; }
.id-main { display: flex; align-items: center; gap: 16px; flex-wrap: wrap; }
.logo { display: grid; place-items: center; width: 48px; height: 48px; border-radius: 12px; border: 1px solid var(--line-strong); color: var(--ink); flex: none; }
.id-text { flex: 1; min-width: 240px; }
.name { font-size: 22px; line-height: 30px; font-weight: 600; }
.id-tags { display: flex; gap: 6px; flex-wrap: wrap; margin-top: 6px; }
.facts { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 12px; margin-top: 16px; padding: 12px 16px; border-radius: 8px; border: 1px solid var(--line); background: var(--canvas); }
.facts.none { display: flex; align-items: center; gap: 8px; color: var(--ink-3); }
.top { align-items: start; }
.fact { display: flex; flex-direction: column; min-width: 0; }
.fact-label { font-size: 12px; color: var(--ink-3); }
.fact-value { display: flex; align-items: center; gap: 4px; font-size: 14px; font-weight: 600; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.evid { display: inline-grid; place-items: center; width: 22px; height: 22px; border: 0; border-radius: 4px; background: none; color: var(--accent); cursor: pointer; flex: none; vertical-align: middle; }
.evid:hover { background: var(--brand-tint); }
.stats { display: grid; grid-template-columns: repeat(5, minmax(0, 1fr)); margin-top: 16px; border-top: 1px solid var(--line); }
.stat { display: flex; align-items: center; justify-content: center; gap: 8px; height: 52px; border: 0; border-bottom: 2px solid transparent; background: none; font: inherit; color: var(--ink-2); cursor: pointer; }
.stat:hover { color: var(--ink); }
.stat.on { border-bottom-color: var(--ink); color: var(--ink); font-weight: 600; }
.stat-icon { display: inline-grid; place-items: center; color: var(--ink-3); }
.stat-num { font-size: 22px; line-height: 30px; font-weight: 600; color: var(--ink); font-variant-numeric: tabular-nums; }
.stat.on .stat-num { color: var(--ink); }
.stat-label { font-size: 14px; }
.notice-title { font-weight: 600; color: var(--ink); }
.notice-title:hover { color: var(--accent); }
.amount { font-weight: 600; }
.details { display: grid; grid-template-columns: 72px minmax(0, 1fr); gap: 10px 12px; margin: 0; }
.details dt { color: var(--ink-3); }
.details dd { margin: 0; word-break: break-all; }
.clamp { display: -webkit-box; -webkit-line-clamp: 4; -webkit-box-orient: vertical; overflow: hidden; }
.extra { font-size: 12px; font-weight: 400; color: var(--ink-3); }
.src-row { display: flex; width: 100%; gap: 8px; align-items: center; min-height: 40px; border: 0; border-top: 1px solid var(--line-2); background: none; font: inherit; color: var(--ink); text-align: left; cursor: pointer; }
.src-row:hover { color: var(--accent); }
.src-row .grow { flex: 1; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
a.el-button { text-decoration: none; }
@media (max-width: 760px) {
  .facts { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  .stats { grid-template-columns: repeat(3, minmax(0, 1fr)); }
  .stat { flex-direction: column; gap: 0; height: auto; padding: 8px 0; }
  .stat-icon { display: none; }
}
</style>
