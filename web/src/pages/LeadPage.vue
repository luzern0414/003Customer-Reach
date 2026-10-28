<script setup lang="ts">
import { reactive, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { ApiError, api, patch, post } from '../api'
import type { LeadDetail, LeadStatus, MatchAnalysis } from '../types'
import { FEEDBACK_KIND, FOLLOWUP_KIND, KIND_TONE, LEAD_STATUS, dateParts, money } from '../format'
import Icon from '../components/Icon.vue'
import SourceDialog from '../components/SourceDialog.vue'

const route = useRoute()
const router = useRouter()
const lead = ref<LeadDetail | null>(null)
const state = ref<'loading' | 'missing' | 'error' | 'ok'>('loading')
const plan = reactive({ status: 'new' as LeadStatus, owner: '', next_followup_at: '' })
const note = reactive({ kind: 'note', content: '' })
const feedback = reactive({ kind: '', content: '' })
const focus = ref('')
const saving = ref('')
const source = ref<string | null>(null)
const STATUSES = Object.entries(LEAD_STATUS) as [LeadStatus, { label: string; tone: string }][]

function apply(data: LeadDetail) {
  lead.value = data
  Object.assign(plan, { status: data.status, owner: data.owner, next_followup_at: data.next_followup_at })
}

async function load() {
  state.value = 'loading'
  try {
    apply(await api<LeadDetail>(`/leads/${route.params.id}`, { notify: false }))
    state.value = 'ok'
  } catch (error) {
    state.value = error instanceof ApiError && error.status === 404 ? 'missing' : 'error'
  }
}
watch(() => route.params.id, load, { immediate: true })

async function savePlan() {
  if (plan.owner.length > 64) return ElMessage.error('负责人不超过 64 字')
  if (plan.status === 'invalid' && lead.value?.status !== 'invalid') {
    try { await ElMessageBox.confirm('', `将 ${lead.value!.company.name} 标为无效`, { confirmButtonText: '标为无效', cancelButtonText: '取消', type: 'warning', confirmButtonClass: 'el-button--danger' }) } catch { return }
  }
  saving.value = 'plan'
  try { apply(await patch<LeadDetail>(`/leads/${lead.value!.id}`, plan)); ElMessage.success('已保存跟进安排') } finally { saving.value = '' }
}

async function addNote() {
  if (!note.content.trim()) return ElMessage.error('请填写跟进内容')
  saving.value = 'note'
  try { apply(await post<LeadDetail>(`/leads/${lead.value!.id}/followups`, note)); note.content = ''; ElMessage.success('已添加跟进记录') } finally { saving.value = '' }
}

async function sendFeedback() {
  if (!feedback.kind) return ElMessage.error('请选择反馈类型')
  if (feedback.kind === 'not_buyer') {
    try { await ElMessageBox.confirm('', `将 ${lead.value!.company.name} 标为不是买家`, { confirmButtonText: '提交', cancelButtonText: '取消', type: 'warning', confirmButtonClass: 'el-button--danger' }) } catch { return }
  }
  saving.value = 'feedback'
  try { apply(await post<LeadDetail>(`/leads/${lead.value!.id}/feedback`, feedback)); Object.assign(feedback, { kind: '', content: '' }); ElMessage.success('已提交反馈') } finally { saving.value = '' }
}

async function analyze() {
  saving.value = 'analysis'
  try { apply(await post<LeadDetail>(`/leads/${lead.value!.id}/analysis`, { focus: focus.value })) } finally { saving.value = '' }
}

const analysis = () => (lead.value?.analysis && 'items' in lead.value.analysis ? (lead.value.analysis as MatchAnalysis) : null)
const FIT_TONE: Record<string, string> = { 相关: 'ok', 能力缺口: 'danger', 待核验: 'warn' }
function copy(text: string) { navigator.clipboard.writeText(text).then(() => ElMessage.success('已复制')) }
</script>

<template>
  <div class="page">
    <div v-if="state === 'loading'" class="card"><el-skeleton :rows="10" animated /></div>
    <div v-else-if="state === 'missing'" class="card empty"><div>线索不存在或已被删除</div><el-button @click="router.push('/leads')">返回线索管理</el-button></div>
    <div v-else-if="state === 'error'" class="error-line">无法读取线索<el-button size="small" @click="load">重试</el-button></div>
    <template v-else-if="lead">
      <div class="page-head">
        <div class="title-block">
          <RouterLink to="/leads" class="crumb"><Icon name="back" :size="16" />线索管理</RouterLink>
          <span class="page-title">{{ lead.company.name }}</span>
          <div class="sub"><span class="tag" :class="LEAD_STATUS[lead.status].tone">{{ lead.status_label }}</span><span>评分 {{ lead.score }}</span>
            <span v-if="lead.company.region">{{ lead.company.region }}</span></div>
        </div>
        <div class="page-actions"><el-button data-action-id="A-309" @click="router.push(`/companies/${lead.company.id}`)"><Icon name="company" :size="16" /><span>打开企业档案</span></el-button></div>
      </div>

      <div class="row-2">
        <div class="stack">
          <div class="card">
            <div class="card-title"><Icon name="cart" :size="18" />采购公告</div>
            <div v-if="!lead.notices.length" class="muted">还没有已核验的采购公告</div>
            <div v-for="n in lead.notices" :key="n.id" class="notice">
              <div class="notice-head"><span class="tag" :class="KIND_TONE[n.kind]">{{ n.kind_label }}</span><span class="muted">{{ n.published_on || '—' }}</span></div>
              <button type="button" class="link-btn notice-title" data-action-id="A-310" @click="source = n.source_id">{{ n.title }}</button>
              <dl class="facts">
                <dt>预算</dt><dd class="num">{{ money(n.budget) }}</dd>
                <dt>成交金额</dt><dd class="num">{{ money(n.amount) }}</dd>
                <dt>截止时间</dt><dd>{{ n.deadline || '—' }}</dd>
                <dt>项目编号</dt><dd>{{ n.project_code || '—' }}</dd>
                <dt>标的</dt><dd>{{ n.items || '—' }}</dd>
                <dt>中标方</dt><dd>{{ n.parties.filter((p) => p.role === 'winner').map((p) => p.name).join('、') || '—' }}</dd>
              </dl>
            </div>
          </div>

          <div class="card">
            <div class="card-title"><Icon name="analysis" :size="18" />产品匹配</div>
            <div class="row">
              <el-input v-model="focus" maxlength="2000" placeholder="分析重点，例如：是否需要国产化认证" />
              <el-button type="primary" :loading="saving === 'analysis'" :disabled="!lead.notices.length" data-action-id="A-315" @click="analyze">
                <Icon name="spark" :size="16" /><span>{{ analysis() ? '重新分析' : '开始匹配分析' }}</span></el-button>
            </div>
            <el-table v-if="analysis()" :data="analysis()!.items" class="mt">
              <el-table-column label="产品" width="140" header-align="center" prop="product" />
              <el-table-column label="判断" width="100" align="center"><template #default="{ row }"><span class="tag" :class="FIT_TONE[row.fit]">{{ row.fit }}</span></template></el-table-column>
              <el-table-column label="需求原文" min-width="180" header-align="center" prop="evidence" />
              <el-table-column label="判断依据" min-width="180" header-align="center" prop="judgement" />
            </el-table>
            <ul v-if="analysis()?.questions.length" class="questions"><li v-for="q in analysis()!.questions" :key="q">{{ q }}</li></ul>
          </div>
          <div class="card">
            <div class="card-title"><Icon name="note" :size="18" />跟进记录</div>
            <el-radio-group v-model="note.kind"><el-radio-button v-for="(l, k) in FOLLOWUP_KIND" :key="k" :value="k">{{ l }}</el-radio-button></el-radio-group>
            <el-input v-model="note.content" type="textarea" :rows="3" maxlength="4000" show-word-limit placeholder="例如：已电话联系采购科，下周发送方案" class="mt" />
            <el-button class="mt" :loading="saving === 'note'" data-action-id="A-313" @click="addNote"><Icon name="plus" :size="16" /><span>添加跟进记录</span></el-button>
            <el-timeline v-if="lead.followups.length" class="mt">
              <el-timeline-item v-for="f in lead.followups" :key="f.id" :timestamp="`${dateParts(f.created_at).date} ${dateParts(f.created_at).time} · ${FOLLOWUP_KIND[f.kind] || f.kind}`">{{ f.content }}</el-timeline-item>
            </el-timeline>
          </div>

          <div class="card">
            <div class="card-title"><Icon name="flag" :size="18" />纠错反馈</div>
            <el-radio-group v-model="feedback.kind" class="fb"><el-radio v-for="(l, k) in FEEDBACK_KIND" :key="k" :value="k">{{ l }}</el-radio></el-radio-group>
            <el-input v-model="feedback.content" type="textarea" :rows="2" maxlength="4000" placeholder="补充内容" class="mt" />
            <el-button class="mt" :loading="saving === 'feedback'" data-action-id="A-314" @click="sendFeedback"><Icon name="send" :size="16" /><span>提交反馈</span></el-button>
            <div v-for="f in lead.feedback" :key="f.id" class="fb-item"><span class="tag grey">{{ FEEDBACK_KIND[f.kind] }}</span><span>{{ f.content || '—' }}</span><span class="muted small">{{ dateParts(f.created_at).date }}</span></div>
          </div>
        </div>

        <div class="stack">
          <div class="card">
            <div class="card-title"><Icon name="calendar" :size="18" />跟进安排</div>
            <el-form label-position="top" @submit.prevent="savePlan">
              <el-form-item label="状态" required><el-select v-model="plan.status"><el-option v-for="[k, s] in STATUSES" :key="k" :label="s.label" :value="k" /></el-select></el-form-item>
              <el-form-item label="负责人"><el-input v-model="plan.owner" maxlength="64" placeholder="例如：王五" /></el-form-item>
              <el-form-item label="下次跟进"><el-date-picker v-model="plan.next_followup_at" type="datetime" value-format="YYYY-MM-DD HH:mm" format="YYYY-MM-DD HH:mm" placeholder="选择时间" /></el-form-item>
              <el-button type="primary" :loading="saving === 'plan'" data-action-id="A-312" @click="savePlan"><Icon name="check" :size="16" /><span>保存跟进安排</span></el-button>
            </el-form>
          </div>

          <div class="card">
            <div class="card-title"><Icon name="phone" :size="18" />联系入口</div>
            <div v-if="!lead.contacts.length" class="muted">公告中未披露联系人</div>
            <div v-for="c in lead.contacts" :key="c.notice_id" class="contact">
              <div><b>{{ c.person || '联系人未披露' }}</b><span v-if="c.phone" class="phone num">{{ c.phone }}
                <button type="button" class="link-btn" title="复制电话" aria-label="复制电话" data-action-id="A-311" @click="copy(c.phone)"><Icon name="copy" :size="14" /></button></span></div>
              <div v-if="c.address" class="muted small">{{ c.address }}</div>
              <div class="muted small">来自：{{ c.notice_title }}</div>
            </div>
          </div>

        </div>
      </div>
    </template>
    <SourceDialog :source-id="source" @close="source = null" />
  </div>
</template>

<style scoped>
.title-block { display: flex; flex-direction: column; gap: 4px; min-width: 0; }
.crumb { display: inline-flex; align-items: center; gap: 4px; color: var(--ink-3); }
.sub { display: flex; gap: 12px; align-items: center; color: var(--ink-3); }
.notice { padding: 12px 0; border-top: 1px solid var(--line-2); }
.notice:first-of-type { border-top: 0; padding-top: 0; }
.notice-head { display: flex; gap: 8px; align-items: center; }
.notice-title { display: block; margin: 6px 0 8px; font-weight: 600; }
.facts { display: grid; grid-template-columns: 72px minmax(0, 1fr) 72px minmax(0, 1fr); gap: 4px 12px; margin: 0; font-size: 14px; }
.facts dt { color: var(--ink-3); }
.facts dd { margin: 0; }
.row { display: flex; gap: 8px; }
.mt { margin-top: 12px; }
.questions { margin: 12px 0 0; padding-left: 20px; color: var(--ink-2); }
.contact { padding: 8px 0; border-top: 1px solid var(--line-2); }
.contact:first-of-type { border-top: 0; }
.phone { display: inline-flex; gap: 4px; align-items: center; margin-left: 12px; }
.fb { display: flex; flex-wrap: wrap; }
.fb-item { display: flex; gap: 8px; align-items: center; margin-top: 8px; }
.fb-item span:nth-child(2) { flex: 1; min-width: 0; }
.el-select, .el-date-editor { width: 100%; }
@media (max-width: 760px) { .facts { grid-template-columns: 72px minmax(0, 1fr); } .row { flex-direction: column; } }
</style>
