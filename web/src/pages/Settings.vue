<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { ApiError, api, del, get, patch, post } from '../api'
import type { KnowledgeItem, Settings } from '../types'
import { dateParts } from '../format'
import Icon from '../components/Icon.vue'

const settings = ref<Settings | null>(null)
const error = ref(false)
const saving = ref('')
const knowledge = ref<KnowledgeItem[]>([])
const dialog = ref(false)
const draft = reactive({ kind: 'preference' as KnowledgeItem['kind'], title: '', body: '' })
const test = ref<{ state: '' | 'running' | 'ok' | 'fail'; text: string }>({ state: '', text: '' })
const KINDS: Record<KnowledgeItem['kind'], string> = { preference: '偏好', exclusion: '排除', product: '产品资料' }

async function load() {
  error.value = false
  try {
    settings.value = await api<Settings>('/settings', { notify: false })
    knowledge.value = await get<KnowledgeItem[]>('/knowledge')
  } catch {
    error.value = true
  }
}
onMounted(load)

async function save(group: 'company' | 'scope') {
  const s = settings.value!
  const body = group === 'company'
    ? { company_name: s.company_name.trim(), company_profile: s.company_profile.trim() }
    : { default_days: s.default_days, target_regions: s.target_regions, max_queries: s.max_queries, max_reads: s.max_reads, max_enrich: s.max_enrich, target_leads: s.target_leads, max_rounds: s.max_rounds, max_model_calls: s.max_model_calls, max_minutes: s.max_minutes }
  saving.value = group
  try {
    settings.value = await patch<Settings>('/settings', body)
    ElMessage.success('已保存')
  } finally {
    saving.value = ''
  }
}

async function addKnowledge() {
  if (!draft.body.trim()) return ElMessage.error('请填写内容')
  saving.value = 'knowledge'
  try {
    knowledge.value.unshift(await post<KnowledgeItem>('/knowledge', { ...draft, body: draft.body.trim() }))
    dialog.value = false
    Object.assign(draft, { kind: 'preference', title: '', body: '' })
    ElMessage.success('已新增')
  } finally {
    saving.value = ''
  }
}

async function disable(item: KnowledgeItem) {
  try {
    await ElMessageBox.confirm('', `停用 ${item.title || KINDS[item.kind]}`, { confirmButtonText: '停用', cancelButtonText: '取消', type: 'warning', confirmButtonClass: 'el-button--danger' })
  } catch { return }
  await del(`/knowledge/${item.id}`)
  knowledge.value = knowledge.value.filter((k) => k.id !== item.id)
  ElMessage.success('已停用')
}

async function testModel() {
  test.value = { state: 'running', text: '' }
  try {
    const result = await api<{ elapsed_ms: number }>('/settings/test-model', { method: 'POST', notify: false })
    test.value = { state: 'ok', text: `结构化输出、流式输出正常 · ${(result.elapsed_ms / 1000).toFixed(1)} 秒` }
  } catch (e) {
    test.value = { state: 'fail', text: e instanceof ApiError ? e.message : '无法连接服务' }
  }
}
</script>

<template>
  <div class="page">
    <div class="page-head"><span class="page-title"><Icon name="settings" :size="22" />系统设置</span></div>
    <div v-if="error" class="error-line">无法读取设置<el-button size="small" @click="load">重试</el-button></div>
    <el-skeleton v-else-if="!settings" :rows="10" animated class="card" />
    <div v-else class="row-2 even">
      <div class="stack">
        <div class="card">
          <div class="card-title"><Icon name="company" :size="18" />公司与产品</div>
          <el-form label-position="top">
            <el-form-item label="公司名称"><el-input v-model="settings.company_name" maxlength="100" placeholder="例如：某某网络安全科技有限公司" /></el-form-item>
            <el-form-item label="公司与产品介绍"><el-input v-model="settings.company_profile" type="textarea" :rows="6" maxlength="4000" show-word-limit
                                                         placeholder="例如：主营下一代防火墙、入侵防御，服务政府与医疗客户" /></el-form-item>
            <el-button type="primary" :loading="saving === 'company'" data-action-id="A-501" @click="save('company')"><Icon name="check" :size="16" /><span>保存公司与产品</span></el-button>
          </el-form>
        </div>
        <div class="card">
          <div class="card-title"><Icon name="search" :size="18" />检索范围与额度</div>
          <el-form label-position="top" class="cols">
            <el-form-item label="默认时间范围（天）"><el-input-number v-model="settings.default_days" :min="1" :max="730" controls-position="right" /></el-form-item>
            <el-form-item label="每次检索数"><el-input-number v-model="settings.max_queries" :min="1" :max="30" controls-position="right" /></el-form-item>
            <el-form-item label="每次阅读公告数"><el-input-number v-model="settings.max_reads" :min="1" :max="60" controls-position="right" /></el-form-item>
            <el-form-item label="目标线索数"><el-input-number v-model="settings.target_leads" :min="1" :max="200" controls-position="right" /></el-form-item>
            <el-form-item label="最多检索轮数"><el-input-number v-model="settings.max_rounds" :min="1" :max="10" controls-position="right" /></el-form-item>
            <el-form-item label="补充工商信息的采购方数"><el-input-number v-model="settings.max_enrich" :min="0" :max="30" controls-position="right" /></el-form-item>
            <el-form-item label="模型调用上限"><el-input-number v-model="settings.max_model_calls" :min="5" :max="200" controls-position="right" /></el-form-item>
            <el-form-item label="最长时长（分钟）"><el-input-number v-model="settings.max_minutes" :min="3" :max="120" controls-position="right" /></el-form-item>
            <el-form-item label="目标地区" class="full">
              <el-select v-model="settings.target_regions" multiple filterable allow-create default-first-option placeholder="例如：广东省" />
            </el-form-item>
          </el-form>
          <el-button type="primary" :loading="saving === 'scope'" data-action-id="A-502" @click="save('scope')"><Icon name="check" :size="16" /><span>保存检索范围与额度</span></el-button>
        </div>
      </div>
      <div class="stack">
        <div class="card">
          <div class="card-title"><Icon name="note" :size="18" /><span class="grow">偏好与排除</span>
            <el-button size="small" data-action-id="A-503" @click="dialog = true"><Icon name="plus" :size="16" /><span>新增</span></el-button></div>
          <div v-if="!knowledge.length" class="muted">还没有偏好、排除或产品资料</div>
          <div v-for="k in knowledge" :key="k.id" class="kitem">
            <div class="krow"><span class="tag" :class="k.kind === 'exclusion' ? 'danger' : k.kind === 'product' ? 'brand' : 'teal'">{{ KINDS[k.kind] }}</span>
              <span class="ktitle">{{ k.title || '—' }}</span><span class="muted small">{{ dateParts(k.updated_at).date }}</span>
              <button type="button" class="link-btn danger" data-action-id="A-504" :aria-label="`停用${k.title}`" @click="disable(k)"><Icon name="trash" :size="16" /></button></div>
            <div class="kbody">{{ k.body }}</div>
          </div>
        </div>
        <div class="card">
          <div class="card-title"><Icon name="spark" :size="18" />模型连接</div>
          <div class="row">
            <el-button :loading="test.state === 'running'" data-action-id="A-505" @click="testModel"><Icon name="play" :size="16" /><span>测试连接</span></el-button>
            <span v-if="test.state === 'ok'" class="tag ok">{{ test.text }}</span>
            <span v-else-if="test.state === 'fail'" class="tag danger">{{ test.text }}</span>
          </div>
        </div>
      </div>
    </div>

    <el-dialog v-model="dialog" title="新增偏好与排除" width="min(560px, calc(100vw - 24px))" align-center :close-on-click-modal="false">
      <el-form label-position="top">
        <el-form-item label="类型" required>
          <el-radio-group v-model="draft.kind"><el-radio-button v-for="(l, k) in KINDS" :key="k" :value="k">{{ l }}</el-radio-button></el-radio-group>
        </el-form-item>
        <el-form-item label="标题"><el-input v-model="draft.title" maxlength="200" placeholder="例如：不做施工总包" /></el-form-item>
        <el-form-item label="内容" required><el-input v-model="draft.body" type="textarea" :rows="5" maxlength="8000" show-word-limit /></el-form-item>
      </el-form>
      <template #footer><el-button @click="dialog = false">取消</el-button><el-button type="primary" :loading="saving === 'knowledge'" @click="addKnowledge">新增</el-button></template>
    </el-dialog>
  </div>
</template>

<style scoped>
.cols { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 0 16px; }
.cols .full { grid-column: 1 / -1; }
.cols :deep(.el-input-number), .cols :deep(.el-select) { width: 100%; }
.kitem { padding: 10px 0; border-top: 1px solid var(--line-2); }
.kitem:first-of-type { border-top: 0; }
.krow { display: flex; gap: 8px; align-items: center; }
.ktitle { flex: 1; min-width: 0; font-weight: 600; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.kbody { margin-top: 4px; color: var(--ink-2); white-space: pre-wrap; display: -webkit-box; -webkit-line-clamp: 3; -webkit-box-orient: vertical; overflow: hidden; }
.danger { color: var(--danger); }
.row { display: flex; gap: 12px; align-items: center; flex-wrap: wrap; }
.grow { flex: 1; }
@media (max-width: 760px) { .cols { grid-template-columns: minmax(0, 1fr); } }
</style>
