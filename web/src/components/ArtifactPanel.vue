<script setup lang="ts">
import {computed} from 'vue'
import {Document,Close,Download,ArrowRight} from '@element-plus/icons-vue'
import CompanyAvatar from './CompanyAvatar.vue'
import OpportunityCard from './OpportunityCard.vue'
const props=defineProps<{companies:any[],files:any[],legacyResults:any[],research?:any,conversationId?:string,preview?:any,loading?:boolean}>()
defineEmits<{(e:'select-file',id:string):void,(e:'select-dataset',id:string):void,(e:'close'):void}>()
/** 只列真实持久资料，来源摘要和全文状态分别显示，不把摘要算作已核验事实。 */
const datasets=computed(()=>props.research?.datasets?.filter((item:any)=>item.phase==='clean')||[])
</script>
<template>
  <aside class="workbench-artifacts" data-testid="workbench-artifacts">
    <div class="artifact-heading"><h2>本次产物</h2><el-button text :icon="Close" aria-label="关闭产物栏" @click="$emit('close')"/></div>
    <section v-if="research?.dataset_count" class="research-status" data-testid="research-summary">
      <div class="research-counts"><span><strong>{{research.accepted}}</strong>核验资料</span><span><strong>{{research.new_records}}</strong>本轮新增</span><span><strong>{{research.cleaned_documents}}</strong>来源资料</span></div>
      <p v-if="research.pending_documents" class="muted">{{research.pending_documents}} 份资料正在后台整理</p>
      <details v-if="research.gaps?.length" class="artifact-disclosure"><summary>待补资料 · {{research.gaps.length}}</summary><p v-for="gap in research.gaps" :key="gap">{{gap}}</p></details>
    </section>
    <div v-if="companies.length" class="artifact-section-title"><h3>企业结果</h3><small>{{companies.length}} 家</small></div>
    <div v-for="company in companies" :key="company.id" class="artifact-card">
      <div class="artifact-title"><CompanyAvatar :company="company" size="small"/><div><h3>{{company.short_name||company.name}}</h3><small v-if="company.short_name&&company.short_name!==company.name">{{company.name}}</small></div></div>
      <div class="artifact-metrics"><span><strong>{{company.tender_purchases||company.project_count}}</strong>采购记录</span><span><strong>{{company.tender_wins||0}}</strong>中标记录</span><span><strong>{{(company.tender_customers||company.customer_count)+(company.tender_suppliers||company.supplier_count)}}</strong>上下游</span></div>
      <p v-if="company.project_count" class="artifact-note">{{company.notice_count}} 条公告 · {{company.buyer_names?.join('、')}}</p>
      <p v-if="company.tender_customers||company.tender_suppliers" class="artifact-note">招投标客户 {{company.tender_customers}} 家 · 供应商 {{company.tender_suppliers}} 家</p><p v-if="company.supplier_count||company.customer_count" class="artifact-note">年报上游 {{company.supplier_count}} 家 · 下游 {{company.customer_count}} 家</p>
      <div class="artifact-actions"><router-link :to="{path:'/companies/'+company.id,query:conversationId?{conversation_id:conversationId}:{}}">完整画像<el-icon><ArrowRight/></el-icon></router-link><a :href="'/api/companies/'+company.id+'/export'"><el-icon><Download/></el-icon>导出</a></div>
    </div>
    <p v-if="!companies.length&&!legacyResults.length" class="artifact-empty">核验后的企业档案与获客线索将在这里出现</p>
    <div v-if="legacyResults.length" class="artifact-opportunities"><div class="artifact-section-title"><h3>获客线索 · {{legacyResults.length}}</h3><router-link :to="{path:'/leads',query:{view:'opportunities',conversation_id:conversationId}}">查看全部 ↗</router-link></div><OpportunityCard v-for="lead in legacyResults" :key="lead.id" :lead="lead" :conversation-id="conversationId" compact/></div>
    <div v-if="files.length" class="artifact-files"><h3>相关文件</h3><button v-for="file in files" :key="file.id" @click="$emit('select-file',file.id)"><el-icon><Document/></el-icon>{{file.filename}}</button></div>
    <details v-if="datasets.length" class="artifact-disclosure source-disclosure"><summary>来源资料 · {{datasets.length}}</summary><button v-for="dataset in datasets" :key="dataset.id" class="dataset-link" @click="$emit('select-dataset',dataset.id)"><el-icon><Document/></el-icon><span>{{dataset.title||'公开资料'}}<small>{{dataset.source_kind==='搜索摘录'?'搜索摘要':'全文资料'}} · {{dataset.origin==='network'?'本轮获取':'历史复用'}}</small></span></button></details>
    <p v-if="loading" class="muted">正在读取资料…</p>
    <div v-if="preview" class="attachment-preview"><template v-if="preview.kind==='research_dataset'"><h3>{{preview.payload?.title||'研究资料'}}</h3><p class="muted">{{preview.payload.original_chars||'—'}} 字原文 · {{preview.payload.total_chunks||'—'}} 个分析片段</p><pre class="source-body">{{preview.payload?.cleaned_body||'资料正在后台整理'}}</pre></template><template v-else><h3>{{preview.filename}}</h3><pre class="source-body">{{preview.text}}</pre></template></div>
  </aside>
</template>
<style scoped>
.workbench-artifacts{background:#fbfcfe;padding:18px 16px}.artifact-heading{display:flex;align-items:center;justify-content:space-between;margin-bottom:16px}.artifact-heading h2{font-size:18px;margin:0}.research-status{padding:0 0 14px;margin-bottom:16px;border-bottom:1px solid var(--line);font-size:14px}.research-counts,.artifact-metrics{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:10px}.research-counts span,.artifact-metrics span{color:#6c7b90;font-size:14px}.research-counts strong,.artifact-metrics strong{display:block;color:#18283d;font-size:21px;line-height:1.5;font-weight:600}.research-status>p{font-size:14px;margin-top:8px}.artifact-section-title{display:flex;justify-content:space-between;align-items:center;margin-bottom:10px}.artifact-section-title h3{font-size:15px;font-weight:600}.artifact-card{padding:12px;border-color:#e0e7f0;border-radius:9px;margin-bottom:10px;box-shadow:0 2px 6px #243c5b03}.artifact-title{align-items:center;justify-content:flex-start;gap:10px}.artifact-title>div{min-width:0}.artifact-title h3{font-size:16px;line-height:1.5;overflow-wrap:anywhere}.artifact-title small{display:block;overflow-wrap:anywhere;line-height:1.5;margin-top:2px}.artifact-monogram{display:grid;place-items:center;flex:none;width:36px;height:36px;border:1px solid #dce8f8;background:#eef5ff;border-radius:8px;font-size:18px;color:#456c9c}.artifact-metrics{margin:14px 0 10px}.artifact-metrics strong{font-size:19px}.artifact-note{font-size:14px;line-height:1.6;color:#6c7b90;overflow-wrap:anywhere}.artifact-actions{display:flex;justify-content:space-between;border-top:1px solid #edf1f7;margin-top:12px;padding-top:10px;font-size:14px}.artifact-actions a{display:flex;gap:6px;align-items:center;padding:2px 0}.artifact-actions .el-icon{font-size:16px;margin:0}.artifact-empty{font-size:14px;color:#78869b;padding:12px 0 20px}.artifact-disclosure{font-size:14px;color:#64748b;margin-top:10px}.artifact-disclosure summary{cursor:pointer;padding:3px 0}.artifact-disclosure p{margin:6px 0;line-height:1.6}.source-disclosure{border-top:1px solid var(--line);padding-top:10px}.dataset-link{display:flex;gap:8px;align-items:flex-start;border:0;background:transparent;padding:8px 0;text-align:left;width:100%;font-size:14px;color:#435975}.dataset-link>.el-icon{margin-top:3px;flex:none}.dataset-link span{min-width:0;overflow-wrap:anywhere}.dataset-link small{display:block}.dataset-link:hover{color:var(--blue);background:#f0f6ff}.artifact-files h3{font-size:15px;margin:16px 0 8px;font-weight:600}.attachment-preview{border-top:1px solid var(--line);margin-top:14px;padding-top:12px}.attachment-preview h3{font-size:16px;overflow-wrap:anywhere}.attachment-preview p{font-size:14px}
</style>
