<script setup lang="ts">
/** tools为真实SSE或持久账本投影，running指所属任务仍执行；不显示模型隐式推理。 */
defineProps<{tools:any[],running?:boolean}>()
const names:Record<string,string>={reuse_tenders:'复用已保存招投标数据',search_tenders:'检索招投标',read_tender:'读取招投标页面',search_accounts:'检索公开资料',fetch_source:'读取来源',fetch_browser:'读取网页',search_knowledge:'检索知识',search_research_data:'检索本地研究资料',persist_lead:'保存客户',persist_company:'保存查询结果',parse_account:'解析商户资料'}
const states:Record<string,string>={running:'执行中',completed:'已完成',paused:'已暂停',rejected:'未通过',unavailable:'不可用',rate_limited:'受限'}
const platforms:Record<string,string>={qianlima:'千里马',chinabidding:'中国采购与招标网',ebnew:'必联网',yfbzb_public:'乙方宝',exa:'全网',exa_original:'全网原始公告'}
const channels:Record<string,string>={tender:'招投标平台',official:'公开网页',directory:'商户目录',procurement:'采购公告',knowledge:'知识库',brand_directory:'品牌门店',mall_directory:'家居商户',industry_directory:'行业黄页',b2b_1688:'1688公开检索',qcc_public:'企查查公开核验',ccgp:'中国政府采购',sz_procurement:'深圳采购',public_registry:'政府企业公示'}
const errors:Record<string,string>={provider_rate_limited:'检索服务暂时受限',site_rate_limited:'该站点暂时受限，改查其他来源',budget_exhausted:'本轮检索额度已用完',candidate_budget_exhausted:'该客户补查额度已用完',site_access_restricted:'该页面限制公开访问',site_robots_disallowed:'该页面不允许自动读取',site_policy_unavailable:'暂时无法核验网站读取规则',site_login_required:'该页面需要登录，改查公开来源',site_verification_required:'该页面需要验证，改查其他来源',url_not_discovered:'来源尚未核验',url_not_public:'来源不属于公开网页',source_channel_mismatch:'来源不属于所选平台',empty_results:'未找到匹配来源',empty_body:'未取得可用正文',verification_required:'搜索引擎要求验证，改用其他来源',bad_tool_output:'返回内容不完整，已丢弃',search_failed:'检索暂时不可用',timeout:'该来源响应超时',error:'该来源暂时不可用',http_404:'页面不存在',HTTPError:'检索服务暂时受限',channel_disabled:'该渠道未启用',operation_in_progress:'该操作正在执行',operation_paused:'该操作已暂停'}
Object.assign(channels,{qcc_mcp:'企查查授权资料',bidresearch:'采购公告',bidresearch_detail:'公告正文'})
Object.assign(names,{get_tender_detail:'核验公告正文'})
Object.assign(names,{qcc_company_lookup:'核验企业资料',qcc_operation_lookup:'核验企业经营资料',qcc_risk_lookup:'核验企业风险',qcc_tender_lookup:'检索企业招投标'})
Object.assign(errors,{mcp_timeout:'采购工具响应超时，已保留已取得的资料',mcp_unavailable:'采购工具暂时无法连接',bidresearch_not_installed:'采购检索工具尚未安装',qcc_timeout:'企查查连接超时',qcc_unavailable:'暂时无法连接企查查',qcc_invalid_response:'企查查返回的资料暂时无法解析',qcc_not_configured:'企查查授权尚未配置',qcc_invalid_token:'企查查授权未通过',qcc_quota_exhausted:'企查查可用积分已用完',qcc_rate_limited:'企查查暂时限制请求频率',qcc_budget_exhausted:'本轮企业资料核验额度已用完'})
function duration(ms=0){return `${(ms/1000).toFixed(1)} 秒`}
/** tool为真实轨迹；搜索标签只表示方向，读页展示实际域名，不将招聘网页称为商场资料。 */
function sourceLabel(tool:any){if(tool.tool==='search_tenders')return platforms[tool.arguments?.source]||'招投标平台';if(['fetch_source','fetch_browser','read_tender'].includes(tool.tool)){try{return new URL(tool.arguments?.url).hostname.replace(/^www\./,'')}catch{return '公开网页'}}const label=channels[tool.channel]||tool.channel;return tool.tool==='search_accounts'?`${label.replace(/公开检索$|公开核验$/,'公开')}检索`:label}
/** tool为受限真实工具投影；仅用真实入参生成一句操作说明，不暴露JSON或推理。 */
function command(tool:any){const args=tool.arguments||{};if(tool.channel==='qcc_mcp')return `查询企查查企业资料 ${args.name||''}`;if(tool.tool==='search_tenders')return `在${platforms[args.source]||'公开采购站点'}检索 ${(args.keywords||[]).join('、')||String(args.query||'').split(' | ')[0]}`;if(args.query)return `检索 ${args.query}`;if(args.url)return `读取 ${args.url}`;if(args.company||args.customer)return `保存 ${args.company||args.customer}`;return names[tool.tool]||tool.tool}
</script>
<template>
  <details v-if="tools.length" class="tool-activity">
    <summary><span class="disclosure-arrow">›</span><span>{{tools.length}} 次工具调用</span><span v-if="running" class="tool-live">执行中</span></summary>
    <div class="tool-activity-body">
      <details v-for="tool in tools" :key="tool.operation_id||tool.id" class="tool-call">
        <summary><span class="disclosure-arrow">›</span><strong>{{names[tool.tool]||tool.tool}}</strong><span>{{sourceLabel(tool)}}</span><span class="tool-call-state">{{tool.error==='empty_results'?'无匹配结果':tool.reused&&tool.status==='completed'?'已复用':states[tool.status]||tool.status}}</span><span :title="tool.attempts>1?'该操作多次尝试的累计耗时':'该操作的执行耗时'">{{tool.status==='running'?'…':duration(tool.elapsed_ms)}}</span><span v-if="tool.attempts>1">{{tool.attempts}} 次尝试</span></summary>
        <div class="tool-call-body"><p class="tool-command">{{command(tool)}}</p><p v-if="tool.error" class="tool-error">{{tool.read_summary||errors[tool.error]||'该来源暂未取得结果'}}</p><p v-else-if="tool.tool==='persist_company'&&tool.status==='completed'&&tool.company_id">企业已保存 · {{tool.accepted_fields||0}} 项资料通过核验<template v-if="tool.rejected_count"> · {{tool.rejected_count}} 项待核验</template></p><p v-else-if="tool.status==='completed'">{{tool.source_count||0}} 个来源<template v-if="tool.network_attempted"> · 本轮新检索 {{tool.fresh_source_count||0}} · 历史复用 {{tool.cached_source_count||0}}</template><template v-if="tool.local_dataset_count"> · {{tool.local_dataset_count}} 份历史数据集</template><template v-if="tool.knowledge_count"> · {{tool.knowledge_count}} 条知识</template></p><template v-for="source in tool.sources||[]" :key="source.url||source.title"><a v-if="source.url" :href="source.url" target="_blank" rel="noopener noreferrer">{{source.title||source.url}} ↗</a><span v-else>{{source.title}}</span></template></div>
      </details>
    </div>
  </details>
</template>
