<script setup lang="ts">
import {ref,computed,watch,onUnmounted} from 'vue'
import {useRoute,useRouter} from 'vue-router'
import {User,ShoppingCart,Share,Download,Document,ArrowRight,Phone,Message,TrendCharts,OfficeBuilding,MagicStick,UploadFilled,CircleCheck,Close} from '@element-plus/icons-vue'
import {api} from '../api'
import {valueText,metricText,monogram,periodLabel} from '../company'
import {brief,factStatus,relationSeries,barPercent,moneyText,projectBudget,procurementOverview} from '../companyOverview'
import type {RelationKind} from '../companyOverview'
import {configureMarkdown} from '../markdown'
import {sourceCards,sourceUrl,sourceHost,relationLabels} from '../companySources'
import CompanyAvatar from '../components/CompanyAvatar.vue'
import TenderIntel from '../components/TenderIntel.vue'
const route=useRoute(),router=useRouter(),data=ref<any>(null),loading=ref(false),error=ref(''),researching=ref(false)
const sourceDrawer=ref(false),sourceContent=ref<any>(null),sourceLoading=ref(false),sourceError=ref(''),sourceLimit=ref(8),archiveContent=ref<any>(null)
const expandedProjects=ref(false),expandedRelations=ref(false),moreRules=ref(false)
const matchDialog=ref(false),productFiles=ref<any[]>([]),uploadInput=ref<HTMLInputElement>(),uploading=ref(false),matching=ref(false),matchError=ref(''),productNote=ref('')
let controller:AbortController|undefined,version=0,sourceVersion=0,uploadVersion=0,matchConversation='',matchToken='',researchToken='',counterpartyToken=''
const header=computed(()=>data.value?.header),facts=computed<any[]>(()=>data.value?.facts||[]),sources=computed<any[]>(()=>data.value?.sources||[])
const first=(field:string,pattern?:RegExp)=>facts.value.find(r=>r.field===field&&r.status==='verified'&&(!pattern||pattern.test(r.label)))
const business=computed(()=>header.value?.facts.business||first('business')),products=computed(()=>header.value?.facts.products||first('products')),address=computed(()=>first('address',/办公地址/)||first('address'))
const productTags=computed(()=>String(products.value?.raw_value||'').split(/[、，,；;]/).filter(Boolean).slice(0,3))
const revenues=computed(()=>facts.value.filter(r=>r.field==='revenue'&&r.status==='verified'))
const annualRevenue=computed(()=>revenues.value.find(r=>r.period_kind==='annual')),halfRevenue=computed(()=>revenues.value.find(r=>r.period_kind==='half_year'))
const contacts=computed(()=>facts.value.filter(r=>['phone','email','website'].includes(r.field)&&!/传真|证券|董秘|监督/.test(r.label+' '+r.note)).sort((a,b)=>Number(b.field==='phone')-Number(a.field==='phone')))
const overview=computed(()=>procurementOverview(data.value)),suppliers=computed(()=>relationSeries(data.value,'supplier')),customers=computed(()=>relationSeries(data.value,'customer'))
const kinds:RelationKind[]=['supplier','customer'],series=(kind:RelationKind)=>kind==='supplier'?suppliers.value:customers.value
/** 年报关系全部没有金额且有招投标对手方时，优先展示招投标合作次数（信息量更高）。 */
const preferTender=(kind:RelationKind)=>tenderRows(kind).length>0&&series(kind).rows.every((r:any)=>r.amount==null)
const concentration=computed(()=>suppliers.value.share),ringLabel=computed(()=>suppliers.value.rows.length===5?'前五占比':'披露占比')
const relationTitle=computed(()=>(!suppliers.value.rows.length||preferTender('supplier'))&&(!customers.value.rows.length||preferTender('customer'))?(tenderRows('supplier').length||tenderRows('customer').length?'按公开招投标合作次数':'暂无具名关系'):suppliers.value.period===customers.value.period?(suppliers.value.period?suppliers.value.period+' 年报披露':'年报披露'):'按各自最新报告期展示')
const subsidiaries=computed(()=>(data.value?.relations||[]).filter((r:any)=>r.relation_type==='subsidiary'))
const extraRelations=computed(()=>(data.value?.relations||[]).filter((r:any)=>!['supplier','customer','subsidiary'].includes(r.relation_type)))
const applications=computed(()=>(data.value?.projects||[]).filter((p:any)=>p.record_kind==='brand_application'))
const projects=computed(()=>overview.value.purchases.length?overview.value.purchases:overview.value.plans)
const registration=computed<Record<string,string>>(()=>Object.fromEntries((data.value?.registration?.fields||[]).map((f:any)=>[f.label,f.value])))
const tenderSummary=computed(()=>data.value?.tenders?.summary||{})
const tenderRows=(kind:RelationKind):any[]=>(data.value?.tenders?.relations?.[kind]||[]) as any[]
const tenderMax=(kind:RelationKind)=>Math.max(1,...tenderRows(kind).map((r:any)=>r.count||0))
const regEntries=computed(()=>[['法定代表人',registration.value['法定代表人']],['注册资本',registration.value['注册资本']],['成立日期',registration.value['成立日期']],['经营状态',registration.value['经营状态']]].filter(([,v])=>v) as [string,string][])
const basicEntries=computed(()=>[header.value?.facts.industry,business.value,products.value,address.value,halfRevenue.value].filter(Boolean))
const analysisParser=configureMarkdown({})
const analysisHtml=computed(()=>data.value?.purchase_analysis?.content?analysisParser.render(data.value.purchase_analysis.content):'')
const metrics=computed(()=>[
 !header.value?.facts.headcount&&registration.value['注册资本']?{key:'capital',label:'注册资本',value:registration.value['注册资本'],icon:User,note:registration.value['成立日期']?'成立于 '+registration.value['成立日期']:'工商登记',entries:[],badge:''}:
 {key:'headcount',label:'员工规模',value:metricText(header.value?.facts.headcount),icon:User,note:header.value?.facts.headcount?[header.value.facts.headcount.as_of,header.value.facts.headcount.scope].filter(Boolean).join(' · '):'未披露',entries:[header.value?.facts.headcount].filter(Boolean),badge:''},
 !annualRevenue.value&&registration.value['经营状态']?{key:'status',label:'经营状态',value:registration.value['经营状态'],icon:TrendCharts,note:registration.value['企业类型']||'工商登记',entries:[],badge:''}:
 {key:'revenue',label:annualRevenue.value?periodLabel(annualRevenue.value):'年度营收',value:metricText(annualRevenue.value),icon:TrendCharts,note:annualRevenue.value?[annualRevenue.value.report_period,annualRevenue.value.scope].filter(Boolean).join(' · '):'未披露',entries:[annualRevenue.value].filter(Boolean),badge:''},
 overview.value.purchases.length?{key:'procurement',label:'公开采购样本',value:overview.value.purchases.length+' 个项目',icon:ShoppingCart,note:(data.value?.procurement_summary.notices??0)+' 条公告',entries:overview.value.purchases,badge:''}
 :(suppliers.value.total==null&&(tenderRows('customer').length||tenderRows('supplier').length))?{key:'tender-relations',label:'客户 / 供应商',value:tenderRows('customer').length+' / '+tenderRows('supplier').length+' 家',icon:Share,note:'招投标合作统计',entries:[],badge:''}
 :{key:'suppliers',label:suppliers.value.rows.length===5?'前五供应商采购额':'已披露供应商采购额',value:moneyText(suppliers.value.total,suppliers.value.unit,suppliers.value.currency),icon:ShoppingCart,note:suppliers.value.period?suppliers.value.period+' · '+(concentration.value!==null?'年度采购占比 '+concentration.value.toFixed(2)+'%':'占比未披露'):'未披露',entries:suppliers.value.rows,badge:''},
 overview.value.equipmentPlan?{key:'plan',label:'设备购置概算',value:projectBudget(overview.value.equipmentPlan).text,icon:OfficeBuilding,note:'概算，不代表实际支出',badge:'建设计划',entries:[overview.value.equipmentPlan]}
 :tenderSummary.value.purchases||tenderSummary.value.wins?{key:'tender',label:'招投标记录',value:(tenderSummary.value.purchases||0)+' 采购 · '+(tenderSummary.value.wins||0)+' 中标',icon:ShoppingCart,note:tenderSummary.value.latest_purchase?'最近采购 '+tenderSummary.value.latest_purchase:'客户 '+(tenderSummary.value.customers||0)+' 家',entries:[],badge:''}
 :{key:'coverage',label:'公开资料',value:sources.value.length+' 份来源',icon:Document,note:facts.value.length+' 项资料',entries:[],badge:''}
])
/** 无参数；读取当前企业并取消旧请求，切换时清空浮层和待提交资料，失败保留重试入口。 */
async function load(){
 const own=++version;++sourceVersion;++uploadVersion;sourceDrawer.value=false;sourceContent.value=null;sourceLoading.value=false;sourceError.value='';archiveContent.value=null
 matchDialog.value=false;productFiles.value=[];productNote.value='';matchError.value='';matching.value=false;uploading.value=false;matchConversation='';matchToken=''
 researching.value=false;researchToken='';counterpartyToken='';expandedProjects.value=false;expandedRelations.value=false;moreRules.value=false
 controller?.abort();controller=new AbortController();loading.value=true;error.value='';data.value=null
 try{const result=await api('/companies/'+route.params.id,'GET',undefined,{notify:false,signal:controller.signal});if(own===version)data.value=result}
 catch(e){if(own===version&&!(e instanceof DOMException&&e.name==='AbortError'))error.value=e instanceof Error?e.message:'企业读取失败'}
 finally{if(own===version)loading.value=false}
}
watch(()=>route.params.id,load,{immediate:true});onUnmounted(()=>{++version;++sourceVersion;++uploadVersion;controller?.abort()})
/** entries为当前事实/关系/项目列表，空列表打开全部来源；默认只展示独立证据片段。 */
function showSource(entries:any[]=[],title='资料来源'){
 ++sourceVersion;sourceDrawer.value=true;sourceLoading.value=false;sourceError.value='';archiveContent.value=null;sourceLimit.value=8
 sourceContent.value=entries.length?{title,cards:sourceCards(entries)}:null
}
/** source为本企业已关联文档；只加载该文档的条目摘要，迟到/关闭响应不得覆盖下一次选择。 */
async function showDocument(source:any){
 const own=++sourceVersion;sourceDrawer.value=true;sourceLoading.value=true;sourceError.value='';sourceContent.value=null;archiveContent.value=null;sourceLimit.value=8
 try{const result=await api('/companies/'+header.value.id+'/documents/'+source.id,'GET',undefined,{notify:false});if(own===sourceVersion)sourceContent.value={title:source.title||'来源文档',document:result.source,cards:sourceCards(result.entries.map((r:any)=>({...r,raw_value:r.value,report_period:r.period})))}}
 catch(e){if(own===sourceVersion)sourceError.value=e instanceof Error?e.message:'来源读取失败'}
 finally{if(own===sourceVersion)sourceLoading.value=false}
}
/** ref为已持久片段；显式展开才读取完整摘录，未成功时保留当前条目。 */
async function fullFragment(ref:any){
 const own=++sourceVersion;sourceError.value=''
 try{const result=await api('/source-fragments/'+ref.id,'GET',undefined,{notify:false});if(own===sourceVersion){ref.text=result.text;ref.truncated=false}}
 catch(e){if(own===sourceVersion)sourceError.value=e instanceof Error?e.message:'摘录读取失败'}
}
/** sourceId为当前条目引用的真实ID；全文仅在用户明确点击后读取，关闭后不接收旧结果。 */
async function showArchive(sourceId:string){
 const own=++sourceVersion;sourceLoading.value=true;sourceError.value=''
 try{const result=await api('/evidence/'+sourceId,'GET',undefined,{notify:false});if(own===sourceVersion)archiveContent.value=result}
 catch(e){if(own===sourceVersion)sourceError.value=e instanceof Error?e.message:'归档读取失败'}
 finally{if(own===sourceVersion)sourceLoading.value=false}
}
/** evidenceId为招投标记录的归档证据；打开来源抽屉并直接显示归档全文。 */
function openArchive(evidenceId:string){sourceDrawer.value=true;sourceContent.value=null;showArchive(evidenceId)}
/** 无参数；关闭抽屉废弃全部迟到响应。 */
function closeSource(){++sourceVersion;sourceLoading.value=false;sourceContent.value=null;archiveContent.value=null;sourceError.value=''}
/** 无参数；提交真实企业补查，重复点击锁定，迟到响应不得跳回旧企业。 */
async function research(){if(researching.value||!header.value)return;const own=version,id=header.value.id;researching.value=true;researchToken ||= crypto.randomUUID();try{const job=await api('/companies/'+id+'/research','POST',{client_token:researchToken,conversation_id:route.query.conversation_id||undefined});if(own===version)await router.push({path:'/',query:{conversation_id:job.conversation_id}})}catch{/* 失败保留原token；响应丢失后的重试不能重复创建模型任务。 */}finally{if(own===version)researching.value=false}}
/** 无参数；显式补当前上下游资料，共用受限任务，失败保留幂等token。 */
async function counterparties(){if(researching.value||!header.value)return;const own=version,id=header.value.id;researching.value=true;counterpartyToken ||= crypto.randomUUID();try{const job=await api('/companies/'+id+'/counterparties/research','POST',{client_token:counterpartyToken});if(own===version)await router.push({path:'/',query:{conversation_id:job.conversation_id}})}catch{/* API显示错误，重试保留同一个token。 */}finally{if(own===version)researching.value=false}}
/** 无参数；只进入准备状态，没有资料和确认提交时不执行模型。 */
function openMatch(){matchError.value='';matchDialog.value=true}
/** event为文件输入事件；最多5份10MB资料，解析成功才纳入提交，迟到响应按企业版本隔离。 */
async function uploadProducts(event:Event){
 const input=event.target as HTMLInputElement;if(uploading.value||matching.value)return
 const selected=Array.from(input.files||[]).slice(0,5-productFiles.value.length),own=version,token=++uploadVersion;uploading.value=true;matchError.value='';matchToken=''
 try{for(const file of selected){if(file.size>10*1024*1024)throw new Error('单份资料不能超过 10 MB');const body=new FormData();body.append('file',file);const row=await api('/attachments','POST',body,{notify:false});if(own!==version||token!==uploadVersion)return;productFiles.value.push(row)}}catch(e){if(own===version&&token===uploadVersion)matchError.value=e instanceof Error?e.message:'资料解析失败，请重试'}finally{if(own===version&&token===uploadVersion){uploading.value=false;input.value=''}}
}
/** 无参数；明确企业ID与已解析附件走文档匹配，结果在工作台流式呈现，失败保留资料和幂等token。 */
async function analyzeProducts(){
 if(matching.value||uploading.value||!productFiles.value.length||!header.value)return
 const own=version,id=header.value.id,name=header.value.name,ids=productFiles.value.map(r=>r.id),note=productNote.value.trim()
 matching.value=true;matchError.value='';matchToken ||= crypto.randomUUID()
 try{if(!matchConversation){const conv=await api('/conversations','POST',undefined,{notify:false});if(own!==version)return;matchConversation=conv.id}
 const content='只读取已上传产品资料，不要搜索或寻找其他客户。结合目标企业“'+name+'”已归档资料，分析产品匹配度与购买意向线索。明确匹配方向、依据、供应商准入条件和需要核验的问题；建设计划不代表实际订单，不提供虚构购买概率、预算余量或采购时间。'+(note?'\n我补充的产品说明：'+note:'')
 const job=await api('/conversations/'+matchConversation+'/messages','POST',{content,attachment_ids:ids,client_token:matchToken,company_id:id,query_mode:'company_match'},{notify:false});if(own===version){matchDialog.value=false;await router.push({path:'/',query:{conversation_id:job.conversation_id}})}
 }catch(e){if(own===version)matchError.value=e instanceof Error?e.message:'分析提交失败，请重试'}finally{if(own===version)matching.value=false}
}
/** project为真实项目；返回原公告完整参数或原备注，空值不生成型号。 */
function specifications(project:any){return project.payload.specifications?.map((s:any)=>s.raw||s.parameter).filter(Boolean).join('；')||project.payload.note||'详细规格未披露'}
</script>
<template>
<div class="detail-page company-overview" data-testid="enterprise-detail">
 <router-link :to="{path:'/leads',query:{view:'companies',...(route.query.conversation_id?{conversation_id:route.query.conversation_id}:{})}}" class="back-link">← 返回查询结果</router-link>
 <div v-if="loading" class="detail-loading"><el-skeleton :rows="12" animated/></div>
 <div v-else-if="error" class="error-state"><h2>暂时无法读取企业</h2><p>{{error}}</p><el-button @click="load">重新读取</el-button></div>
 <template v-else-if="data">
 <header class="company-header"><CompanyAvatar :company="header" size="large"/><div class="company-identity"><h1>{{header.name}}</h1><div class="tag-row"><span v-if="header.short_name" class="outline-tag">{{header.short_name}}</span><span v-if="header.facts.stock_code" class="outline-tag">证券代码 {{valueText(header.facts.stock_code.raw_value)}}</span><span v-if="header.view_scope==='group'" class="outline-tag">集团资料</span></div><p class="company-subtitle"><span v-if="header.facts.industry||registration['行业']">{{brief(header.facts.industry?.raw_value||registration['行业'],40)}} · </span><span v-if="registration['注册地址']">{{brief(registration['注册地址'],24)}} · </span><span v-if="header.research_as_of">资料截至 {{header.research_as_of}}</span></p></div><div class="company-actions"><a :href="'/api/companies/'+header.id+'/export'" class="outline-button"><el-icon><Download/></el-icon>导出资料</a><el-button type="primary" :icon="Document" :loading="researching" @click="research">继续研究</el-button></div></header>
 <div class="overview-metrics" data-testid="overview-metrics"><button v-for="metric in metrics" :key="metric.key" class="overview-metric" :data-metric="metric.key" @click="showSource(metric.entries,metric.label)"><span class="metric-icon"><el-icon><component :is="metric.icon"/></el-icon></span><span class="metric-body"><span class="metric-label">{{metric.label}}</span><span class="metric-value">{{metric.value}}<span v-if="metric.badge" class="signal-tag amber">{{metric.badge}}</span></span><span class="metric-note" :title="metric.note">{{metric.note}}</span></span></button></div>
 <div class="overview-layout" data-testid="overview-layout"><div class="overview-main"><div class="overview-top">
 <section class="overview-card overview-basics" data-testid="overview-basics"><div class="overview-card-head"><h2>企业基本信息</h2><button class="source-link" aria-label="查看企业基本信息来源" @click="showSource(basicEntries,'企业基本信息')"><el-icon><Document/></el-icon></button></div><dl class="overview-facts"><div><dt>行业</dt><dd :title="valueText(header.facts.industry?.raw_value||registration['行业'])">{{brief(header.facts.industry?.raw_value||registration['行业'],34)}}</dd></div><div><dt>主营</dt><dd :title="valueText(business?.raw_value)">{{brief(business?.raw_value,44)}}</dd></div><div><dt>产品</dt><dd class="product-tags"><span v-for="tag in productTags" :key="tag" :title="tag">{{brief(tag,12)}}</span><span v-if="!productTags.length" class="muted">未取得</span></dd></div><div><dt>地址</dt><dd :title="valueText(address?.raw_value||registration['注册地址'])">{{brief(address?.raw_value||registration['注册地址'],30)}}</dd></div><div v-for="[label,value] in regEntries" :key="label"><dt>{{label}}</dt><dd :title="value">{{brief(value,30)}}</dd></div><div v-if="halfRevenue"><dt>{{periodLabel(halfRevenue)}}</dt><dd><strong>{{metricText(halfRevenue)}}</strong><small v-if="halfRevenue&&/未经审计/.test(halfRevenue.note)">未经审计</small></dd></div></dl><div class="overview-contacts"><div v-for="fact in contacts.slice(0,2)" :key="fact.id" class="contact-line"><el-icon><component :is="fact.field==='phone'?Phone:fact.field==='email'?Message:Document"/></el-icon><a v-if="fact.contact_href&&fact.status==='verified'" :href="fact.contact_href">{{valueText(fact.raw_value)}}</a><span v-else>{{valueText(fact.raw_value)}}<small v-if="fact.status!=='verified'"> · {{factStatus(fact.status)}}</small></span><button :aria-label="'查看'+fact.label+'来源'" @click="showSource([fact],fact.label)">来源</button></div><p v-if="!contacts.length&&!registration['电话']" class="muted">联系方式未披露</p><div v-if="!contacts.length&&registration['电话']" class="contact-line"><el-icon><Phone/></el-icon><span>{{registration['电话']}}<small> · 工商登记</small></span></div><a v-if="data.registration?.source_url" class="registration-source" :href="sourceUrl(data.registration.source_url)" target="_blank" rel="noopener noreferrer">工商信息来源：{{sourceHost(data.registration.source_url)}} ↗</a></div></section>
 <section class="overview-card overview-procurement" data-testid="overview-procurement"><div class="overview-card-head"><h2>采购信息</h2><button class="source-link" @click="showSource([...overview.rules,...overview.categoryFacts,...overview.purchases],'采购信息')">查看依据 ↗</button></div><div class="procurement-body"><div class="procurement-copy"><div v-if="overview.categories.length" class="product-tags"><span v-for="category in overview.categories.slice(0,3)" :key="category" :title="category">{{brief(category,12)}}</span></div><h3>{{overview.rules.length?'采购方式':'采购概况'}}</h3><ul v-if="overview.rules.length" class="procurement-rules"><li v-for="fact in overview.rules.slice(0,moreRules?overview.rules.length:2)" :key="fact.id"><button :title="valueText(fact.raw_value)" @click="showSource([fact],fact.label)">{{brief(fact.raw_value,64)}}</button></li></ul><div v-else-if="overview.purchases.length" class="procurement-sample"><strong>{{overview.purchases.length}} 个采购项目</strong><p>{{data.procurement_summary.notices}} 条公告<template v-if="data.procurement_summary.quantity_disclosed"> · {{data.procurement_summary.quantity_disclosed}} 个注明数量</template></p></div><div v-else-if="tenderSummary.purchases" class="procurement-sample"><strong>{{tenderSummary.purchases}} 条采购公告</strong><p>最近一条 {{tenderSummary.latest_purchase||'日期未知'}}</p><div v-if="data.tenders.top_items?.length" class="product-tags"><span v-for="item in data.tenders.top_items.slice(0,4)" :key="item.name" :title="item.name">{{brief(item.name,10)}}</span></div></div><p v-else class="muted procurement-empty">暂未找到采购记录。</p></div><figure v-if="concentration!==null" class="concentration-chart" :aria-label="'已披露供应商年度采购占比 '+concentration.toFixed(2)+'%'" data-testid="supplier-concentration"><div class="ring-wrap"><svg viewBox="0 0 120 120" aria-hidden="true"><circle cx="60" cy="60" r="47" class="ring-track"/><circle cx="60" cy="60" r="47" class="ring-value" :stroke-dasharray="(concentration/100*295.31)+' 295.31'" transform="rotate(-90 60 60)"/></svg><div class="ring-label"><strong>{{concentration.toFixed(2)}}%</strong><span>{{ringLabel}}</span></div></div><figcaption><span><i class="legend-dot blue"/>披露 {{concentration.toFixed(2)}}%</span><span><i class="legend-dot pale"/>其余 {{(100-concentration).toFixed(2)}}%</span></figcaption></figure><div v-else class="procurement-evidence"><span class="evidence-icon"><el-icon><ShoppingCart/></el-icon></span><strong>{{overview.purchases.length||tenderSummary.purchases?'有公开采购':'暂无数据'}}</strong><span>{{overview.purchases.length?'见采购项目':tenderSummary.purchases?'见下方招投标':'可继续研究补充'}}</span></div></div><button v-if="overview.plans.length" class="procurement-plan" @click="expandedProjects=!expandedProjects"><el-icon><OfficeBuilding/></el-icon><span><strong>{{brief(overview.equipmentPlan?.title||overview.plans[0].title,26)}}</strong><small>{{overview.plans.length}} 项建设计划 · 概算非实际支出</small></span><span class="signal-tag amber">计划披露</span></button><button v-else-if="overview.purchases.length" class="procurement-plan purchase" @click="expandedProjects=!expandedProjects"><el-icon><Document/></el-icon><span><strong>查看采购项目</strong><small>采购方、数量、规格与进度</small></span><el-icon><ArrowRight/></el-icon></button><footer class="overview-card-foot"><button v-if="overview.rules.length>2" @click="moreRules=!moreRules">{{moreRules?'收起':'更多机制'}}</button></footer></section>
 </div>
 <section class="overview-card overview-relations" data-testid="overview-relations"><div class="overview-card-head"><h2>上下游关系</h2><span class="muted">{{relationTitle}}</span></div><div class="relationship-flow"><template v-for="kind in kinds" :key="kind"><div v-if="kind==='customer'" class="relation-hub"><el-icon class="upstream-arrow"><ArrowRight/></el-icon><span><strong>{{header.short_name||header.name}}</strong><small>{{brief(header.facts.industry?.raw_value||registration['行业'],16)}}</small></span><el-icon class="downstream-arrow"><ArrowRight/></el-icon></div><div :class="['relation-column',kind]" :data-relation-kind="kind"><div class="relation-column-head"><span class="relation-icon"><el-icon><Share/></el-icon></span><h3>{{kind==='supplier'?'上游供应商':'下游客户'}}</h3><small v-if="series(kind).rows.length&&!preferTender(kind)">{{(series(kind).period||'报告期未披露')+' · '+(kind==='supplier'?'采购额':'销售额')}}</small></div><ol v-if="series(kind).rows.length&&!preferTender(kind)" class="relation-bars"><li v-for="row in series(kind).rows.slice(0,5)" :key="row.id"><div class="relation-entry"><router-link :to="row.detail_url" :title="row.counterparty_name+' · '+row.direction">{{row.counterparty_name}}</router-link><small>{{row.reason}}</small></div><span v-if="barPercent(row,series(kind))!==null" class="bar-track" :title="moneyText(row.amount,row.unit,row.currency)"><span :style="{width:barPercent(row,series(kind))+'%'}"/></span><span v-else class="bar-unavailable">无金额</span><span class="bar-amount">{{moneyText(row.amount,row.unit,row.currency)}}</span></li></ol><ol v-else-if="tenderRows(kind).length" class="relation-bars tender-fallback"><li v-for="row in tenderRows(kind).slice(0,5)" :key="row.name"><div class="relation-entry"><span :title="row.name">{{row.name}}</span><small>{{row.basis_labels.join(' · ')}}</small></div><span class="bar-track"><span :style="{width:Math.max(6,row.count/tenderMax(kind)*100)+'%'}"/></span><span class="bar-amount">{{row.count}} 次</span></li></ol><div v-else class="relation-empty"><el-icon><Share/></el-icon><p>暂无{{kind==='supplier'?'供应商':'客户'}}名单</p><button class="source-link" :disabled="researching" @click="research">继续研究 ↗</button></div></div></template></div><footer class="overview-card-foot"><button :disabled="researching" @click="counterparties">补充上下游企业资料 ↗</button><button @click="expandedRelations=!expandedRelations">{{expandedRelations?'收起完整关系':'查看完整关系'}} ↗</button></footer></section>
 </div>
 <aside class="overview-card overview-ai" data-testid="overview-ai"><div class="overview-card-head"><h2><el-icon><MagicStick/></el-icon>AI 购买意向</h2><span class="signal-tag violet">{{data.purchase_analysis ? 'AI 推理' : '待专项分析'}}</span></div><h3 class="ai-status">{{data.purchase_analysis ? '已完成产品匹配' : overview.insights.length ? '已披露需求方向' : tenderSummary.purchases ? '近期采购方向' : '暂无需求资料'}}</h3><p class="ai-description">{{data.purchase_analysis ? '基于上传产品与归档资料 · ' + data.purchase_analysis.created_at : '上传产品资料后分析匹配度'}}</p><div v-if="analysisHtml" class="ai-rendered" data-testid="purchase-analysis" v-html="analysisHtml"/><router-link v-if="data.purchase_analysis" class="analysis-full-link" :to="{path:'/',query:{conversation_id:data.purchase_analysis.conversation_id}}">查看完整分析与过程 ↗</router-link><div v-if="!analysisHtml&&overview.insights.length" class="purchase-insights"><article v-for="(insight,index) in overview.insights" :key="insight.title" :class="['purchase-insight',insight.tone]"><span class="insight-number">{{index+1}}</span><div><div class="insight-heading"><button class="insight-title" :aria-label="'查看' + insight.title + '依据'" @click="showSource(insight.entries,insight.title)">{{insight.title}}</button><span :class="['signal-tag',insight.tone]">{{insight.label}}</span></div><p>{{insight.statement}}</p></div></article></div><div v-else-if="!analysisHtml&&tenderSummary.purchases" class="tender-signals"><div v-if="data.tenders.top_items?.length" class="tender-items"><span v-for="item in data.tenders.top_items.slice(0,6)" :key="item.name" class="item-chip">{{item.name}}</span></div><ol class="tender-list"><li v-for="record in data.tenders.purchases.slice(0,4)" :key="record.id"><div class="tender-line"><span :title="record.title">{{record.title}}</span><time>{{record.published_at}}</time></div></li></ol></div><div v-else-if="!analysisHtml" class="ai-empty"><el-icon><Document/></el-icon></div><div class="ai-action"><el-button type="primary" :icon="UploadFilled" @click="openMatch">上传产品，分析匹配度<el-icon><ArrowRight/></el-icon></el-button></div><footer class="overview-card-foot"><button @click="showSource([...overview.rules,...overview.plans,...overview.purchases],'购买分析依据')">查看依据 ↗</button></footer></aside></div>
 <TenderIntel v-if="data.tenders" :tenders="data.tenders" @archive="openArchive"/>
 <section v-if="projects.length" class="overview-records"><button class="records-toggle" :aria-expanded="expandedProjects" @click="expandedProjects=!expandedProjects"><span><el-icon><Document/></el-icon>{{overview.purchases.length?'采购需求与公告':'建设计划详情'}} <small>· {{projects.length}} 项</small></span><span>{{expandedProjects?'收起':'展开'}} {{expandedProjects?'−':'+'}}</span></button><div v-if="expandedProjects" class="project-records"><article v-for="project in projects" :key="project.id"><div class="record-heading"><h3>{{project.payload.product||project.title}}</h3></div><dl class="overview-facts"><div><dt>采购方</dt><dd>{{project.buyer_name}}</dd></div><div><dt>阶段</dt><dd>{{project.temporal_status}}</dd></div><div><dt>{{project.record_kind==='plan'?'概算':'预算'}}</dt><dd>{{projectBudget(project).text}}<small v-if="project.record_kind==='plan'||project.payload.budget?.tax">{{project.record_kind==='plan'?'非实际支出':project.payload.budget.tax}}</small></dd></div><div><dt>数量</dt><dd>{{project.payload.quantity!=null?project.payload.quantity+' '+(project.payload.unit||''):'未注明'}}</dd></div></dl><p>{{specifications(project)}}</p><footer><small>{{project.published_at||project.payload.timing||'日期未披露'}}</small><button class="source-link" @click="showSource([project],project.title)">查看原文 ↗</button></footer></article></div></section>
 <section v-if="expandedRelations" class="overview-records complete-relations"><h2>全部关系</h2><div v-for="row in data.relations" :key="row.id" class="complete-relation"><router-link :to="row.detail_url">{{row.counterparty_name}}</router-link><small>{{relationLabels[row.relation_type]||'关联企业'}} · {{row.report_period||'报告期未知'}}</small><span>{{moneyText(row.amount,row.unit,row.currency)}}<small v-if="row.share!=null"> · {{row.share}}%</small></span><button class="source-link" @click="showSource([row],row.counterparty_name||row.title)">依据</button></div><p v-if="!data.relations.length" class="muted">暂无关系记录。</p></section>
 <details v-if="overview.purchases.length&&overview.plans.length" class="overview-records additional-records"><summary>其他建设计划 · {{overview.plans.length}} 项</summary><div v-for="project in overview.plans" :key="project.id" class="related-line"><span>{{project.title}}</span><span>{{projectBudget(project).text}}</span><button @click="showSource([project],project.title)">来源</button></div></details>
 <details v-if="subsidiaries.length||extraRelations.length||applications.length" class="overview-records additional-records"><summary>关联企业与其他线索</summary><div v-for="row in [...subsidiaries,...extraRelations]" :key="row.id" class="related-line"><router-link v-if="row.counterparty_id" :to="'/companies/'+row.counterparty_id">{{row.counterparty_name}}</router-link><span v-else>{{row.counterparty_name}}</span><span class="muted">{{row.payload.ownership_field||relationLabels[row.relation_type]||'关联企业'}}</span><button @click="showSource([row],row.counterparty_name||row.title)">依据</button></div><div v-for="row in applications" :key="row.id" class="related-line"><span>{{row.title}}</span><button @click="showSource([row],row.counterparty_name||row.title)">来源</button></div></details>
 <details v-if="facts.length" class="overview-records additional-records"><summary>全部企业事实 · {{facts.length}} 项</summary><div v-for="fact in facts" :key="fact.id" class="related-line"><span :title="valueText(fact.raw_value)">{{fact.label}}：{{brief(String(valueText(fact.raw_value))+(fact.raw_unit?' '+fact.raw_unit:''),60)}}</span><span class="muted">{{fact.report_period||fact.as_of||factStatus(fact.status)}}</span><button @click="showSource([fact],fact.label)">原文</button></div></details>
 <footer class="overview-page-foot"><span>{{sources.length}} 份可追溯来源</span><button class="source-link" @click="showSource()">查看全部来源 ↗</button></footer>
 </template>
 <el-drawer v-model="sourceDrawer" title="资料来源" size="min(720px,100vw)" class="entry-source-drawer" @close="closeSource">
  <p v-if="sourceError" role="alert" class="source-error">{{sourceError}}</p>
  <el-skeleton v-if="sourceLoading" :rows="6" animated/>
  <template v-else-if="archiveContent">
   <button class="source-link" @click="++sourceVersion;archiveContent=null">← 返回条目</button>
   <h2>{{archiveContent.title}}</h2>
   <a v-if="sourceUrl(archiveContent.url)" :href="sourceUrl(archiveContent.url)" target="_blank" rel="noopener noreferrer">打开原网站 ↗</a>
   <pre class="source-body">{{archiveContent.body}}</pre>
  </template>
  <template v-else-if="sourceContent">
   <div v-if="sourceContent.document||sourceContent.cards.length>1" class="source-preview-heading"><span class="source-eyebrow">资料依据</span><h2>{{sourceContent.title}}</h2>
    <template v-if="sourceContent.document"><p class="muted">{{sourceContent.document.published_at||''}}</p><a v-if="sourceUrl(sourceContent.document.url)" class="source-origin" :href="sourceUrl(sourceContent.document.url)" target="_blank" rel="noopener noreferrer">打开原网站 ↗</a><button class="source-link" @click="showArchive(sourceContent.document.id)">查看全文</button></template>
   </div>
   <article v-for="card in sourceContent.cards.slice(0,sourceLimit)" :key="card.id" class="entry-source-card" :data-entry-id="card.id">
    <header><span class="signal-tag blue">{{card.label}}</span><h3>{{card.title}}</h3></header>
    <dl v-if="card.fields.length" class="entry-source-fields"><div v-for="field in card.fields" :key="field.label"><dt>{{field.label}}</dt><dd>{{field.value}}</dd></div></dl>
    <section v-for="ref in card.refs" :key="ref.source_id+':'+ref.id" class="entry-source-excerpt">
     <div class="excerpt-heading"><strong>{{ref.quote_kind==='continuous'?'原文摘录':'摘录'}}</strong><span v-if="ref.page_start">第 {{ref.page_start}}{{ref.page_end!==ref.page_start?'–'+ref.page_end:''}} 页</span></div>
     <p class="source-quote">{{ref.text}}</p>
     <button v-if="ref.truncated" class="source-link" @click="fullFragment(ref)">展开完整摘录</button>
     <footer><span>{{ref.title}}</span><a v-if="sourceUrl(ref.page_url||ref.url)" :href="sourceUrl(ref.page_url||ref.url)" target="_blank" rel="noopener noreferrer">打开原网站 ↗</a><button class="source-link" @click="showArchive(ref.source_id)">查看全文</button></footer>
    </section>
    <p v-if="!card.refs.length" class="muted">暂无摘录</p>
    <div v-if="!card.refs.length" class="entry-source-links"><template v-for="id in card.sourceIds" :key="id"><a v-if="sourceUrl(sources.find(s=>s.id===id)?.url)" :href="sourceUrl(sources.find(s=>s.id===id)?.url)" target="_blank" rel="noopener noreferrer">{{sources.find(s=>s.id===id)?.title||'打开原网站'}} ↗</a></template></div>
   </article>
   <button v-if="sourceContent.cards.length>sourceLimit" class="source-more" @click="sourceLimit+=8">再显示 {{Math.min(8,sourceContent.cards.length-sourceLimit)}} 项（剩余 {{sourceContent.cards.length-sourceLimit}} 项）</button>
   <button class="source-link source-back" @click="showSource()">全部来源 ↗</button>
  </template>
  <template v-else>
   <p class="source-list-count">{{sources.length}} 份来源</p>
   <div v-for="source in sources" :key="source.id" class="source-document-item">
    <div><h3>{{source.title||'来源文档'}}</h3><p>{{source.published_at||''}}<span v-if="sourceUrl(source.url)"> · {{sourceHost(source.url)}}</span></p></div>
    <div class="source-document-actions"><button class="source-link" @click="showDocument(source)">相关资料</button><a v-if="sourceUrl(source.url)" :href="sourceUrl(source.url)" target="_blank" rel="noopener noreferrer">原网站 ↗</a></div>
   </div><p v-if="!sources.length" class="muted">暂无来源</p>
  </template>
 </el-drawer>
 <el-dialog v-model="matchDialog" title="分析产品与企业的匹配度" width="600px" class="product-match-dialog" :close-on-click-modal="!matching&&!uploading" :close-on-press-escape="!matching&&!uploading" :show-close="!matching&&!uploading"><p class="match-target"><el-icon><OfficeBuilding/></el-icon>{{header?.name}}</p><p class="muted">上传目录或规格资料，分析与该企业的匹配度。</p><input ref="uploadInput" class="visually-hidden" type="file" multiple accept=".pdf,.doc,.docx,.xls,.xlsx,.txt,.csv" aria-label="上传产品资料" :disabled="uploading||matching" @change="uploadProducts"><button class="match-upload" :disabled="uploading||matching||productFiles.length>=5" @click="uploadInput?.click()"><el-icon><UploadFilled/></el-icon><strong>{{uploading?'正在解析资料…':'选择产品资料'}}</strong><span>PDF、Word、Excel 或文本 · 每份 10 MB · 最多 5 份</span></button><ul v-if="productFiles.length" class="match-file-list"><li v-for="file in productFiles" :key="file.id"><el-icon><CircleCheck/></el-icon><span>{{file.filename}}<small v-if="file.truncated||file.parse?.warnings?.length">{{file.truncated?'部分解析':''}} {{file.parse?.warnings?.join('；')}}</small></span><el-button text :icon="Close" :aria-label="'移除 '+file.filename" :disabled="uploading||matching" @click="productFiles=productFiles.filter(row=>row.id!==file.id);matchToken=''"/></li></ul><el-input v-model="productNote" type="textarea" :rows="3" :maxlength="2000" :disabled="matching" placeholder="补充产品型号、优势或希望确认的问题（可选）" aria-label="补充产品说明" @input="matchToken=''"/><p v-if="matchError" role="alert" class="match-error">{{matchError}}</p><template #footer><el-button :disabled="matching||uploading" @click="matchDialog=false">取消</el-button><el-button type="primary" :loading="matching" :disabled="!productFiles.length||uploading" @click="analyzeProducts">开始 AI 分析</el-button></template></el-dialog>
</div>
</template>
