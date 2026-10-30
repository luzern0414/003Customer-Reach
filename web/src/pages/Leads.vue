<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus/es/components/message/index'
import { ElMessageBox } from 'element-plus/es/components/message-box/index'
import { api, patch, query } from '../api'
import type { LeadItem, LeadList, LeadStatus } from '../types'
import { LEAD_STATUS, TONE_DOT, dateParts, due, monthDay, wan } from '../format'
import Icon from '../components/Icon.vue'

const route = useRoute()
const router = useRouter()
const SIZES = [10, 20, 50, 100]
function savedSize() {
  try { const n = Number(localStorage.getItem('dr.page_size')); return SIZES.includes(n) ? n : 20 } catch { return 20 }
}
const q = ref('')
// 默认先看待处理的新线索；“全部”放在最后
const status = ref<LeadStatus | ''>(route.query.status === 'all' ? '' : ((route.query.status as LeadStatus) || 'new'))
const owner = ref('')
// 默认只看还能投标的线索（没有截止时间或尚未截止）
const openOnly = ref(route.query.open !== '0')
const range = ref<'today' | '7' | '30' | 'all' | 'custom'>('all')
const custom = ref<[string, string] | null>(null)
const page = ref(Number(route.query.page) || 1)
const pageSize = ref(SIZES.includes(Number(route.query.page_size)) ? Number(route.query.page_size) : savedSize())
const data = ref<LeadList | null>(null)
const loading = ref(false)
const error = ref(false)
const flash = ref('')
let timer: number | undefined

const RANGES = [{ v: 'today', l: '今日' }, { v: '7', l: '近 7 天' }, { v: '30', l: '近 30 天' }, { v: 'all', l: '全部' }] as const
const STATUSES = Object.entries(LEAD_STATUS) as [LeadStatus, { label: string; tone: string }][]

function iso(d: Date) { return dateParts(d.toISOString()).date }
function purchaseLines(value?: string | null, fallback?: string | null) {
  const text = (value || fallback || '').trim()
  if (!text) return []
  const parts = text.split(/\r?\n|[；;，,]/).flatMap((part) => part.split('、'))
    .map((part) => part.replace(/\s+/g, ' ').replace(/^[•·●\-]+/, '').trim())
    .filter(Boolean)
  if (parts.length <= 3) return parts
  return [...parts.slice(0, 2), parts.slice(2).join('、')]
}
const filters = computed(() => {
  let start = '', end = ''
  if (range.value === 'today') start = iso(new Date())
  else if (range.value === '7' || range.value === '30') start = iso(new Date(Date.now() - Number(range.value) * 86400000))
  else if (range.value === 'custom' && custom.value) [start, end] = custom.value
  return { q: q.value.trim(), status: status.value, owner: owner.value, start, end, open: openOnly.value ? 1 : 0 }
})

async function load() {
  loading.value = true
  error.value = false
  router.replace({ query: { ...route.query, status: status.value || 'all', open: openOnly.value ? '1' : '0', page: String(page.value), page_size: String(pageSize.value) } })
  try {
    data.value = await api<LeadList>(`/leads${query({ ...filters.value, page: page.value, page_size: pageSize.value })}`, { notify: false })
  } catch {
    error.value = true
  } finally {
    loading.value = false
  }
}
watch(q, () => { window.clearTimeout(timer); timer = window.setTimeout(() => { page.value = 1; load() }, 250) })
watch([status, owner, range, custom, openOnly], () => { page.value = 1; load() })
watch(page, load)
watch(pageSize, (n) => {
  try { localStorage.setItem('dr.page_size', String(n)) } catch { /* 本机存储不可用 */ }
  if (page.value !== 1) page.value = 1
  else load()
})
onMounted(load)

const counts = computed(() => data.value?.counts)
const exportUrl = computed(() => `/api/leads/export${query(filters.value)}`)
const items = computed(() => (data.value?.items || []).map((row) => ({
  ...row,
  due: due(row.notice?.deadline_at || row.notice?.deadline),
  purchaseLines: purchaseLines(row.notice?.items, row.notice?.title || row.match_reason),
})))
// 整页为空的列隐藏；整页取值相同的评分写在状态行
const hasOwner = computed(() => items.value.some((r) => r.owner))
const hasRegion = computed(() => items.value.some((r) => r.company.region))
const hasFollowup = computed(() => items.value.some((r) => r.next_followup_at))
const sameScore = computed(() => { const s = new Set(items.value.map((r) => r.score)); return items.value.length > 1 && s.size === 1 ? items.value[0].score : null })
const filtered = computed(() => !!(q.value || status.value || owner.value || range.value !== 'all'))

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
    <div class="card flush">
      <div class="toolbar head">
        <el-input v-model="q" class="search" clearable placeholder="搜索企业名称或公告" data-action-id="A-301" @keydown.esc="q = ''">
          <template #prefix><Icon name="search" :size="16" /></template>
        </el-input>
        <el-select v-model="owner" clearable filterable placeholder="负责人" class="owner" data-action-id="A-303">
          <el-option v-for="o in data?.owners || []" :key="o" :label="o" :value="o" />
        </el-select>
        <span class="seg">
          <button v-for="r in RANGES" :key="r.v" type="button" :class="{ on: range === r.v }" data-action-id="A-304" @click="range = r.v; custom = null">{{ r.l }}</button>
        </span>
        <el-date-picker v-model="custom" type="daterange" value-format="YYYY-MM-DD" start-placeholder="开始日期" end-placeholder="结束日期" class="dates"
                        @change="range = custom ? 'custom' : 'all'" />
        <span class="grow" />
        <a :href="exportUrl" class="el-button" data-action-id="A-308"><Icon name="download" :size="16" /><span>导出筛选结果<template v-if="data">（{{ data.total }} 条）</template></span></a>
      </div>
      <div class="chips status-row">
        <button v-for="[k, s] in STATUSES" :key="k" type="button" class="chip" :class="[{ on: status === k, zero: !counts?.[k] }, `tone-${s.tone}`]" data-action-id="A-302" @click="status = k">
          {{ s.label }}<span class="count">{{ counts?.[k] ?? '' }}</span></button>
        <button type="button" class="chip" :class="{ on: !status }" data-action-id="A-302" @click="status = ''">全部<span class="count">{{ counts?.all ?? '' }}</span></button>
        <span class="grow" />
        <span v-if="sameScore !== null" class="muted small">本页评分均为 {{ sameScore }}</span>
        <label class="open-only"><el-switch v-model="openOnly" size="small" data-action-id="A-302" />只看可投标</label>
      </div>

      <div v-if="error" class="error-line">无法读取线索<el-button size="small" @click="load">重试</el-button></div>
      <template v-else>
        <el-table v-loading="loading && !!data" :data="items" row-key="id" :row-class-name="rowClass" class="desktop">
          <el-table-column label="客户" min-width="190" header-align="center">
            <template #default="{ row }"><RouterLink :to="`/leads/${row.id}`" class="cell-main cell-clip" :title="row.company.name" data-action-id="A-305">{{ row.company.name }}</RouterLink></template>
          </el-table-column>
          <el-table-column v-if="hasRegion" label="地区" width="120" align="center">
            <template #default="{ row }"><span class="cell-clip" :title="row.company.region">{{ row.company.region || '—' }}</span></template>
          </el-table-column>
          <el-table-column label="采购内容" min-width="280" header-align="center">
            <template #default="{ row }">
              <div class="purchase-cell" :title="row.notice?.title || row.match_reason">
                <span v-if="row.notice?.kind_label" class="tag plain kind">{{ row.notice.kind_label }}</span>
                <ul v-if="row.purchaseLines.length" class="purchase-list">
                  <li v-for="(line, index) in row.purchaseLines" :key="`${index}-${line}`">{{ line }}</li>
                </ul>
                <span v-else class="muted">—</span>
              </div>
            </template>
          </el-table-column>
          <el-table-column label="预算（万元）" width="120" header-align="center" align="right">
            <template #default="{ row }"><span class="num money">{{ wan(row.notice?.budget ?? row.notice?.amount) }}</span></template>
          </el-table-column>
          <el-table-column label="发布" width="120" align="center"><template #default="{ row }"><span class="num muted">{{ monthDay(row.notice?.published_on) }}</span></template></el-table-column>
          <el-table-column label="投标截止" width="184" align="center">
            <template #default="{ row }"><span v-if="row.due.short" class="due"><span class="num">{{ row.due.short }}</span><span class="due-left" :class="row.due.tone">{{ row.due.label }}</span></span><span v-else class="muted">—</span></template>
          </el-table-column>
          <el-table-column v-if="sameScore === null" label="评分" width="72" align="center"><template #default="{ row }"><span class="num">{{ row.score }}</span></template></el-table-column>
          <el-table-column label="状态" width="140" align="center">
            <template #default="{ row }">
              <el-select :model-value="row.status" size="small" class="status-select" data-action-id="A-306" @change="(v: LeadStatus) => changeStatus(row, v)">
                <template #prefix><span class="dot" :class="TONE_DOT[LEAD_STATUS[row.status as LeadStatus].tone]" /></template>
                <el-option v-for="[k, s] in STATUSES" :key="k" :label="s.label" :value="k" />
              </el-select>
            </template>
          </el-table-column>
          <el-table-column v-if="hasOwner" label="负责人" width="100" align="center"><template #default="{ row }">{{ row.owner || '—' }}</template></el-table-column>
          <el-table-column v-if="hasFollowup" label="下次跟进" width="120" align="center">
            <template #default="{ row }"><span class="num">{{ row.next_followup_at ? row.next_followup_at.slice(5, 16) : '—' }}</span></template>
          </el-table-column>
          <el-table-column label="创建" width="120" align="center"><template #default="{ row }"><span class="num muted">{{ monthDay(dateParts(row.created_at).date) }}</span></template></el-table-column>
          <el-table-column label="操作" width="72" align="center">
            <template #default="{ row }"><RouterLink :to="`/leads/${row.id}`" data-action-id="A-305">打开</RouterLink></template>
          </el-table-column>
          <template #empty>
            <div v-if="!loading" class="empty"><span class="icon-wrap"><Icon name="lead" :size="24" /></span>
              <div>{{ !data?.counts.all && openOnly ? '没有还能投标的线索' : filtered && status !== 'new' ? '没有符合条件的线索' : status === 'new' && data?.counts.all ? '没有新线索' : '还没有线索' }}</div>
              <el-button v-if="!data?.counts.all" type="primary" @click="router.push('/workbench')"><Icon name="plus" :size="16" /><span>去找买家</span></el-button></div>
          </template>
        </el-table>

        <div class="mobile">
          <RouterLink v-for="row in items" :key="row.id" :to="`/leads/${row.id}`" class="mcard" data-action-id="A-305">
            <div class="mrow"><span class="cell-main">{{ row.company.name }}</span><span class="tag" :class="LEAD_STATUS[row.status].tone">{{ row.status_label }}</span></div>
            <div class="mval" :title="row.notice?.title || row.match_reason">
              <ul v-if="row.purchaseLines.length" class="purchase-list">
                <li v-for="(line, index) in row.purchaseLines" :key="`${index}-${line}`">{{ line }}</li>
              </ul>
              <span v-else class="muted">—</span>
            </div>
            <div class="mrow"><span v-if="row.due.short" class="due"><span class="num muted">截止 {{ row.due.short }}</span><span class="due-left" :class="row.due.tone">{{ row.due.label }}</span></span><span v-else /><b class="num">{{ wan(row.notice?.budget ?? row.notice?.amount) }} 万元</b></div>
          </RouterLink>
          <div v-if="data && !data.items.length" class="empty">没有线索</div>
        </div>

        <div v-if="data && data.total" class="pager">
          <el-pagination v-model:current-page="page" v-model:page-size="pageSize" :page-sizes="SIZES" :total="data.total" data-action-id="A-307"
                         :layout="data.total > pageSize ? 'total, sizes, prev, pager, next' : 'total, sizes'" />
        </div>
      </template>
    </div>
  </div>
</template>

<style scoped>
.toolbar.head { padding: 12px 16px; }
.toolbar.head .search { width: 240px; }
.owner { width: 140px; }
.head :deep(.el-date-editor--daterange) { --el-date-editor-width: 240px; width: 240px; flex: none; }
.status-row { padding: 0 16px 12px; }
.chip[class*="tone-"] { transition: color .16s ease, background-color .16s ease, border-color .16s ease; }
.chip.tone-brand:hover, .chip.tone-brand.on { color: var(--accent-hover); background: var(--accent-tint); border-color: transparent; }
.chip.tone-warn:hover, .chip.tone-warn.on { color: var(--warn); background: var(--warn-tint); border-color: transparent; }
.chip.tone-teal:hover, .chip.tone-teal.on { color: var(--teal); background: var(--teal-tint); border-color: transparent; }
.chip.tone-purple:hover, .chip.tone-purple.on { color: var(--purple); background: var(--purple-tint); border-color: transparent; }
.chip.tone-ok:hover, .chip.tone-ok.on { color: var(--ok); background: var(--ok-tint); border-color: transparent; }
.chip.tone-grey:hover, .chip.tone-grey.on { color: var(--ink-2); background: var(--subtle); border-color: transparent; }
.kind { margin-right: 8px; vertical-align: 1px; }
.purchase-cell { min-width: 0; color: var(--ink-2); }
.purchase-list { display: flex; flex-direction: column; gap: 2px; margin: 0; padding: 0; list-style: none; line-height: 20px; }
.purchase-list li { position: relative; overflow: hidden; padding-left: 12px; text-overflow: ellipsis; white-space: nowrap; }
.purchase-list li::before { content: ''; position: absolute; top: 8px; left: 1px; width: 5px; height: 5px; border-radius: 50%; background: var(--accent); }
.open-only { display: inline-flex; align-items: center; gap: 8px; margin-left: 12px; color: var(--ink-2); cursor: pointer; white-space: nowrap; }
.money { font-weight: 600; color: var(--ink); }
.status-select { width: 100px; }
.status-select :deep(.el-select__prefix) { margin-right: 2px; }
.pager { padding: 12px 16px; border-top: 1px solid var(--line); }
:deep(.flash) td { animation: flash 1.2s; }
@keyframes flash { 0% { background: var(--subtle); } 100% { background: transparent; } }
a.el-button { text-decoration: none; }
.mobile { display: none; }
@media (max-width: 760px) {
  .desktop { display: none; }
  .mobile { display: flex; flex-direction: column; border-top: 1px solid var(--line); }
  .mcard { display: flex; flex-direction: column; gap: 4px; padding: 10px 16px; border-bottom: 1px solid var(--line); color: var(--ink); }
  .mrow { display: flex; justify-content: space-between; align-items: center; gap: 12px; min-height: 24px; }
  .mval { color: var(--ink-2); min-width: 0; }
  .mval .purchase-list { gap: 1px; }
  .mval .purchase-list li { white-space: normal; display: -webkit-box; -webkit-box-orient: vertical; -webkit-line-clamp: 2; }
  .owner, .seg { width: 100%; max-width: none; }
  .head :deep(.el-date-editor--daterange) { --el-date-editor-width: 100%; width: 100%; }
}
</style>
