<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus/es/components/message/index'
import MarkdownRender from 'markstream-vue'
import 'markstream-vue/index.css'
import { api, get, post } from '../api'
import type { Attachment, CompanyCard, Conversation, ConversationItem, Job, ToolCall } from '../types'
import { emptyJob, followJob, isTerminal, type JobState } from '../jobStream'
import { configureMarkdown, displayMarkdown } from '../markdown'
import { JOB_STATUS, LEAD_STATUS, dayGroup, duration } from '../format'
import Icon from '../components/Icon.vue'
import ReportCard from '../components/ReportCard.vue'
import { exhausted, loadMe } from '../session'

const route = useRoute()
const router = useRouter()
const conversations = ref<ConversationItem[]>([])
const conversation = ref<Conversation | null>(null)
const loading = ref(false)
const loadError = ref('')
const live = ref<JobState | null>(null)
const results = ref<{ companies: CompanyCard[]; related: number }>({ companies: [], related: 0 })
const input = ref('')
const files = ref<Attachment[]>([])
const uploading = ref(false)
const sending = ref(false)
const choice = ref('')
const showSteps = ref(false)
const showList = ref(false)
// 宽屏的历史对话栏可收起，选择记在本机；未选择过时 1600 以下默认收起，让研究报告的表格有足够宽度
const listOpen = ref(readListPref())
function readListPref() {
  try { const v = localStorage.getItem('dr.convs'); if (v) return v === 'open' } catch { /* 本机存储不可用 */ }
  return window.innerWidth >= 1600
}
function toggleList() {
  if (window.innerWidth <= 840) { showList.value = true; return }
  listOpen.value = !listOpen.value
  try { localStorage.setItem('dr.convs', listOpen.value ? 'open' : 'closed') } catch { /* 本机存储不可用 */ }
}
const showArtifacts = ref(false)
const scroller = ref<HTMLElement | null>(null)
const fileInput = ref<HTMLInputElement | null>(null)
let stopFollow: (() => void) | null = null
const now = ref(Date.now())
const ticker = window.setInterval(() => { now.value = Date.now() }, 1000)

const EXAMPLES = [
  { label: '找买家', icon: 'search', text: '我们做下一代防火墙，找最近两个月在采购防火墙的单位' },
  { label: '查企业', icon: 'company', text: '研究北京航天广通科技有限公司的采购、中标与上下游' },
  { label: '限定地区', icon: 'pin', text: '找广东省近 90 天采购视频监控设备的学校和医院' },
  { label: '排除对象', icon: 'flag', text: '找近 30 天采购服务器的单位，排除高校和医院' },
]
const TOOL_ICON: Record<string, string> = {
  understand: 'spark', search_company: 'company', search_notices: 'search', screen: 'flag', read_notices: 'doc',
  extract_notice: 'check', read_profile: 'company', extract_profile: 'check',
}

const conversationId = computed(() => (route.params.id as string) || '')
const latestJob = computed<Job | null>(() => conversation.value?.jobs.at(-1) || null)
const busy = computed(() => !!live.value && ['queued', 'running'].includes(live.value.status))
const grouped = computed(() => {
  const groups: Record<string, ConversationItem[]> = {}
  for (const item of conversations.value) (groups[dayGroup(item.updated_at)] ||= []).push(item)
  return ['今天', '昨天', '更早'].filter((g) => groups[g]).map((g) => ({ name: g, items: groups[g] }))
})

async function loadList() {
  conversations.value = await get<ConversationItem[]>('/conversations').catch(() => conversations.value)
}

async function loadConversation(id: string) {
  stopFollow?.()
  live.value = null
  results.value = { companies: [], related: 0 }
  if (!id) { conversation.value = null; return }
  loading.value = true
  loadError.value = ''
  try {
    conversation.value = await api<Conversation>(`/conversations/${id}`, { notify: false })
    const job = latestJob.value
    if (job) {
      startFollow(job)
      loadResults(job.id)
    }
    await scrollBottom()
  } catch {
    loadError.value = '无法读取这段对话'
  } finally {
    loading.value = false
  }
}

function startFollow(job: Job) {
  const state = emptyJob(job.id, job.status)
  Object.assign(state, { stage: job.stage, metrics: job.metrics, handover: job.handover, error: job.error })
  live.value = state
  stopFollow = followJob(state, async () => {
    await refreshConversation()
  })
}

async function refreshConversation() {
  if (!conversationId.value) return
  const data = await api<Conversation>(`/conversations/${conversationId.value}`, { notify: false }).catch(() => null)
  if (data) conversation.value = data
  loadList()
  if (latestJob.value) loadResults(latestJob.value.id)
}

async function loadResults(jobId: string) {
  results.value = await get(`/jobs/${jobId}/results`).catch(() => results.value)
}

watch(() => live.value?.resultVersion, () => { if (live.value) loadResults(live.value.id) })
watch(() => live.value?.draft, () => scrollBottom(true))
watch(() => live.value?.tools.length, () => scrollBottom(true))
watch(() => live.value?.title, (title) => { if (title && conversation.value) { conversation.value.title = title; loadList() } })
watch(conversationId, (id) => loadConversation(id))

async function scrollBottom(onlyIfNear = false) {
  await nextTick()
  const el = scroller.value
  if (!el) return
  if (onlyIfNear && el.scrollHeight - el.scrollTop - el.clientHeight > 160) return
  el.scrollTop = el.scrollHeight
}

async function newConversation() {
  router.push('/workbench')
  input.value = ''
  files.value = []
}

async function send() {
  const content = input.value.trim()
  if (!content || busy.value || sending.value || exhausted()) return
  sending.value = true
  try {
    let id = conversationId.value
    if (!id) {
      id = (await post<ConversationItem>('/conversations')).id
    }
    const result = await post<{ job: Job }>(`/conversations/${id}/messages`, { content, attachment_ids: files.value.map((f) => f.id) })
    input.value = ''
    files.value = []
    loadMe()
    if (id !== conversationId.value) {
      await router.push(`/c/${id}`)
    } else {
      await refreshConversation()
      startFollow(result.job)
    }
    await scrollBottom()
  } finally {
    sending.value = false
  }
}

function onKey(event: KeyboardEvent) {
  if (event.key === 'Enter' && !event.shiftKey && !event.isComposing) {
    event.preventDefault()
    send()
  }
}

async function upload(event: Event) {
  const list = Array.from((event.target as HTMLInputElement).files || [])
  ;(event.target as HTMLInputElement).value = ''
  if (files.value.length + list.length > 5) { ElMessage.warning('最多上传 5 份资料'); return }
  uploading.value = true
  try {
    for (const file of list) {
      const form = new FormData()
      form.append('file', file)
      files.value.push(await api<Attachment>('/attachments', { method: 'POST', body: form }))
    }
  } finally {
    uploading.value = false
  }
}

async function stop() {
  if (live.value) await post(`/jobs/${live.value.id}/pause`).catch(() => null)
}

async function resume(body: { choice?: string; skip?: boolean } = {}) {
  if (!live.value) return
  const id = live.value.id
  await post(`/jobs/${id}/continue`, body)
  stopFollow?.()
  const job = await get<Job>(`/jobs/${id}`)
  startFollow({ ...job, status: 'running' })
  choice.value = ''
}

function copy(text: string) {
  navigator.clipboard.writeText(text).then(() => ElMessage.success('已复制'))
}

function jobOf(messageJobId: string | null): Job | undefined {
  return conversation.value?.jobs.find((j) => j.id === messageJobId)
}
function isLive(jobId: string | null) {
  return !!live.value && live.value.id === jobId
}
function replyFor(jobId: string | null) {
  const job = jobOf(jobId)
  return conversation.value?.messages.find((m) => m.role === 'assistant' && m.job_id === jobId && job?.reply_message_id === m.id)
}
function showReport(jobId: string | null) {
  const job = jobOf(jobId)
  const status = isLive(jobId) && live.value ? live.value.status : job?.status
  return !!job && job.mode !== 'chat' && job.mode !== '' && ['completed', 'partial'].includes(status || '')
}
const userMessages = computed(() => conversation.value?.messages.filter((m) => m.role === 'user') || [])
// 进行中的步骤：最早开始的一条显示在折叠行；每一步运行中每秒更新已用时，结束后显示用时
const running = computed(() => (live.value?.tools || []).filter((t) => t.status === 'running'))
const failedSteps = computed(() => (live.value?.tools || []).filter((t) => ['failed', 'blocked'].includes(t.status)).length)
function toolTime(t: ToolCall) {
  if (t.status === 'running') return `已用 ${duration(Math.max(0, now.value - (t.startedAt || now.value)))}`
  return t.elapsed_ms ? `用时 ${duration(t.elapsed_ms)}` : ''
}
const toolSummary = (j: JobState) => {
  const searches = j.tools.filter((t) => t.tool === 'search_notices').length
  const reads = j.tools.filter((t) => t.tool === 'extract_notice' && t.status === 'completed').length
  return `${searches} 次检索 · 读 ${reads} 篇公告 · 用时 ${duration(j.metrics.elapsed_ms)}`
}
const roleLabel = { target: '目标企业', buyer: '采购方', related: '相关' }

function onEsc(event: KeyboardEvent) { if (event.key === 'Escape') { showArtifacts.value = false; showList.value = false } }
onMounted(() => { loadMe(); loadList(); loadConversation(conversationId.value); window.addEventListener('keydown', onEsc) })
onBeforeUnmount(() => { stopFollow?.(); window.clearInterval(ticker); window.removeEventListener('keydown', onEsc) })
</script>

<template>
  <div class="wb">
    <aside class="convs" :class="{ open: showList, collapsed: !listOpen }">
      <div class="convs-head">
        <el-button type="primary" class="new" data-action-id="A-101" @click="newConversation"><Icon name="plus" :size="16" /><span>新建对话</span></el-button>
      </div>
      <div class="convs-body">
        <template v-for="g in grouped" :key="g.name">
          <div class="convs-group">{{ g.name }}</div>
          <RouterLink v-for="c in g.items" :key="c.id" :to="`/c/${c.id}`" class="conv" data-action-id="A-102"
                      :class="{ on: c.id === conversationId }" @click="showList = false">
            <span class="conv-title">{{ c.title }}</span>
            <span v-if="c.status === 'running' || c.status === 'queued'" class="conv-dot run" aria-label="运行中" />
            <span v-else-if="c.status === 'awaiting_user'" class="tag warn">等待处理</span>
          </RouterLink>
        </template>
        <div v-if="!conversations.length" class="muted conv-empty">还没有对话</div>
      </div>
    </aside>
    <div v-if="showList" class="wb-mask" @click="showList = false" />

    <section class="chat">
      <header class="chat-head">
        <button type="button" class="icon-btn" :aria-label="listOpen ? '收起历史对话' : '展开历史对话'" :title="listOpen ? '收起历史对话' : '展开历史对话'" @click="toggleList"><Icon name="sidebar" :size="18" /></button>
        <span class="chat-title">{{ conversation?.title || '获客工作台' }}</span>
        <button type="button" class="icon-btn" aria-label="本次产物" title="本次产物" @click="showArtifacts = !showArtifacts"><Icon name="company" :size="18" /></button>
      </header>

      <div ref="scroller" class="scroll">
        <div class="thread">
          <div v-if="loadError" class="narrow error-line">{{ loadError }}<el-button size="small" @click="loadConversation(conversationId)">重试</el-button></div>
          <el-skeleton v-else-if="loading" class="narrow" :rows="6" animated />

          <div v-else-if="!conversation" class="narrow welcome">
            <span class="welcome-mark"><Icon name="radar" :size="28" /></span>
            <div class="welcome-title">描述你的产品找买家，或输入企业名称查企业</div>
            <div class="examples">
              <button v-for="e in EXAMPLES" :key="e.label" type="button" class="example" data-action-id="A-113" @click="input = e.text">
                <span class="ex-head"><span class="ex-icon"><Icon :name="e.icon" :size="18" /></span>{{ e.label }}</span>
                <span class="ex-text">{{ e.text }}</span>
              </button>
            </div>
          </div>

          <template v-else>
            <template v-for="m in userMessages" :key="m.id">
              <div class="narrow"><div class="umsg">
                <div>{{ m.content }}</div>
                <div v-if="m.attachments.length" class="files"><span v-for="f in m.attachments" :key="f.id" class="tag plain"><Icon name="attach" :size="14" />{{ f.filename }}</span></div>
              </div></div>

              <div class="narrow agent">
              <span class="agent-mark" aria-hidden="true"><Icon name="spark" :size="16" /></span>
              <div class="agent-body">
              <!-- 研究过程：当前任务实时，历史任务显示汇总 -->
              <div v-if="isLive(m.job_id) && live" class="proc">
                <div class="proc-head">
                  <span class="stage"><span v-if="busy" class="conv-dot run" />{{ busy ? (live.stageLabel || '准备中') : JOB_STATUS[live.status].label }}</span>
                  <span class="muted small">{{ busy ? `已用 ${duration((live.metrics.elapsed_ms || 0) + now - live.syncedAt)}` : toolSummary(live) }}<template v-if="busy && live.progress.to_read"> · 待读 {{ live.progress.to_read }} 篇</template></span>
                </div>
                <!-- 步骤默认折叠；进行中时折叠行显示正在进行的一步与实时已用时 -->
                <div v-if="busy && !showSteps && running.length" class="now-line">
                  <span class="tool-icon running"><Icon :name="TOOL_ICON[running[0].tool] || 'doc'" :size="16" /></span>
                  <span class="tool-name">{{ running[0].label }}<span v-if="running.length > 1" class="now-more">等 {{ running.length }} 项进行中</span></span>
                  <span class="tool-meta num">{{ toolTime(running[0]) }}</span>
                </div>
                <button v-if="live.tools.length" type="button" class="steps-toggle" :aria-expanded="showSteps" @click="showSteps = !showSteps">
                  <Icon :name="showSteps ? 'back' : 'chevron'" :size="14" />{{ showSteps ? '收起步骤' : `展开 ${live.tools.length} 个步骤` }}<span v-if="failedSteps" class="danger-text">（{{ failedSteps }} 个失败）</span></button>
                <details v-for="t in (showSteps ? live.tools : [])" :key="t.id" class="tool" :open="t.status === 'failed'" data-action-id="A-104">
                  <summary>
                    <span class="tool-icon" :class="t.status"><Icon :name="TOOL_ICON[t.tool] || 'doc'" :size="16" /></span>
                    <span class="tool-name">{{ t.label }}</span>
                    <span class="tool-meta num">{{ [t.status === 'running' ? '' : t.count !== undefined ? `${t.count} 条` : t.summary, toolTime(t)].filter(Boolean).join(' · ') }}</span>
                  </summary>
                  <div class="tool-body">
                    <div v-if="t.summary">{{ t.summary }}</div>
                    <div v-if="t.error" class="danger-text">{{ t.error }}</div>
                    <a v-if="t.url" :href="t.url" target="_blank" rel="noopener" data-action-id="A-105"><Icon name="external" :size="14" />{{ t.url }}</a>
                  </div>
                </details>
              </div>
              <div v-else-if="jobOf(m.job_id)" class="proc compact"><span class="tag" :class="JOB_STATUS[jobOf(m.job_id)!.status].tone">{{ JOB_STATUS[jobOf(m.job_id)!.status].label }}</span>
                <span class="muted small">用时 {{ duration(jobOf(m.job_id)!.metrics.elapsed_ms) }}</span></div>

              <!-- 交接卡 -->
              <div v-if="isLive(m.job_id) && live?.status === 'awaiting_user'" class="handover">
                <template v-if="live.handover.kind === 'identity'">
                  <div class="ho-title">选择要研究的企业</div>
                  <el-radio-group v-model="choice" class="ho-choices">
                    <el-radio v-for="c in live.handover.candidates" :key="c" :value="c">{{ c }}</el-radio>
                  </el-radio-group>
                  <div class="ho-act"><el-button type="primary" :disabled="!choice" data-action-id="A-108" @click="resume({ choice })">选择这家企业</el-button></div>
                </template>
                <template v-else>
                  <div class="ho-title">{{ live.handover.kind === 'verify' ? '需要验证' : '需要登录' }}：{{ live.handover.site_name }}</div>
                  <div class="ho-body">在 Edge 中打开的页面{{ live.handover.kind === 'verify' ? '完成验证' : '登录' }}后继续</div>
                  <div class="ho-act">
                    <el-button type="primary" data-action-id="A-106" @click="resume()"><Icon name="login" :size="16" /><span>我已处理，继续</span></el-button>
                    <el-button data-action-id="A-107" @click="resume({ skip: true })"><Icon name="skip" :size="16" /><span>跳过该网站</span></el-button>
                  </div>
                </template>
              </div>

              <!-- 回答 -->
              <div v-if="isLive(m.job_id) && live?.draft" class="answer">
                <MarkdownRender mode="chat" html-policy="escape" :custom-markdown-it="configureMarkdown" :content="displayMarkdown(live.draft, live.final)"
                                :final="live.final" :smooth-streaming="false" :render-code-blocks-as-pre="true" :fade="false" />
                <div v-if="live.final" class="answer-tools"><button type="button" class="icon-btn" title="复制回答" aria-label="复制回答" data-action-id="A-103" @click="copy(live.draft)"><Icon name="copy" :size="16" /></button>
                  <span class="elapsed"><Icon name="history" :size="14" />总用时 {{ duration(live.metrics.elapsed_ms) }}</span></div>
              </div>
              <div v-else-if="replyFor(m.job_id)?.content" class="answer">
                <MarkdownRender mode="chat" html-policy="escape" :custom-markdown-it="configureMarkdown" :content="replyFor(m.job_id)!.content" :final="true"
                                :render-code-blocks-as-pre="true" :fade="false" />
                <div class="answer-tools"><button type="button" class="icon-btn" title="复制回答" aria-label="复制回答" data-action-id="A-103" @click="copy(replyFor(m.job_id)!.content)"><Icon name="copy" :size="16" /></button>
                  <span v-if="jobOf(m.job_id)" class="elapsed"><Icon name="history" :size="14" />总用时 {{ duration(jobOf(m.job_id)!.metrics.elapsed_ms) }}</span></div>
              </div>

              <!-- 暂停、部分完成、失败 -->
              <div v-if="isLive(m.job_id) && live && ['paused', 'failed', 'partial'].includes(live.status)" class="result-line" :class="live.status">
                <Icon :name="live.status === 'failed' ? 'alert' : 'stop'" :size="16" />
                <span>{{ live.status === 'failed' ? (live.error || '研究失败') : live.status === 'paused' ? `已暂停在“${live.stageLabel || live.stage}”` : '部分站点或步骤未完成' }}</span>
                <RouterLink v-if="live.status === 'failed' && /采集/.test(live.error)" to="/sources">查看数据源</RouterLink>
                <el-button size="small" data-action-id="A-116" @click="resume()"><Icon name="play" :size="14" /><span>继续研究</span></el-button>
              </div>
              </div>
              </div>
              <!-- 研究报告：对话文字保持 760 宽，报告按对话区全宽展开 -->
              <div v-if="showReport(m.job_id)" class="wide"><ReportCard :job-id="m.job_id!" :version="isLive(m.job_id) ? live?.resultVersion : 0" /></div>
            </template>
          </template>
        </div>
      </div>

      <footer class="composer">
        <div class="column">
          <div v-if="files.length" class="files">
            <el-tag v-for="f in files" :key="f.id" closable data-action-id="A-112" @close="files = files.filter((x) => x.id !== f.id)">{{ f.filename }}</el-tag>
          </div>
          <div class="input-box">
            <button type="button" class="icon-btn" title="上传资料" aria-label="上传资料" :disabled="uploading || busy || exhausted()" data-action-id="A-111" @click="fileInput?.click()">
              <Icon name="attach" />
            </button>
            <input ref="fileInput" type="file" hidden multiple accept=".pdf,.doc,.docx,.xls,.xlsx,.csv,.txt" @change="upload" />
            <textarea v-model="input" rows="1" maxlength="8000" :disabled="busy || exhausted()" :placeholder="exhausted() ? '使用次数已用完' : '描述你的产品，或输入企业名称'" @keydown="onKey" />
            <button v-if="busy" type="button" class="send stop" title="停止" aria-label="停止" data-action-id="A-110" @click="stop"><Icon name="stop" :size="16" /></button>
            <button v-else type="button" class="send" title="发送" aria-label="发送" :disabled="!input.trim() || sending || exhausted()" data-action-id="A-109" @click="send"><Icon name="send" :size="16" /></button>
          </div>
          <div v-if="uploading" class="muted small">正在解析资料…</div>
        </div>
      </footer>
    </section>

    <div v-if="showArtifacts && conversation" class="art-mask" @click="showArtifacts = false" />
    <aside v-if="showArtifacts && conversation" class="artifacts">
      <div class="card-title"><Icon name="company" :size="18" /><span class="grow">本次产物</span>
        <button type="button" class="icon-btn" aria-label="关闭" title="关闭" @click="showArtifacts = false"><Icon name="close" :size="16" /></button></div>
      <div v-if="!results.companies.length" class="muted small">研究产出的企业与线索会出现在这里</div>
      <div v-for="c in results.companies" :key="c.id" class="acard">
        <RouterLink :to="`/companies/${c.id}`" class="aname" data-action-id="A-114">{{ c.name }}</RouterLink>
        <div class="ameta"><span class="tag" :class="c.role === 'target' ? 'brand' : 'signal'">{{ roleLabel[c.role || 'related'] }}</span>
          <span>采购 {{ c.purchases }} · 中标 {{ c.wins }}</span></div>
        <RouterLink v-if="c.lead" :to="`/leads/${c.lead.id}`" class="alead" data-action-id="A-115">
          <span class="tag" :class="LEAD_STATUS[c.lead.status].tone">{{ LEAD_STATUS[c.lead.status].label }}</span>线索评分 {{ c.lead.score }}</RouterLink>
      </div>
      <div v-if="results.related" class="muted small">另有 {{ results.related }} 家相关企业</div>
    </aside>
  </div>
</template>

<style scoped>
.wb { display: flex; flex: 1; height: 100%; min-height: 0; background: var(--surface); }
.convs { width: 248px; flex: none; border-right: 1px solid var(--line); display: flex; flex-direction: column; background: var(--canvas); }
.convs.collapsed { display: none; }
.convs-head { padding: 12px 10px 8px; }
.new { width: 100%; }
.convs-body { flex: 1; overflow-y: auto; padding: 0 8px 16px; }
.convs-group { font-size: 12px; color: var(--ink-3); padding: 12px 8px 4px; }
.conv { display: flex; align-items: center; gap: 8px; height: 36px; padding: 0 10px; border: 1px solid transparent; border-radius: 8px; color: var(--ink-2); font-size: 14px; }
.conv:hover { background: var(--subtle); color: var(--ink); }
.conv.on { background: var(--surface); border-color: var(--line); color: var(--ink); font-weight: 600; box-shadow: var(--shadow); }
.conv-title { flex: 1; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.conv-empty { padding: 16px 8px; }
.conv-dot { display: inline-block; width: 6px; height: 6px; border-radius: 50%; background: #a1a1aa; flex: none; }
.conv-dot.run { background: var(--accent); animation: pulse 1.2s infinite; }
@keyframes pulse { 50% { opacity: .35; } }
.chat { flex: 1; min-width: 0; display: flex; flex-direction: column; }
.chat-head { display: flex; align-items: center; gap: 8px; height: 52px; padding: 0 12px; border-bottom: 1px solid var(--line); flex: none; }
.chat-title { flex: 1; min-width: 0; font-size: 16px; font-weight: 600; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.icon-btn { display: inline-grid; place-items: center; width: 32px; height: 32px; border: 0; border-radius: 8px; background: none; color: var(--ink-2); cursor: pointer; }
.icon-btn:hover:not(:disabled) { background: var(--subtle); color: var(--ink); }
.icon-btn:disabled { color: #a1a1aa; cursor: not-allowed; }
.scroll { flex: 1; overflow-y: auto; padding: 20px 16px; }
.thread { display: flex; flex-direction: column; gap: 16px; }
.narrow { width: 100%; max-width: 760px; margin: 0 auto; display: flex; flex-direction: column; }
.wide { width: 100%; max-width: 1280px; margin: 0 auto; }
.welcome { padding: 8vh 0 0; align-items: center; gap: 12px; }
.welcome-mark { display: grid; place-items: center; width: 48px; height: 48px; border-radius: 12px; border: 1px solid var(--line-strong); background: var(--surface); color: var(--ink); }
.welcome-title { font-size: 22px; line-height: 30px; font-weight: 600; margin-bottom: 12px; text-align: center; }
.examples { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 12px; width: 100%; }
.example { display: flex; flex-direction: column; gap: 6px; text-align: left; padding: 14px 16px; border: 1px solid var(--line); border-radius: 12px; background: var(--surface); font: inherit; color: var(--ink); cursor: pointer; }
.example:hover { border-color: var(--line-strong); background: var(--canvas); }
.ex-head { display: flex; align-items: center; gap: 8px; font-size: 14px; font-weight: 600; }
.ex-icon { display: inline-grid; place-items: center; color: var(--ink-3); }
.ex-text { font-size: 14px; line-height: 22px; color: var(--ink-2); }
.agent { flex-direction: row; gap: 12px; align-items: flex-start; }
.agent-mark { display: grid; place-items: center; width: 28px; height: 28px; border-radius: 8px; border: 1px solid var(--line-strong); color: var(--ink-2); flex: none; margin-top: 2px; }
.agent-body { flex: 1; min-width: 0; display: flex; flex-direction: column; gap: 10px; }
.umsg { align-self: flex-end; max-width: 85%; padding: 8px 14px; border-radius: 12px; background: var(--subtle); font-size: 16px; line-height: 26px; white-space: pre-wrap; }
.files { display: flex; flex-wrap: wrap; gap: 6px; margin-top: 6px; }
.proc { border: 1px solid var(--line); border-radius: 8px; padding: 0 12px 6px; font-size: 14px; background: var(--surface); }
.proc.compact { display: flex; gap: 8px; align-items: center; padding: 8px 12px; }
.proc-head { display: flex; justify-content: space-between; align-items: center; gap: 8px; min-height: 40px; border-bottom: 1px solid var(--line); flex-wrap: wrap; }
.stage { display: inline-flex; align-items: center; gap: 8px; font-weight: 600; color: var(--ink); }
.steps-toggle { display: inline-flex; align-items: center; gap: 4px; padding: 6px 0 0; border: 0; background: none; color: var(--ink-2); font: inherit; font-size: 14px; cursor: pointer; }
.steps-toggle:hover { color: var(--ink); }
.tool summary { display: flex; align-items: center; gap: 10px; min-height: 36px; cursor: pointer; list-style: none; }
.now-line { display: flex; align-items: center; gap: 10px; min-height: 36px; }
.now-more { margin-left: 8px; font-size: 12px; color: var(--ink-3); }
.tool-meta.num { font-variant-numeric: tabular-nums; }
.tool-icon { display: inline-grid; place-items: center; width: 24px; height: 24px; border-radius: 6px; border: 1px solid var(--line); color: var(--ink-3); flex: none; }
.tool-icon.running { color: var(--accent); border-color: var(--line-strong); animation: pulse 1.2s infinite; }
.tool-icon.failed, .tool-icon.blocked { color: var(--danger); border-color: #fecaca; }
.tool-icon.awaiting_user { color: var(--warn); border-color: #fde68a; }
.tool-icon.captured, .tool-icon.completed { color: var(--ok); }
.tool summary::-webkit-details-marker { display: none; }
.tool-name { flex: 1; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; color: var(--ink-2); }
.tool-meta { font-size: 12px; color: var(--ink-3); white-space: nowrap; }
.tool-body { padding: 0 0 8px 34px; color: var(--ink-2); font-size: 14px; word-break: break-all; }
.tool-body a { display: inline-flex; gap: 4px; align-items: center; }
.danger-text { color: var(--danger); }
.handover { border: 1px solid #fde68a; background: var(--warn-tint); border-radius: 12px; padding: 14px 16px; }
.ho-title { font-size: 16px; font-weight: 600; }
.ho-body { margin: 4px 0 12px; color: var(--ink-2); }
.ho-choices { display: flex; flex-direction: column; align-items: flex-start; margin: 8px 0 12px; }
.ho-act { display: flex; gap: 8px; flex-wrap: wrap; }
.answer { font-size: 16px; line-height: 26px; }
.answer :deep(h1), .answer :deep(h2) { font-size: 18px; line-height: 26px; margin: 16px 0 8px; }
.answer :deep(h3), .answer :deep(h4) { font-size: 16px; line-height: 24px; margin: 12px 0 6px; }
.answer :deep(table) { font-size: 14px; }
.answer-tools { display: flex; align-items: center; gap: 8px; margin-top: 4px; }
.elapsed { display: inline-flex; align-items: center; gap: 4px; font-size: 12px; color: var(--ink-3); }
.result-line { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; padding: 8px 12px; border: 1px solid var(--line); border-radius: 8px; color: var(--ink-2); }
.result-line.failed { border-color: #fecaca; background: var(--danger-tint); color: var(--danger); }
.result-line > span { flex: 1; min-width: 0; }
.composer { flex: none; padding: 12px 16px 16px; }
.column { max-width: 760px; margin: 0 auto; display: flex; flex-direction: column; gap: 8px; }
.input-box { display: flex; align-items: flex-end; gap: 8px; padding: 8px; border: 1px solid var(--line-strong); border-radius: 12px; background: var(--surface); }
.input-box:focus-within { border-color: var(--ink-3); box-shadow: 0 0 0 3px var(--subtle); }
.input-box textarea { flex: 1; min-height: 32px; max-height: 208px; border: 0; outline: 0; resize: none; font: inherit; font-size: 16px; line-height: 26px; padding: 3px 0; field-sizing: content; color: var(--ink); background: none; }
.input-box textarea::placeholder { color: var(--ink-3); }
.send { display: grid; place-items: center; width: 32px; height: 32px; border: 0; border-radius: 8px; background: var(--action); color: #fff; cursor: pointer; flex: none; }
.send:hover { background: var(--action-hover); }
.send:disabled { background: var(--subtle); color: #a1a1aa; cursor: not-allowed; }
.artifacts { width: 320px; flex: none; border-left: 1px solid var(--line); padding: 16px; overflow-y: auto; background: var(--surface); }
.acard { border: 1px solid var(--line); border-radius: 12px; padding: 12px; margin-bottom: 8px; }
.aname { display: block; font-weight: 600; color: var(--ink); }
.aname:hover { color: var(--accent); }
.ameta { display: flex; gap: 8px; align-items: center; margin-top: 6px; font-size: 12px; color: var(--ink-3); }
.alead { display: flex; gap: 8px; align-items: center; margin-top: 8px; font-size: 12px; color: var(--ink-2); }
.wb-mask, .art-mask { display: none; }
@media (max-width: 1199px) {
  .art-mask { display: block; position: fixed; inset: 0; z-index: 24; background: rgba(0, 0, 0, .3); }
  .artifacts { position: fixed; z-index: 25; top: 50%; left: 50%; transform: translate(-50%, -50%); width: min(420px, calc(100vw - 24px)); max-height: 80vh; border: 0; border-radius: 12px; box-shadow: var(--shadow-pop); }
}
@media (max-width: 840px) {
  .convs, .convs.collapsed { display: flex; position: fixed; z-index: 25; inset: 0 auto 0 0; width: 280px; transform: translateX(-100%); transition: transform .2s; }
  .convs.open { transform: none; }
  .wb-mask { display: block; position: fixed; inset: 0; z-index: 24; background: rgba(0, 0, 0, .3); }
}
@media (max-width: 760px) {
  .examples { grid-template-columns: minmax(0, 1fr); }
  .scroll { padding: 16px 12px; }
  .composer { padding: 8px 12px 12px; }
  .umsg { max-width: 92%; }
}
</style>
