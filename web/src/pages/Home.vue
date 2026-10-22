<script setup lang="ts">
import {ref,computed,onMounted,onUnmounted,nextTick,watch} from 'vue'
import MarkdownRender from 'markstream-vue'
import ToolActivity from '../components/ToolActivity.vue'
import ArtifactPanel from '../components/ArtifactPanel.vue'
import {useRoute} from 'vue-router'
import 'markstream-vue/index.css'
import {Plus,Paperclip,Top,Refresh,Clock,Document,CopyDocument,Menu,Files} from '@element-plus/icons-vue'
import {ElMessage} from 'element-plus'
import {api} from '../api'
import {displayMarkdown,configureMarkdown} from '../markdown'

const conversations=ref<any[]>([]),current=ref<any>(null),job=ref<any>(null),draft=ref(''),attachments=ref<any[]>([])
const uploading=ref(false),sending=ref(false),changing=ref(false),acting=ref(false),history=ref(false),panel=ref(window.innerWidth>=1280)
const messageRoot=ref<HTMLElement>(),fileInput=ref<HTMLInputElement>(),composer=ref<HTMLTextAreaElement>(),clockTick=ref(0)
const preview=ref<any>(null),previewLoading=ref(false),resultTab=ref('results'),results=ref<any[]>([])
const route=useRoute(),companyResults=ref<any[]>([])
const traceVisible=ref(false),traceLoading=ref(false),traceData=ref<any>(null),selectedResearchId=ref('')
const identityNames=ref<Record<string,string>>({}),identityContexts=ref<Record<string,string>>({})
const identityTokens=new Map<string,string>()
let wideViewport=window.innerWidth>=1280
/** 无参数；跨越分屏断点时收起浮层，避免桌面结果栏遮挡手机确认按钮。 */
function onViewportResize(){const wide=window.innerWidth>=1280;if(wide!==wideViewport){wideViewport=wide;panel.value=wide}resizeComposer()}
const researchSummary=computed(()=>(selectedResearchId.value?current.value?.jobs?.find((item:any)=>item.id===selectedResearchId.value):job.value)?.research_summary||{})
watch(()=>route.query.conversation_id,id=>{if(id&&String(id)!==current.value?.id)void open(String(id))})
const panelFiles=computed(()=>[...new Map([...(current.value?.attachments||[]),...attachments.value].map(x=>[x.id,x])).values()])
const messageJobs=computed(()=>new Map((current.value?.jobs||[]).filter((x:any)=>x.reply_message_id).map((x:any)=>[x.reply_message_id,x])))
const workspaceTitle=computed(()=>{const title=current.value?.title;if(title&&!['新的获客对话','新研究','新对话'].includes(title))return title;const company=companyResults.value.length===1?companyResults.value[0]:null;return company?(company.short_name||company.name.slice(0,10))+'研究':'新研究'})
let stream:EventSource|null=null,epoch=0,timer:ReturnType<typeof setInterval>,seenAt=performance.now(),baseElapsed=0,previewToken=0,uploadToken=0,resultSignature='',resultToken=0,traceToken=0,researchToken=0
const recoveryTimers=new Set<ReturnType<typeof setTimeout>>()
/** run为恢复操作，own为会话版本；仅当前会话重试，卸载时统一清理计时器。 */
function retryLater(run:()=>void,own:number){const handle=setTimeout(()=>{recoveryTimers.delete(handle);if(own===epoch)run()},1500);recoveryTimers.add(handle)}
const activeStates=['queued','running','cancelling']
const busy=computed(()=>sending.value||changing.value||acting.value||activeStates.includes(job.value?.status))
const stageLabels:Record<string,string>={intent:'模型识别需求',quick:'回应消息',context:'读取记忆',profile:'分析产品',plan:'规划渠道',decide:'选择渠道',search:'检索资料',read:'读取来源',extract:'核验客户',save:'保存客户',gap:'补查缺口',answer:'生成回答',learn:'更新知识',company_context:'检索本地资料',company_resolve:'确认查询主体',company_enrich:'核验工商资料',company_tenders:'检索采购与上下游',company_counterparties:'补齐上下游资料',company_plan:'规划企业查询',company_collect:'本地与网络检索',company_clean:'清洗并沉淀资料',company_extract:'整理结构化资料',company_save:'保存查询结果',company_gap:'分析缺口并补查',company_answer:'整理研究结论'}
const elapsed=computed(()=>{clockTick.value;return (job.value?.metrics?.clock_is_partial?'≥':'')+formatTime(baseElapsed+(activeStates.includes(job.value?.status)?performance.now()-seenAt:0))})
function formatTime(ms:number){const value=Math.max(0,ms||0);return value<10?'<0.01 秒':value<1000?`${(value/1000).toFixed(2)} 秒`:value<60000?`${(value/1000).toFixed(1)} 秒`:`${Math.floor(value/60000)} 分 ${Math.floor(value%60000/1000)} 秒`}
/** error为后端保留的失败码，可空；返回简短可读文案，原始诊断仍留后端日志。 */
function failureText(error=''){if(/预算|额度|budget/i.test(error))return '本轮额度已用完';if(/429|RateLimit/i.test(error))return '服务暂时受限';if(/401|Authentication/i.test(error))return '模型连接配置无效';if(/Timeout|超时/i.test(error))return '响应超时';if(/Connect|Network/i.test(error))return '连接暂时失败';return '回答未完成'}
function scroll(){const root=messageRoot.value;if(root)root.scrollTop=root.scrollHeight}
function closeStream(){stream?.close();stream=null}
async function reloadList(own=epoch){const rows=await api('/conversations');if(own===epoch)conversations.value=rows}
/** value为当前任务投影；refresh默认真表示重新读产物，过程事件可为false避免每步重复全量查询。 */
function updateJob(value:any,refresh=true){const previous=(current.value?.jobs||[]).find((x:any)=>x.id===value.id);const row={...previous,...value,tools:value.tools||previous?.tools||[]};job.value=row;if(current.value){const index=current.value.jobs.findIndex((x:any)=>x.id===row.id);if(index<0)current.value.jobs.unshift(row);else current.value.jobs[index]=row}if(refresh)void loadResults(row,epoch)}
/** own为会话版本；仅汇总当前对话关联lead_ids，普通追问不清掉已保存结果，不混入全站CRM。 */
async function loadResults(_row:any,own:number,attempt=0){
  const conv=current.value;if(!conv)return
  const ids=[...new Set<string>(conv.jobs.flatMap((x:any)=>x.lead_ids||[]))]
  const versions=conv.jobs.map((x:any)=>[x.id,x.status,x.stage,x.updated_at,x.finished_at,(x.tools||[]).map((tool:any)=>tool.operation_id+':'+tool.status).join(',')].join(':')).join('|')
  const signature=conv.id+':'+ids.join(',')+':'+versions
  if(signature===resultSignature)return
  const token=++resultToken,previous=new Map(results.value.map(x=>[x.id,x]))
  const [companyData,researchData,...loaded]=await Promise.allSettled([api('/companies?conversation_id='+conv.id+'&visibility=primary','GET',undefined,{notify:false}),
    _row?.id?api('/jobs/'+_row.id+'/research','GET',undefined,{notify:false}):Promise.resolve({}),...ids.map(id=>api('/leads/'+id,'GET',undefined,{notify:false}))])
  if(own!==epoch||token!==resultToken)return
  if(companyData.status==='fulfilled')companyResults.value=companyData.value.items
  // 空历史会话的两个可选ID都为undefined，不能据此向null任务写入研究摘要。
  if(researchData.status==='fulfilled'&&job.value&&_row?.id&&job.value.id===_row.id)job.value.research_summary=researchData.value
  // 临时失败保留已显示的客户，只有整批成功才锁定签名，避免一次故障永久隐藏结果。
  results.value=loaded.flatMap((x,index)=>x.status==='fulfilled'?[x.value]:x.reason?.status!==404&&previous.has(ids[index])?[previous.get(ids[index])]:[])
  if(companyData.status==='fulfilled'&&researchData.status==='fulfilled'&&loaded.every(x=>x.status==='fulfilled'||x.reason?.status===404))resultSignature=signature
  else if(attempt<2)retryLater(()=>void loadResults(_row,own,attempt+1),own)
  else ElMessage.warning('部分结果暂时无法读取，请重新打开对话')
}
/** id为持久助手消息ID；历史轮次读其任务计时，活动轮次实时递增。 */
function messageTime(id:number){const item:any=messageJobs.value.get(id);if(!item||item.elapsed_ms==null||item.graph_version==='v1'&&!item.started_at)return '—';return item.id===job.value?.id?elapsed.value:(item.metrics?.clock_is_partial?'≥':'')+formatTime(item.elapsed_ms)}
function messageJob(id:number):any{return messageJobs.value.get(id)}
/** item为对应回答的真实任务；只有最新待确认轮次提供操作，历史卡片保持只读。 */
function identityPending(item:any){return item?.id===job.value?.id&&item?.status==='needs_input'&&['needs_confirmation','insufficient'].includes(item?.metrics?.company_resolution?.status)}
/** item为原任务、candidateId可空；明确选择或补充后续接原ID，重试复用token，切会话丢弃迟到响应。 */
async function confirmIdentity(item:any,candidateId=''){
  if(!identityPending(item)||busy.value)return
  const own=epoch,id=item.id,conversationId=current.value.id,resolution=item.metrics.company_resolution
  const name=(identityNames.value[id]||'').trim(),context=(identityContexts.value[id]||'').trim()
  if(!candidateId&&!name&&!context){ElMessage.warning('请补充企业全称或地区');return}
  const request={conversation_id:conversationId,resolution_revision:resolution.revision,candidate_id:candidateId||null,name:candidateId?'':name,context:candidateId?'':context}
  const key=id+':'+JSON.stringify(request);if(!identityTokens.has(key))identityTokens.set(key,crypto.randomUUID())
  acting.value=true
  try{
    const row=await api('/jobs/'+id+'/identity-confirmation','POST',{...request,client_token:identityTokens.get(key)},{notify:false})
    if(own!==epoch||job.value?.id!==id)return
    updateJob(row);baseElapsed=row.elapsed_ms||0;seenAt=performance.now();subscribe(id,own)
    const conv=await api('/conversations/'+conversationId,'GET',undefined,{notify:false})
    if(own===epoch&&job.value?.id===id){current.value.messages=conv.messages;await nextTick();scroll()}
  }catch(e){if(own===epoch&&job.value?.id===id)ElMessage.error(e instanceof Error?e.message:'确认提交失败')}
  finally{if(own===epoch)acting.value=false}
}
function fileMeta(id:string){return current.value?.attachments?.find((x:any)=>x.id===id)}
/** id为真实附件ID；只打开提取原文，不由模型生成预览，切换会话后忽略迟到响应。 */
async function showFile(id:string){const own=epoch,token=++previewToken;panel.value=true;resultTab.value='files';preview.value=null;previewLoading.value=true;try{const row=await api('/attachments/'+id,'GET',undefined,{notify:false});if(own===epoch&&token===previewToken)preview.value=row}catch(error){if(own===epoch&&token===previewToken)ElMessage.error(error instanceof Error?error.message:'无法读取文件')}finally{if(own===epoch&&token===previewToken)previewLoading.value=false}}
/** id为后端数据集ID；展示清洗原文/最终覆盖，未核验提议不冒充客户事实，沿用预览版本守卫。 */
async function showDataset(id:string){const own=epoch,token=++previewToken;panel.value=true;preview.value=null;previewLoading.value=true;try{const row=await api('/research-datasets/'+id,'GET',undefined,{notify:false});if(own===epoch&&token===previewToken)preview.value={...row,kind:'research_dataset'}}catch(error){if(own===epoch&&token===previewToken)ElMessage.error(error instanceof Error?error.message:'无法读取清洗资料')}finally{if(own===epoch&&token===previewToken)previewLoading.value=false}}
/** id为该轮真实任务ID；只在用户点击时读取LangSmith元信息，切会话后丢弃迟到响应。 */
async function showTrace(id:string){const own=epoch,token=++traceToken;traceVisible.value=true;traceLoading.value=true;traceData.value=null;try{const row=await api('/jobs/'+id+'/trace','GET',undefined,{notify:false});if(own===epoch&&token===traceToken)traceData.value=row}catch{if(own===epoch&&token===traceToken)ElMessage.error('暂时无法读取运行链路')}finally{if(own===epoch&&token===traceToken)traceLoading.value=false}}
/** id为该轮持久任务ID；打开其清洗资料，历史轮次不切换正在执行的当前任务，迟到响应不覆盖新选择。 */
async function showResearch(id:string){const own=epoch,token=++researchToken;selectedResearchId.value=id;panel.value=true;preview.value=null;++previewToken;try{const data=await api('/jobs/'+id+'/research','GET',undefined,{notify:false});if(own===epoch&&token===researchToken){const row=current.value?.jobs.find((item:any)=>item.id===id);if(row)row.research_summary=data}}catch{if(own===epoch&&token===researchToken)ElMessage.error('暂时无法读取该轮清洗资料')}}
/** 无参数；原生textarea随正文长短伸缩，超过220px后才允许内部滚动。 */
function resizeComposer(){const element=composer.value;if(!element)return;element.style.height='auto';element.style.height=Math.min(220,Math.max(44,element.scrollHeight))+'px';element.style.overflowY=element.scrollHeight>220?'auto':'hidden'}
/** event为键盘事件；中文组合输入不发送，Shift+Enter保留换行，普通Enter提交。 */
function onKeydown(event:KeyboardEvent){if(event.key==='Enter'&&!event.shiftKey&&!event.ctrlKey&&!event.altKey&&!event.metaKey&&!event.isComposing){event.preventDefault();void send()}}
watch(draft,()=>nextTick(resizeComposer));watch(panel,()=>nextTick(resizeComposer))
/** payload来自真实工具事件；operation_id用于合并重放，不能凭前端虚构工具步骤。 */
function toolEvent(payload:any){if(!job.value||!payload.operation_id)return;const tools=[...(job.value.tools||[])];const index=tools.findIndex((x:any)=>x.operation_id===payload.operation_id);if(index<0)tools.push(payload);else tools[index]={...tools[index],...payload};updateJob({...job.value,tools},['persist_company','persist_lead'].includes(payload.tool)&&payload.status==='completed')}

/** id为真实会话ID；epoch防止迟到响应污染新会话，切换时关闭旧SSE。 */
async function open(id:string){
  const own=++epoch;closeStream();traceVisible.value=false;++traceToken;selectedResearchId.value='';++researchToken;changing.value=true;acting.value=false;draft.value='';uploading.value=false;++uploadToken;if(fileInput.value)fileInput.value.value=''
  try{
    const row=await api('/conversations/'+id);if(own!==epoch)return
    current.value=row;job.value=row.jobs?.find((x:any)=>activeStates.includes(x.status))||row.jobs?.[0]||null;attachments.value=[];history.value=false;preview.value=null;previewLoading.value=false;++previewToken;results.value=[];companyResults.value=[];resultSignature=''
    if(job.value){baseElapsed=job.value.elapsed_ms||0;seenAt=performance.now();const detail=await api('/jobs/'+job.value.id);if(own!==epoch)return;updateJob(detail);baseElapsed=detail.elapsed_ms||0;seenAt=performance.now();if(activeStates.includes(detail.status))subscribe(detail.id,own)}
    else baseElapsed=0
    void loadResults(job.value,own)
    await nextTick();scroll()
  }catch{/* api显示网络错误，保留已加载会话供重试。 */}finally{if(own===epoch)changing.value=false}
}
/** keepAttachments为首次发送自动建会话时的保留标志；切换中锁定输入，防止迟到清空新正文。 */
async function create(keepAttachments=false){if(changing.value)return;closeStream();traceVisible.value=false;++traceToken;selectedResearchId.value='';++researchToken;const own=++epoch;changing.value=true;acting.value=false;uploading.value=false;++uploadToken;if(fileInput.value)fileInput.value.value='';if(!keepAttachments){attachments.value=[];draft.value=''}try{const row=await api('/conversations','POST');if(own!==epoch)return;current.value={...row,messages:[],jobs:[],attachments:[]};job.value=null;baseElapsed=0;history.value=false;preview.value=null;previewLoading.value=false;++previewToken;results.value=[];companyResults.value=[];resultSignature='';await reloadList(own)}catch{/* api显示创建错误，原会话可重新选择。 */}finally{if(own===epoch)changing.value=false}}
function ensureMessage(id:number){let message=current.value?.messages.find((x:any)=>x.id===id);if(!message){message={id,role:'assistant',content:'',final:false};current.value.messages.push(message)}if(job.value?.reply_message_id!==id)updateJob({...job.value,reply_message_id:id});return message}

/** jobId为当前任务，own为会话版本；delta按真实消息ID积累，重连事件由服务器游标去重重放。 */
function subscribe(jobId:string,own:number){
  closeStream();const conversationId=current.value.id;const connection=new EventSource('/api/jobs/'+jobId+'/events');stream=connection;let profileRequested=false,terminalRequested=false
  const valid=()=>own===epoch&&job.value?.id===jobId&&stream===connection
  /** attempt为失败次数；终态已持久化，恢复GET失败不能覆盖后来提交的新轮次。 */
  async function refreshFinal(attempt=0){
    try{const conv=await api('/conversations/'+conversationId,'GET',undefined,{notify:false});if(!valid()||sending.value||acting.value)return;current.value=conv;const finalJob=conv.jobs.find((x:any)=>x.id===jobId);if(finalJob)updateJob(finalJob);await reloadList(own);if(valid()){await nextTick();scroll()}}
    catch{if(!valid())return;if(attempt<2)retryLater(()=>void refreshFinal(attempt+1),own);else ElMessage.warning('回答已保留，历史同步失败，请重新打开对话')}
  }
  connection.addEventListener('message.reset',event=>{if(!valid())return;const d=JSON.parse((event as MessageEvent).data);const m=ensureMessage(d.message_id);m.content='';m.generation_id=d.generation_id;m.final=false})
  connection.addEventListener('message.delta',async event=>{if(!valid())return;const d=JSON.parse((event as MessageEvent).data);const m=ensureMessage(d.message_id);if(m.generation_id&&m.generation_id!==d.generation_id)return;const root=messageRoot.value;const pinned=!root||root.scrollHeight-root.scrollTop-root.clientHeight<100;m.content+=d.delta;m.final=false;await nextTick();if(valid()&&pinned)scroll()})
  connection.addEventListener('message.completed',event=>{if(!valid())return;const d=JSON.parse((event as MessageEvent).data);const m=ensureMessage(d.message_id);m.content=d.content;m.final=true})
  connection.addEventListener('stage',event=>{if(!valid())return;const d=JSON.parse((event as MessageEvent).data);if(job.value)job.value.stage=d.stage})
  for(const type of ['tool.started','tool.finished','tool.reused'])connection.addEventListener(type,event=>{if(valid())toolEvent(JSON.parse((event as MessageEvent).data))})
  connection.addEventListener('intent.completed',event=>{if(!valid())return;const d=JSON.parse((event as MessageEvent).data);if(d.title){current.value.title=d.title;const item=conversations.value.find(x=>x.id===conversationId);if(item)item.title=d.title}})
  connection.addEventListener('status',async event=>{
    if(!valid())return;const d=JSON.parse((event as MessageEvent).data);updateJob({...job.value,...d});baseElapsed=d.elapsed_ms||0;seenAt=performance.now()
    if(!activeStates.includes(d.status)){connection.close();if(!terminalRequested){terminalRequested=true;void refreshFinal()}return}
    if(!profileRequested&&['plan','decide','search','read','extract','save','gap','answer','learn'].includes(d.stage)){
      profileRequested=true;try{const row=await api('/conversations/'+conversationId,'GET',undefined,{notify:false});if(valid()&&!terminalRequested)current.value.profile=row.profile}catch{profileRequested=false}
    }
  })
}
async function send(){
  if(!draft.value.trim()||busy.value||uploading.value)return;sending.value=true
  try{
    const initialEpoch=epoch
    if(!current.value){await create(true);if(epoch!==initialEpoch+1||!current.value)return}
    const own=epoch,id=current.value.id,content=draft.value.trim(),sentFiles=[...attachments.value]
    const result=await api('/conversations/'+id+'/messages','POST',{content,attachment_ids:sentFiles.map(x=>x.id),client_token:crypto.randomUUID()})
    if(own!==epoch)return
    selectedResearchId.value='';++researchToken
    draft.value='';attachments.value=[];current.value.attachments=[...(current.value.attachments||[]),...sentFiles];current.value.messages.push({id:'local-'+result.id,role:'user',content,attachment_ids:sentFiles.map(x=>x.id)});if(result.metrics?.conversation_title)current.value.title=result.metrics.conversation_title;const listItem=conversations.value.find(x=>x.id===id);if(listItem)listItem.title=current.value.title;updateJob(result);baseElapsed=result.elapsed_ms||0;seenAt=performance.now();subscribe(result.id,own);await nextTick();if(own===epoch)scroll()
  }catch{/* api已显示可追踪错误；保留草稿与附件供重试。 */}finally{sending.value=false}
}
async function upload(event:Event){const own=epoch,token=++uploadToken;const input=event.target as HTMLInputElement;const files=Array.from(input.files||[]).slice(0,5-attachments.value.length);uploading.value=true;try{for(const file of files){const body=new FormData();body.append('file',file);const row=await api('/attachments','POST',body,{notify:false});if(own!==epoch||token!==uploadToken)return;attachments.value.push(row)}}catch(error){if(own===epoch&&token===uploadToken)ElMessage.error(error instanceof Error?error.message:'文件解析失败')}finally{if(own===epoch&&token===uploadToken){uploading.value=false;input.value=''}}}
async function action(type:string){const own=epoch,id=job.value?.id;if(!id||acting.value)return;acting.value=true;try{const state=await api('/jobs/'+id+'/'+type,'POST');if(own!==epoch)return;updateJob(state);const row=await api('/jobs/'+id);if(own!==epoch)return;updateJob(row);subscribe(id,own)}catch{/* api已显示错误，保留当前状态供重试。 */}finally{if(own===epoch)acting.value=false}}
async function copy(text:string){try{await navigator.clipboard.writeText(text);ElMessage.success('已复制')}catch{ElMessage.error('无法复制，请选择文本复制')}}
function example(){draft.value='我们销售吊灯、吸顶灯和轨道灯，寻找深圳灯具经销商、零售门店。排除生产厂商，优先核验主营品类、公开业务电话与地址。'}
onMounted(async()=>{window.addEventListener('resize',onViewportResize);await reloadList();const selected=String(route.query.conversation_id||'');if(selected)await open(selected);else if(conversations.value.length)await open(conversations.value[0].id);timer=setInterval(()=>clockTick.value++,500);await nextTick();resizeComposer()})
onUnmounted(()=>{++epoch;closeStream();clearInterval(timer);for(const handle of recoveryTimers)clearTimeout(handle);recoveryTimers.clear();window.removeEventListener('resize',onViewportResize)})
</script>

<template>
  <div class="research-page">
    <div :class="['research-body',{'has-panel':panel}]">
      <section class="chat-workspace" data-testid="workbench-chat">
        <div class="workbench-heading"><h1>{{workspaceTitle}}</h1><div class="row"><el-button text :icon="Menu" aria-label="历史对话" @click="history=true"/><el-button text :icon="Plus" aria-label="新对话" :disabled="busy" @click="create()"/><el-button text :icon="Files" aria-label="结果与文件" :aria-expanded="panel" @click="panel=!panel"/></div></div>
        <div ref="messageRoot" class="message-scroll">
          <div v-if="!current?.messages?.length" class="chat-empty"><h2>从一个企业或采购问题开始</h2><p>输入企业名称，研究客户画像、公开采购需求与上下游关系；也可以上传产品资料寻找买家。</p><button class="starter" @click="draft='查询一家企业的完整画像，请先询问我企业名称，确认后检索公开采购和上下游资料。'">研究指定企业 <span>↗</span></button><button class="starter" @click="example">分析产品并寻找买家 <span>↗</span></button></div>
          <div v-else class="message-list">
            <article v-for="message in current.messages" :key="message.id" :class="['chat-message',message.role]">
              <template v-if="message.role==='assistant'">
                <span class="message-avatar">R</span><div class="assistant-body">
                <div class="answer-meta"><span class="turn-duration" title="包含规划、工具、分析和回答的累计执行时间"><el-icon><Clock/></el-icon>总耗时 {{messageTime(message.id)}}</span><span v-if="messageJob(message.id)?.metrics?.first_verified_result_ms" class="first-result-time" title="首批核验结果实际保存的时间">首批 {{formatTime(messageJob(message.id).metrics.first_verified_result_ms)}}</span><span v-if="activeStates.includes(messageJob(message.id)?.status)">{{messageJob(message.id).status==='cancelling'?'停止中':stageLabels[messageJob(message.id).stage]||'回答中'}}</span><span v-else-if="messageJob(message.id)?.status==='paused'">已停止</span><el-button v-if="messageJob(message.id)?.id===job?.id&&job&&['paused','partial','failed'].includes(job.status)" text size="small" :icon="Refresh" :disabled="acting" @click="action('resume')">继续</el-button></div>
                <ToolActivity :tools="messageJob(message.id)?.tools||[]" :running="activeStates.includes(messageJob(message.id)?.status)"/>
                <p v-if="messageJob(message.id)?.metrics?.company_resolution?.name" class="identity-resolved">按 {{messageJob(message.id).metrics.company_resolution.name}} 查询</p>
                <section v-if="identityPending(messageJob(message.id))" class="identity-confirmation" aria-label="确认查询企业">
                  <h3>确认查询企业</h3>
                  <div v-for="candidate in messageJob(message.id).metrics.company_resolution.candidates" :key="candidate.id" class="identity-candidate">
                    <div><h4>{{candidate.name}}</h4><p v-if="candidate.address||candidate.industry">{{[candidate.address,candidate.industry].filter(Boolean).join(' · ')}}</p><a v-if="/^https?:\/\//i.test(candidate.url)" :href="candidate.url" target="_blank" rel="noopener noreferrer">{{candidate.title||'身份来源'}} ↗</a></div>
                    <el-button :disabled="busy" @click="confirmIdentity(messageJob(message.id),candidate.id)">选择这家</el-button>
                  </div>
                  <form class="identity-supplement" @submit.prevent="confirmIdentity(messageJob(message.id))"><el-input v-model="identityNames[messageJob(message.id).id]" placeholder="企业全称（选填）" aria-label="企业全称" :disabled="busy"/><el-input v-model="identityContexts[messageJob(message.id).id]" placeholder="地区、行业或官网（选填）" aria-label="企业消歧信息" :disabled="busy"/><el-button native-type="submit" type="primary" :loading="acting" :disabled="busy&&!acting">补充并核验</el-button></form>
                </section>
                <p v-if="!message.content&&messageJob(message.id)?.error" class="tool-error">{{failureText(messageJob(message.id).error)}}</p>
                <div class="markdown-content"><MarkdownRender mode="chat" html-policy="escape" :custom-markdown-it="configureMarkdown" :content="displayMarkdown(message.content,message.final!==false&&!['paused','failed'].includes(messageJob(message.id)?.status))" :final="message.final!==false||!busy" :smooth-streaming="false" :render-code-blocks-as-pre="true" :fade="false"/></div>
                <div v-if="message.content" class="message-actions"><el-button text :icon="CopyDocument" title="复制回答" aria-label="复制回答" @click="copy(message.content)"/></div>
                </div>
              </template>
              <template v-else><div class="user-content"><div class="markdown-content user-markdown"><MarkdownRender mode="chat" html-policy="escape" :custom-markdown-it="configureMarkdown" :content="message.content" :final="true" :render-code-blocks-as-pre="true" :fade="false"/></div><div v-if="message.attachment_ids?.length" class="message-files"><button v-for="id in message.attachment_ids" :key="id" @click="showFile(id)"><el-icon><Document/></el-icon>{{fileMeta(id)?.filename||'产品附件'}}</button></div></div><span class="user-avatar">我</span></template>
            </article>
            <div v-if="job&&!current.messages.some((x:any)=>x.id===job.reply_message_id)" class="pending-turn"><div class="answer-meta"><span class="turn-duration" title="包含规划、工具、分析和回答的累计执行时间"><el-icon><Clock/></el-icon>总耗时 {{elapsed}}</span><span>{{job.status==='cancelling'?'停止中':job.status==='paused'?'已停止':activeStates.includes(job.status)?stageLabels[job.stage]||'准备回答':job.status==='failed'?'回答失败':'待继续'}}</span><el-button v-if="['paused','partial','failed'].includes(job.status)" text size="small" :icon="Refresh" :disabled="acting" @click="action('resume')">继续</el-button></div><ToolActivity :tools="job.tools||[]" :running="busy"/><p v-if="job.error" class="tool-error">{{failureText(job.error)}}</p></div>
          </div>
        </div>
        <div class="composer-wrap">
          <div class="composer-box">
            <div v-if="attachments.length" class="attachment-list"><el-tag v-for="(file,i) in attachments" :key="file.id" :closable="!busy" @close="!busy&&attachments.splice(i,1)"><button class="attachment-preview-button" @click="showFile(file.id)">{{file.filename}} · {{file.truncated?'部分解析':file.parse?.warnings?.length?'需核对':'已解析'}}</button></el-tag></div>
            <button class="icon-button" aria-label="上传产品资料" title="上传产品资料" :disabled="busy||uploading||attachments.length>=5" @click="fileInput?.click()"><el-icon><Paperclip/></el-icon></button><textarea ref="composer" v-model="draft" aria-label="获客需求" placeholder="继续研究某家企业，或上传产品资料…" :disabled="busy" rows="1" @keydown="onKeydown"/>
            <div class="composer-controls"><div class="row"><span v-if="uploading" class="composer-model">解析文件…</span><input ref="fileInput" hidden type="file" accept=".pdf,.doc,.docx,.xls,.xlsx,.csv,.txt" multiple @change="upload"/></div><button v-if="busy" class="send-button stop-button" aria-label="停止回答" :disabled="!job||job?.status==='cancelling'||sending||changing||acting" @click="action('pause')"><span class="stop-square"/></button><button v-else class="send-button" aria-label="发送" :disabled="!draft.trim()||uploading" @click="send"><el-icon><Top/></el-icon></button></div>
          </div>
        </div>
      </section>
      <ArtifactPanel v-if="panel" :companies="companyResults" :files="panelFiles" :legacy-results="results" :research="researchSummary" :conversation-id="current?.id" :preview="preview" :loading="previewLoading" @close="panel=false" @select-file="showFile" @select-dataset="showDataset"/>
    </div>
    <el-drawer v-model="history" title="历史对话" direction="ltr" size="280px"><el-button text class="new-conversation" :icon="Plus" :disabled="sending" @click="create()">新对话</el-button><button v-for="item in conversations" :key="item.id" :class="['history-item',{active:item.id===current?.id}]" @click="open(item.id)">{{item.title}}</button><p v-if="!conversations.length" class="history-empty">暂无对话</p></el-drawer>
    <el-drawer v-model="traceVisible" title="运行链路" size="min(680px, 94vw)"><p v-if="traceLoading" class="muted">正在读取真实运行记录…</p><template v-else-if="traceData?.available"><a :href="traceData.url" target="_blank" rel="noopener noreferrer">在 LangSmith 查看 ↗</a><p v-if="traceData.truncated" class="muted">这里只预览最近的运行步骤，完整链路可在 LangSmith 查看。</p><div v-for="run in traceData.runs.filter((item:any)=>['llm','tool'].includes(item.type)||stageLabels[item.name]||item.name==='LangGraph')" :key="run.id" class="trace-row"><span>{{stageLabels[run.phase]||stageLabels[run.name]||(run.type==='llm'?'模型请求':run.type==='tool'?'资料工具':run.name)}}</span><span>{{run.has_error?'未完成':run.elapsed_ms==null?'执行中':'已执行'}} · {{run.elapsed_ms==null?'—':formatTime(run.elapsed_ms)}}</span></div></template><p v-else class="muted">{{traceData?.enabled?'该轮云端记录暂未取得':'链路追踪尚未启用'}}</p></el-drawer>
  </div>
</template>
