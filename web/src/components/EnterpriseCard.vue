<script setup lang="ts">
import {ArrowRight} from '@element-plus/icons-vue'
import {metricText,valueText,periodLabel} from '../company'
import CompanyAvatar from './CompanyAvatar.vue'
defineProps<{company:any,conversationId?:string,compact?:boolean}>()
</script>
<template>
  <router-link :to="{path:'/companies/'+company.id,query:conversationId?{conversation_id:conversationId}:{}}" :class="['enterprise-card',{compact}]" data-testid="enterprise-card">
    <div class="enterprise-card-heading"><CompanyAvatar :company="company"/><div><h2>{{company.name}}</h2><div v-if="company.view_scope==='group'||company.entity_kind==='brand'||company.origin==='historical_snapshot'" class="tag-row"><span v-if="company.view_scope==='group'" class="soft-tag">集团汇总</span><span v-else-if="company.entity_kind==='brand'" class="soft-tag">品牌</span><span v-if="company.origin==='historical_snapshot'" class="soft-tag">历史资料</span></div><p v-if="company.facts.industry" class="muted enterprise-industry">{{valueText(company.facts.industry.raw_value)}}</p></div></div>
    <dl v-if="company.tender_purchases||company.tender_wins" class="card-facts"><div><dt>采购公告</dt><dd>{{company.tender_purchases}} 条</dd></div><div><dt>中标记录</dt><dd>{{company.tender_wins}} 条</dd></div><div><dt>客户</dt><dd>{{company.tender_customers}} 家</dd></div><div><dt>供应商</dt><dd>{{company.tender_suppliers}} 家</dd></div></dl>
    <dl v-else-if="company.project_count" class="card-facts"><div><dt>采购项目</dt><dd>{{company.project_count}} 个</dd></div><div><dt>公告</dt><dd>{{company.notice_count??'—'}} 条</dd></div><div><dt>采购方</dt><dd>{{company.buyer_names?.join(' / ')||company.name}}</dd></div><div v-if="company.procurement_categories?.length"><dt>采购方向</dt><dd>{{company.procurement_categories.join(' / ')}}</dd></div></dl>
    <dl v-else-if="company.facts.headcount||company.facts.revenue||company.supplier_count||company.customer_count" class="card-facts"><div><dt>员工</dt><dd>{{metricText(company.facts.headcount)}}<small v-if="company.facts.headcount">{{company.facts.headcount.as_of}} · {{company.facts.headcount.scope}}</small></dd></div><div><dt>营收</dt><dd>{{metricText(company.facts.revenue)}}<small v-if="company.facts.revenue" class="inline-scope" :title="company.facts.revenue.report_period"> · {{periodLabel(company.facts.revenue)}} · {{company.facts.revenue.scope}}</small></dd></div><div><dt>上下游</dt><dd>上游 {{company.supplier_count}} 家 / 下游 {{company.customer_count}} 家</dd></div><div><dt>资料</dt><dd>{{company.fact_count}} 项</dd></div></dl>
    <p v-else class="card-empty muted">暂未取得公开资料，可进入详情继续研究</p>
    <footer><span>更新于 {{company.research_as_of||company.updated_at?.slice(0,10)}}</span><strong>查看企业详情 <el-icon><ArrowRight/></el-icon></strong></footer>
  </router-link>
</template>
