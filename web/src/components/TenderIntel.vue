<script setup lang="ts">
import {ref,computed} from 'vue'
import {ShoppingCart,Trophy,Share,Document} from '@element-plus/icons-vue'
import {sourceUrl,sourceHost} from '../companySources'
/** tenders为企业详情的招投标投影（后端tender_view）；只展示已保存记录，空列表显示对应空状态。 */
const props=defineProps<{tenders:any}>()
const emit=defineEmits<{archive:[evidenceId:string]}>()
const kind=ref<'customer'|'supplier'|'competitor'>('customer'),showAllPurchases=ref(false),showAllWins=ref(false)
const summary=computed(()=>props.tenders?.summary||{})
const diagnostics=computed(()=>props.tenders?.diagnostics||{})
const purchases=computed<any[]>(()=>props.tenders?.purchases||[]),wins=computed<any[]>(()=>props.tenders?.wins||[])
const relations=computed<any[]>(()=>props.tenders?.relations?.[kind.value]||[])
const maxCount=computed(()=>Math.max(1,...relations.value.map(r=>r.count||0)))
const kinds=[{key:'customer',label:'客户',hint:'向本企业采购（本企业中标）'},{key:'supplier',label:'供应商',hint:'为本企业供货（本企业采购的中标方）'},{key:'competitor',label:'竞争对手',hint:'同一项目共同投标'}] as const
const hint=computed(()=>kinds.find(k=>k.key===kind.value)?.hint)
const stats=computed(()=>[
 {label:'采购公告',value:summary.value.purchases,note:summary.value.latest_purchase?'最近 '+summary.value.latest_purchase:''},
 {label:'中标',value:summary.value.wins,note:summary.value.candidates?'另有候选 '+summary.value.candidates+' 条':''},
 {label:'客户',value:summary.value.customers,note:''},{label:'供应商',value:summary.value.suppliers,note:''},{label:'竞争对手',value:summary.value.competitors,note:''}])
const hasData=computed(()=>stats.value.some(s=>s.value)||summary.value.candidates||summary.value.pending)
/** item为物资清单行；数量与单位按原文拼接，缺失时只显示名称。 */
function itemText(item:any){return item.name+(item.quantity?' ×'+String(item.quantity).replace(/\.0$/,'')+(item.unit||''):'')}
/** record为招投标记录；原文链接优先逐条公告，其次为企业主页列表。 */
function link(record:any){return sourceUrl(record.url)}
const basisLabel:Record<string,string>={records:'公告',platform_stats:'平台统计',third_party_list:'名录'}
function roleLabel(record:any){const quote=String(record.quote||'');if(record.role==='candidate'){if(quote.startsWith('备选供应商中标人'))return '备选中标';if(quote.startsWith('备选成交'))return '备选成交';return '候选'}return quote.match(/^第[一二三四五六七八九十\d]+中标人/)?.[0]||'中标'}
</script>
<template>
<section class="overview-card tender-intel" data-testid="tender-intel">
 <div class="overview-card-head"><h2>招投标与合作关系</h2><span class="muted">{{summary.platforms?.length?'来自 '+summary.platforms.length+' 个招投标平台':''}}</span></div>
 <p v-if="tenders.reused" class="muted">本次结果包含工具缓存资料，原公告日期与已归档正文保留；未确认字段仍为空。</p>
 <p v-if="diagnostics.mode" class="muted tender-diagnostics">{{diagnostics.mode==='history'?'历史公告研究（最多五页）':'近期公告研究'}} · 检索线索 {{diagnostics.raw_count||0}} 条 · 正文取得 {{diagnostics.full_text_count||0}} 份 · 原文角色确认 {{diagnostics.confirmed_count||0}} 份<template v-if="diagnostics.unique_record_count!=null"> · 合并记录 {{diagnostics.unique_record_count}} 条</template><template v-if="diagnostics.date_rejected"> · 时间筛除 {{diagnostics.date_rejected}} 条</template><template v-if="diagnostics.subject_rejected"> · 主体未匹配 {{diagnostics.subject_rejected}} 条</template><template v-if="diagnostics.details_failed"> · 详情未取得 {{diagnostics.details_failed}} 条</template>。线索数不代表中标或采购数，历史业绩不代表当前采购意向。</p>
 <p v-if="!hasData" class="muted tender-empty">暂未找到招投标记录，可点击右上角“继续研究”重新查询。</p>
 <template v-else>
 <dl class="tender-stats"><div v-for="stat in stats" :key="stat.label"><dt>{{stat.label}}</dt><dd>{{stat.value||0}}</dd><small v-if="stat.note">{{stat.note}}</small></div></dl>
 <div class="tender-grid">
  <div class="tender-panel">
   <h3><el-icon><ShoppingCart/></el-icon>近期采购需求</h3>
   <div v-if="tenders.top_items?.length" class="tender-items"><span class="tender-items-label">常购物资</span><span v-for="item in tenders.top_items.slice(0,8)" :key="item.name" class="item-chip" :title="item.spec">{{item.name}}<small v-if="item.count>1"> {{item.count}} 次</small></span></div>
   <ol v-if="purchases.length" class="tender-list">
    <li v-for="record in purchases.slice(0,showAllPurchases?purchases.length:6)" :key="record.id">
     <div class="tender-line"><a v-if="link(record)" :href="link(record)" target="_blank" rel="noopener noreferrer" :title="record.title">{{record.title}}</a><span v-else>{{record.title}}</span><time>{{record.published_at||'日期未披露'}}</time></div>
     <div v-if="record.items.length||record.budget||record.winner_names.length" class="tender-meta"><span v-for="item in record.items.slice(0,4)" :key="item.name+item.spec" class="item-chip" :title="item.spec">{{itemText(item)}}</span><span v-if="record.items.length>4" class="muted">等 {{record.items.length}} 项</span><span v-if="record.budget">预算 {{record.budget}}</span><span v-if="record.winner_names.length">中标：{{record.winner_names.join('、')}}</span></div>
    </li>
   </ol>
   <p v-else class="muted">未取得本企业发布的采购公告。</p>
   <button v-if="purchases.length>6" class="text-button" @click="showAllPurchases=!showAllPurchases">{{showAllPurchases?'收起':'查看全部 '+purchases.length+' 条'}}</button>
  </div>
  <div class="tender-panel">
   <h3><el-icon><Share/></el-icon>合作关系</h3>
   <div class="segmented" role="tablist"><button v-for="k in kinds" :key="k.key" role="tab" :aria-selected="kind===k.key" :class="{active:kind===k.key}" @click="kind=k.key">{{k.label}} <small>{{tenders.relations?.[k.key]?.length||0}}</small></button></div>
   <p class="muted relation-hint">{{hint}} · 次数为公开招投标次数，不代表交易金额</p>
   <ol v-if="relations.length" class="partner-bars">
    <li v-for="row in relations.slice(0,10)" :key="row.name">
     <div class="partner-name"><span :title="row.name">{{row.name}}</span><span class="basis-tags"><small v-for="b in row.bases" :key="b" class="basis-tag">{{basisLabel[b]||b}}</small></span></div>
     <span class="bar-track"><span :style="{width:Math.max(6,(row.count||0)/maxCount*100)+'%'}"/></span>
     <span class="partner-count">{{row.count||'—'}} 次</span>
     <a v-if="row.evidence?.[0]&&sourceUrl(row.evidence[0].url)" class="partner-source" :href="sourceUrl(row.evidence[0].url)" target="_blank" rel="noopener noreferrer" :title="row.evidence[0].quote">{{sourceHost(row.evidence[0].url)}} ↗</a>
    </li>
   </ol>
   <p v-else class="muted">暂未取得{{kinds.find(k=>k.key===kind)?.label}}名单。</p>
  </div>
 </div>
 <details v-if="wins.length" class="tender-wins" :open="showAllWins" @toggle="showAllWins=($event.target as HTMLDetailsElement).open">
  <summary><el-icon><Trophy/></el-icon>中标与候选记录 · {{wins.length}} 条</summary>
  <ol class="tender-list">
   <li v-for="record in wins" :key="record.id"><div class="tender-line"><a v-if="link(record)" :href="link(record)" target="_blank" rel="noopener noreferrer">{{record.title}}</a><span v-else>{{record.title}}</span><time>{{record.published_at||'日期未披露'}}</time></div>
    <div class="tender-meta"><span :class="['role-tag',record.role]">{{roleLabel(record)}}</span><span v-if="record.buyer_name">采购方：{{record.buyer_name}}</span><span v-if="record.candidate_bid?.price">本企业投标报价 {{record.candidate_bid.price}} {{record.candidate_bid.unit}}</span><span v-if="record.amount">{{record.role==='winner'?'成交金额':'公告金额'}} {{record.amount}}</span><span v-if="record.candidate_names.length">候选人：{{record.candidate_names.slice(0,4).join('、')}}</span><button v-if="record.evidence_id" class="text-button" @click="emit('archive',record.evidence_id)"><el-icon><Document/></el-icon>原文</button></div>
    <details v-if="record.disclosed_performance?.length" class="performance-list"><summary>公告披露的本企业历史业绩 · {{record.disclosed_performance.length}} 项</summary><ul><li v-for="item in record.disclosed_performance" :key="item.title"><span>{{item.title}}</span><small>{{item.signed_at||'签约时间未披露'}} · {{item.contract_amount||'合同价格未披露'}}</small></li></ul><p class="muted">业绩披露不等于本项目成交，也不自动证明客户关系。</p></details>
   </li>
  </ol>
 </details>
 <details v-if="tenders.pending?.length" class="tender-wins"><summary>待核实的相关公告 · {{tenders.pending.length}} 条</summary><p class="muted">这些公告提到了该企业，但尚未确认它是采购方还是中标方。</p><ol class="tender-list"><li v-for="record in tenders.pending" :key="record.id"><div class="tender-line"><a v-if="link(record)" :href="link(record)" target="_blank" rel="noopener noreferrer">{{record.title}}</a><span v-else>{{record.title}}</span><time>{{record.published_at}}</time></div></li></ol></details>
 </template>
</section>
</template>
<style scoped>
.performance-list{margin-top:12px;font-size:14px;line-height:1.7}
.performance-list summary{cursor:pointer}
.performance-list ul{padding-left:20px;margin:10px 0}
.performance-list li{margin:8px 0;overflow-wrap:anywhere}
.performance-list small{display:block;font-size:14px;color:var(--text-muted,#666)}
</style>
