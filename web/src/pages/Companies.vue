<script setup lang="ts">
import { onMounted, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { api, query } from '../api'
import type { CompanyCard } from '../types'
import { KIND_TONE, LEAD_STATUS } from '../format'
import Icon from '../components/Icon.vue'

const router = useRouter()
const q = ref('')
const role = ref('')
const page = ref(1)
const data = ref<{ total: number; items: CompanyCard[] } | null>(null)
const loading = ref(false)
const error = ref(false)
let timer: number | undefined
const ROLES = [{ v: '', l: '全部' }, { v: 'buyer', l: '采购方' }, { v: 'winner', l: '中标方' }]
const KIND_BY_LABEL: Record<string, string> = { 采购意向: 'intent', 招标公告: 'tender', 更正公告: 'change', 中标候选: 'candidate', 中标结果: 'award', 合同公告: 'contract' }

async function load() {
  loading.value = true
  error.value = false
  try {
    data.value = await api(`/companies${query({ q: q.value.trim(), role: role.value, page: page.value, page_size: 20 })}`, { notify: false })
  } catch {
    error.value = true
  } finally {
    loading.value = false
  }
}
watch(q, () => { window.clearTimeout(timer); timer = window.setTimeout(() => { page.value = 1; load() }, 250) })
watch(role, () => { page.value = 1; load() })
watch(page, load)
onMounted(load)
</script>

<template>
  <div class="page">
    <div class="page-head"><span class="page-title"><Icon name="company" :size="22" />企业档案</span></div>
    <div class="card">
      <div class="toolbar">
        <el-input v-model="q" class="search" clearable placeholder="搜索企业名称" data-action-id="A-201" @keydown.esc="q = ''">
          <template #prefix><Icon name="search" :size="16" /></template>
        </el-input>
        <button v-for="r in ROLES" :key="r.v" type="button" class="chip" :class="{ on: role === r.v }" data-action-id="A-202" @click="role = r.v">{{ r.l }}</button>
      </div>
      <div v-if="error" class="error-line">无法读取企业档案<el-button size="small" @click="load">重试</el-button></div>
      <template v-else>
        <el-table v-loading="loading && !!data" :data="data?.items || []" row-key="id" @row-click="(row: CompanyCard) => router.push(`/companies/${row.id}`)" class="clickable">
          <el-table-column label="企业" min-width="210" header-align="center">
            <template #default="{ row }">
              <RouterLink :to="`/companies/${row.id}`" class="cell-main" data-action-id="A-203">{{ row.name }}</RouterLink>
              <div class="cell-sub">
                <span v-if="row.business_status" class="status">{{ row.business_status }}</span>{{ [row.industry, row.region].filter(Boolean).join(' · ') }}
              </div>
            </template>
          </el-table-column>
          <el-table-column label="主营业务" min-width="160" header-align="center" show-overflow-tooltip>
            <template #default="{ row }"><span class="scope">{{ row.scope || '—' }}</span></template>
          </el-table-column>
          <el-table-column label="法人 / 注册资本" width="148" align="center">
            <template #default="{ row }">
              <template v-if="row.legal_person || row.registered_capital"><div>{{ row.legal_person || '—' }}</div><div class="cell-sub num">{{ row.registered_capital || '—' }}</div></template>
              <span v-else>—</span>
            </template>
          </el-table-column>
          <el-table-column label="联系人" width="150" align="center">
            <template #default="{ row }">
              <template v-if="row.contact || row.phone">
                <div v-if="row.contact?.person">{{ row.contact.person }}</div><div class="num" :class="{ 'cell-sub': row.contact?.person }">{{ row.contact?.phone || row.phone }}</div>
              </template>
              <span v-else>—</span>
            </template>
          </el-table-column>
          <el-table-column label="采购 / 中标" width="118" align="center">
            <template #default="{ row }"><span class="num counts"><b>{{ row.purchases }}</b> / <b>{{ row.wins }}</b></span></template>
          </el-table-column>
          <el-table-column label="最近公告" width="130" align="center">
            <template #default="{ row }">
              <template v-if="row.latest_notice"><span class="tag" :class="KIND_TONE[KIND_BY_LABEL[row.latest_notice.kind] || 'other']">{{ row.latest_notice.kind }}</span>
                <div class="cell-sub">{{ row.latest_notice.date || '—' }}</div></template>
              <span v-else>—</span>
            </template>
          </el-table-column>
          <el-table-column label="线索" width="96" align="center">
            <template #default="{ row }"><span v-if="row.lead" class="tag" :class="LEAD_STATUS[row.lead.status as keyof typeof LEAD_STATUS].tone">{{ LEAD_STATUS[row.lead.status as keyof typeof LEAD_STATUS].label }}</span><span v-else>—</span></template>
          </el-table-column>
          <template #empty>
            <div v-if="loading" class="muted">&nbsp;</div>
            <div v-else class="empty"><span class="icon-wrap"><Icon name="company" :size="40" /></span>
              <div>{{ q || role ? '没有符合条件的企业' : '还没有企业档案' }}</div>
              <el-button v-if="!q && !role" type="primary" @click="router.push('/workbench')"><Icon name="plus" :size="16" /><span>发起研究</span></el-button></div>
          </template>
        </el-table>
        <div v-if="data && data.total > 20" class="pager">
          <el-pagination v-model:current-page="page" layout="total, prev, pager, next" :page-size="20" :total="data.total" data-action-id="A-204" />
        </div>
      </template>
    </div>
  </div>
</template>

<style scoped>
.clickable :deep(.el-table__row) { cursor: pointer; }
.status { margin-right: 6px; color: var(--ok); }
.scope { color: var(--ink-2); }
.counts b { font-weight: 600; color: var(--ink); }
</style>
