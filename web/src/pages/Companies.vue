<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { api, query } from '../api'
import type { CompanyCard } from '../types'
import { LEAD_STATUS, monthDay } from '../format'
import Icon from '../components/Icon.vue'

const route = useRoute()
const router = useRouter()
const SIZES = [10, 20, 50, 100]
function savedSize() {
  try { const n = Number(localStorage.getItem('dr.page_size')); return SIZES.includes(n) ? n : 20 } catch { return 20 }
}
const q = ref('')
const role = ref((route.query.role as string) || '')
const page = ref(Number(route.query.page) || 1)
const pageSize = ref(SIZES.includes(Number(route.query.page_size)) ? Number(route.query.page_size) : savedSize())
const data = ref<{ total: number; items: CompanyCard[] } | null>(null)
const loading = ref(false)
const error = ref(false)
let timer: number | undefined

const ROLES = [{ v: '', l: '全部' }, { v: 'buyer', l: '采购方' }, { v: 'winner', l: '中标方' }]

async function load() {
  loading.value = true
  error.value = false
  router.replace({ query: { ...route.query, role: role.value || undefined, page: String(page.value), page_size: String(pageSize.value) } })
  try {
    data.value = await api(`/companies${query({ q: q.value.trim(), role: role.value, page: page.value, page_size: pageSize.value })}`, { notify: false })
  } catch {
    error.value = true
  } finally {
    loading.value = false
  }
}
watch(q, () => { window.clearTimeout(timer); timer = window.setTimeout(() => { page.value = 1; load() }, 250) })
watch(role, () => { page.value = 1; load() })
watch(page, load)
watch(pageSize, (n) => {
  try { localStorage.setItem('dr.page_size', String(n)) } catch { /* 本机存储不可用 */ }
  if (page.value !== 1) page.value = 1
  else load()
})
onMounted(load)

const items = computed(() => data.value?.items || [])
// 整页为空的列隐藏
const hasScope = computed(() => items.value.some((r) => r.scope))
const hasLegal = computed(() => items.value.some((r) => r.legal_person))
const hasCapital = computed(() => items.value.some((r) => r.registered_capital))
const phoneOf = (row: CompanyCard) => row.contact?.phone || row.phone || ''
</script>

<template>
  <div class="page">
    <div class="card flush">
      <div class="toolbar head">
        <el-input v-model="q" class="search" clearable placeholder="搜索企业名称" data-action-id="A-201" @keydown.esc="q = ''">
          <template #prefix><Icon name="search" :size="16" /></template>
        </el-input>
        <span class="seg">
          <button v-for="r in ROLES" :key="r.v" type="button" :class="{ on: role === r.v }" data-action-id="A-202" @click="role = r.v">{{ r.l }}</button>
        </span>
      </div>
      <div v-if="error" class="error-line">无法读取企业档案<el-button size="small" @click="load">重试</el-button></div>
      <template v-else>
        <el-table v-loading="loading && !!data" :data="items" row-key="id" class="clickable desktop" @row-click="(row: CompanyCard) => router.push(`/companies/${row.id}`)">
          <el-table-column label="企业" min-width="240" header-align="center">
            <template #default="{ row }">
              <span class="unit">
                <RouterLink :to="`/companies/${row.id}`" class="cell-main name" :title="row.name" data-action-id="A-203">{{ row.name }}</RouterLink>
                <span v-if="row.industry" class="tag plain ind" :title="row.industry">{{ row.industry }}</span>
              </span>
            </template>
          </el-table-column>
          <el-table-column v-if="hasScope" label="主营业务" min-width="200" header-align="center">
            <template #default="{ row }"><span class="cell-clip scope" :title="row.scope">{{ row.scope || '—' }}</span></template>
          </el-table-column>
          <el-table-column v-if="hasLegal" label="法人" width="110" align="center">
            <template #default="{ row }"><span class="cell-clip" :title="row.legal_person">{{ row.legal_person || '—' }}</span></template>
          </el-table-column>
          <el-table-column v-if="hasCapital" label="注册资本" width="120" header-align="center" align="right">
            <template #default="{ row }"><span class="num">{{ row.registered_capital || '—' }}</span></template>
          </el-table-column>
          <el-table-column label="联系电话" width="210" header-align="center">
            <template #default="{ row }">
              <span v-if="phoneOf(row)" class="contact" :title="[row.contact?.person, phoneOf(row)].filter(Boolean).join(' ')">
                <span v-if="row.contact?.person" class="who">{{ row.contact.person }}</span><span class="num phone">{{ phoneOf(row) }}</span></span>
              <span v-else class="muted">—</span>
            </template>
          </el-table-column>
          <el-table-column label="采购" width="72" align="center"><template #default="{ row }"><span class="num">{{ row.purchases }}</span></template></el-table-column>
          <el-table-column label="中标" width="72" align="center"><template #default="{ row }"><span class="num">{{ row.wins }}</span></template></el-table-column>
          <el-table-column label="最近公告" width="164" align="center">
            <template #default="{ row }">
              <span v-if="row.latest_notice" class="due"><span class="tag plain">{{ row.latest_notice.kind }}</span><span class="num muted">{{ monthDay(row.latest_notice.date) }}</span></span>
              <span v-else class="muted">—</span>
            </template>
          </el-table-column>
          <el-table-column label="线索" width="104" align="center">
            <template #default="{ row }"><span v-if="row.lead" class="tag" :class="LEAD_STATUS[row.lead.status as keyof typeof LEAD_STATUS].tone">{{ LEAD_STATUS[row.lead.status as keyof typeof LEAD_STATUS].label }}</span><span v-else class="muted">—</span></template>
          </el-table-column>
          <template #empty>
            <div v-if="loading" class="muted">&nbsp;</div>
            <div v-else class="empty"><span class="icon-wrap"><Icon name="company" :size="24" /></span>
              <div>{{ q || role ? '没有符合条件的企业' : '还没有企业档案' }}</div>
              <el-button v-if="!q && !role" type="primary" @click="router.push('/workbench')"><Icon name="plus" :size="16" /><span>发起研究</span></el-button></div>
          </template>
        </el-table>

        <div class="mobile">
          <RouterLink v-for="row in items" :key="row.id" :to="`/companies/${row.id}`" class="mcard" data-action-id="A-203">
            <div class="mrow"><span class="cell-main">{{ row.name }}</span><span v-if="row.lead" class="tag" :class="LEAD_STATUS[row.lead.status as keyof typeof LEAD_STATUS].tone">{{ LEAD_STATUS[row.lead.status as keyof typeof LEAD_STATUS].label }}</span></div>
            <div class="mrow muted"><span>采购 {{ row.purchases }} · 中标 {{ row.wins }}</span><span class="num">{{ phoneOf(row) }}</span></div>
          </RouterLink>
        </div>

        <div v-if="data && data.total" class="pager">
          <el-pagination v-model:current-page="page" v-model:page-size="pageSize" :page-sizes="SIZES" :total="data.total" data-action-id="A-204"
                         :layout="data.total > pageSize ? 'total, sizes, prev, pager, next' : 'total, sizes'" />
        </div>
      </template>
    </div>
  </div>
</template>

<style scoped>
.toolbar.head { padding: 12px 16px; }
.clickable :deep(.el-table__row) { cursor: pointer; }
/* 单位类型标签放不下时整体换到被裁掉的第二行，不挤压名称 */
.unit { display: flex; flex-wrap: wrap; align-items: center; column-gap: 8px; height: 22px; overflow: hidden; min-width: 0; }
.name { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; flex: 0 0 auto; max-width: 100%; }
.ind { flex: none; max-width: 10em; overflow: hidden; text-overflow: ellipsis; display: inline-block; line-height: 22px; }
.scope { color: var(--ink-2); }
.contact { display: flex; gap: 8px; overflow: hidden; white-space: nowrap; }
.who { color: var(--ink); overflow: hidden; text-overflow: ellipsis; max-width: 6em; }
.phone { overflow: hidden; text-overflow: ellipsis; }
.pager { padding: 12px 16px; border-top: 1px solid var(--line); }
.mobile { display: none; }
@media (max-width: 760px) {
  .desktop { display: none; }
  .mobile { display: flex; flex-direction: column; border-top: 1px solid var(--line); }
  .mcard { display: flex; flex-direction: column; gap: 4px; padding: 10px 16px; border-bottom: 1px solid var(--line); color: var(--ink); }
  .mrow { display: flex; justify-content: space-between; align-items: center; gap: 12px; }
  .seg { width: 100%; }
}
</style>
