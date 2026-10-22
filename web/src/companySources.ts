/** 条目来源卡片仅投影API中的原值与证据，不以文档首段代替当前条目。 */
import {valueText} from './company'
import {projectBudget} from './companyOverview'
export const relationLabels:Record<string,string>={supplier:'供应商',customer:'客户',subsidiary:'子公司',service_supplier:'服务供应商'}
/** url为可空原始地址；返回HTTP(S)原值，非法协议/凭据或空值返回空串。 */
export function sourceUrl(url?:string):string {if(!url)return '';try{const parsed=new URL(url);return ['https:','http:'].includes(parsed.protocol)&&!parsed.username&&!parsed.password?url:''}catch{return ''}}
/** url为可空来源地址；有效时返回原域名，无效或空值返回空串。 */
export function sourceHost(url?:string):string {return sourceUrl(url)?new URL(url!).hostname:''}
/** rows为API条目列表，可空；按真实条目ID去重并追加项目的独立公告，不拼接全文。 */
export function sourceCards(rows:any[]=[]):any[] {
  const selected=[...rows.filter(Boolean)]
  for(const row of rows.filter(Boolean))selected.push(...(row.notices||[]))
  return [...new Map(selected.map(row=>[row.id,row])).values()].map(row=>{
    const kind=row.kind||(row.counterparty_name?'relation':row.field?'fact':row.record_kind?'project':'notice')
    const title=row.counterparty_name||row.label||row.title||'资料'
    const fields:any[]=[]
    if(kind==='fact')fields.push({label:'数值',value:valueText(row.raw_value)+(row.raw_unit?' '+row.raw_unit:'')})
    if(kind==='relation'){
      if(row.amount!=null)fields.push({label:row.relation_type==='customer'?'销售额':'采购额',value:row.amount.toLocaleString('zh-CN',{maximumFractionDigits:2})+' '+(row.unit||'')+(row.currency&&row.currency!=='CNY'?' · '+row.currency:'')})
      if(row.share!=null)fields.push({label:'占比',value:row.share+'%'})
    }
    if(kind==='project'){
      if(row.buyer_name)fields.push({label:'买方',value:row.buyer_name})
      fields.push({label:row.record_kind==='plan'?'概算':'预算',value:projectBudget(row).text})
      if(row.temporal_status||row.stage)fields.push({label:'阶段',value:row.temporal_status||row.stage})
      if(row.payload?.quantity!=null)fields.push({label:'数量',value:row.payload.quantity+' '+(row.payload.unit||'')})
    }
    if(row.report_period||row.as_of||row.published_at)fields.push({label:kind==='notice'?'发布':'报告期',value:row.report_period||row.as_of||row.published_at})
    if(row.deadline)fields.push({label:'截止',value:row.deadline})
    if(row.scope)fields.push({label:'统计范围',value:row.scope})
    const refs=[...new Map((row.evidence_refs||[]).map((ref:any)=>[ref.source_id+':'+ref.id,ref])).values()]
    return {id:row.id,kind,title,label:kind==='relation'?relationLabels[row.relation_type]||'关联主体':kind==='fact'?'企业事实':kind==='notice'?'公告':row.record_kind==='plan'?'建设计划':row.record_kind==='brand_application'?'品牌应用':'采购项目',fields,refs,sourceIds:row.source_ids||[]}
  })
}
