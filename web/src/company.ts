/** 企业显示格式仅处理API值；空值显示未取得，不含任何企业样例或采购数字。 */
export function valueText(value:unknown):string{return value==null||value===''?'未取得':Array.isArray(value)?value.join('、'):typeof value==='object'?JSON.stringify(value):String(value)}
/** fact为可空后端事实，精度保留到合适单位；报告期与口径由调用组件展示。 */
export function metricText(fact:any):string{
  if(!fact)return '未取得'
  const n=fact.numeric_value
  if(n==null)return valueText(fact.raw_value)+(fact.raw_unit?' '+fact.raw_unit:'')
  if(/元/.test(fact.unit||fact.raw_unit||''))return n>=1e8?(n/1e8).toFixed(2)+' 亿元':n>=1e4?(n/1e4).toLocaleString('zh-CN',{maximumFractionDigits:2})+' 万元':n.toLocaleString('zh-CN',{maximumFractionDigits:2})+' 元'
  return n.toLocaleString('zh-CN',{maximumFractionDigits:2})+(fact.unit?' '+fact.unit:'')
}
/** 数额、单位均来自后端，可空；未明确币种时不补货币符号。 */
export function amountText(amount:number|null,unit='元'):string{return amount==null?'未披露':unit==='元'&&Math.abs(amount)>=1e4?(amount/1e4).toLocaleString('zh-CN',{minimumFractionDigits:2,maximumFractionDigits:2})+' 万元':amount.toLocaleString('zh-CN',{maximumFractionDigits:2})+' '+unit}
/** 摘要为后端主体投影；字母主体保留首字符，汉字使用首字，不推断简称。 */
export function monogram(company:any):string{return (company.short_name||company.name||'企').slice(0,1)}
/** 格式化原报告期；不把半年度值贴为年营收，也不补不存在的年份。 */
export function periodLabel(fact:any):string{const p=fact?.report_period||fact?.as_of||'';const y=p.match(/\d{4}/)?.[0]||'';return fact?.period_kind==='half_year'?y+' 上半年营收':fact?.period_kind==='annual'?y+' 年营收':p+' 营收'}
