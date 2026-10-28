<script setup lang="ts">
import { computed } from 'vue'

// 默认头像：按用户 id 的哈希固定一只卡通动物（扁平填色 + 深灰描边）
const props = withDefaults(defineProps<{ seed: string; size?: number }>(), { size: 36 })

const ANIMALS = [
  { bg: '#fff1b8', face: '#ffd666', ears: 'M9 13L11 5l6 5M31 13l-2-8-6 5', inner: '' }, // 猫
  { bg: '#ffe7ba', face: '#d4a373', ears: 'M8 12a4 4 0 1 1 6-4M32 12a4 4 0 1 0-6-4', inner: '' }, // 熊
  { bg: '#d6e4ff', face: '#ffffff', ears: 'M15 11c-2-6-1-10 1-10s3 4 2 10M25 11c1-6 0-10-2-10s-3 4-2 10', inner: '' }, // 兔
  { bg: '#d9f7be', face: '#ffa940', ears: 'M9 15L8 4l9 6M31 15l1-11-9 6', inner: 'M13 26c3 5 11 5 14 0' }, // 狐
]
const animal = computed(() => {
  let hash = 0
  for (const ch of props.seed) hash = (hash * 31 + ch.charCodeAt(0)) >>> 0
  return ANIMALS[hash % ANIMALS.length]
})
</script>

<template>
  <svg class="avatar" :width="size" :height="size" viewBox="0 0 40 40" aria-hidden="true">
    <circle cx="20" cy="20" r="20" :fill="animal.bg" />
    <g stroke="#1f2329" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" vector-effect="non-scaling-stroke">
      <path :d="animal.ears" :fill="animal.face" />
      <ellipse cx="20" cy="23" rx="12" ry="11" :fill="animal.face" />
      <path v-if="animal.inner" :d="animal.inner" fill="none" />
      <path d="M18.5 26.5l1.5 1.5 1.5-1.5" fill="none" />
    </g>
    <circle cx="15.5" cy="21.5" r="1.6" fill="#1f2329" />
    <circle cx="24.5" cy="21.5" r="1.6" fill="#1f2329" />
  </svg>
</template>

<style scoped>
.avatar { flex: none; border-radius: 50%; display: block; }
</style>
