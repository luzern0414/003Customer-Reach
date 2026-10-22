"""统一公开渠道能力和检索范围；平台索引检索不等同取得授权API或完整联系方式。"""
from typing import Literal
from urllib.parse import urlparse
import re
from pathlib import Path

SearchChannel=Literal['official','directory','procurement','brand_directory','mall_directory','industry_directory','b2b_1688','qcc_public','ccgp','sz_procurement','public_registry']

CHANNELS={
 'knowledge':{'name':'第一方与知识库','status':'ready','description':'你上传的产品资料、已有客户和已核实的资料','provider':'本地知识库','mode':'local'},
 'official':{'name':'企业官网','status':'ready','description':'企业官网的产品与联系方式','objective':'企业官网产品与联系我们页面，优先同一主体的公开联系方式','suffix':'官网 联系我们 主营产品','purpose':'发现与联系核验'},
 'directory':{'name':'品牌与行业目录','status':'ready','description':'品牌门店、商场商户等目录，用于发现和核对客户','objective':'品牌授权经销商、具体门店或家居商场商户目录，不能用主办方电话代替商户电话','suffix':'授权门店 商户目录 电话 地址','purpose':'发现与交叉核验'},
 'procurement':{'name':'公开采购公告','status':'ready','description':'政府及企业公开的采购公告','objective':'政府采购或公共资源交易原始公告，严格区分采购人、代理、中标供应商及截止时间','suffix':'采购公告 采购人 截止日期','purpose':'采购信号','procurement':True},
 'brand_directory':{'name':'品牌经销门店','status':'ready','description':'品牌官方的经销门店名录','objective':'品牌官方门店经销商目录，核验具体城市、门店地址、店名和门店电话；总部客服不替代店铺联系人','suffix':'品牌 授权经销商 门店 地址 电话','purpose':'门店发现'},
 'mall_directory':{'name':'家居商场商户','status':'ready','description':'家居、建材商场的入驻商户名录','objective':'家居建材或灯饰商场的具体分店入驻商户目录，优先店铺主营、地址、业务电话；招商电话与商户电话分开','suffix':'家居商场 入驻品牌 灯饰区 商户 电话','purpose':'门店发现'},
 'industry_directory':{'name':'行业黄页与商会','status':'ready','description':'行业黄页与商会会员名录（信息可能过时）','objective':'具体企业的行业黄页、商协会成员目录或商户介绍，优先公开业务电话、邮箱和地址。陈旧登记或生产商身份必须明确','suffix':'商行 经销批发 联系电话 邮箱 地址','purpose':'发现与联系方式补查'},
 'b2b_1688':{'name':'1688 公开发现','status':'ready','description':'1688 公开店铺与采购信息（需登录的内容不读取）','objective':'只查1688公开店铺或公开采购商机，取得具体企业名、地区、主营、公开业务联系方式及角色。无正文或需登录字段留空；商品上架不证明采购','suffix':'1688 店铺 公司 联系方式','scope':'site:1688.com','domains':['1688.com'],'exclude_hosts':['open.1688.com','page.1688.com'],'purpose':'公开候选发现'},
 'qcc_public':{'name':'企查查公开核验','status':'ready','description':'企查查公开页面，用于核对企业名称与经营状态','objective':'企查查具体企业公开页，核实名称、城市、经营状态、经营范围与真实公开联系方式；接口文档、平台客服不是企业线索，未公开字段留空','suffix':'企查查 企业 经营状态 经营范围','scope':'site:qcc.com','domains':['qcc.com','qichacha.com'],'exclude_hosts':['openapi.qcc.com','api.qichacha.com'],'purpose':'主体核验'},
 'ccgp':{'name':'中国政府采购网','status':'ready','description':'中国政府采购网公告','objective':'中国政府采购网原始公告，核实采购人名称、地址、采购单位联系方式、标的与发布时间/截止日期，排除代理电话和无关医疗灯具','suffix':'采购公告 采购单位 联系方式','scope':'site:ccgp.gov.cn','domains':['ccgp.gov.cn'],'purpose':'采购信号','procurement':True},
 'sz_procurement':{'name':'深圳公共资源交易','status':'ready','description':'深圳公共资源交易与政府采购公告','objective':'深圳公共资源交易或政府采购原始公告，优先采购人、公开电话、项目名称、发布与截止日期，采购人/代理/供应商分开','suffix':'深圳 采购公告 采购人 联系方式','scope':'site:szggzy.com','domains':['szggzy.com','sz.gov.cn'],'purpose':'采购信号','procurement':True},
 'public_registry':{'name':'政府企业公示','status':'ready','description':'政府企业信用公示，用于核对企业登记信息','objective':'政府企业登记或信用公示具体主体资料，核实完整企业名、登记状态、信用代码及地区；只有导航或框架页不算企业资料，不将登记范围当采购意图','suffix':'企业 信用公示 统一社会信用代码 经营状态','domains':['gov.cn'],'purpose':'主体核验'},
 'company_api':{'name':'企查查授权 API','status':'authorization_required','description':'企查查官方接口，需单独申请账号与额度','provider':'企查查官方API','mode':'authorized_api'},
 'rfq':{'name':'1688 授权采购','status':'authorization_required','description':'1688 开放平台采购接口，需单独申请授权','provider':'1688开放平台','mode':'authorized_api'},
 'intent':{'name':'商业 Intent','status':'authorization_required','description':'商业采购意向数据，需购买数据服务','provider':'商业意向供应商','mode':'authorized_api'},
}
for _key,_value in CHANNELS.items():
    if _value.get('objective'):
        _value.setdefault('provider','Exa MCP + 公开网页')
        _value.setdefault('mode','public_index')

# 只登记已真实读取的目录入口，不登记客户事实；每轮fetch成功后才产生Evidence。
PUBLIC_ENTRIES=[
    {'channel':'mall_directory','region':'深圳','products':'灯|照明','url':'http://www.leanju.com:8080/subbranch-detail/i-24.html'},
    {'channel':'mall_directory','region':'深圳','products':'灯|照明','url':'http://www.leanju.com:8080/subbranch-detail/i-26.html'},
    {'channel':'brand_directory','region':'深圳','products':'灯|照明|开关|电气','roles':['dealer','retailer'],'url':'http://www.ad.siemens.com.cn/wa/Retailing_Map/map_Guangdong.html'},
    {'channel':'ccgp','region':'深圳','products':'灯|照明','roles':['project_buyer'],'url':'https://www.ccgp.gov.cn/cggg/dfgg/gkzb/'},
    {'channel':'mall_directory','region':'深圳','products':'灯|照明','url':'http://www.leanju.com:8080/subbranch/'},
    {'channel':'industry_directory','region':'深圳','products':'灯|照明','url':'https://www.b2b168.com/'},
    {'channel':'industry_directory','region':'深圳','products':'灯|照明','url':'https://www.jc001.cn/'},
    {'channel':'industry_directory','region':'深圳','products':'灯|照明','url':'https://www.yunfale.com/'},
]


def public_entries(profile: dict, enabled: list[str], channel: str='', roles: list[str] | None=None, prompt: str='') -> list[dict]:
    """profile为本轮地区/产品，enabled为启用渠道，channel可空，roles为空时不筛角色；返回公开入口，不创建来源或客户。

    prompt为本轮要求，空则仅按设置；显式禁止的目录不能借directory父渠道读。原渠道/地区/产品/总预算限制保持。
    """
    products=' '.join(str(item.get('name','')) for item in profile.get('products',[]))
    result=[]
    disabled={key for _,key,denied,_ in _channel_mentions(prompt) if denied}
    for entry in PUBLIC_ENTRIES:
        if entry['channel'] in disabled:continue
        if profile.get('region')!=entry['region'] or not re.search(entry['products'],products):continue
        # 只排已核验用途明确且不匹配的兜底入口；未知用途不硬拒，选定采购步骤仍保留真实入口读取。
        if roles and entry.get('roles') and not set(roles).intersection(entry['roles']) and not (channel and CHANNELS[entry['channel']].get('procurement')):continue
        route=channel or (entry['channel'] if entry['channel'] in enabled else '' if CHANNELS[entry['channel']].get('procurement') else 'directory')
        if CHANNELS[entry['channel']].get('procurement') and route!=entry['channel']:continue
        if route not in enabled or route not in {entry['channel'],'directory'}:continue
        result.append({'url':entry['url'],'channel':route})
    return result


def available_channels(enabled: list[str], procurement: bool=True) -> list[str]:
    """enabled为用户启用ID，procurement控制采购信号渠道；返回实际公开搜索能力，未知/授权未就绪不参与。"""
    return [key for key in enabled if key in CHANNELS and CHANNELS[key].get('objective') and
            CHANNELS[key]['status']=='ready' and (procurement or not CHANNELS[key].get('procurement'))]


def matches_channel(channel: str, url: str) -> bool:
    """channel为已登记渠道，url为真实返回URL；限定平台必须匹配域名且排除文档/接口主机，未知返回False。"""
    item=CHANNELS.get(channel)
    if not item:return False
    host=(urlparse(url).hostname or '').lower()
    if not host or host in item.get('exclude_hosts',[]):return False
    return not item.get('domains') or any(host==domain or host.endswith('.'+domain) for domain in item['domains'])


def channel_instructions(enabled: list[str]) -> str:
    """enabled为任务渠道设置；返回模型可用渠道及用途，不包含凭据，未就绪渠道不暴露为工具能力。"""
    return '\n'.join(f'{key}：{CHANNELS[key]["name"]}，{CHANNELS[key]["purpose"]}，{CHANNELS[key]["description"]}' for key in available_channels(enabled))


def _channel_mentions(prompt: str) -> list[tuple[int,str,bool,bool]]:
    """prompt为当前要求，可空；返回位置/渠道/明确否定/仅限标记，不把捏造禁令或API权限描述当平台禁用。"""
    patterns=[('1688|阿里巴巴','b2b_1688'),('企查查|qcc','qcc_public'),('中国政府采购','ccgp'),
        ('深圳(?:政府采购|公共资源)|深圳.{0,10}(?:采购网|交易网|采购公告|交易公告)','sz_procurement'),('商场|家居城|卖场','mall_directory'),
        ('品牌.{0,6}(?:门店|目录|授权)|官方.{0,6}经销','brand_directory'),('行业黄页|行业目录|商会','industry_directory'),('信用公示|工商公示','public_registry'),
        ('官网|企业网站','official')]
    commands=[r'(?:不要|别|不允许|禁止|禁用|暂不|不必|不需要|无需|不用|不使用|不查|跳过|排除)(?:再|继续|去|优先)?(?:查询|查找|搜索|检索|使用|访问|通过|抓取|爬取|查|用|从)?',
        r'(?<!先)(?:只|仅)(?:查询|查找|搜索|检索|使用|通过|查|用)',
        r'(?:查询|查找|搜索|检索|使用|访问|通过|从|查|用)']
    result=[]
    for clause in re.finditer(r'[^。；;，,！？!\n]+',prompt or ''):
        for pattern,key in patterns:
            for match in re.finditer(pattern,clause[0],re.I):
                if re.match(r'\s*(?:API|授权接口|接口|密钥|Key|Secret|权限)',clause[0][match.end():],re.I):continue
                prefix=clause[0][:match.start()];flags=[]
                for command in commands:
                    connected=False
                    for marker in re.finditer(command,prefix):
                        between=prefix[marker.end():]
                        for alias,_ in patterns:between=re.sub(alias,'',between,flags=re.I)
                        if re.fullmatch(r'(?:\s|、|和|或|以及|及|与|或者|平台|渠道|公开|索引)*',between):connected=True
                    flags.append(connected)
                # 官网也可能只是待补字段；只有明确查/用命令才当检索前缀。
                if key=='official' and not any(flags):continue
                result.append((clause.start()+match.start(),key,flags[0],flags[1]))
    return sorted(result,key=lambda item:item[0])


def active_channels(prompt: str, enabled: list[str]) -> list[str]:
    """prompt为当前消息（可空）、enabled为已有启用范围；排明确不查平台并应用仅查名单，保留知识工具，不改设置/预算、不启用新平台。"""
    mentions=_channel_mentions(prompt)
    disabled={key for _,key,denied,_ in mentions if denied}
    exclusive={key for _,key,denied,only in mentions if only and not denied}
    return [key for key in enabled if key not in disabled and (not exclusive or key in exclusive or key=='knowledge')]


def blocked_source(url: str, prompt: str) -> bool:
    """url为真实网址、prompt为当前要求，均可空；只拒显式禁用的已知平台根域/登记品牌目录路径，未知站点不猜用途，不改原文或访问权限。"""
    disabled={key for _,key,denied,_ in _channel_mentions(prompt) if denied}
    exclusive={key for _,key,denied,only in _channel_mentions(prompt) if only and not denied}
    if exclusive:disabled.update(set(CHANNELS)-exclusive)
    if not disabled:return False
    try:host=(urlparse(url).hostname or '').lower()
    except (TypeError,ValueError):return False
    domains={key:CHANNELS[key]['domains'] for key in ['b2b_1688','qcc_public','ccgp']}
    domains.update({'sz_procurement':['szggzy.com'],'mall_directory':['leanju.com'],
        'industry_directory':['yunfale.com','b2b168.com','jc001.cn','hc23.com'],
        'public_registry':['gsxt.gov.cn','creditchina.gov.cn']})
    if any(key in disabled and any(host==domain or host.endswith('.'+domain) for domain in values) for key,values in domains.items()):return True
    # 品牌官网也有产品/公司资料；只禁已登记的门店目录路径，不粗暴封整个品牌站点。
    if 'brand_directory' in disabled and (host=='siemens.com.cn' or host.endswith('.siemens.com.cn')):
        return any(entry['channel']=='brand_directory' and urlparse(url).path.startswith(urlparse(entry['url']).path.rsplit('/',1)[0]+'/') for entry in PUBLIC_ENTRIES)
    return False


def requested_channels(prompt: str, enabled: list[str]) -> list[str]:
    """prompt为当前要求，enabled为已有范围；明确先查指令优先于画像中的平台名，其余按位置，禁用/未启用不强制，空返回空。"""
    allowed=available_channels(active_channels(prompt,enabled))
    mentions=[item for item in _channel_mentions(prompt) if item[1] in allowed and not item[2]]
    priority=[]
    # 画像可能先写“家居城”，不能把该名词排在后文明确“先尝试1688、企查查”之前。
    for clause in re.finditer(r'[^。；;，,！？!\n]+',prompt or ''):
        marker=re.search(r'(?:先|优先)(?:只|仅)?(?:尝试|查询|查找|搜索|检索|使用|访问|通过|抓取|爬取|查|用)',clause[0])
        if marker:
            priority.extend(item for item in mentions if clause.start()+marker.end()<=item[0]<clause.end())
    return list(dict.fromkeys(item[1] for item in [*priority,*mentions]))


def required_sites(prompt: str) -> int:
    """prompt为当前要求，可为空；只将明确网站数量/跨站核验要求转成1..8，不把客户家数当来源数。"""
    match=re.search(r'([2-8二三四五六七八两])\s*[个家处]?\s*(?:不同|独立)?\s*(?:网站|站点|平台|来源)',prompt or '')
    if match:return int(match[1]) if match[1].isdigit() else {'两':2,'二':2,'三':3,'四':4,'五':5,'六':6,'七':7,'八':8}[match[1]]
    return 2 if re.search('跨站|交叉核验|交叉验证|多个来源|多来源核验',prompt or '') else 1


def reference_channel(url: str, enabled: list[str]) -> str:
    """url为当前用户提供的公开链接，enabled为渠道设置；返回可读渠道或空，不借通用官网绕过已关闭平台。"""
    host=(urlparse(url).hostname or '').lower()
    for key in ['b2b_1688','qcc_public','ccgp','sz_procurement']:
        domains=CHANNELS[key].get('domains',[])
        if any(host==domain or host.endswith('.'+domain) for domain in domains):
            return key if key in enabled and matches_channel(key,url) else ''
    if host in {'leanju.com','www.leanju.com'} and 'mall_directory' in enabled:return 'mall_directory'
    if any(host==domain or host.endswith('.'+domain) for domain in ['siemens.com.cn','opple.com.cn','nvc-lighting.com.cn']) and 'brand_directory' in enabled:return 'brand_directory'
    return next((key for key in ['official','industry_directory','directory','mall_directory','brand_directory','public_registry'] if key in enabled and matches_channel(key,url)),'')


def reference_urls(prompt: str, enabled: list[str]) -> list[dict]:
    """prompt为当前消息、enabled为设置；最多4个明确HTTP链接作为读取入口，无正文不作为客户证据。"""
    result=[]
    enabled=active_channels(prompt,enabled)
    urls=list(dict.fromkeys(url.rstrip('.,;!') for url in re.findall(r'https?://[^\s<>()\[\]，。；、]+',prompt or '')))[:4]
    for url in urls:
        if blocked_source(url,prompt):continue
        uri=urlparse(url);channel=reference_channel(url,enabled)
        if channel and len(url)<=2000 and not uri.username and not uri.password:result.append({'url':url,'channel':channel})
    return result


def preferred_channels(prompt: str, enabled: list[str]) -> list[str]:
    """prompt为当前非空要求，enabled为启用列表；明确平台先执行，不启用的渠道不会被偷偷开启。"""
    allowed=available_channels(active_channels(prompt,enabled))
    preferred=requested_channels(prompt,enabled)
    return [*preferred,*[key for key in allowed if key not in preferred]]


def source_label(url: str) -> str:
    """url为真实来源，可空；返回平台名或域名，不凭所选查询渠道假定官网身份。"""
    host=(urlparse(url).hostname or '').lower()
    labels={'1688.com':'1688','qcc.com':'企查查','qichacha.com':'企查查','ccgp.gov.cn':'中国政府采购网',
        'szggzy.com':'深圳公共资源交易','gsxt.gov.cn':'国家企业信用公示','creditchina.gov.cn':'信用中国',
        'yunfale.com':'云发了行业目录','b2b168.org':'免费黄页网','b2b168.com':'八方资源网',
        'jc001.cn':'九正建材网','1024sj.com':'1024商务网','hc23.com':'HC23企业目录',
        'leanju.com':'乐安居官网','siemens.com.cn':'西门子官网'}
    return next((label for domain,label in labels.items() if host==domain or host.endswith('.'+domain)),host)


def source_rules(enabled: list[str]) -> str:
    """enabled为任务启用渠道；加载共同及全部启用渠道规则，最多6000字符；超限明确失败，不能静默丢末尾平台。"""
    path=Path(__file__).resolve().parents[1]/'skills/buyer-research/references/runtime-playbook.md'
    content=path.read_text(encoding='utf-8')
    parts=re.split(r'(?m)^## ([a-z0-9_]+)\s*$',content)
    selected=[f'渠道规则[{parts[index]}]\n'+parts[index+1].strip() for index in range(1,len(parts)-1,2) if parts[index]=='common' or parts[index] in enabled]
    value='\n\n'.join(selected)
    if len(value)>6000:raise ValueError('channel_rules_exceed_limit')
    return value
