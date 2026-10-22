/** 综合详情的纯显示投影；仅选择API事实，不生成企业样例或购买概率。 */
import {amountText, valueText} from './company'
export type RelationKind = 'supplier' | 'customer'
export interface RelationSeries {rows:any[]; period:string; comparable:boolean; max:number|null; unit:string; currency:string|null; total:number|null; share:number|null; sourceIds:string[]}
export interface PurchaseInsight {title:string; statement:string; label:string; tone:string; sourceIds:string[]; entries:any[]}
/** text可空，limit为正整数；返回原文摘要，省略部分明确用省略号。 */
export function brief(text:unknown, limit=58):string {const raw=valueText(text).replace(/\s+/g,' ').trim();return raw.length>limit?raw.slice(0,limit)+'…':raw}
/** status为可空API状态；未知状态不当已核验。 */
export function factStatus(status?:string):string {return ({verified:'已核验',inactive:'已失效',disputed:'存在争议',pending:'待核验',masked:'原值遮挡'} as Record<string,string>)[status||'']||'待核验'}
/** detail可空，kind限供应商/客户；取各自最新期，混币种禁止同轴比较，空金额不补零。 */
export function relationSeries(detail:any,kind:RelationKind):RelationSeries {
  const summary=detail?.relation_summary?.[kind]||{},period=summary.period||''
  const rows=(detail?.relations||[]).filter((r:any)=>r.relation_type===kind&&r.report_period===period)
    .sort((a:any,b:any)=>(a.rank??Number.MAX_SAFE_INTEGER)-(b.rank??Number.MAX_SAFE_INTEGER)||(b.amount??-1)-(a.amount??-1))
  const units=new Set(rows.map((r:any)=>JSON.stringify([r.unit,r.currency])))
  const comparable=rows.length>0&&units.size===1&&rows.every((r:any)=>typeof r.amount==='number'&&Number.isFinite(r.amount)&&r.amount>=0)
  // 占比须逐家披露且合计合法，不把未知份额当0拼成完整饼图。
  const share=units.size===1&&rows.length>0&&rows.every((r:any)=>typeof r.share==='number'&&Number.isFinite(r.share)&&r.share>=0)&&typeof summary.share==='number'&&summary.share>=0&&summary.share<=100?summary.share:null
  return {rows,period,comparable,max:comparable?Math.max(...rows.map((r:any)=>r.amount)):null,unit:summary.unit||'',currency:summary.currency||null,total:comparable&&typeof summary.amount==='number'?summary.amount:null,share,sourceIds:[...new Set<string>(rows.flatMap((r:any)=>r.source_ids||[]))]}
}
/** row为关系记录，series为同口径投影；未知/混币种返回null，已披露零值才画零长度。 */
export function barPercent(row:any,series:RelationSeries):number|null {return !series.comparable||series.max===null||typeof row.amount!=='number'?null:series.max===0?0:row.amount/series.max*100}
/** value为可空金额，unit为原单位，currency可空；明确CNY才换万元，外币保留原数值与币种。 */
export function moneyText(value:number|null,unit?:string,currency?:string|null):string {
  if(value===null)return '未披露'
  if(currency&&currency!=='CNY')return value.toLocaleString('zh-CN',{maximumFractionDigits:2})+' '+(unit||'原单位未披露')+' · '+currency
  if(currency===null&&unit!=='人民币元')return value.toLocaleString('zh-CN',{maximumFractionDigits:2})+' '+(unit||'原单位未披露')+' · 币种未披露'
  return amountText(value,unit==='人民币元'?'元':unit||'单位未披露')
}
/** project可空；返回原预算值/单位，空预算保持未披露，建设计划不改为支出。 */
export function projectBudget(project:any) {const p=project?.payload||{},b=p.budget,value=typeof b==='number'?b:typeof b?.amount==='number'?b.amount:null,unit=typeof b==='object'&&b?.unit||p.unit||'';return {value,unit,text:moneyText(value,unit)}}
/** detail为可空API详情；返回披露机制、品类、计划及历史条件分析，不称已实时调用AI。 */
export function procurementOverview(detail:any) {
  const facts=(detail?.facts||[]).filter((r:any)=>r.status==='verified')
  const priority=(r:any)=>/采购组织|采购模式/.test(r.label)?4:/准入|年度订单|长周期/.test(r.label)?3:/价格/.test(r.label)?2:0
  const rules:any[]=facts.filter((r:any)=>r.field==='procurement_rule'||/采购特征/.test(r.category)).sort((a:any,b:any)=>priority(b)-priority(a))
  const categoryFacts:any[]=facts.filter((r:any)=>/采购品类/.test(r.category)).sort((a:any,b:any)=>Number(/结构件|电子元器件|功能部件/.test(b.label))-Number(/结构件|电子元器件|功能部件/.test(a.label)))
  const purchases:any[]=(detail?.projects||[]).filter((r:any)=>r.record_kind==='procurement'),plans:any[]=(detail?.projects||[]).filter((r:any)=>r.record_kind==='plan')
  // 总项凭原披露名/备注选取，不把未知的分项预算相加后冒充完整概算。
  const equipmentPlan=plans.find(r=>/设备/.test(r.title)&&/总项|总额|购置/.test(r.title+' '+(r.payload?.note||''))&&projectBudget(r).value!==null)
  const categories=[...new Set<string>(categoryFacts.map(r=>valueText(r.raw_value)))]
  if(!categories.length)categories.push(...[...new Set<string>(purchases.map(r=>r.payload?.group||r.payload?.category).filter(Boolean))])
  const insights:PurchaseInsight[]=[]
  if(rules.length||categoryFacts.length)insights.push({title:'生产物料',label:'已披露',tone:'blue',statement:brief(categoryFacts.length?categories.slice(0,3).join('、'):rules[0].raw_value,72),sourceIds:[...new Set<string>([...categoryFacts,...rules.slice(0,2)].flatMap(r=>r.source_ids||[]))],entries:[...categoryFacts,...rules.slice(0,2)]})
  if(equipmentPlan)insights.push({title:'设备购置',label:'建设计划',tone:'amber',statement:'设备概算 '+projectBudget(equipmentPlan).text,sourceIds:equipmentPlan.source_ids||[],entries:[equipmentPlan]})
  const systemPlans=plans.filter(r=>/仓储|工业互联网|信息化/.test(r.title))
  if(systemPlans.length)insights.push({title:'信息化建设',label:'建设计划',tone:'violet',statement:brief(systemPlans.map(r=>r.payload?.product||r.title).join('、'),72),sourceIds:[...new Set<string>(systemPlans.flatMap(r=>r.source_ids||[]))],entries:systemPlans})
  const historical=purchases.filter(r=>r.payload?.future_purchase_possibility?.assessment)
  if(!insights.length)insights.push(...historical.slice(0,3).map(r=>({title:brief(r.payload.product||r.title,26),label:'历史研究',tone:'blue',statement:brief(r.payload.future_purchase_possibility.assessment,92),sourceIds:r.source_ids||[],entries:[r]})))
  if(!insights.length&&purchases.length)insights.push({title:'公开采购需求',label:'公开需求',tone:'blue',statement:brief(purchases.slice(0,3).map(r=>r.payload.product||r.title).join('、'),92),sourceIds:purchases[0].source_ids||[],entries:purchases.slice(0,3)})
  return {rules,categories,categoryFacts,purchases,plans,equipmentPlan,insights:insights.slice(0,3)}
}
