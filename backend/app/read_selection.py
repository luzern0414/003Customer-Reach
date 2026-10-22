"""读取前的检索信号筛选；不能由摘要授予客户资格或联系方式归属。"""
import re
from urllib.parse import urlparse


def read_selection(row: dict, roles: list[str], region: str, position: int=0) -> dict:
    """row为真实搜索来源，roles为明确目标，region可空，position为原顺序；返回许可/原因/排序键。

    只拒已知供应商聚合页或明确制造且没有目标角色信号的摘要；未知和混合经营保持待核验。
    """
    text=(row.get('title') or '')+'\n'+(row.get('body') or '')
    signals={'dealer':'经销|批发|代理|授权门店','retailer':'零售|专卖店|门市',
        'mall':'家居城|灯饰城|家居卖场|家居商场|入驻商户|入驻品牌',
        'project_buyer':'采购人|采购方|招标人'}
    manufacturing=bool(re.search('生产加工|研发.*生产|生产厂家|厂家直销|专业.*生产|制造商|灯饰厂|灯具厂',text))
    matched=any(re.search(pattern,text) for role,pattern in signals.items() if role in roles) or ('manufacturer' in roles and manufacturing)
    parsed=urlparse(row.get('url',''))
    reason='target_signal' if matched else 'unknown_role'
    allowed=True
    if (parsed.hostname or '').lower() in {'exa.ai','www.exa.ai'} and parsed.path.startswith('/library/'):
        allowed=False;reason='provider_library'
    elif roles and 'manufacturer' not in roles and manufacturing and not matched:
        allowed=False;reason='manufacturer_only'
    local=bool(region and region in text)
    contact=bool(re.search(r'(?<!\d)(?:1[3-9]\d{9}|0\d{2,3}[- ]?\d{7,8})(?!\d)|[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}',text))
    return {'allowed':allowed,'reason':reason,'priority':(manufacturing and not matched,not matched,not local,not contact,position)}
