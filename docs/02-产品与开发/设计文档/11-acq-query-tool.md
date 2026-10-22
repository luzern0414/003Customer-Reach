import json, pathlib, datetime, hashlib
root=pathlib.Path(r'D:\Codes\000GithubProject\Result\001_bid_research_tool')
outdir=pathlib.Path(r'D:\Codes\000GithubProject\Result\003_成都宏天智企业研究\research_notes\成都宏天智 企业关系 调研')
outdir.mkdir(parents=True,exist_ok=True)
recs=json.loads((root/'data'/'chengdu-hongtianzhi'/'records.json').read_text(encoding='utf-8'))
fetch=json.loads(pathlib.Path(r'D:\Codes\000GithubProject\tmp_ebnew_fetch.json').read_text(encoding='utf-8'))
byidx={x['idx']:x for x in fetch}
meta={
0: dict(role='备选成交供应商',buyer='华润雪花啤酒(四川)有限责任公司新都分公司',agency=None,scope='过滤槽及沉淀槽增设视频监控项目',amount=None,quote='备选成交：供应商名称：成都宏天智电子有限公司；成交供应商为成都慧翼科技有限公司。采购人：华润雪花啤酒(四川)有限责任公司新都分公司。'),
1: dict(role='第二成交候选人',buyer='中国邮政集团有限公司四川省分公司',agency='成都万安建设项目管理有限公司',scope='2025年四川邮政机要通信专业车载安防设备第二次维保服务项目',amount=None,quote='第二成交候选人为：成都宏天智电子有限公司；采购人：中国邮政集团有限公司四川省分公司；招标代理：成都万安建设项目管理有限公司。'),
2: dict(role='第二中标人',buyer='中国邮政储蓄银行股份有限公司四川省分行',agency='天之瓴建设股份有限公司',scope='四川省分行辖内二级分行办公及营业场所2025-2027年技防系统维保服务项目',amount='masked',quote='第一中标人重庆东原科技发展有限公司，第二中标人成都宏天智电子有限公司，第三中标人成都诚银科技有限公司；招标代理机构天之瓴建设股份有限公司；招标人中国邮政储蓄银行股份有限公司四川省分行。'),
3: dict(role='备选供应商中标人',buyer='中国邮政集团有限公司四川省分公司',agency='成都万安建设项目管理有限公司',scope='四川邮政技防服务项目',amount='masked_discount_rate',quote='主供应商中标人为杭州海康威视系统技术有限公司；备选供应商中标人为成都宏天智电子有限公司；中标价为被遮挡的含税投标报价折扣系数；招标人中国邮政集团有限公司四川省分公司；招标代理机构成都万安建设项目管理有限公司。'),
4: dict(role='备选供应商中标人',buyer='中国邮政集团有限公司四川省分公司',agency='成都万安建设项目管理有限公司',scope='四川邮政技防服务项目',amount='masked_discount_rate',quote='主供应商中标人为杭州海康威视系统技术有限公司；备选供应商中标人为成都宏天智电子有限公司；中标价被遮挡；招标人中国邮政集团有限公司四川省分公司；招标代理机构成都万安建设项目管理有限公司。'),
5: dict(role='第二中标候选人',buyer='中国邮政储蓄银行股份有限公司四川省分行',agency='天之瓴建设股份有限公司',scope='中国邮政储蓄银行四川省分行辖内二级分行办公及营业场所2025-2027年技防系统维保服务项目',amount='masked',quote='评标委员会推荐第一中标候选人重庆东原科技发展有限公司、第二中标候选人成都宏天智电子有限公司、第三中标候选人成都诚银科技有限公司；招标代理机构天之瓴建设股份有限公司；招标人中国邮政储蓄银行股份有限公司四川省分行。'),
6: dict(role='第二成交候选人',buyer='中国邮政集团有限公司四川省分公司',agency='成都万安建设项目管理有限公司',scope='2025年四川邮政机要通信专业车载安防设备维保服务项目',amount=None,quote='第一成交候选人为成都商信科技发展有限责任公司，第二成交候选人为成都宏天智电子有限公司，第三成交候选人为成都华建建筑智能化工程有限公司；采购人中国邮政集团有限公司四川省分公司；招标代理成都万安建设项目管理有限公司。'),
7: dict(role='第二中标人',buyer='中国邮政储蓄银行股份有限公司四川省分行',agency='天之瓴建设股份有限公司',scope='中国邮政储蓄银行四川省分行2024年全省LED门楣屏设备及安装服务项目',amount=None,quote='第一中标人浙江大华技术股份有限公司，第二中标人成都宏天智电子有限公司；招标代理机构天之瓴建设股份有限公司；招标人中国邮政储蓄银行股份有限公司四川省分行。'),
8: dict(role='包件中标人（包件号被遮挡）',buyer='中国邮政储蓄银行股份有限公司四川省分行',agency='四川铭信工程招标咨询有限公司',scope='中国邮政储蓄银行股份有限公司四川省分行技防系统设计安装服务项目',amount=None,quote='某包件中标人名称：成都宏天智电子有限公司；采购代理机构四川铭信工程招标咨询有限公司；采购人中国邮政储蓄银行股份有限公司四川省分行。具体包件号由页面以星号遮挡，不能确定包件编号。'),
9: dict(role='第二中标候选人',buyer='中国邮政储蓄银行股份有限公司四川省分行',agency='天之瓴建设股份有限公司',scope='中国邮政储蓄银行四川省分行2024年全省LED门楣屏设备及安装服务项目',amount=None,quote='第一中标候选人浙江大华技术股份有限公司、第二中标候选人成都宏天智电子有限公司、第三中标候选人广电运通集团股份有限公司、第四中标候选人深圳市奥拓电子股份有限公司；招标代理机构天之瓴建设股份有限公司；招标人中国邮政储蓄银行股份有限公司四川省分行。'),
11: dict(role='第二成交候选供应商',buyer='中国邮政集团有限公司雅安市分公司',agency='成都万安建设项目管理有限公司',scope='中国邮政集团有限公司雅安市分公司枢纽综合楼网络设备间设施设备采购项目（第二次）',amount=None,quote='第一成交候选人四川宏泰仁和建设有限公司，第二成交候选人成都宏天智电子有限公司，第三成交候选人成都创鑫智能科技有限公司；采购人中国邮政集团有限公司雅安市分公司；采购代理机构成都万安建设项目管理有限公司。'),
12: dict(role='第三中标候选人',buyer='成都市邛崃生态环境局',agency='四川今晗建设咨询有限公司',scope='智慧蓉城邛崃市新型基础设施建设项目—邛崃市空气监测网络升级项目施工/标段',amount='masked_bid_price',quote='中标候选人排序：第一名中移系统集成有限公司，第二名成都华建建筑智能化工程有限公司，第三名成都宏天智电子有限公司；项目业主成都市沄崃投资集团有限公司；招标人成都市邛崃生态环境局；招标代理机构四川今晗建设咨询有限公司；投标报价被遮挡。'),
13: dict(role='第三中标候选人',buyer='成都市邛崃生态环境局',agency=None,scope='智慧蓉城邛崃市新型基础设施建设项目—邛崃市空气监测网络升级项目施工/标段',amount=None,quote='中标候选人：中移系统集成有限公司第一名、成都华建建筑智能化工程有限公司第二名、成都宏天智电子有限公司第三名；招标人成都市邛崃生态环境局；页面未公开代理机构或金额。'),
14: dict(role='中标人',buyer='青藏铁路公安局格尔木公安处',agency='青海硕胜项目管理有限责任公司',scope='青藏铁路公安局格尔木公安处沱沱河派出所指挥室及配套设备维保项目',amount='masked_per_year',quote='中标人：成都宏天智电子有限公司；中标金额：*****/年；服务时间三年（合同一年一签）；采购单位青藏铁路公安局格尔木公安处；采购代理机构青海硕胜项目管理有限责任公司。'),
15: dict(role='成交供应商',buyer='青藏铁路公安局',agency='青海诚德工程咨询管理有限公司',scope='青藏铁路公安局中心机房维保服务',amount='masked_per_year',quote='成交供应商：成都宏天智电子有限公司；成交金额：******.**元/年；服务期限三年（合同一年一签）；采购人青藏铁路公安局；采购代理机构青海诚德工程咨询管理有限公司。'),
16: dict(role='中标（成交）供应商',buyer='成都东部新区管理委员会文化旅游体育局',agency='四川国际招标有限责任公司',scope='成都七中东部学校中小学专用功能室建设项目（货物类：功能室配套）',amount='masked_total',quote='供应商名称：成都宏天智电子有限公司；供应商地址（部分遮挡）：成都市武侯区人民南路四段……；中标（成交）金额被遮挡；货物类主要标的为功能室配套，品牌爱芝音等；代理机构四川国际招标有限责任公司。'),
17: dict(role='第二中标候选人',buyer='中国华西企业股份有限公司',agency=None,scope='中华西淮州新城三级综合医院建设项目智能化工程采购',amount=None,quote='中标候选单位：四川思联机电工程有限公司第一名、成都宏天智电子有限公司第二名、四川远瞻赢实业集团有限公司第三名；招标人/公司中国华西企业股份有限公司；代理机构未在公开正文显示。'),
18: dict(role='第二中标候选人',buyer='青羊大数据公司（页面未给出完整法定名称）',agency=None,scope='青羊大数据公司2022年第二批软硬件设备采购',amount='masked_bid_price',quote='中标候选人第二名：成都宏天智电子有限公司，投标报价被遮挡；第一名四川万华智飞科技有限公司，第三名成都慧翼科技有限公司；代理机构未在公开正文显示。'),
19: dict(role='包件中标人（包件号被遮挡）',buyer='中国邮政储蓄银行股份有限公司四川省分行',agency='天之瓴建设股份有限公司',scope='中国邮政储蓄银行四川省分行技防系统设计安装服务采购项目',amount=None,quote='某包件中标人名称：成都宏天智电子有限公司；招标代理机构天之瓴建设股份有限公司；招标人中国邮政储蓄银行股份有限公司四川省分行。其余包件中标人和金额不应归属于本公司。')
}
verified=[]
for idx,m in meta.items():
 r=recs[idx]; f=byidx.get(idx,{})
 if not f:
  ev=(r.get('detail') or {}).get('evidence') or []
  if ev:
   f={'sha256':ev[0].get('sha256'),'bytes':None}
 verified.append({
  'source':'ebnew', 'source_url':r['url'].replace('http://','https://'), 'record_id':r.get('source_id'),
  'published_at':r.get('published_at'), 'project_title':r.get('title'), 'company_name':'成都宏天智电子有限公司',
  'exact_name_visible':True, 'role':m['role'], 'buyer':m['buyer'], 'agency':m['agency'], 'scope':m['scope'],
  'amount':m['amount'], 'amount_status': 'masked_by_public_page' if isinstance(m['amount'],str) and m['amount'].startswith('masked') else ('not_stated' if m['amount'] is None else 'unknown'),
  'evidence_quote':m['quote'], 'access':'public_html_http_200', 'member_wall_observed':True,
  'confidence':'high', 'evidence_sha256':f.get('sha256'), 'fetched_bytes':f.get('bytes'),
  'limitations':'EBnew页面显示“未登录，***号内容请登录后查看”；只记录页面直接可见的公司、角色、采购方、代理机构和项目范围，不猜测被遮挡金额、日期、项目编号或包件。'
 })
# all leads from short dataset; de-dupe source/url
short=json.loads((root/'data'/'hongtianzhi-short'/'records.json').read_text(encoding='utf-8'))
leads=[]; seen=set()
for r in short:
 src=r.get('source'); url=r.get('url')
 orig_url=url
 if src not in ('qianlima','jianyu','chinabidding'): continue
 if not url and src=='jianyu': url='https://www.jianyu360.cn/jylab/supsearch/index.html?keywords=%E6%88%90%E9%83%BD%E5%AE%8F%E5%A4%A9%E6%99%BA%E7%94%B5%E5%AD%90&selectType=title&searchGroup=1'
 key=(src, orig_url if orig_url else (r.get('source_id'), r.get('title'), r.get('published_at')))
 if key in seen: continue
 seen.add(key)
 leads.append({'source':src,'source_url':url,'record_id':r.get('source_id'),'published_at':r.get('published_at'),'title':r.get('title'),'region':r.get('region'),'match_scope':r.get('match_scope'),'detail_status':r.get('detail',{}).get('status'),'verification':'search_result_or_visible_list_only','role':None,'amount':None,'buyer':None,'agency':None,'note':'搜索结果标题/列表与关键词相关；详情为登录或会员遮挡/未抓取，不能据此确认成都宏天智电子有限公司在项目中的角色或金额。'})
# negative checks
data={
 'subject':{'name':'成都宏天智电子有限公司','aliases':['宏天智','成都宏天智电子']},
 'generated_at':'2026-10-12',
 'scope':'公开网页招标/采购证据；不绕过登录、会员墙、验证码或robots限制。',
 'method':{'primary':'复用001_bid_research_tool的公开适配器，并对EBnew详情页以普通HTTPS GET重放验证；页面显示200且正文直接包含公司全称才列为verified。','memberwall_policy':'不尝试注册、登录、破解或替换遮挡字段；金额仅保留明确未遮挡值，星号字段标为masked_by_public_page。'},
 'verified_tenders':verified,
 'search_leads':{'count':len(leads),'records':leads,'group_counts':{k:sum(1 for x in leads if x['source']==k) for k in sorted(set(x['source'] for x in leads))}},
 'negative_checks':[
  {'source':'ggzy','query':'成都宏天智电子有限公司','date_range':'2025-10-12 to 2026-10-13 and 2026-01-01 to 2026-10-13','result_count':0,'status':'public_api_success_zero','url':'https://www.ggzy.gov.cn/information/pubTradingInfo/getTradList','note':'API返回code=200、records=[]；不能推断历史上从未参与。'},
  {'source':'yfbzb','query':'成都宏天智电子有限公司','result_count':0,'status':'captured_public_search_no_positive_record','url':'https://www.yfbzb.com/search/invitedBidSearch','note':'现有公开检索捕获无正向结果；不是全历史否定。'},
  {'source':'chinabidding_org','query':'成都宏天智电子有限公司','result_count':0,'status':'not_in_short_positive_capture','url':'http://www.chinabidding.org.cn/LuceneSearch.aspx','note':'未形成可核验正向详情；不将空结果当作无历史数据。'}
 ],
 'unverified_fetches':[{'source':'ebnew','record_id':recs[10].get('source_id'),'source_url':recs[10]['url'].replace('http://','https://'),'published_at':recs[10].get('published_at'),'title':recs[10].get('title'),'status':'network_timeout_during_public_replay','note':'目录搜索命中，但本次普通GET超时；不作为已验证事实。'}]
}
(outdir/'tenders.json').write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8')
# Markdown notes exactly three top-level sections
lines=[]
lines.append('# 成都宏天智电子有限公司公开招标与采购证据')
lines.append('')
lines.append('## 精确公司名出现在公开详情正文的记录')
lines.append('')
lines.append('### Takeaway')
lines.append('普通 HTTPS GET 在必联网（EBnew）公开详情页验证到 19 条详情记录（2 条已有原始捕获 + 17 条本次普通 GET 复放成功）；另 1 条在复放时超时未列入已验证；19 条均直接出现“成都宏天智电子有限公司”。可确认的关系集中在安防/技防系统、维保、LED 门楣屏、网络设备间、空气监测网络、弱电智能化、教学功能室及软硬件设备等项目。公司在已验证样本中多为第二/第三中标候选人或备选供应商，另有可见的中标人、成交供应商和包件中标人（包件号遮挡）记录。')
lines.append('')
lines.append('### Cited Findings')
for x in verified:
 amount='金额状态：'+('页面以星号遮挡' if x['amount_status']=='masked_by_public_page' else ('页面未陈述' if x['amount_status']=='not_stated' else x['amount_status']))
 lines.append(f"- {x['published_at']}《{x['project_title']}》：{x['role']}；采购方：{x['buyer'] or '未公开'}；代理机构：{x['agency'] or '未公开'}；范围：{x['scope']}；{amount}。证据摘录：“{x['evidence_quote']}” — [EBnew 详情页]({x['source_url']})")
lines.append('')
lines.append('### Inferences')
lines.append('- 公开样本显示其业务轨迹以视频监控、技防系统、安防设备维保、LED 显示屏、弱电/智能化工程、网络设备和教学功能室配套为主；这是从项目标题和公开正文的项目范围归纳，不代表完整产品目录。')
lines.append('- 中国邮政/邮储银行四川省分行、成都万安建设项目管理有限公司、天之瓴建设股份有限公司在多条记录中重复出现，构成已观察到的采购方/代理方关联网络；重复出现不等同于长期合作或股权关系。')
lines.append('- 在被验证的 19 条 EBnew 记录中，未发现公开可读的完整投标金额；星号金额不能通过本次合规公开抓取恢复。')
lines.append('')
lines.append('### Gaps')
lines.append('- EBnew 记录大多显示“您当前未登录，***号内容请登录后查看”，项目编号、完整日期、预算、投标报价、折扣率和部分包件号被遮挡；没有尝试登录、注册或绕过遮挡。')
lines.append('- 1 条 2024-11-01 的同系列技防系统候选人页面在本次普通 GET 复放时网络超时，因此只作为未验证线索。')
lines.append('')
lines.append('## 会员/登录遮挡站点的检索线索与空结果')
lines.append('')
lines.append('### Takeaway')
lines.append(f"千里马 {sum(1 for x in leads if x['source']=='qianlima')} 条、剑鱼 {sum(1 for x in leads if x['source']=='jianyu')} 条、中国招标投标公共服务平台（chinabidding.com.cn）{sum(1 for x in leads if x['source']=='chinabidding')} 条被现有公开检索捕获为关键词相关线索；其详情状态为登录/会员遮挡或未请求，不能把标题命中当成公司中标、供应商或金额事实。全国公共资源交易平台（ggzy.gov.cn）针对全称在两个公开日期范围内 API 返回成功但 0 条，易招标（yfbzb）现有捕获也无正向记录。")
lines.append('')
lines.append('### Cited Findings')
for src in ('qianlima','jianyu','chinabidding'):
 arr=[x for x in leads if x['source']==src]
 if not arr: continue
 lines.append(f"- {src}：共 {len(arr)} 条检索线索。示例：")
 for x in arr[:8]:
  lines.append(f"  - {x['published_at']}《{x['title']}》；详情状态 `{x['detail_status']}`；[来源页]({x['source_url']})")
 lines.append('  - 其余记录与上述同类，完整记录、来源哈希和状态见 `tenders.json` 的 `search_leads.records`。')
lines.append('- GGZY 全称检索：公开接口 [getTradList](https://www.ggzy.gov.cn/information/pubTradingInfo/getTradList) 在 2025-10-12 至 2026-10-13、2026-01-01 至 2026-10-13 两个范围均返回 `code=200` 且 `records=[]`；这只是本次时间窗空结果。')
lines.append('- YFBZB 全称检索：[公开检索入口](https://www.yfbzb.com/search/invitedBidSearch) 的现有捕获无正向记录；不能据此断言历史无项目。')
lines.append('')
lines.append('### Inferences')
lines.append('- 会员站点结果适合作为后续人工核验的项目线索库：优先用标题明确包含四川/成都及安防、弱电、网络、设备采购的记录，再到采购人官网或公共资源交易原站核对。')
lines.append('- 跨站重复项目（例如井研设备采购、成雅工业园弱电、德昌智慧交通、华润雪花视频监控、四川邮政技防/维保）可作为实体关系候选，但详情被遮挡时只保留“线索”标签。')
lines.append('')
lines.append('### Gaps')
lines.append('- 千里马、剑鱼及中国招标投标公共服务平台的公开列表可以证明关键词相关，但本次未取得可公开核验的公司角色、采购方、代理方或金额；没有绕过登录、会员、验证码或 robots 限制。')
lines.append('- `tenders.json` 保存了 103 条按来源及记录标识去重检索线索，可供主任务 Excel 作为“待核验招标线索”页导入；不得把这些记录直接标为中标、成交或供应商。')
(outdir/'tenders.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
print('wrote',outdir/'tenders.json',len(verified),len(leads))



                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                             