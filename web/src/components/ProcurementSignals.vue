<script setup lang="ts">
/** signals为后端带时效状态的真实公告投影；空列表不显示，无模型推断或前端日期补造。 */
defineProps<{signals?:any[]}>()
const roles:Record<string,string>={buyer:'采购方',supplier:'供应方',agency:'代理机构'}
</script>
<template>
  <div v-if="signals?.length" class="procurement-signals"><h3>采购公告</h3><section v-for="(item,index) in signals" :key="item.source_id+':'+index" class="procurement-record"><div class="row"><strong>{{item.display_status}}</strong><small>{{roles[item.participant_role]||''}}</small></div><p v-if="item.deadline" class="panel-meta">截止 {{item.deadline}}</p><details><summary>公告原文</summary><p class="pre-text">{{item.quote}}</p><template v-if="item.buyer_quote&&item.buyer_quote!==item.quote"><small>采购人</small><p class="pre-text">{{item.buyer_quote}}</p></template><template v-if="item.deadline_quote&&item.deadline_quote!==item.quote"><small>截止时间</small><p class="pre-text">{{item.deadline_quote}}</p></template></details><a v-if="item.url" :href="item.url" target="_blank" rel="noopener noreferrer">{{item.title||'来源'}} ↗</a></section></div>
</template>
