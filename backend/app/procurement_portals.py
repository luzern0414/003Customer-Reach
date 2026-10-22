"""集团自建电子采购平台目录：央企/大型企业发布自身采购的源头平台。

清单来源：开源项目 BidMonitor-AI（github.com/zhiqianzheng/BidMonitor-AI，src/monitor_core.py 站点表，仅引用网址事实，未复制代码）。
可用状态为 2026-10-10 本项目实测：直接读取或浏览器渲染后首页能看到带日期的公告列表才标记 available；
需要登录、出现滑动验证、robots 禁止、连接失败或首页无公告列表的平台保留在目录中但不访问。
"""
import re
from typing import Literal
from pydantic import BaseModel, Field

Status = Literal['available', 'login_required', 'verification', 'robots_disallowed', 'unreachable', 'no_public_list']


class Portal(BaseModel):
    """一个集团采购平台；groups为判定目标企业所属集团的名称关键词。"""
    key: str
    name: str
    url: str
    groups: list[str] = Field(default_factory=list)
    access: Literal['http', 'browser'] = 'http'
    status: Status = 'no_public_list'
    checked_at: str = '2026-10-10'


PORTALS: list[Portal] = [
    Portal(key='sgcc', name='国家电网新一代电子商务平台', url='https://ecp.sgcc.com.cn/', groups=['国家电网', '国网'], access='browser', status='available'),
    Portal(key='ceec', name='中国能建电子采购平台', url='https://ec.ceec.net.cn/', groups=['中国能源建设', '中国能建', '葛洲坝', '中国电力工程顾问'], access='http', status='available'),
    Portal(key='jchc', name='江苏交通控股招标采购平台', url='https://zbcg.jchc.cn/portal', groups=['江苏交通控股', '江苏交控'], access='browser', status='available'),
    Portal(key='csg', name='中国南方电网供应链服务平台', url='http://www.bidding.csg.cn/', groups=['南方电网', '南网'], status='login_required'),
    Portal(key='powerchina', name='中国电建采购电子商务平台', url='https://ec.powerchina.cn/', groups=['中国电建', '中国电力建设', '电建'], status='login_required'),
    Portal(key='chng', name='华能集团电子商务平台', url='http://ec.chng.com.cn/ecmall/', groups=['华能'], status='unreachable'),
    Portal(key='chdtp', name='中国华电电子商务平台', url='http://www.chdtp.com/', groups=['华电'], status='unreachable'),
    Portal(key='cdt', name='中国大唐电子商务平台', url='http://www.cdt-ec.com/', groups=['大唐'], access='browser', status='no_public_list'),
    Portal(key='neep', name='国家能源e购', url='https://www.neep.shop/', groups=['国家能源', '国能'], access='browser', status='no_public_list'),
    Portal(key='cgnpc', name='中广核电子商务平台', url='https://ecp.cgnpc.com.cn', groups=['中广核', '中国广核'], access='browser', status='no_public_list'),
    Portal(key='ctg', name='中国三峡电子采购平台', url='https://eps.ctg.com.cn/', groups=['三峡'], status='login_required'),
    Portal(key='espic', name='电能e招采（国家电投）', url='https://ebid.espic.com.cn/', groups=['国家电投', '国家电力投资'], status='login_required'),
    Portal(key='sdicc', name='国投集团电子采购平台', url='https://www.sdicc.com.cn/', groups=['国投', '国家开发投资'], status='unreachable'),
    Portal(key='minmetals', name='中国五矿集团供应链管理平台', url='https://ec.minmetals.com.cn/', groups=['五矿'], access='browser', status='no_public_list'),
    Portal(key='cnbm', name='中国建材集团采购平台', url='https://c.cnbm.com.cn/', groups=['中国建材', '中建材'], status='robots_disallowed'),
    Portal(key='ccccltd', name='中交集团供应链管理系统', url='http://ec.ccccltd.cn/', groups=['中国交建', '中交'], status='unreachable'),
    Portal(key='cecep', name='中国节能环保电子采购平台', url='http://www.ebidding.cecep.cn/', groups=['中国节能'], status='unreachable'),
    Portal(key='crc', name='华润集团守正电子招标采购平台', url='https://szecp.crc.com.cn/', groups=['华润'], status='unreachable'),
    Portal(key='faw', name='中国一汽电子招标采购交易平台', url='https://srm.etp.faw.cn/staging', groups=['一汽', '中国第一汽车'], status='unreachable'),
    Portal(key='dongfang', name='东方电气', url='http://nsrm.dongfang.com/', groups=['东方电气'], status='unreachable'),
    Portal(key='xcmg', name='徐工全球数字化供应链系统平台', url='http://xdsc.xcmg.com:8985/', groups=['徐工', '徐州工程机械'], status='no_public_list'),
    Portal(key='longi', name='隆基股份SRM系统', url='https://srm.longi.com:6080', groups=['隆基'], status='login_required'),
    Portal(key='sunwoda', name='欣旺达SRM', url='https://srm.sunwoda.com/', groups=['欣旺达'], status='login_required'),
    Portal(key='powerbeijing', name='北京京能电子商务平台', url='http://www.powerbeijing-ec.com', groups=['京能', '北京能源'], status='unreachable'),
    Portal(key='gdg', name='广州发展集团电子采购平台', url='https://eps.gdg.com.cn/', groups=['广州发展'], status='unreachable'),
    Portal(key='hghn', name='华光环能数字化采购管理平台', url='https://hgcg.hghngroup.com/', groups=['华光环能'], status='no_public_list'),
]
DATE_RE = re.compile(r'(20\d{2})[-./年](\d{1,2})[-./月](\d{1,2})')
NOTICE_RE = re.compile('采购|招标|询价|中标|成交|结果|公告|比选|竞争性|谈判|候选')


def portals_for(company: str) -> list[Portal]:
    """company为企业全称；返回其所属集团、当前可读的采购平台（按集团关键词匹配）。"""
    name = re.sub(r'\s+', '', company or '')
    return [p for p in PORTALS if p.status == 'available' and any(g in name for g in p.groups)]


def parse_portal_notices(text: str) -> list[dict]:
    """text为平台首页正文（Markdown或纯文本）；返回带日期的公告标题，去掉图片标记与列表符号。"""
    rows, seen = [], set()
    for raw in (text or '').splitlines():
        line = re.sub(r'!\[[^\]]*\]\([^)]*\)', ' ', raw)
        line = re.sub(r'^\s*[-*•]\s*', '', line)
        line = re.sub(r'\s+', ' ', line).strip()
        date = DATE_RE.search(line)
        if not date or not NOTICE_RE.search(line): continue
        title = DATE_RE.sub('', line).strip(' |-·')
        if not 6 <= len(title) <= 200 or title in seen: continue
        seen.add(title)
        rows.append({'title': title, 'published_at': f'{date.group(1)}-{int(date.group(2)):02d}-{int(date.group(3)):02d}'})
    return rows


def name_variants(company: str) -> list[str]:
    """company为企业全称；返回用于匹配公告标题的写法（全称、去“有限公司/有限责任公司”后缀）。"""
    name = re.sub(r'\s+', '', company or '')
    short = re.sub(r'(股份)?有限(责任)?公司$', '', name)
    return list(dict.fromkeys([v for v in (name, short) if len(v) >= 4]))
