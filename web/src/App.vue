<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import Icon from './components/Icon.vue'

const route = useRoute()
const drawer = ref(false)
const MENU = [
  { group: '概览', items: [{ id: 'N-000', to: '/', label: '概览', icon: 'overview', match: /^\/$/ }] },
  { group: '获客', items: [
    { id: 'N-001', to: '/workbench', label: '获客工作台', icon: 'workbench', match: /^\/(workbench|c\/)/ },
    { id: 'N-002', to: '/companies', label: '企业档案', icon: 'company', match: /^\/companies/ },
    { id: 'N-003', to: '/leads', label: '线索管理', icon: 'lead', match: /^\/leads/ },
  ] },
  { group: '配置', items: [
    { id: 'N-004', to: '/sources', label: '数据源', icon: 'source', match: /^\/sources/ },
    { id: 'N-005', to: '/settings', label: '系统设置', icon: 'settings', match: /^\/settings/ },
  ] },
]
const full = computed(() => route.meta.full === true)
watch(() => route.fullPath, () => { drawer.value = false })
</script>

<template>
  <div class="shell">
    <aside class="side" :class="{ open: drawer }">
      <div class="brand"><span class="brand-mark"><Icon name="radar" :size="22" /></span>DealRadar</div>
      <nav>
        <div v-for="g in MENU" :key="g.group" class="group">
          <div class="group-title">{{ g.group }}</div>
          <RouterLink v-for="item in g.items" :key="item.to" :to="item.to" class="menu-item" :data-navigation-id="item.id"
                      :class="{ on: item.match.test(route.path) }">
            <Icon :name="item.icon" />{{ item.label }}
          </RouterLink>
        </div>
      </nav>
    </aside>
    <div v-if="drawer" class="mask" @click="drawer = false" />
    <div class="main" :class="{ full }">
      <header class="topbar">
        <button type="button" class="menu-btn" aria-label="打开菜单" @click="drawer = true"><Icon name="menu" /></button>
        <span class="top-brand">DealRadar</span>
      </header>
      <RouterView />
    </div>
  </div>
</template>

<style scoped>
.shell { display: flex; height: 100%; }
.side { width: 216px; flex: none; background: #fff; border-right: 1px solid var(--line); padding: 16px 12px; overflow-y: auto; }
.brand { display: flex; align-items: center; gap: 10px; height: 44px; padding: 0 8px; font-size: 20px; line-height: 28px; font-weight: 600; margin-bottom: 4px; }
.brand-mark { display: inline-grid; place-items: center; width: 36px; height: 36px; border-radius: 10px; background: var(--brand); color: #fff; }
.group { padding: 10px 0; border-top: 1px solid var(--line-2); }
.group:first-child { border-top: 0; }
.group-title { margin: 0 10px 6px; padding-left: 8px; border-left: 3px solid #c9cdd4; font-weight: 600; font-size: 13px; line-height: 18px; color: var(--ink-3); }
.menu-item { display: flex; align-items: center; gap: 10px; height: 42px; padding: 0 12px; border-radius: 8px; color: var(--ink-2); font-size: 15px; position: relative; }
.menu-item:hover { background: #f5f5f5; color: var(--ink); }
.menu-item.on { background: var(--brand-tint); color: var(--brand-press); font-weight: 600; }
.menu-item.on::before { content: ''; position: absolute; left: 0; top: 10px; bottom: 10px; width: 3px; border-radius: 2px; background: var(--brand); }
.main { flex: 1; min-width: 0; overflow-y: auto; }
.main.full { overflow: hidden; display: flex; flex-direction: column; }
.topbar { display: none; }
.mask { display: none; }
@media (max-width: 760px) {
  .side { position: fixed; z-index: 30; inset: 0 auto 0 0; width: 100%; max-width: 100%; transform: translateX(-100%); transition: transform .2s; }
  .side.open { transform: none; }
  .mask { display: block; position: fixed; inset: 0; z-index: 20; background: rgba(0, 0, 0, .3); }
  .topbar { display: flex; align-items: center; gap: 8px; height: 48px; padding: 0 12px; background: #fff; border-bottom: 1px solid var(--line); flex: none; }
  .menu-btn { display: grid; place-items: center; width: 40px; height: 40px; border: 0; background: none; color: var(--ink); }
  .top-brand { font-weight: 600; font-size: 16px; }
}
</style>
