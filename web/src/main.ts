import { createApp } from 'vue'
import { createRouter, createWebHistory } from 'vue-router'
import ElementPlus from 'element-plus'
import zhCn from 'element-plus/es/locale/lang/zh-cn'
import 'element-plus/dist/index.css'
import './theme.css'
import App from './App.vue'
import { setUnauthorizedHandler } from './api'
import { loadMe, session } from './session'

const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/login', component: () => import('./pages/Login.vue'), meta: { title: '登录', public: true } },
    { path: '/register', component: () => import('./pages/Login.vue'), meta: { title: '注册', public: true } },
    { path: '/', component: () => import('./pages/Overview.vue'), meta: { title: '概览' } },
    { path: '/workbench', component: () => import('./pages/Workbench.vue'), meta: { title: '获客工作台', full: true } },
    { path: '/c/:id', component: () => import('./pages/Workbench.vue'), meta: { title: '获客工作台', full: true } },
    { path: '/companies', component: () => import('./pages/Companies.vue'), meta: { title: '企业档案' } },
    { path: '/companies/:id', component: () => import('./pages/CompanyPage.vue'), meta: { title: '企业主页' } },
    { path: '/leads', component: () => import('./pages/Leads.vue'), meta: { title: '线索管理' } },
    { path: '/leads/:id', component: () => import('./pages/LeadPage.vue'), meta: { title: '线索主页' } },
    { path: '/sources', component: () => import('./pages/Sources.vue'), meta: { title: '数据源', admin: true } },
    { path: '/settings', component: () => import('./pages/Settings.vue'), meta: { title: '系统设置', admin: true } },
    { path: '/:rest(.*)', redirect: '/' },
  ],
})
router.beforeEach(async (to) => {
  if (!session.loaded) await loadMe()
  if (to.meta.public) return session.me ? '/' : true
  if (!session.me) return { path: '/login', query: to.fullPath === '/' ? {} : { redirect: to.fullPath } }
  if (to.meta.admin && !session.me.is_admin) return '/'
  return true
})
setUnauthorizedHandler(() => {
  session.me = null
  if (!router.currentRoute.value.meta.public) router.push({ path: '/login', query: { redirect: router.currentRoute.value.fullPath } })
})
router.afterEach((to) => { document.title = `${to.meta.title || ''} · DealRadar` })

createApp(App).use(router).use(ElementPlus, { locale: zhCn }).mount('#app')
