<script setup lang="ts">
import {ref,onMounted,onUnmounted,watch} from 'vue'
import {useRoute} from 'vue-router'
import {ElMessage,ElMessageBox} from 'element-plus'
import {Plus,Download,Search,ArrowRight,Refresh,More} from '@element-plus/icons-vue'
import {api,stages,factLabels,roles} from '../api'
import FactValue from '../components/FactValue.vue'
import ProcurementSignals from '../components/ProcurementSignals.vue'

const rows=ref<any[]>([]),total=ref(0),stats=ref<Record<string,number>>({}),page=ref(1),q=ref(''),status=ref(''),city=ref(''),role=ref('')
const route=useRoute()
const loading=ref(false),selection=ref<any[]>([]),batchStage=ref(''),drawer=ref(false),detail=ref<any>(null),form=ref<any>({}),note=ref(''),kind=ref('note'),saving=ref(false)
const source=ref<any>(null),sourceVisible=ref(false),activeTab=ref('profile'),feedbackType=ref('relevant'),feedbackText=ref('')
const fields=['display_name','city','industry','owner','phone','email','wechat','website','address','contact_name','contact_position']
const labels:Record<string,string>={display_name:'客户名称',city:'城市',industry:'行业',owner:'销售负责人',phone:'业务电话',email:'邮箱',wechat:'公开业务微信',website:'联系网站',address:'地址',contact_name:'客户联系人',contact_position:'联系人职位'}
const feedbackLabels:Record<string,string>={relevant:'相关客户',nonbuyer:'非买家',incorrect:'信息有误',stale:'信息失效'}
const appliedQuery=ref(query())
let listToken=0,detailToken=0,sourceToken=0
function query(){return new URLSearchParams({q:q.value,status:status.value,city:city.value,buyer_role:role.value,page:String(page.value),page_size:'20'}).toString()}
async function load(){const token=++listToken,requested=query();loading.value=true;try{const r=await api('/leads?'+requested);if(token!==listToken)return;rows.value=r.items;total.value=r.total;stats.value=r.stats;appliedQuery.value=requested}finally{if(token===listToken)loading.value=false}}
async function filter(){page.value=1;await load()}
async function open(id?:string){const token=++detailToken;const value=id?await api('/leads/'+id):null;if(token!==detailToken)return;activeTab.value='profile';detail.value=value;form.value={display_name:'',city:'',industry:'',owner:'',phone:'',email:'',address:'',status:'new',buyer_role:'unknown',next_followup:'',tags:[],...(value||{})};for(const f of ['phone','email','wechat','address','website','contact_name','contact_position'])form.value[f]=value?.facts?.[f]?.value||'';note.value='';feedbackText.value='';drawer.value=true}
/** 仅发送变更字段，保护未修改公开事实的引用及核验状态；表单失败保持原值可重试。 */
async function save(){if(!form.value.display_name?.trim()){ElMessage.warning('填写客户名称');return}const token=detailToken;saving.value=true;try{const body:any={};for(const f of [...fields,'status','buyer_role','next_followup','tags']){const old=['phone','email','wechat','address','website','contact_name','contact_position'].includes(f)?detail.value?.facts?.[f]?.value||'':detail.value?.[f];if(!detail.value||JSON.stringify(old)!==JSON.stringify(form.value[f]))body[f]=form.value[f]??''}const r=await api('/leads'+(detail.value?'/'+detail.value.id:''),detail.value?'PATCH':'POST',body);ElMessage.success('已保存');if(token===detailToken)await open(r.id);await load()}finally{saving.value=false}}
async function addNote(){if(!note.value.trim())return;const id=detail.value.id,token=detailToken;await api('/leads/'+id+'/followups','POST',{content:note.value,kind:kind.value});const value=await api('/leads/'+id);if(token===detailToken&&detail.value?.id===id){detail.value=value;note.value=''}ElMessage.success('已记录')}
async function archive(row:any){await ElMessageBox.confirm('归档此客户？','归档',{confirmButtonText:'归档'});await api('/leads/'+row.id,'DELETE');drawer.value=false;await load()}
async function batch(){if(!batchStage.value||!selection.value.length)return;for(const r of selection.value)await api('/leads/'+r.id,'PATCH',{status:batchStage.value});ElMessage.success('已更新');await load()}
async function sample(){await ElMessageBox.confirm('导入历史研究资料？','历史资料');const r=await api('/leads/import-sample','POST');ElMessage.success('新增 '+r.imported+' 条');await load()}
async function evidence(id:string){const token=++sourceToken;const value=await api('/evidence/'+id);if(token!==sourceToken)return;source.value=value;sourceVisible.value=true}
async function feedback(){const id=detail.value.id,token=detailToken;const prior=new Set<string>(detail.value.tags||[]);await api('/leads/'+id+'/feedback','POST',{kind:feedbackType.value,content:feedbackText.value});const value=await api('/leads/'+id);if(token===detailToken&&detail.value?.id===id){detail.value=value;form.value.tags=[...new Set<string>([...(form.value.tags||[]),...(value.tags||[]).filter((tag:string)=>!prior.has(tag))])];feedbackText.value=''}await load();ElMessage.success('反馈已记住')}
watch(()=>route.query.lead_id,id=>{if(id)void open(String(id))})
onMounted(()=>{void load();if(route.query.lead_id)void open(String(route.query.lead_id))})
onUnmounted(()=>{++listToken;++detailToken;++sourceToken})
</script>

<template>
  <div class="page leads-page">
    <div class="page-title-row"><div class="row"><h1>客户线索</h1><span class="count-pill">{{total}}</span></div><div class="row"><el-dropdown><el-button text :icon="More" aria-label="更多操作"/><template #dropdown><el-dropdown-menu><el-dropdown-item @click="sample">导入历史资料</el-dropdown-item></el-dropdown-menu></template></el-dropdown><a :href="'/api/leads/export?'+appliedQuery"><el-button :icon="Download">导出</el-button></a><el-button type="primary" :icon="Plus" @click="open()">新建客户</el-button></div></div>
    <div class="view-tabs"><button :class="{active:!status}" @click="status='';filter()">全部</button><button v-for="(label,key) in stages" :key="key" :class="{active:status===key}" @click="status=String(key);filter()">{{label}}<small>{{stats[key]||0}}</small></button></div>
    <section class="lead-table-surface">
      <div class="table-tools"><el-input v-model="q" placeholder="搜索客户" :prefix-icon="Search" clearable @keyup.enter="filter" @clear="filter"/><div class="row"><el-input v-model="city" placeholder="城市" clearable @keyup.enter="filter" @clear="filter"/><el-select v-model="role" placeholder="买家角色" clearable @change="filter"><el-option v-for="(label,key) in roles" :key="key" :label="label" :value="key"/></el-select><el-button text :icon="Refresh" title="刷新" aria-label="刷新" @click="load"/></div></div>
      <div v-if="selection.length" class="selection-bar"><span>{{selection.length}} 已选</span><el-select v-model="batchStage" placeholder="状态"><el-option v-for="(label,key) in stages" :key="key" :label="label" :value="key"/></el-select><el-button size="small" @click="batch">更新</el-button></div>
      <el-table :data="rows" v-loading="loading" @selection-change="selection=$event" @row-dblclick="open($event.id)">
        <el-table-column type="selection" width="40"/>
        <el-table-column label="客户" min-width="250"><template #default="{row}"><button class="lead-name" @click="open(row.id)">{{row.display_name}}</button><div v-if="row.tags?.length" class="tiny-tags"><span v-for="tag in row.tags" :key="tag">{{tag}}</span></div></template></el-table-column>
        <el-table-column prop="city" label="城市" width="90"/>
        <el-table-column label="角色" width="110"><template #default="{row}"><span :class="['role-label',row.buyer_role||'unknown']">{{roles[row.buyer_role]||'待核实'}}</span></template></el-table-column>
        <el-table-column label="状态" width="110"><template #default="{row}"><span :class="['crm-status',row.status]"><i></i>{{stages[row.status]||row.status}}</span></template></el-table-column>
        <el-table-column label="优先级" width="78"><template #default="{row}"><span class="priority-value">{{row.score}}</span></template></el-table-column>
        <el-table-column label="联系方式" min-width="220"><template #default="{row}"><FactValue :fact="row.facts?.phone" phone/><small v-if="row.contact_summary?.phone_incomplete" class="lead-contact-email">短号待核验</small><small v-else-if="row.contact_summary?.phone_status==='invalid'" class="lead-contact-email">号码格式待核验</small><div v-if="row.facts?.email?.value" class="lead-contact-email"><FactValue :fact="row.facts.email" email/></div><FactValue v-if="row.facts?.wechat?.value" :fact="row.facts.wechat" wechat/><small v-if="!row.contact_summary?.usable_fields?.length" class="lead-contact-email">联系信息待补</small></template></el-table-column>
        <el-table-column label="负责人" width="110"><template #default="{row}">{{row.owner||'—'}}</template></el-table-column>
        <el-table-column label="下次跟进" width="152"><template #default="{row}">{{row.next_followup?.slice(5,16)||'—'}}</template></el-table-column>
        <el-table-column label="" width="50" fixed="right"><template #default="{row}"><el-button text :icon="ArrowRight" title="客户详情" aria-label="客户详情" @click="open(row.id)"/></template></el-table-column>
        <template #empty><el-empty description="暂无客户" :image-size="75"/></template>
      </el-table>
      <div class="table-pagination"><el-pagination v-model:current-page="page" :total="total" :page-size="20" layout="prev, pager, next" @current-change="load"/></div>
    </section>
    <el-drawer v-model="drawer" :title="detail?.display_name||'新建客户'" size="660px">
      <div v-if="detail" class="lead-contact-actions"><a v-if="detail.contact_summary?.phone_href" :href="detail.contact_summary.phone_href">拨打电话</a><a v-if="detail.contact_summary?.usable_fields?.includes('email')" :href="'mailto:'+detail.facts.email.value">邮件</a><FactValue v-if="detail.facts?.website?.value" :fact="detail.facts.website" website/><FactValue v-if="detail.facts?.wechat?.value" :fact="detail.facts.wechat" wechat/><span v-if="detail.contact_summary?.phone_status==='invalid'">号码格式待核验</span><span>{{detail.contact_summary?.purpose}}</span></div>
      <el-tabs v-model="activeTab">
        <el-tab-pane name="profile" label="资料"><el-form label-position="top" class="lead-form"><el-form-item v-for="field in fields" :key="field" :label="labels[field]"><el-input v-model="form[field]"/><FactValue v-if="detail&&(detail.facts?.[field]?.effective_date||detail.facts?.[field]?.scope||detail.facts?.[field]?.alternatives?.length||['disputed','inactive'].includes(detail.facts?.[field]?.verification))" :fact="detail.facts[field]" :phone="field==='phone'" :email="field==='email'" :website="field==='website'" :wechat="field==='wechat'"/></el-form-item><el-form-item label="状态"><el-select v-model="form.status"><el-option v-for="(label,key) in stages" :key="key" :label="label" :value="key"/></el-select></el-form-item><el-form-item label="买家角色"><el-select v-model="form.buyer_role"><el-option v-for="(label,key) in roles" :key="key" :label="label" :value="key"/></el-select></el-form-item><el-form-item label="下次跟进"><el-date-picker v-model="form.next_followup" type="datetime" value-format="YYYY-MM-DD HH:mm:ss" placeholder="选择时间" clearable/></el-form-item><el-form-item label="标签"><el-select v-model="form.tags" multiple filterable allow-create default-first-option/></el-form-item></el-form><div class="row"><el-button type="primary" :loading="saving" @click="save">保存</el-button><el-button v-if="detail" text type="danger" @click="archive(detail)">归档</el-button></div><template v-if="detail"><div v-if="detail.match_reason" class="match-summary">{{detail.match_reason}}</div><div v-for="field in ['credit_code','registry_status','categories','brands','headcount','revenue','procurement','supplier','purchase_price','frequency']" :key="field" class="fact-row"><span>{{factLabels[field]}}</span><FactValue :fact="detail.facts?.[field]"/></div><ProcurementSignals :signals="detail.procurement_signals"/></template></el-tab-pane>
        <el-tab-pane name="sources" label="证据" :disabled="!detail"><div v-for="(item,i) in detail?.evidence" :key="i" class="evidence-card"><div class="row"><span class="field-label">{{factLabels[item.field]||item.field}}</span><small>{{item.captured_at}}</small></div><blockquote>{{item.quote||item.snippet||'—'}}</blockquote><a :href="item.url" target="_blank" rel="noopener noreferrer">{{item.title||item.url}} ↗</a><el-button v-if="item.source_id&&!detail.tags?.includes('历史研究样本')" text size="small" @click="evidence(item.source_id)">原文</el-button></div><el-empty v-if="!detail?.evidence?.length" description="暂无证据"/></el-tab-pane>
        <el-tab-pane name="followups" label="跟进" :disabled="!detail"><el-select v-model="kind"><el-option label="备注" value="note"/><el-option label="电话" value="phone"/><el-option label="拜访" value="visit"/><el-option label="邮件" value="email"/></el-select><el-input v-model="note" type="textarea" :rows="4" placeholder="记录沟通与下一步…" class="note-input"/><el-button type="primary" @click="addNote">记录</el-button><el-timeline class="followups"><el-timeline-item v-for="item in detail?.followups" :key="item.id" :timestamp="item.created_at"><p class="pre-text">{{item.content}}</p></el-timeline-item></el-timeline></el-tab-pane>
        <el-tab-pane name="feedback" label="反馈" :disabled="!detail"><el-radio-group v-model="feedbackType"><el-radio-button v-for="(label,key) in feedbackLabels" :key="key" :value="key">{{label}}</el-radio-button></el-radio-group><el-input v-model="feedbackText" type="textarea" :rows="4" placeholder="补充原因…" class="note-input"/><el-button type="primary" @click="feedback">提交反馈</el-button><div v-for="item in detail?.feedback" :key="item.id" class="feedback-row"><strong>{{feedbackLabels[item.kind]}}</strong><small>{{item.created_at}}</small><p>{{item.content}}</p></div></el-tab-pane>
      </el-tabs>
    </el-drawer>
    <el-dialog v-model="sourceVisible" title="来源原文" width="80%"><a :href="source?.url" target="_blank" rel="noopener noreferrer">{{source?.url}}</a><pre class="source-body">{{source?.body}}</pre></el-dialog>
  </div>
</template>
