<script setup lang="ts">
import {computed} from 'vue'
import {useRoute} from 'vue-router'
import {House,Document,Setting} from '@element-plus/icons-vue'
const route=useRoute()
const workbench=computed(()=>route.path==='/')
const title=computed(()=>route.path.startsWith('/companies/')?'查询结果 / 企业详情':route.path.startsWith('/opportunities/')?'查询结果 / 客户机会':route.path==='/settings'?'设置':route.path==='/'?'工作台':route.path==='/legacy-leads'?'销售跟进':'查询结果')
</script>
<template>
  <div :class="['shell',{'workbench-shell':workbench,'query-shell':route.path==='/leads'}]">
    <aside class="sidebar" data-testid="app-sidebar">
      <router-link to="/" class="brand"><span class="brand-mark">R</span><span><strong>Client Reach</strong><small>Agent 工作台</small></span></router-link>
      <nav aria-label="主要导航">
        <router-link to="/" aria-label="工作台" :class="{active:workbench}"><el-icon><House/></el-icon><span>工作台</span></router-link>
        <router-link to="/leads" aria-label="查询结果" :class="{active:route.path.startsWith('/companies/')||route.path.startsWith('/opportunities/')||route.path==='/leads'||route.path==='/legacy-leads'}"><el-icon><Document/></el-icon><span>查询结果</span></router-link>
        <router-link to="/settings" aria-label="设置"><el-icon><Setting/></el-icon><span>设置</span></router-link>
      </nav>
    </aside>
    <main class="main">
      <header class="global-header"><strong>{{title}}</strong></header>
      <router-view/>
    </main>
  </div>
</template>
