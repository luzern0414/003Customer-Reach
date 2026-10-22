<script setup lang="ts">
import {ref,watch,onMounted,onUnmounted} from 'vue'
import {useRoute,useRouter} from 'vue-router'
import {Search,Refresh} from '@element-plus/icons-vue'
import EnterpriseCard from '../components/EnterpriseCard.vue'
import OpportunityCard from '../components/OpportunityCard.vue'
import {api,stages} from '../api'
const route=useRoute(),router=useRouter(),query=ref(''),kind=ref(''),status=ref(''),scope=ref(String(route.query.conversation_id||''))
const view=ref(route.query.view==='companies'?'companies':'opportunities'),rows=ref<any[]>([]),total=ref(0),page=ref(1),loading=ref(false),error=ref(''),conversations=ref<any[]>([])
const counts=ref<Record<string,number|null>>({opportunities:null,companies:null})
let controller:AbortController|undefined,version=0,debounce:ReturnType<typeof setTimeout>|undefined,conversationController=new AbortController()
/** 取消旧页请求并守卫全部投影；某一视图失败不填入另一类数据。 */
async function load(){
 const own=++version;controller?.abort();controller=new AbortController();loading.value=true;error.value=''
 const requested=view.value,common={q:query.value,conversation_id:scope.value,page:String(page.value),page_size:'12'}
 try{
  const data=await api((requested==='companies'?'/companies?':'/leads?')+new URLSearchParams({...common,...(requested==='companies'?{entity_kind:kind.value}:{status:status.value})}),'GET',undefined,{notify:false,signal:controller.signal});if(own!==version)return
  rows.value=data.items;total.value=data.total;counts.value[requested]=data.total
  const alternate=requested==='companies'?'opportunities':'companies'
  try{const other=await api((alternate==='companies'?'/companies?':'/leads?')+new URLSearchParams({q:query.value,conversation_id:scope.value,page:'1',page_size:'1'}),'GET',undefined,{notify:false,signal:controller.signal});if(own===version)counts.value[alternate]=other.total}catch{/* 次视图计数失败不隐藏已读结果 */}
 }catch(e){if(own===version&&!(e instanceof DOMException&&e.name==='AbortError'))error.value=e instanceof Error?e.message:'加载失败，请重试'}finally{if(own===version)loading.value=false}
}
function reset(){rows.value=[];total.value=0;page.value=1;void load()}
watch([kind,status,scope],()=>{page.value=1;void load()})
watch(view,()=>{reset();void router.replace({path:'/leads',query:{...route.query,view:view.value}})})
watch(query,()=>{clearTimeout(debounce);debounce=setTimeout(()=>{page.value=1;void load()},250)})
watch(()=>route.query.conversation_id,value=>{scope.value=String(value||'')})
watch(()=>route.query.view,value=>{if(value==='companies'||value==='opportunities')view.value=value})
onMounted(async()=>{void load();try{conversations.value=await api('/conversations','GET',undefined,{notify:false,signal:conversationController.signal})}catch{/* 保留独立结果读取 */}})
onUnmounted(()=>{++version;controller?.abort();conversationController.abort();clearTimeout(debounce)})
</script>
<template>
 <div class="query-page page acquisition-results">
  <div class="acquisition-page-heading"><div><h1>查询结果</h1><p>从公开需求到产品匹配，再到客户跟进。</p></div><router-link to="/legacy-leads">管理客户与导出 ↗</router-link></div>
  <div class="acquisition-view-tabs" role="tablist" aria-label="结果类型"><button v-for="item in [{id:'opportunities',label:'获客线索'},{id:'companies',label:'企业档案'}]" :key="item.id" role="tab" :aria-selected="view===item.id" :class="{active:view===item.id}" @click="view=item.id">{{item.label}}<span>{{counts[item.id]??'—'}}</span></button></div>
  <div class="query-toolbar"><el-input v-model="query" :prefix-icon="Search" :placeholder="view==='companies'?'搜索企业名称':'搜索客户名称'" clearable aria-label="搜索名称"/><el-select v-if="view==='companies'" v-model="kind" placeholder="全部类型" aria-label="企业类型"><el-option label="全部类型" value=""/><el-option label="企业" value="legal"/><el-option label="品牌" value="brand"/><el-option label="待确认" value="unknown"/></el-select><el-select v-else v-model="status" placeholder="全部跟进状态" aria-label="跟进状态"><el-option label="全部跟进状态" value=""/><el-option v-for="(label,key) in stages" :key="key" :label="label" :value="key"/></el-select><el-select v-model="scope" placeholder="全部对话" aria-label="按对话筛选" filterable><el-option label="全部对话" value=""/><el-option v-for="conversation in conversations" :key="conversation.id" :label="conversation.title" :value="conversation.id"/></el-select><el-button :icon="Refresh" :loading="loading" aria-label="刷新结果" @click="load"/></div>
  <p class="result-count muted">{{total}} {{view==='companies'?'家企业档案':'条客户线索'}}<template v-if="view==='opportunities'"> · 采购状态按当前时间核验，线索不代表已确认订单</template></p>
  <div v-if="error" class="error-state"><p>{{error}}</p><el-button @click="load">重新读取</el-button></div>
  <div v-else-if="loading&&!rows.length" class="card-grid"><el-skeleton v-for="i in 3" :key="i" :rows="7" animated/></div>
  <div v-else-if="rows.length" class="card-grid" :data-testid="view==='companies'?'enterprise-card-grid':'opportunity-card-grid'"><template v-if="view==='companies'"><EnterpriseCard v-for="company in rows" :key="company.id" :company="company" :conversation-id="scope"/></template><template v-else><OpportunityCard v-for="lead in rows" :key="lead.id" :lead="lead" :conversation-id="scope"/></template></div>
  <div v-else class="empty-state"><h2>{{view==='companies'?'还没有企业档案':'还没有获客线索'}}</h2><p>{{view==='companies'?'在工作台输入企业名称，研究采购与上下游。':'在工作台介绍产品和目标市场，检索有具体需求的潜在客户。'}}</p><el-button @click="router.push('/')">去工作台</el-button></div>
  <el-pagination v-if="total>12" v-model:current-page="page" :total="total" :page-size="12" layout="prev,pager,next" @current-change="load"/>
 </div>
</template>
