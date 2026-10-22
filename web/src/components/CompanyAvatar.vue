<script setup lang="ts">
import {ref,watch} from 'vue'
import {monogram} from '../company'
/** company为后端企业摘要；有官网图标时显示图标，加载失败或没有时显示企业首字。 */
const props=defineProps<{company:any,size?:'small'|'medium'|'large'}>()
const failed=ref(false)
watch(()=>props.company?.logo_url,()=>{failed.value=false})
</script>
<template>
  <span :class="['company-avatar',size||'medium',{'has-logo':company?.logo_url&&!failed}]" aria-hidden="true">
    <img v-if="company?.logo_url&&!failed" :src="company.logo_url" alt="" loading="lazy" @error="failed=true">
    <template v-else>{{monogram(company||{})}}</template>
  </span>
</template>
