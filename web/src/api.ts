import { ElMessage } from 'element-plus'
/** path为非空本地API路径，method默认GET，body可省略或为JSON/FormData。
 * options.notify默认true；异步文件请求可设false，由调用方确认仍属当前会话后再显示错误。
 * 返回后端JSON；网络或非2xx抛含请求ID的Error，不隐藏后端失败。
 */
export async function api(path:string, method='GET', body?:unknown, options:{notify?:boolean,signal?:AbortSignal}={}):Promise<any>{
  try {
    const response=await fetch('/api'+path,{method,signal:options.signal,headers:body instanceof FormData?{}:{'Content-Type':'application/json'},body:body===undefined?undefined:body instanceof FormData?body:JSON.stringify(body)})
    const data=await response.json()
    if(!response.ok) throw Object.assign(new Error((data.error||JSON.stringify(data.detail)||'请求失败')+(data.request_id?' · 请求 '+data.request_id:'')),{status:response.status})
    return data
  } catch(error){if(options.notify!==false&&!(error instanceof DOMException&&error.name==='AbortError'))ElMessage.error(error instanceof Error?error.message:'网络连接失败');throw error}
}
export const stages:Record<string,string>={new:'新线索',review:'待核验',contacted:'已联系',nurture:'持续跟进',converted:'已成交',invalid:'无效'}
export const factLabels:Record<string,string>={name:'名称',city:'城市',legal_name:'法人主体',address:'地址',phone:'业务电话',email:'邮箱',website:'联系网站',wechat:'公开业务微信',contact_name:'联系人',contact_position:'联系人职位',credit_code:'信用代码',registry_status:'登记状态',buyer_role:'买家角色',industry:'行业',categories:'主营品类',brands:'经营品牌',headcount:'人员规模',revenue:'年营收',procurement:'采购信息',supplier:'供货公司',purchase_price:'采购价格',frequency:'采购频次'}
export const roles:Record<string,string>={dealer:'经销商',retailer:'零售门店',mall:'家居卖场',project_buyer:'项目采购方',manufacturer:'制造商',unknown:'待核实'}
