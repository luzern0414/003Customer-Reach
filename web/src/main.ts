import { createApp } from 'vue'
import { createRouter, createWebHistory } from 'vue-router'
import ElementPlus from 'element-plus'
import zhCn from 'element-plus/es/locale/lang/zh-cn'
import 'element-plus/dist/index.css'
import App from './App.vue'
import './theme.css'
import './company-overview.css'
import './components.css'
import './acquisition.css'
const router=createRouter({history:createWebHistory(),routes:[{path:'/',component:()=>import('./pages/Home.vue')},{path:'/leads',component:()=>import('./pages/QueryResults.vue')},{path:'/opportunities/:id',component:()=>import('./pages/LeadDetail.vue')},{path:'/companies/:id',component:()=>import('./pages/CompanyDetail.vue')},{path:'/companies/:id/relations/:relationId',component:()=>import('./pages/CounterpartyDetail.vue')},{path:'/legacy-leads',component:()=>import('./pages/Leads.vue')},{path:'/settings',component:()=>import('./pages/Settings.vue')}]})
createApp(App).use(router).use(ElementPlus,{locale:zhCn}).mount('#app')
