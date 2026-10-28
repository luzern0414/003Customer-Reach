<script setup lang="ts">
import { computed, nextTick, ref, watch } from 'vue'
import { get } from '../api'
import type { SourceDetail } from '../types'
import { dateParts } from '../format'
import Icon from './Icon.vue'

const props = defineProps<{ sourceId: string | null; quote?: string }>()
const emit = defineEmits<{ close: [] }>()
const source = ref<SourceDetail | null>(null)
const error = ref('')
const body = ref<HTMLElement | null>(null)

watch(() => props.sourceId, async (id) => {
  source.value = null
  error.value = ''
  if (!id) return
  try {
    source.value = await get<SourceDetail>(`/sources/${id}`)
    await nextTick()
    body.value?.querySelector('mark')?.scrollIntoView({ block: 'center' })
  } catch {
    error.value = '无法读取原文'
  }
}, { immediate: true })

// 引用在正文中的位置：忽略空白差异后定位，高亮原文对应片段。
const parts = computed(() => {
  const text = source.value?.text || ''
  const quote = (props.quote || '').replace(/\s+/g, '')
  if (!quote) return [{ text, hit: false }]
  const positions: number[] = []
  let compact = ''
  for (let i = 0; i < text.length; i++) if (!/\s/.test(text[i])) { positions.push(i); compact += text[i] }
  const at = compact.indexOf(quote)
  if (at < 0) return [{ text, hit: false }]
  const start = positions[at], end = positions[at + quote.length - 1] + 1
  return [{ text: text.slice(0, start), hit: false }, { text: text.slice(start, end), hit: true }, { text: text.slice(end), hit: false }]
})
</script>

<template>
  <el-dialog :model-value="!!sourceId" :title="source?.title || '来源原文'" width="min(760px, calc(100vw - 24px))" align-center
             @close="emit('close')">
    <div v-if="error" class="error-line">{{ error }}</div>
    <el-skeleton v-else-if="!source" :rows="8" animated />
    <template v-else>
      <div class="meta">
        <span>{{ source.site }}</span><span>读取于 {{ dateParts(source.fetched_at).date }} {{ dateParts(source.fetched_at).time }}</span>
        <a :href="source.url" target="_blank" rel="noopener" data-action-id="A-212"><Icon name="external" :size="16" />打开原网页</a>
      </div>
      <div ref="body" class="source-text"><template v-for="(part, i) in parts" :key="i"><mark v-if="part.hit">{{ part.text }}</mark><template v-else>{{ part.text }}</template></template></div>
    </template>
  </el-dialog>
</template>

<style scoped>
.meta { display: flex; flex-wrap: wrap; gap: 16px; align-items: center; margin-bottom: 12px; color: var(--ink-3); }
.meta a { display: inline-flex; gap: 4px; align-items: center; margin-left: auto; }
</style>
