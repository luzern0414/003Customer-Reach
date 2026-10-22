<script setup lang="ts">
import {Close,Document} from '@element-plus/icons-vue'
import FactValue from './FactValue.vue'
import ProcurementSignals from './ProcurementSignals.vue'
import {roles,factLabels} from '../api'
/** files/results/profile为当前对话的后端数据；preview为选中文件的真实提取文本。 */
defineProps<{files:any[],results:any[],profile:any,preview:any,loading:boolean,tab:string}>()
defineEmits<{close:[],selectFile:[id:string],changeTab:[tab:string]}>()
/** lead为真实CRM投影；同网址逐字段引文只显示一个链接，不删除后端证据。 */
function sources(lead:any){
  // 公告组件已提供来源入口，汇总区只补充其他来源，逐字段原始证据仍保留。
  const shown=new Set((lead.procurement_signals||[]).map((item:any)=>item.url).filter(Boolean))
  return [...new Map<string,any>((lead.contact_summary?.sources||lead.evidence||[]).filter((item:any)=>item.url&&!shown.has(item.url)).map((item:any)=>[item.url,item])).values()]
}
</script>
<template>
  <aside class="result-panel" aria-label="结果与文件面板">
    <div class="result-panel-header"><div class="result-tabs"><button v-for="item in [{id:'results',label:'结果'},{id:'files',label:'文件'},{id:'data',label:'数据'}]" :key="item.id" :class="{active:tab===item.id}" @click="$emit('changeTab',item.id)">{{item.label}}</button></div><el-button text :icon="Close" aria-label="关闭结果面板" @click="$emit('close')"/></div>
    <div class="result-panel-body">
      <template v-if="tab==='results'">
        <p v-if="!results.length" class="panel-empty">暂无客户结果</p>
        <section v-for="lead in results" :key="lead.id" class="result-entry">
          <h3>{{lead.display_name}}</h3><p>{{[lead.city,roles[lead.buyer_role],lead.industry].filter(Boolean).join(' · ')}}</p>
          <FactValue v-if="lead.facts?.categories?.value" :fact="lead.facts.categories"/>
          <p class="panel-meta">{{lead.matched_products?.length?'相关产品 · '+lead.matched_products.join('、'):'产品适配待核验'}}</p>
          <div class="contact-fields">
            <FactValue v-if="lead.facts?.phone?.value" :fact="lead.facts.phone" phone/>
            <small v-if="lead.contact_summary?.phone_incomplete">原文未提供区号</small>
            <small v-if="lead.contact_summary?.phone_status==='invalid'">号码格式待核验</small>
            <FactValue v-if="lead.facts?.email?.value" :fact="lead.facts.email" email/>
            <FactValue v-if="lead.facts?.website?.value" :fact="lead.facts.website" website/>
            <FactValue v-if="lead.facts?.wechat?.value" :fact="lead.facts.wechat" wechat/>
            <FactValue v-if="lead.facts?.address?.value" :fact="lead.facts.address"/>
            <div v-if="lead.facts?.contact_name?.value" class="contact-person"><span>联系人</span><FactValue :fact="lead.facts.contact_name"/><FactValue v-if="lead.facts?.contact_position?.value" :fact="lead.facts.contact_position"/></div>
            <p v-if="lead.contact_summary" class="panel-meta">{{lead.contact_summary.status}} · {{lead.contact_summary.purpose}}</p>
            <p v-if="lead.contact_summary?.missing_fields?.length" class="panel-meta">待补 · {{lead.contact_summary.missing_fields.map((key:string)=>factLabels[key]||key).join('、')}}</p>
          </div>
          <p v-if="lead.match_reason">{{lead.match_reason}}</p><ProcurementSignals :signals="lead.procurement_signals"/>
          <details v-if="sources(lead).length" class="lead-sources"><summary>{{lead.contact_summary?.site_count??0}} 个网站 · {{lead.contact_summary?.source_count??sources(lead).length}} 个页面</summary>
            <div v-for="source in sources(lead)" :key="source.url"><a :href="source.url" target="_blank" rel="noopener noreferrer">{{source.title||source.url}} ↗</a><small>{{source.platform}} {{source.captured_at}}</small></div>
          </details>
        </section>
      </template>
      <template v-else-if="tab==='files'"><p v-if="!files.length" class="panel-empty">暂无文件</p><button v-for="file in files" :key="file.id" :class="['panel-file',{active:preview?.id===file.id}]" @click="$emit('selectFile',file.id)"><el-icon><Document/></el-icon><span>{{file.filename}}</span><small>{{file.truncated?'部分解析':file.parse?.warnings?.length?'需核对':'已解析'}}</small></button><div v-loading="loading" class="panel-preview"><template v-if="preview"><h3>{{preview.filename}}</h3><p class="panel-meta">{{preview.characters}} 字符 · {{preview.parse?.method||'文本提取'}}</p><p v-for="warning in preview.parse?.warnings||[]" :key="warning" class="parse-warning">{{warning}}</p><div class="panel-source">{{preview.text}}</div></template></div></template>
      <template v-else><p v-if="!profile?.products?.length&&!files.length" class="panel-empty">暂无数据</p><section v-for="product in profile?.products||[]" :key="product.name" class="result-entry"><h3>{{product.name}}</h3><p>{{[product.model,product.specifications,product.price].filter(Boolean).join(' · ')}}</p></section><p v-if="profile?.region" class="panel-meta">地区 · {{profile.region}}</p><p v-if="profile?.target_buyers?.length" class="panel-meta">买家 · {{profile.target_buyers.join('、')}}</p><p v-if="profile?.exclusions?.length" class="panel-meta">排除 · {{profile.exclusions.join('、')}}</p><section v-for="file in files" :key="file.id" class="result-entry"><h3>{{file.filename}}</h3><p>{{file.characters}} 字符<template v-if="file.parse?.pages"> · {{file.parse.pages}} 页</template><template v-if="file.parse?.sheets?.length"> · {{file.parse.sheets.length}} 张表</template><template v-if="file.parse?.tables"> · {{file.parse.tables}} 个表格</template></p><p v-if="file.parse?.ocr_pages?.length">OCR · {{file.parse.ocr_pages.length}} 页</p><p v-if="file.parse?.formula_without_cache">{{file.parse.formula_without_cache}} 个公式无缓存值</p><p v-if="file.truncated">部分解析</p></section></template>
    </div>
  </aside>
</template>
