<script setup lang="ts">
import {ref,computed,watch,onMounted,onUnmounted} from 'vue'
import {useRoute,useRouter} from 'vue-router'
import {ElMessage} from 'element-plus'
import {api,stages,factLabels,roles} from '../api'
import FactValue from '../components/FactValue.vue'
import LeadAnalysis from '../components/LeadAnalysis.vue'
const route=useRoute(),router=useRouter(),data=ref<any>(null),loading=ref(false),error=ref(''),saving=ref(false),analysing=ref(false),analysisError=ref('')
const form=ref<any>({}),note=ref(''),kind=ref('note'),noting=ref(false),feedbackText=ref(''),feedbackKind=ref('incorrect'),feedbackBusy=ref(false)
const source=ref<any>(null),sourceOpen=ref(false),sourceLoading=ref(false),sourceError=ref(''),analysisNote=ref('')
let version=0,routeVersion=0,controller:AbortController|undefined,sourceVersion=0,sourceController:AbortController|undefined,analysisToken='',analysisRequest=''
const mutationBusy=computed(()=>saving.value||noting.value||feedbackBusy.value)
const projects=computed(()=>data.value?.acquisition?.projects||[])
const products=computed(()=>data.value?.acquisition?.research_context?.products||[])
const conversationId=computed(()=>String(data.value?.acquisition?.research_context?.conversation_id||''))
const feedbackLabels:Record<string,string>={relevant:'相关客户',nonbuyer:'非买家',incorrect:'信息有误',stale:'信息失效'}
const citations=computed<any[]>(()=>data.value?.evidence||[])
const sources=computed<any[]>(()=>[...new Map(citations.value.filter(e=>e.source_id).map(e=>[e.source_id,e])).values()])
/** 所有读取按当前路由版本守卫；详情刷新保留草稿，切客户清空。 */
async function load(reset=true){
 const own=++version;controller?.abort();controller=new AbortController();loading.value=true;error.value=''
 if(reset){++routeVersion;saving.value=false;noting.value=false;feedbackBusy.value=false;analysing.value=false;data.value=null;note.value='';feedbackText.value='';analysisNote.value='';analysisToken='';analysisRequest='';analysisError.value='';sourceOpen.value=false;sourceController?.abort();++sourceVersion}
 const previous=data.value
 const scope=String(route.query.conversation_id||'')
 try{const result=await api('/leads/'+route.params.id+(scope?'?'+new URLSearchParams({conversation_id:scope}):''),'GET',undefined,{notify:false,signal:controller.signal});if(own!==version)return;for(const key of ['status','owner','next_followup'])if(reset||form.value[key]===(previous?.[key]||''))form.value[key]=result[key]||'';data.value=result}
 catch(e){if(own===version&&!(e instanceof DOMException&&e.name==='AbortError'))error.value=e instanceof Error?e.message:'客户资料读取失败'}finally{if(own===version)loading.value=false}
}
async function save(){if(mutationBusy.value)return;const own=routeVersion,id=data.value.id;const body:any={};for(const key of ['status','owner','next_followup'])if(form.value[key]!==data.value[key])body[key]=form.value[key]??'';if(!Object.keys(body).length)return;saving.value=true;try{await api('/leads/'+id,'PATCH',body,{notify:false});if(own===routeVersion){await load(false);if(own===routeVersion)ElMessage.success('跟进安排已保存')}}catch(e){if(own===routeVersion)ElMessage.error(e instanceof Error?e.message:'保存失败')}finally{if(own===routeVersion)saving.value=false}}
async function addNote(){if(!note.value.trim()||mutationBusy.value)return;const own=routeVersion,id=data.value.id;noting.value=true;try{await api('/leads/'+id+'/followups','POST',{content:note.value,kind:kind.value},{notify:false});if(own===routeVersion){note.value='';await load(false);if(own===routeVersion)ElMessage.success('沟通记录已保存')}}catch(e){if(own===routeVersion)ElMessage.error(e instanceof Error?e.message:'记录失败')}finally{if(own===routeVersion)noting.value=false}}
async function feedback(){if(mutationBusy.value)return;const own=routeVersion,id=data.value.id;feedbackBusy.value=true;try{await api('/leads/'+id+'/feedback','POST',{content:feedbackText.value,kind:feedbackKind.value},{notify:false});if(own===routeVersion){feedbackText.value='';await load(false);if(own===routeVersion)ElMessage.success('反馈已保存，后续分析会考虑此记录')}}catch(e){if(own===routeVersion)ElMessage.error(e instanceof Error?e.message:'反馈失败')}finally{if(own===routeVersion)feedbackBusy.value=false}}
async function analyze(){if(analysing.value||mutationBusy.value)return;const own=routeVersion,id=data.value.id,conv=conversationId.value;const request=JSON.stringify({id,conv,note:analysisNote.value});if(request!==analysisRequest){analysisToken=crypto.randomUUID();analysisRequest=request}analysing.value=true;analysisError.value='';try{const job=await api('/leads/'+id+'/analysis','POST',{conversation_id:conv,client_token:analysisToken,content:analysisNote.value},{notify:false});if(own===routeVersion)await router.push({path:'/',query:{conversation_id:job.conversation_id}})}catch(e){if(own===routeVersion)analysisError.value=e instanceof Error?e.message:'分析提交失败'}finally{if(own===routeVersion)analysing.value=false}}
async function showSource(id:string){const own=++sourceVersion;sourceController?.abort();sourceController=new AbortController();sourceOpen.value=true;source.value=null;sourceLoading.value=true;sourceError.value='';try{const value=await api('/evidence/'+id,'GET',undefined,{notify:false,signal:sourceController.signal});if(own===sourceVersion)source.value=value}catch(e){if(own===sourceVersion&&!(e instanceof DOMException&&e.name==='AbortError'))sourceError.value=e instanceof Error?e.message:'原文读取失败'}finally{if(own===sourceVersion)sourceLoading.value=false}}
watch(sourceOpen,value=>{if(!value){++sourceVersion;sourceController?.abort();source.value=null}})
watch(()=>[route.params.id,route.query.conversation_id],()=>void load())
onMounted(()=>void load());onUnmounted(()=>{++version;++routeVersion;++sourceVersion;controller?.abort();sourceController?.abort()})
</script>
<template>
 <div class="page acquisition-detail" v-loading="loading">
  <router-link :to="{path:'/leads',query:{view:'opportunities',...(route.query.conversation_id?{conversation_id:route.query.conversation_id}:{})}}" class="back-link">← 获客线索</router-link>
  <div v-if="error" class="error-state"><p>{{error}}</p><el-button @click="load()">重新读取</el-button></div>
  <template v-if="data">
   <header class="acquisition-detail-heading"><div><p class="acquisition-eyebrow">客户研究与跟进</p><h1>{{data.display_name}}</h1><p>{{[data.city,roles[data.buyer_role],data.industry].filter(Boolean).join(' · ')}}</p></div><div class="acquisition-heading-actions"><span>{{stages[data.status]}}</span><a href="#followup">安排跟进 ↓</a><router-link v-if="data.company_id" :to="'/companies/'+data.company_id">企业档案 ↗</router-link><router-link :to="{path:'/legacy-leads',query:{lead_id:data.id}}">编辑客户资料 ↗</router-link></div></header>
   <div class="acquisition-layout">
    <main class="acquisition-main">
     <section class="acquisition-section"><div class="acquisition-section-heading"><h2>具体需求</h2><span>{{projects.length}} 条公告 · {{data.acquisition.open_count}} 条公开采购</span></div>
      <div v-if="!projects.length" class="acquisition-empty"><p>{{data.facts?.procurement?.value||'尚未取得绑定本客户的采购公告。可继续研究采购需求，也可先核验业务场景。'}}</p></div>
      <article v-for="project in projects" :key="project.source_id" class="acquisition-project"><div class="acquisition-project-top"><span class="opportunity-state">{{project.status}}</span><span v-if="project.published_at">发布 {{project.published_at}}</span></div><h3>{{project.name?.value||project.title||'采购公告'}}</h3>
       <dl class="acquisition-project-fields"><div><dt>实际采购人</dt><dd>{{project.buyer||'待核验'}}</dd></div><div><dt>项目编号</dt><dd>{{project.number?.value||'未取得'}}</dd></div><div><dt>响应 / 投标截止</dt><dd>{{project.deadline||'期限待核验'}}</dd></div><div v-for="amount in project.amounts" :key="amount.label"><dt>{{amount.label}}</dt><dd>{{amount.value}}</dd></div></dl>
       <div v-if="project.requirements" class="acquisition-requirement"><strong>采购需求原文</strong><p>{{project.requirements.value}}</p></div><p v-else class="acquisition-muted">详细需求未取得，不能确认技术适配。</p>
       <details class="acquisition-disclosure"><summary>项目原文与核验依据</summary><blockquote>{{project.quote}}</blockquote><p>{{project.buyer_quote}}</p><p>{{project.deadline_quote}}</p><p v-if="project.source_truncated">归档正文部分截断，未读内容待核验。</p></details>
       <div class="acquisition-source-line"><a v-if="project.url" :href="project.url" target="_blank" rel="noopener noreferrer">查看原公告 ↗</a><button v-if="project.has_body" @click="showSource(project.source_id)">查看归档全文</button><span>采集 {{project.captured_at||'时间未记录'}}</span></div>
      </article>
      <p class="acquisition-muted">金额按公告原始口径展示，预算与限价不是成交额；公告状态不代表已确认订单。</p>
     </section>
     <section class="acquisition-section" id="analysis"><div class="acquisition-section-heading"><h2>产品匹配与行动建议</h2><el-button :loading="analysing" :disabled="!products.length||!conversationId||mutationBusy" @click="analyze">{{data.analysis?'重新分析':'AI 匹配分析'}}</el-button></div>
      <div v-if="products.length" class="analysis-product-context"><strong>本次产品资料</strong><p v-for="(product,index) in products" :key="index">{{product.name}}<template v-if="product.specifications"> · {{product.specifications}}</template></p><el-input v-model="analysisNote" type="textarea" :rows="2" maxlength="2000" placeholder="补充本次评估重点，例如部署方式、行业案例或交付边界（仅作用户资料）" aria-label="分析重点"/></div><p v-else class="acquisition-muted">请先在工作台介绍产品或上传资料，形成产品画像。</p>
      <p v-if="analysisError" class="acquisition-error">{{analysisError}}</p><LeadAnalysis :analysis="data.analysis"/>
     </section>
     <section class="acquisition-section"><div class="acquisition-section-heading"><h2>完整客户资料与来源</h2><span>{{data.contact_summary.site_count}} 个网站 · {{data.contact_summary.source_count}} 个页面</span></div>
      <div class="acquisition-facts"><div v-for="(fact,field) in data.facts" :key="field"><strong>{{factLabels[field]||field}}</strong><details v-if="field==='procurement'" class="acquisition-disclosure"><summary>查看完整采购资料</summary><FactValue :fact="fact"/></details><FactValue v-else :fact="fact" :phone="field==='phone'" :email="field==='email'" :website="field==='website'" :wechat="field==='wechat'"/></div></div>
      <details class="acquisition-disclosure"><summary>逐字段原文证据 · {{citations.length}} 项</summary><article v-for="(citation,index) in citations" :key="index" class="acquisition-citation"><strong>{{factLabels[citation.field]||citation.field}}</strong><blockquote>{{citation.quote||citation.snippet}}</blockquote><a v-if="citation.url" :href="citation.url" target="_blank" rel="noopener noreferrer">{{citation.title||citation.url}} ↗</a></article></details>
      <div class="acquisition-source-list"><div v-for="item in sources" :key="item.source_id"><a :href="item.url" target="_blank" rel="noopener noreferrer">{{item.title||item.url}} ↗</a><button @click="showSource(item.source_id)">归档原文</button></div></div>
     </section>
    </main>
    <aside class="acquisition-side">
     <section class="acquisition-section" id="followup"><h2>跟进安排</h2><el-form :disabled="mutationBusy" label-position="top"><el-form-item label="跟进状态"><el-select v-model="form.status" aria-label="跟进状态"><el-option v-for="(label,key) in stages" :key="key" :label="label" :value="key"/></el-select></el-form-item><el-form-item label="负责人"><el-input v-model="form.owner" maxlength="100" placeholder="分配销售负责人"/></el-form-item><el-form-item label="下次跟进"><el-date-picker v-model="form.next_followup" type="datetime" value-format="YYYY-MM-DD HH:mm:ss" placeholder="安排时间" clearable/></el-form-item></el-form><el-button type="primary" :loading="saving" :disabled="noting||feedbackBusy" @click="save">保存跟进安排</el-button></section>
     <section class="acquisition-section"><h2>公开联系入口</h2><div v-for="field in ['phone','email','website','wechat','contact_name','contact_position','address']" :key="field" class="acquisition-contact"><template v-if="data.facts[field]?.value"><strong>{{factLabels[field]}}</strong><FactValue :fact="data.facts[field]" :phone="field==='phone'" :email="field==='email'" :website="field==='website'" :wechat="field==='wechat'"/></template></div><p class="acquisition-muted">{{data.contact_summary.status}} · {{data.contact_summary.purpose}}</p><p v-if="data.contact_summary.phone_incomplete" class="acquisition-muted">原文未提供区号，不补号拨打。</p><p v-if="data.contact_summary.phone_status==='invalid'" class="acquisition-muted">号码格式待核验。</p></section>
     <section class="acquisition-section"><h2>待核资料</h2><ul><li v-for="gap in data.acquisition.gaps" :key="gap">{{gap}}</li></ul><router-link v-if="conversationId" :to="{path:'/',query:{conversation_id:conversationId}}">在工作台继续研究 ↗</router-link></section>
     <section class="acquisition-section"><h2>沟通记录</h2><el-select v-model="kind" :disabled="mutationBusy" aria-label="沟通方式"><el-option label="备注" value="note"/><el-option label="电话" value="phone"/><el-option label="邮件" value="email"/><el-option label="拜访" value="visit"/></el-select><el-input v-model="note" :disabled="mutationBusy" type="textarea" :rows="4" maxlength="5000" placeholder="记录实际沟通、需求变化和下一步" aria-label="沟通记录"/><el-button :loading="noting" :disabled="!note.trim()||saving||feedbackBusy" @click="addNote">保存沟通记录</el-button><p v-if="!data.followups?.length" class="acquisition-muted">尚无沟通记录。</p><article v-for="item in data.followups" :key="item.id" class="acquisition-followup"><small>{{item.created_at}}</small><p>{{item.content}}</p></article></section>
     <section class="acquisition-section"><h2>纠错与反馈</h2><el-select v-model="feedbackKind" :disabled="mutationBusy" aria-label="反馈类型"><el-option v-for="(label,key) in feedbackLabels" :key="key" :label="label" :value="key"/></el-select><el-input v-model="feedbackText" :disabled="mutationBusy" type="textarea" :rows="2" maxlength="2000" placeholder="说明需要核验的信息或不适配原因" aria-label="反馈说明"/><el-button :loading="feedbackBusy" :disabled="saving||noting" @click="feedback">保存反馈</el-button><details v-if="data.feedback?.length" class="acquisition-disclosure"><summary>已有反馈 · {{data.feedback.length}}</summary><p v-for="item in data.feedback" :key="item.id">{{feedbackLabels[item.kind]}} · {{item.content}}</p></details></section>
    </aside>
   </div>
  </template>
  <el-drawer v-model="sourceOpen" title="来源归档原文" size="min(760px, 100%)"><div v-loading="sourceLoading"><p v-if="sourceError" class="acquisition-error">{{sourceError}}</p><template v-if="source"><a :href="source.url" target="_blank" rel="noopener noreferrer">{{source.title||source.url}} ↗</a><pre class="source-body">{{source.body}}</pre></template></div></el-drawer>
 </div>
</template>
