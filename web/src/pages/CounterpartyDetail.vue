<script setup lang="ts">
import {computed,ref,watch,onUnmounted} from 'vue'
import {useRoute,useRouter} from 'vue-router'
import {Document,ArrowRight,OfficeBuilding,Link} from '@element-plus/icons-vue'
import {api} from '../api'
import {valueText} from '../company'
import {moneyText} from '../companyOverview'
import {sourceUrl} from '../companySources'
const route=useRoute(),router=useRouter(),data=ref<any>(null),loading=ref(false),error=ref(''),researching=ref(false)
let version=0,controller:AbortController|undefined,token=''
const relation=computed(()=>data.value?.relation),profile=computed(()=>data.value?.counterparty)
const fields=computed(()=>profile.value?.facts||{})
const ownFields=computed(()=>[['business','主营'],['products','产品'],['industry','行业'],['address','地址']].filter(([key])=>fields.value[key]).map(([key,label])=>({key,label,value:fields.value[key].raw_value})))
const relationLinks=computed(()=>relation.value?.evidence_refs||[])
const sources=computed(()=>profile.value?.sources||[])
/** 无参数；按两个持久ID读取独立关系，切换立即取消旧请求，错误保留重试。 */
async function load(){const own=++version;controller?.abort();controller=new AbortController();loading.value=true;error.value='';data.value=null;researching.value=false;token='';try{const result=await api('/companies/'+route.params.id+'/relations/'+route.params.relationId,'GET',undefined,{notify:false,signal:controller.signal});if(own===version)data.value=result}catch(e){if(own===version&&!(e instanceof DOMException&&e.name==='AbortError'))error.value=e instanceof Error?e.message:'资料读取失败'}finally{if(own===version)loading.value=false}}
/** 无参数；显式补该对手方资料，原token重试，迟到响应不改变当前企业。 */
async function research(){if(researching.value)return;const own=version;researching.value=true;token ||= crypto.randomUUID();try{const job=await api('/companies/'+route.params.id+'/relations/'+route.params.relationId+'/research','POST',{client_token:token},{notify:false});if(own===version)await router.push({path:'/',query:{conversation_id:job.conversation_id}})}catch(e){if(own===version)error.value=e instanceof Error?e.message:'补齐提交失败'}finally{if(own===version)researching.value=false}}
watch(()=>[route.params.id,route.params.relationId],load,{immediate:true});onUnmounted(()=>{++version;controller?.abort()})
</script>
<template>
 <div class="detail-page company-overview counterparty-page">
  <router-link class="back-link" :to="'/companies/'+route.params.id">← 返回企业详情</router-link>
  <el-skeleton v-if="loading" :rows="10" animated/>
  <div v-else-if="!data" class="error-state"><h2>暂时无法加载</h2><p>{{error}}</p><el-button @click="load">重新读取</el-button></div>
  <template v-else>
   <header class="counterparty-header"><div><span class="source-eyebrow">{{relation.relation_label}}<template v-if="relation.report_period"> · {{relation.report_period}}</template></span><h1>{{profile?.name||relation.counterparty_name}}</h1><p v-if="profile&&profile.name!==relation.counterparty_name" class="muted">报告中的名称：{{relation.counterparty_name}}</p></div><el-button type="primary" :icon="Document" :loading="researching" @click="research">{{profile?'更新企业资料':'查询企业资料'}}</el-button></header>
   <p v-if="error" class="source-error" role="alert">{{error}}</p>
   <div class="counterparty-grid">
    <section class="overview-card relationship-detail"><div class="overview-card-head"><h2>与{{data.company.short_name||data.company.name}}的关系</h2></div>
     <div class="counterparty-direction"><span>{{relation.from_name}}</span><el-icon><ArrowRight/></el-icon><span>{{relation.to_name}}</span></div>
     <h3>{{relation.direction}}</h3><p class="muted">{{relation.reason}}</p>
     <dl class="entry-source-fields"><div><dt>{{relation.amount_label}}</dt><dd>{{moneyText(relation.amount,relation.unit,relation.currency)}}</dd></div><div><dt>占比</dt><dd>{{relation.share!=null?relation.share+'%':'未披露'}}</dd></div><div><dt>报告期</dt><dd>{{relation.report_period||'未披露'}}</dd></div><div v-if="relation.trade_product"><dt>交易产品</dt><dd>{{relation.trade_product}}</dd></div></dl>
     <section v-for="ref in relationLinks" :key="ref.binding_id" class="entry-source-excerpt"><div class="excerpt-heading"><strong>原文依据</strong><span>{{ref.title}}</span></div><p class="source-quote">{{ref.text}}</p><a v-if="sourceUrl(ref.page_url||ref.url)" :href="sourceUrl(ref.page_url||ref.url)" target="_blank" rel="noopener noreferrer">查看原文 ↗</a></section>
    </section>
    <section class="overview-card counterparty-profile"><div class="overview-card-head"><h2><el-icon><OfficeBuilding/></el-icon>企业资料</h2><span v-if="!profile" class="signal-tag amber">待查询</span></div>
     <template v-if="profile"><dl class="overview-facts"><div v-for="field in ownFields" :key="field.key"><dt>{{field.label}}</dt><dd>{{valueText(field.value)}}</dd></div></dl><a v-if="sourceUrl(fields.website?.raw_value)" class="counterparty-website" :href="sourceUrl(fields.website.raw_value)" target="_blank" rel="noopener noreferrer"><el-icon><Link/></el-icon>访问企业官网 ↗</a><p v-if="profile.research_as_of" class="muted counterpart-date">更新于 {{profile.research_as_of}}</p>
      <div class="counterparty-sources"><h3>资料来源</h3><a v-for="source in sources.filter((s:any)=>sourceUrl(s.url))" :key="source.id" :href="sourceUrl(source.url)" target="_blank" rel="noopener noreferrer">{{source.title||'企业资料'}} ↗</a></div><router-link :to="profile.profile_url" class="source-link">查看企业详情 ↗</router-link>
     </template>
     <div v-else class="counterparty-empty"><el-icon><OfficeBuilding/></el-icon><h3>{{relation.counterparty_name}}</h3><p>{{relation.identity_status==='composite'?'报告中为多家企业合并披露，无法单独查询':'尚未查询这家企业的资料'}}</p><el-button v-if="relation.identity_status!=='composite'" :loading="researching" @click="research">查询企业资料</el-button></div>
    </section>
   </div>
  </template>
 </div>
</template>
