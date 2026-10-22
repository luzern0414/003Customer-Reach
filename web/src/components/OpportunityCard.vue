<script setup lang="ts">
import {computed} from 'vue'
import {stages} from '../api'
const props=defineProps<{lead:any,compact?:boolean,conversationId?:string}>()
const project=computed(()=>props.lead.acquisition?.projects?.[0])
</script>
<template>
  <article :class="['opportunity-card',{compact}]">
    <div class="opportunity-card-top"><span class="opportunity-state">{{lead.acquisition?.open_count?'有公开采购':project?.status||'需求待核验'}}</span><span>{{stages[lead.status]||'待核验'}}</span></div>
    <h3><router-link :to="{path:'/opportunities/'+lead.id,query:conversationId?{conversation_id:conversationId}:{}}">{{lead.display_name}}</router-link></h3>
    <p class="opportunity-location">{{[lead.city,lead.industry].filter(Boolean).join(' · ')||'地区与行业待补'}}</p>
    <p class="opportunity-demand">{{project?.name?.value||project?.title||lead.facts?.categories?.value||'尚未取得具体需求原文'}}</p>
    <div v-if="project?.amounts?.length" class="opportunity-amounts"><span v-for="amount in project.amounts" :key="amount.label"><small>{{amount.label}}</small><strong>{{amount.value}}</strong></span></div>
    <p v-if="project?.deadline" class="opportunity-deadline">响应 / 投标截止 <strong>{{project.deadline}}</strong></p>
    <p v-if="lead.acquisition?.projects?.length>1" class="opportunity-location">另有 {{lead.acquisition.projects.length-1}} 条公告，详情逐条保留</p>
    <div class="opportunity-card-bottom"><span>{{lead.owner||'待分配负责人'}}<template v-if="lead.next_followup"> · 跟进 {{lead.next_followup.slice(5,16)}}</template></span><router-link :to="{path:'/opportunities/'+lead.id,query:conversationId?{conversation_id:conversationId}:{}}">查看与跟进 ↗</router-link></div>
  </article>
</template>
