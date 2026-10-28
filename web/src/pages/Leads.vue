<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { api, patch, query } from '../api'
import type { LeadItem, LeadList, LeadStatus } from '../types'
import { LEAD_STATUS, dateParts } from '../format'
import Icon from '../components/Icon.vue'

const route = useRoute()
const router = useRouter()
const q = ref('')
const status = ref<LeadStatus | ''>((route.query.status as LeadStatus) || '')
const owner = ref('')
const range = ref<'today' | '7' | '30' | 'all' | 'custom'>('all')
const custom = ref<[string, string] | null>(null)
const page = ref(1)
const data = ref<LeadList | null>(null)
const loading = ref(false)
const error = ref(false)
const flash = ref('')
let timer: number | undefined

const RANGES = [{ v: 'today', l: '今日' }, { v: '7', l: '近 7 天' }, { v: '30', l: '近 30 天' }, { v: 'all', l: '全部' }] as const
const STATUSES = Object.entries(LEAD_STATUS) as [LeadStatus, { label: string; tone: string }][]

function iso(d: Date) { return dateParts(d.toISOString()).date }
const filters = computed(() => {
  let start = '', end = ''
  if (range.value === 'today') start = iso(new Date())
  else if (range.value === '7' || range.value === '30') start = iso(new Date(Date.now() - Number(range.value) * 86400000))
  else if (range.value === 'custom' && custom.value) [start, end] = custom.value
  return { q: q.value.trim(), status: status.value, owner: owner.value, start, end }
})

async function load() {
  loading.value = true
  error.value = false
  try {
    data.value = await api<LeadList>(`/leads${query({ ...filters.value, page: page.value, page_size: 20 })}`, { notify: false })
  } catch {
    error.value = true
  } finally {
    loading.value = false
  }
}
watch(q, () => { window.clearTimeout(timer); timer = window.setTimeout(() => { page.value = 1; load() }, 250) })
watch([status, owner, range, custom], () => { page.value = 1; load() })
watch(page, load)
onMounted(load)

const counts = computed(() => data.value?.counts)
const stats = computed(() => counts.value ? [
  { label: '全部线索', value: counts.value.all, icon: 'lead' },
  { label: '新线索', value: counts.value.new, icon: 'flag' },
  { label: '跟进中', value: counts.value.contacted + counts.value.following, icon: 'phone' },
  { label: '已成交', value: counts.value.won, icon: 'check' },
] : [])
const exportUrl = computed(() => `/api/leads/export${query(filters.value)}`)

async function changeStatus(row: LeadItem, next: LeadStatus) {
  if (next === row.status) return
  if (next === 'invalid') {
    try {
      await ElMessageBox.confirm('', `将 ${row.company.name} 标为无效`, { confirmButtonText: '标为无效', cancelButtonText: '取消', type: 'warning', confirmButtonClass: 'el-button--danger' })
    } catch { return }
  }
  await patch(`/leads/${row.id}`, { status: next })
  ElMessage.success('已更新状态')
  flash.value = row.id
  window.setTimeout(() => { flash.value = '' }, 1200)
  load()
}
const rowClass = ({ row }: { row: LeadItem }) => (row.id === flash.value ? 'flash' : '')
</script>

<template>
  <div class="page">
    <div class="page-head">
      <span class="page-title"><Icon name="lead" :size="22" />线索管理</span>
      <div class="page-actions"><a :href="exportUrl" class="el-button" data-action-id="A-308"><Icon name="download" :size="16" /><span>导出</span></a></div>
    </div>

    <div class="kpis">
      <div v-for="s in stats" :key="s.label" class="kpi">
        <div class="kpi-top"><span class="kpi-icon"><Icon :name="s.icon" :size="18" /></span><span class="kpi-label">{{ s.label }}</span></div>
        <div class="kpi-num">{{ s.value }}</div>
      </div>
    </div>

    <div class="card">
      <div class="toolbar">
        <el-input v-model="q" class="search" clearable placeholder="搜索客户或线索依据" data-action-id="A-301" @keydown.esc="q = ''">
          <template #prefix><Icon name="search" :size="16" /></template>
        </el-input>
        <el-select v-model="owner" clearable filterable placeholder="负责人" class="owner" data-action-id="A-303">
          <el-option v-for="o in data?.owners || []" :key="o" :label="o" :value="o" />
        </el-select>
        <button v-for="r in RANGES" :key="r.v" type="button" class="chip" :class="{ on: range === r.v }" data-action-id="A-304" @click="range = r.v; custom = null">{{ r.l }}</button>
        <el-date-picker v-model="custom" type="daterange" value-format="YYYY-MM-DD" start-placeholder="开始日期" end-placeholder="结束日期" class="dates"
                        @change="range = custom ? 'custom' : 'all'" />
      </div>
      <div class="toolbar status-row">
        <button type="button" class="chip" :class="{ on: !status }" data-action-id="A-302" @click="status = ''">全部 {{ counts?.all ?? '' }}</button>
        <button v-for="[k, s] in STATUSES" :key="k" type="button" class="chip" :class="{ on: status === k }" data-action-id="A-302" @click="status = k">{{ s.label }} {{ counts?.[k] ?? '' }}</button>
      </div>

      <div v-if="error" class="error-line">无法读取线索<el-button size="small" @click="load">重试</el-button></div>
      <template v-else>
        <el-table v-loading="loading && !!data" :data="data?.items || []" row-key="id" :row-class-name="rowClass" class="desktop">
          <el-table-column label="客户" min-width="200" header-align="center">
            <template #default="{ row }">
              <RouterLink :to="`/leads/${row.id}`" class="cell-main" data-action-id="A-305">{{ row.company.name }}</RouterLink>
              <div v-if="row.company.region" class="cell-sub">{{ row.company.region }}</div>
            </template>
          </el-table-column>
          <el-table-column label="线索依据" min-width="240" header-align="center" show-overflow-tooltip>
            <template #default="{ row }">{{ row.match_reason || '—' }}</template>
          </el-table-column>
          <el-table-column label="评分" width="80" align="center"><template #default="{ row }"><span class="num">{{ row.score }}</span></template></el-table-column>
          <el-table-column label="状态" width="140" align="center">
            <template #default="{ row }">
              <el-select :model-value="row.status" class="status-select" data-action-id="A-306" @change="(v: LeadStatus) => changeStatus(row, v)">
                <el-option v-for="[k, s] in STATUSES" :key="k" :label="s.label" :value="k" />
              </el-select>
            </template>
          </el-table-column>
          <el-table-column label="负责人" width="100" align="center"><template #default="{ row }">{{ row.owner || '—' }}</template></el-table-column>
          <el-table-column label="下次跟进" width="110" align="center">
            <template #default="{ row }"><div class="cell-date">{{ row.next_followup_at ? row.next_followup_at.slice(0, 10) : '—' }}<small v-if="row.next_followup_at.length > 10">{{ row.next_followup_at.slice(11, 16) }}</small></div></template>
          </el-table-column>
          <el-table-column label="创建" width="110" align="center"><template #default="{ row }">{{ dateParts(row.created_at).date }}</template></el-table-column>
          <el-table-column label="操作" width="80" align="center">
            <template #default="{ row }"><RouterLink :to="`/leads/${row.id}`" data-action-id="A-305">打开</RouterLink></template>
          </el-table-column>
          <template #empty>
            <div v-if="!loading" class="empty"><span class="icon-wrap"><Icon name="lead" :size="40" /></span>
              <div>{{ q || status || owner || range !== 'all' ? '没有符合条件的线索' : '还没有线索' }}</div>
              <el-button v-if="!(q || status || owner || range !== 'all')" type="primary" @click="router.push('/workbench')"><Icon name="plus" :size="16" /><span>去找买家</span></el-button></div>
          </template>
        </el-table>

        <div class="mobile">
          <RouterLink v-for="row in data?.items || []" :key="row.id" :to="`/leads/${row.id}`" class="mcard" data-action-id="A-305">
            <div class="mrow"><span class="cell-main">{{ row.company.name }}</span><span class="tag" :class="LEAD_STATUS[row.status].tone">{{ row.status_label }}</span></div>
            <div class="mrow"><span class="muted">线索依据</span><span class="mval">{{ row.match_reason || '—' }}</span></div>
            <div class="mrow"><span class="muted">评分</span><span>{{ row.score }}</span></div>
            <div class="mrow"><span class="muted">负责人</span><span>{{ row.owner || '—' }}</span></div>
            <div class="mrow"><span class="muted">创建</span><span>{{ dateParts(row.created_at).date }}</span></div>
          </RouterLink>
          <div v-if="data && !data.items.length" class="empty">没有线索</div>
        </div>

        <div v-if="data && data.total > 20" class="pager">
          <el-pagination v-model:current-page="page" layout="total, prev, pager, next" :page-size="20" :total="data.total" data-action-id="A-307" />
        </div>
      </template>
    </div>
  </div>
</template>

<style scoped>
.kpis { grid-template-columns: repeat(4, minmax(0, 1fr)); }
.owner { width: 140px; }
.dates { max-width: 280px; }
.status-row { margin-top: -4px; }
.status-select { width: 112px; }
:deep(.flash) td { animation: flash 1.2s; }
@keyframes flash { 0% { background: var(--brand-tint); } 100% { background: transparent; } }
a.el-button { text-decoration: none; }
.mobile { display: none; }
@media (max-width: 760px) {
  .kpis { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  .desktop { display: none; }
  .mobile { display: flex; flex-direction: column; gap: 12px; }
  .mcard { display: flex; flex-direction: column; gap: 6px; padding: 12px; border: 1px solid var(--line); border-radius: 12px; color: var(--ink); }
  .mrow { display: flex; justify-content: space-between; gap: 12px; min-height: 24px; }
  .mval { text-align: right; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .owner, .dates { width: 100%; max-width: none; }
}
</style>
