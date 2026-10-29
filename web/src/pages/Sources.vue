<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { ElMessage } from 'element-plus/es/components/message/index'
import { ElMessageBox } from 'element-plus/es/components/message-box/index'
import { ApiError, api, del, patch, post } from '../api'
import type { DataSources, SiteInfo } from '../types'
import { dateParts, duration } from '../format'
import Icon from '../components/Icon.vue'

interface TestResult {
  status: string; error: string; url: string; links: number; matched: number; elapsed_ms: number
  samples: { title: string; url: string }[]
  detail: { status: string; title: string; chars: number; excerpt: string } | null
}

interface Discovered { domain: string; title: string; sample_url: string; hits: number; adopted: number; last_seen: string; config: Record<string, unknown> }
const data = ref<DataSources | null>(null)
const discovered = ref<Discovered[]>([])
const error = ref(false)
const checking = ref(false)
const switching = ref('')
const dialog = ref(false)
const editing = ref<string | null>(null)
const saving = ref(false)
const testing = ref(false)
const test = ref<TestResult | null>(null)
const testError = ref('')
const form = reactive({ name: '', kind: 'procurement', mode: 'template', template: '', domain: '', detail: '', login: false, by_company: false, note: '', keyword: '视频监控' })

async function load(refresh = false) {
  checking.value = true
  error.value = false
  try {
    data.value = await api<DataSources>(`/sources${refresh ? '?refresh=true' : ''}`, { notify: false })
    discovered.value = await api<Discovered[]>('/discovered-sources', { notify: false }).catch(() => [])
  } catch {
    error.value = true
  } finally {
    checking.value = false
  }
}
onMounted(() => load())

const groups = computed(() => [
  { kind: 'procurement', title: '招投标', icon: 'cart', sites: data.value?.sites.filter((s) => s.kind === 'procurement') || [] },
  { kind: 'business', title: '企业信息', icon: 'company', sites: data.value?.sites.filter((s) => s.kind === 'business') || [] },
])
const enabledProcurement = computed(() => data.value?.sites.filter((s) => s.kind === 'procurement' && s.enabled).length || 0)
const locked = (site: SiteInfo) => site.kind === 'procurement' && site.enabled && enabledProcurement.value <= 1

async function toggle(site: SiteInfo, value: boolean) {
  switching.value = site.id
  const before = site.enabled
  site.enabled = value
  try {
    await patch('/settings', { sources: Object.fromEntries(data.value!.sites.map((s) => [s.id, s.enabled])) })
    ElMessage.success(value ? `已启用${site.name}` : `已停用${site.name}`)
  } catch {
    site.enabled = before
  } finally {
    switching.value = ''
  }
}

function openForm(site?: SiteInfo) {
  editing.value = site?.id || null
  Object.assign(form, site
    ? { name: site.name, kind: site.kind, mode: site.mode, template: site.template, domain: site.domain, detail: site.detail, login: site.login, by_company: site.by_company, note: site.note }
    : { name: '', kind: 'procurement', mode: 'template', template: '', domain: '', detail: '', login: false, by_company: false, note: '' })
  test.value = null
  testError.value = ''
  dialog.value = true
}

async function runTest(site?: SiteInfo) {
  if (site) openForm(site)
  testing.value = true
  test.value = null
  testError.value = ''
  try {
    test.value = await api<TestResult>('/sources/test', { method: 'POST', body: { ...form }, notify: false })
  } catch (e) {
    testError.value = e instanceof ApiError ? e.message : '测试失败'
  } finally {
    testing.value = false
  }
}

async function save() {
  saving.value = true
  try {
    if (editing.value) await patch(`/sources/sites/${editing.value}`, form)
    else await post('/sources/sites', form)
    ElMessage.success('已保存数据源')
    dialog.value = false
    load()
  } finally {
    saving.value = false
  }
}

function addDiscovered(item: Discovered) {
  openForm()
  Object.assign(form, item.config)
}

async function dismiss(item: Discovered) {
  await post(`/discovered-sources/${encodeURIComponent(item.domain)}/dismiss`)
  discovered.value = discovered.value.filter((d) => d.domain !== item.domain)
}

async function remove(site: SiteInfo) {
  try {
    await ElMessageBox.confirm('', `删除数据源 ${site.name}`, { confirmButtonText: '删除', cancelButtonText: '取消', type: 'warning', confirmButtonClass: 'el-button--danger' })
  } catch { return }
  await del(`/sources/sites/${site.id}`)
  ElMessage.success('已删除')
  load()
}

const STATUS_TONE: Record<string, string> = { captured: 'ok', partial: 'signal', awaiting_user: 'warn', blocked: 'danger', failed: 'danger' }
const STATUS_LABEL: Record<string, string> = { captured: '成功', partial: '部分取得', awaiting_user: '需登录', blocked: '受限', failed: '失败' }
const testOk = computed(() => !!test.value && test.value.matched > 0 && !!test.value.detail && test.value.detail.chars > 200)
</script>

<template>
  <div class="page">
    <div class="page-head">
      <div class="page-actions"><el-button type="primary" @click="openForm()"><Icon name="plus" :size="16" /><span>新增数据源</span></el-button></div>
    </div>
    <div v-if="error" class="error-line">无法读取数据源<el-button size="small" @click="load()">重试</el-button></div>
    <el-skeleton v-else-if="!data" :rows="8" animated class="card" />
    <template v-else>
      <div class="card tool">
        <span class="tool-mark"><Icon name="radar" :size="18" /></span>
        <div class="tool-main">
          <div class="tool-title">采集工具 <span class="tag" :class="data.crawler.ready ? 'ok' : 'danger'">{{ data.crawler.ready ? '就绪' : '未连接' }}</span></div>
          <div class="muted small">版本 {{ data.crawler.version || '—' }} · 浏览器 {{ data.crawler.profile || '—' }}<template v-if="!data.crawler.ready && data.crawler.hint"> · {{ data.crawler.hint }}</template></div>
        </div>
        <el-button :loading="checking" data-action-id="A-401" @click="load(true)"><Icon name="refresh" :size="16" /><span>重新检测</span></el-button>
      </div>

      <section v-for="g in groups" :key="g.kind" class="card flush">
        <div class="card-title pad"><Icon :name="g.icon" :size="18" /><span class="grow">{{ g.title }}</span><span class="extra">{{ g.sites.filter((s) => s.enabled).length }} / {{ g.sites.length }} 已启用</span></div>
        <el-table :data="g.sites" row-key="id" class="desktop">
          <el-table-column label="站点" min-width="260" header-align="center">
            <template #default="{ row }">
              <div class="cell-main">{{ row.name }} <span v-if="row.custom" class="tag brand">自定义</span><span v-else-if="row.origin === 'luzcrawl'" class="tag grey">LuzCrawl</span><span v-if="row.region" class="tag purple" :title="`需求含${row.region}时自动加入`">{{ row.region }}</span></div>
              <div class="cell-sub">{{ row.note || (row.mode === 'site_search' ? `站内搜索 · ${row.domain}` : '地址模板') }}</div>
            </template>
          </el-table-column>
          <el-table-column label="登录" width="110" align="center">
            <template #default="{ row }"><span class="tag" :class="row.login ? 'warn' : 'grey'">{{ row.login ? '需要登录' : '免登录' }}</span></template>
          </el-table-column>
          <el-table-column label="启用" width="90" align="center">
            <template #default="{ row }">
              <el-tooltip :disabled="!locked(row)" content="至少保留一个招投标站点" placement="top">
                <el-switch :model-value="row.enabled" :loading="switching === row.id" :disabled="locked(row)" data-action-id="A-402"
                           :aria-label="`启用${row.name}`" @change="(v: string | number | boolean) => toggle(row, !!v)" />
              </el-tooltip>
            </template>
          </el-table-column>
          <el-table-column label="尝试 / 成功 / 被采用" width="180" align="center">
            <template #default="{ row }"><span class="num">{{ row.stats ? `${row.stats.attempts} / ${row.stats.successes} / ${row.stats.adopted}` : '—' }}</span></template>
          </el-table-column>
          <el-table-column label="最近状态" width="130" align="center">
            <template #default="{ row }">
              <template v-if="row.stats"><span class="tag" :class="STATUS_TONE[row.stats.last_status] || 'grey'">{{ STATUS_LABEL[row.stats.last_status] || row.stats.last_status }}</span>
                <div class="cell-sub">{{ dateParts(row.stats.last_at).date }}</div></template>
              <span v-else>—</span>
            </template>
          </el-table-column>
          <el-table-column label="操作" width="170" align="center">
            <template #default="{ row }">
              <template v-if="row.custom">
                <button type="button" class="link-btn op" @click="runTest(row)"><Icon name="play" :size="14" />测试</button>
                <button type="button" class="link-btn op" @click="openForm(row)"><Icon name="note" :size="14" />编辑</button>
                <button type="button" class="link-btn op danger" @click="remove(row)"><Icon name="trash" :size="14" />删除</button>
              </template>
              <span v-else class="muted small">{{ row.origin === 'luzcrawl' ? '—' : '内置' }}</span>
            </template>
          </el-table-column>
        </el-table>
        <div class="mobile">
          <div v-for="row in g.sites" :key="row.id" class="mcard">
            <div class="mrow"><span class="cell-main">{{ row.name }}</span>
              <el-switch :model-value="row.enabled" :loading="switching === row.id" :disabled="locked(row)" :aria-label="`启用${row.name}`"
                         @change="(v: string | number | boolean) => toggle(row, !!v)" /></div>
            <div class="cell-sub">{{ row.note }}</div>
            <div class="mrow"><span class="muted">尝试 / 成功 / 被采用</span><span>{{ row.stats ? `${row.stats.attempts} / ${row.stats.successes} / ${row.stats.adopted}` : '—' }}</span></div>
          </div>
        </div>
      </section>
      <section class="card flush">
        <div class="card-title pad"><Icon name="radar" :size="18" /><span class="grow">发现的来源</span><span class="extra">全网检索中出现、尚未登记的招采网站</span></div>
        <div v-if="!discovered.length" class="empty small">研究时会自动发现新的招采网站</div>
        <div v-for="d in discovered" :key="d.domain" class="disc-row">
          <span class="disc-main"><span class="cell-main">{{ d.title || d.domain }}</span>
            <a class="cell-sub" :href="d.sample_url" target="_blank" rel="noopener">{{ d.domain }}</a></span>
          <span class="disc-stat num">出现 {{ d.hits }} 次</span>
          <span class="tag" :class="d.adopted ? 'ok' : 'grey'">读出公告 {{ d.adopted }}</span>
          <span class="disc-ops">
            <button type="button" class="link-btn op" @click="addDiscovered(d)"><Icon name="plus" :size="14" />添加</button>
            <button type="button" class="link-btn op muted" @click="dismiss(d)"><Icon name="close" :size="14" />忽略</button>
          </span>
        </div>
      </section>
    </template>

    <el-dialog v-model="dialog" :title="editing ? '编辑数据源' : '新增数据源'" width="min(720px, calc(100vw - 24px))" align-center :close-on-click-modal="false">
      <el-form label-position="top" class="site-form">
        <el-form-item label="站点名称" required><el-input v-model="form.name" maxlength="100" placeholder="例如：广东省政府采购网" /></el-form-item>
        <el-form-item label="类型" required>
          <el-radio-group v-model="form.kind"><el-radio-button value="procurement">招投标</el-radio-button><el-radio-button value="business">企业信息</el-radio-button></el-radio-group>
        </el-form-item>
        <el-form-item label="接入方式" required class="full">
          <el-radio-group v-model="form.mode"><el-radio-button value="template">检索地址模板</el-radio-button><el-radio-button value="site_search">站内搜索</el-radio-button></el-radio-group>
        </el-form-item>
        <el-form-item v-if="form.mode === 'template'" label="检索地址" required class="full">
          <el-input v-model="form.template" placeholder="https://example.com/search?keyword={q}&start={start_date}" />
        </el-form-item>
        <el-form-item v-else label="站点域名" required class="full"><el-input v-model="form.domain" placeholder="www.example.com" /></el-form-item>
        <el-form-item label="公告链接规则" class="full"><el-input v-model="form.detail" placeholder="例如：example\.com/notice/\d+" /></el-form-item>
        <el-form-item label="用途"><el-input v-model="form.note" maxlength="200" placeholder="例如：广东省政府采购公告" /></el-form-item>
        <el-form-item label="选项"><el-checkbox v-model="form.login">需要登录</el-checkbox><el-checkbox v-model="form.by_company">支持按企业名检索</el-checkbox></el-form-item>
      </el-form>

      <div class="test-box">
        <div class="test-head">
          <el-input v-model="form.keyword" class="kw" maxlength="40" placeholder="测试关键词"><template #prefix><Icon name="search" :size="16" /></template></el-input>
          <el-button :loading="testing" @click="runTest()"><Icon name="play" :size="16" /><span>测试检索</span></el-button>
          <span v-if="testing" class="muted small">正在用浏览器检索并读取第一篇公告</span>
        </div>
        <div v-if="testError" class="error-line">{{ testError }}</div>
        <template v-if="test">
          <div class="test-stats">
            <span class="tag" :class="testOk ? 'ok' : 'danger'">{{ testOk ? '可用' : '不可用' }}</span>
            <span>页面状态 {{ STATUS_LABEL[test.status] || test.status }}</span><span>链接 {{ test.links }} 个</span>
            <span>匹配公告 <b>{{ test.matched }}</b> 篇</span><span>用时 {{ duration(test.elapsed_ms) }}</span>
          </div>
          <div v-if="test.error" class="muted">{{ test.error }}</div>
          <ul v-if="test.samples.length" class="samples"><li v-for="s in test.samples" :key="s.url"><a :href="s.url" target="_blank" rel="noopener">{{ s.title || s.url }}</a></li></ul>
          <div v-if="test.detail" class="detail"><b>{{ test.detail.title || '第一篇公告' }}</b> · 正文 {{ test.detail.chars }} 字<div class="muted">{{ test.detail.excerpt }}</div></div>
        </template>
      </div>
      <template #footer><el-button @click="dialog = false">取消</el-button><el-button type="primary" :loading="saving" @click="save">保存数据源</el-button></template>
    </el-dialog>
  </div>
</template>

<style scoped>
.cell-main .tag { margin-left: 6px; }
.tool { display: flex; align-items: center; gap: 12px; }
.tool-main { flex: 1; min-width: 0; }
.tool-title { display: flex; gap: 8px; align-items: center; font-size: 16px; font-weight: 600; }
.tool-mark { display: inline-grid; place-items: center; width: 36px; height: 36px; border-radius: 8px; border: 1px solid var(--line-strong); color: var(--ink); flex: none; }
.pad { padding: 14px 16px 6px; margin: 0; }
.grow { flex: 1; }
.extra { font-size: 12px; font-weight: 400; color: var(--ink-3); }
.op { display: inline-flex; align-items: center; gap: 2px; margin: 0 6px; font-size: 14px; }
.danger { color: var(--danger); }
.site-form { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 0 16px; }
.site-form .full { grid-column: 1 / -1; }
.test-box { border-radius: 8px; border: 1px solid var(--line); background: var(--canvas); padding: 12px 14px; display: flex; flex-direction: column; gap: 8px; }
.test-head { display: flex; gap: 8px; align-items: center; flex-wrap: wrap; }
.kw { width: 220px; }
.test-stats { display: flex; gap: 14px; align-items: center; flex-wrap: wrap; }
.samples { margin: 0; padding-left: 20px; font-size: 14px; }
.samples a { word-break: break-all; }
.detail { font-size: 14px; }
.disc-row { display: flex; align-items: center; gap: 12px; padding: 10px 20px; border-top: 1px solid var(--line-2); }
.disc-main { flex: 1; min-width: 0; display: flex; flex-direction: column; }
.disc-main .cell-main { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.disc-stat { font-size: 14px; color: var(--ink-2); white-space: nowrap; }
.disc-ops { display: flex; white-space: nowrap; }
.mobile { display: none; }
@media (max-width: 760px) {
  .desktop { display: none; }
  .mobile { display: flex; flex-direction: column; gap: 12px; padding: 0 12px 12px; }
  .mcard { padding: 12px; border: 1px solid var(--line); border-radius: 12px; display: flex; flex-direction: column; gap: 6px; }
  .mrow { display: flex; justify-content: space-between; align-items: center; gap: 12px; min-height: 40px; }
  .tool { flex-wrap: wrap; }
  .site-form { grid-template-columns: minmax(0, 1fr); }
}
</style>
