<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { get, post } from '../api'
import type { ConversationItem } from '../types'
import { dayGroup } from '../format'
import Icon from './Icon.vue'

const emit = defineEmits<{ close: [] }>()
const route = useRoute()
const router = useRouter()
const conversations = ref<ConversationItem[]>([])
const grouped = computed(() => {
  const groups: Record<string, ConversationItem[]> = {}
  for (const item of conversations.value) (groups[dayGroup(item.updated_at)] ||= []).push(item)
  return ['今天', '昨天', '更早'].filter((group) => groups[group]).map((name) => ({ name, items: groups[name] }))
})
async function load() { conversations.value = await get<ConversationItem[]>('/conversations').catch(() => conversations.value) }
async function newConversation() {
  const conversation = await post<ConversationItem>('/conversations')
  await router.push(`/c/${conversation.id}`)
  emit('close')
}
onMounted(load)
watch(() => route.fullPath, load)
</script>

<template>
  <section class="history" aria-label="会话历史">
    <div class="history-divider" />
    <div class="history-head"><span>会话历史</span><button type="button" class="history-new" title="新建对话" @click="newConversation"><Icon name="plus" :size="14" /></button></div>
    <button type="button" class="history-create" @click="newConversation"><Icon name="plus" :size="14" />新建对话</button>
    <div v-for="group in grouped" :key="group.name" class="history-group">
      <div class="history-label">{{ group.name }}</div>
      <RouterLink v-for="item in group.items" :key="item.id" :to="`/c/${item.id}`" class="history-item" :class="{ on: item.id === route.params.id }" @click="emit('close')">
        <span class="history-item-title">{{ item.title }}</span>
        <span v-if="item.status === 'running' || item.status === 'queued' || item.status === 'replanning'" class="conv-dot run" aria-label="运行中" />
        <span v-else-if="item.status === 'awaiting_user' || item.status === 'awaiting_input'" class="tag warn">等待处理</span>
      </RouterLink>
    </div>
    <div v-if="!conversations.length" class="muted history-empty">还没有对话</div>
  </section>
</template>

<style scoped>
.history { flex: none; padding: 0 0 8px; }
.history-divider { height: 1px; margin: 8px 0 4px; background: var(--line); }
.history-head { display: flex; align-items: center; justify-content: space-between; padding: 8px 10px 4px; color: var(--ink-3); font-size: 12px; }
.history-new { display: grid; place-items: center; width: 24px; height: 24px; padding: 0; border: 0; border-radius: 6px; background: none; color: var(--ink-3); cursor: pointer; }
.history-new:hover { background: var(--subtle); color: var(--ink); }
.history-create { display: flex; align-items: center; gap: 8px; width: calc(100% - 16px); height: 32px; margin: 2px 8px 4px; padding: 0 10px; border: 1px solid var(--line); border-radius: 8px; background: var(--surface); color: var(--ink-2); font: inherit; cursor: pointer; }
.history-create:hover { background: var(--subtle); color: var(--ink); }
.history-group { padding: 2px 8px 0; }
.history-label { padding: 8px 8px 4px; color: var(--ink-3); font-size: 12px; }
.history-item { display: flex; align-items: center; gap: 8px; min-height: 32px; padding: 0 10px; border: 1px solid transparent; border-radius: 8px; color: var(--ink-2); font-size: 13px; }
.history-item:hover { background: var(--subtle); color: var(--ink); }
.history-item.on { background: var(--surface); border-color: var(--line); color: var(--ink); font-weight: 600; box-shadow: var(--shadow); }
.history-item-title { flex: 1; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.conv-dot { display: inline-block; width: 6px; height: 6px; border-radius: 50%; background: #a1a1aa; flex: none; }
.conv-dot.run { background: var(--accent); animation: pulse 1.2s infinite; }
.history-empty { padding: 8px 10px; font-size: 12px; }
@keyframes pulse { 50% { opacity: .35; } }
</style>
