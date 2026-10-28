<script setup lang="ts">
import { computed, reactive, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import type { FormInstance, FormRules } from 'element-plus'
import { api, ApiError } from '../api'
import Icon from '../components/Icon.vue'
import { signIn, type Account } from '../session'

const route = useRoute()
const router = useRouter()
const registering = computed(() => route.path === '/register')
const formRef = ref<FormInstance>()
const form = reactive({ username: '', password: '', confirm: '' })
const loading = ref(false)
const error = ref('')

const rules = computed<FormRules>(() => ({
  username: [
    { required: true, message: '请输入用户名', trigger: 'blur' },
    ...(registering.value ? [{ pattern: /^[A-Za-z0-9_一-鿿]{3,20}$/, message: '3–20 位中文、字母、数字或下划线', trigger: 'blur' }] : []),
  ],
  password: [
    { required: true, message: '请输入密码', trigger: 'blur' },
    ...(registering.value ? [{ min: 6, max: 64, message: '密码长度为 6–64 位', trigger: 'blur' }] : []),
  ],
  confirm: [
    { required: true, message: '请再次输入密码', trigger: 'blur' },
    { validator: (_: unknown, value: string, done: (e?: Error) => void) => done(value === form.password ? undefined : new Error('两次输入的密码不一致')), trigger: 'blur' },
  ],
}))

watch(registering, () => { error.value = ''; formRef.value?.clearValidate() })
// 修改密码后重新校验确认密码
watch(() => form.password, () => { if (registering.value && form.confirm) formRef.value?.validateField('confirm').catch(() => null) })

async function submit() {
  if (loading.value || !(await formRef.value?.validate().catch(() => false))) return
  loading.value = true
  error.value = ''
  try {
    const account = await api<Account>(registering.value ? '/auth/register' : '/auth/login', {
      method: 'POST', notify: false, body: { username: form.username.trim(), password: form.password },
    })
    signIn(account)
    const target = typeof route.query.redirect === 'string' && route.query.redirect.startsWith('/') ? route.query.redirect : '/workbench'
    await router.replace(target)
  } catch (e) {
    error.value = e instanceof ApiError ? e.message : '无法连接服务，请稍后重试'
  } finally {
    loading.value = false
  }
}
</script>

<template>
  <div class="login">
    <div class="panel">
      <section class="visual">
        <div class="brand"><span class="brand-mark"><Icon name="radar" :size="22" /></span>DealRadar</div>
        <svg class="art" viewBox="0 0 360 260" fill="none" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
          <g stroke="#4e5969" stroke-width="1.5" vector-effect="non-scaling-stroke">
            <path d="M24 236h312" />
            <path d="M40 236V128l44-14v122M84 136h40v100M54 140h10M54 160h10M54 180h10M54 200h10M98 154h12M98 174h12M98 194h12" />
            <path d="M232 236V150h44v86M276 168h40v68M246 166h16M246 186h16M246 206h16M290 184h12M290 204h12" />
            <rect x="140" y="138" width="80" height="98" rx="6" fill="#fff" />
            <path d="M154 158h52M154 174h52M154 190h36M154 206h44" />
          </g>
          <g stroke="#2f54eb" stroke-width="1.5" vector-effect="non-scaling-stroke">
            <circle cx="180" cy="74" r="54" />
            <circle cx="180" cy="74" r="34" />
            <circle cx="180" cy="74" r="14" />
            <path d="M180 74l38-38" />
            <circle cx="206" cy="58" r="4" fill="#2f54eb" />
            <circle cx="160" cy="98" r="3" fill="#2f54eb" />
            <path d="M154 206h44" />
          </g>
        </svg>
        <p class="slogan">从招投标公告里找到正在采购的客户</p>
      </section>

      <section class="form-side">
        <h1>{{ registering ? '注册账号' : '登录' }}</h1>
        <el-form ref="formRef" :model="form" :rules="rules" label-position="top" size="large" hide-required-asterisk @submit.prevent="submit">
          <el-form-item label="用户名" prop="username">
            <el-input v-model="form.username" maxlength="20" autocomplete="username" placeholder="例如 sales_wang">
              <template #prefix><Icon name="user" :size="18" /></template>
            </el-input>
          </el-form-item>
          <el-form-item label="密码" prop="password">
            <el-input v-model="form.password" type="password" show-password maxlength="64"
                      :autocomplete="registering ? 'new-password' : 'current-password'">
              <template #prefix><Icon name="lock" :size="18" /></template>
            </el-input>
          </el-form-item>
          <el-form-item v-if="registering" label="确认密码" prop="confirm">
            <el-input v-model="form.confirm" type="password" show-password maxlength="64" autocomplete="new-password">
              <template #prefix><Icon name="lock" :size="18" /></template>
            </el-input>
          </el-form-item>
          <div v-if="error" class="error" role="alert"><Icon name="alert" :size="16" />{{ error }}</div>
          <el-button type="primary" native-type="submit" class="submit" :loading="loading">{{ registering ? '注册并登录' : '登录' }}</el-button>
        </el-form>
        <div class="switch">
          <template v-if="registering">已有账号？<RouterLink :to="{ path: '/login', query: route.query }">去登录</RouterLink></template>
          <template v-else>还没有账号？<RouterLink :to="{ path: '/register', query: route.query }">立即注册</RouterLink></template>
        </div>
      </section>
    </div>
  </div>
</template>

<style scoped>
.login { min-height: 100%; display: grid; place-items: center; padding: 24px 16px; background: var(--page); overflow-y: auto; }
.panel { width: 100%; max-width: 920px; display: grid; grid-template-columns: minmax(0, 1fr) 400px; background: var(--card); border-radius: 12px; box-shadow: var(--shadow); overflow: hidden; }
.visual { display: flex; flex-direction: column; gap: 24px; padding: 32px; background: var(--brand-tint); }
.brand { display: flex; align-items: center; gap: 10px; font-size: 20px; line-height: 28px; font-weight: 600; color: var(--ink); }
.brand-mark { display: inline-grid; place-items: center; width: 36px; height: 36px; border-radius: 10px; background: var(--brand); color: #fff; }
.art { width: 100%; max-width: 400px; margin: auto; }
.slogan { margin: 0; font-size: 17px; line-height: 26px; font-weight: 600; color: var(--brand-press); text-align: center; }
.form-side { padding: 40px 40px 32px; display: flex; flex-direction: column; justify-content: center; }
h1 { margin: 0 0 24px; font-size: 24px; line-height: 32px; font-weight: 600; }
.form-side :deep(.el-form-item) { margin-bottom: 24px; }
.form-side :deep(.el-form-item__error) { font-size: 13px; padding-top: 4px; }
.form-side :deep(.el-form-item__label) { font-size: 15px; color: var(--ink); }
.form-side :deep(.el-input__prefix) { color: var(--ink-3); }
.form-side :deep(.el-input--large) { font-size: 15px; }
.error { display: flex; align-items: center; gap: 6px; margin: -4px 0 12px; padding: 8px 12px; border-radius: 8px; background: var(--danger-tint); color: var(--danger); font-size: 14px; }
.submit { width: 100%; height: 44px; font-size: 16px; }
.switch { margin-top: 20px; text-align: center; font-size: 14px; color: var(--ink-3); }
.switch a { color: var(--brand); font-weight: 600; }
.switch a:hover { color: var(--brand-hover); }
@media (max-width: 760px) {
  .login { place-items: start center; padding: 0; background: var(--card); }
  .panel { grid-template-columns: minmax(0, 1fr); border-radius: 0; box-shadow: none; }
  .visual { padding: 20px 16px 16px; gap: 12px; }
  .art { max-width: 260px; }
  .slogan { font-size: 15px; }
  .form-side { padding: 24px 16px 32px; }
}
</style>
