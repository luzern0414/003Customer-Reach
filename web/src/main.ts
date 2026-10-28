import { createApp } from 'vue'
import { createRouter, createWebHistory } from 'vue-router'
import ElementPlus from 'element-plus'
import zhCn from 'element-plus/es/locale/lang/zh-cn'
import 'element-plus/dist/index.css'
import './theme.css'
import App from './App.vue'

const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/', component: () => import('./pages/Overview.vue'), meta: { title: '概览' } },
    { path: '/workbench', component: () => import('./pages/Workbench.vue'), meta: { title: '获客工作台', full: true } },
    { path: '/c/:id', component: () => import('./pages/Workbench.vue'), meta: { title: '获客工作台', full: true } },
    { path: '/companies', component: () => import('./pages/Companies.vue'), meta: { title: '企业档案' } },
    { path: '/companies/:id', component: () => import('./pages/CompanyPage.vue'), meta: { title: '企业主页' } },
    { path: '/leads', component: () => import('./pages/Leads.vue'), meta: { title: '线索管理' } },
    { path: '/leads/:id', component: () => import('./pages/LeadPage.vue'), meta: { title: '线索主页' } },
    { path: '/sources', component: () => import('./pages/Sources.vue'), meta: { title: '数据源' } },
    { path: '/settings', component: () => import('./pages/Settings.vue'), meta: { title: '系统设置' } },
    { path: '/:rest(.*)', redirect: '/' },
  ],
})
router.afterEach((to) => { document.title = `${to.meta.title || ''} · DealRadar` })

createApp(App).use(router).use(ElementPlus, { locale: zhCn }).mount('#app')
