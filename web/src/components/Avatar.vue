<script setup lang="ts">
// 默认头像：圆形发丝边框里放线性人像，不用卡通形象与文字头像
import Icon from './Icon.vue'

withDefaults(defineProps<{ seed?: string; size?: number }>(), { size: 32 })
</script>

<template>
  <span class="avatar" :style="{ width: size + 'px', height: size + 'px' }" aria-hidden="true"><Icon name="user" :size="Math.round(size / 2)" /></span>
</template>

<style scoped>
.avatar { display: inline-grid; place-items: center; flex: none; border-radius: 50%; border: 1px solid var(--line-strong); background: var(--surface); color: var(--ink-2); }
</style>
