"""用户明确客群优先于成品经销默认规则；制造角色不等于已确认采购。"""
import re


def manufacturer_target(prompt: str) -> bool:
    """prompt为当前任务原要求，可空；只有正向寻找制造企业才启用，卖方自述/排除厂家/网页内容不能授权。"""
    maker=r'(?:制造商|生产[^，。；\n]{0,12}(?:企业|公司|厂家|工厂)|制造[^，。；\n]{0,12}(?:企业|公司|厂家|工厂)|生产厂家|工厂|厂家|灯具厂)'
    guarded=re.sub(r'[^，。；\n]*(?:不要|不能|不应)(?:把|将)[^，。；\n]*(?:已确认|已采购|采购意向|采购客户|采购需求)[^，。；\n]*','',prompt or '')
    if re.search(r'(?:排除|不(?:找|要|包括|考虑|需要|想|用)|禁止)[^，。；\n]{0,16}'+maker,guarded):return False
    if re.search(maker+r'[^，。；\n]{0,6}(?:除外|不要|不考虑)',prompt or ''):return False
    for clause in re.split(r'[，。；,;\n]',prompt or ''):
        if re.search(maker+r'的(?:经销商|代理商|零售门店|门店)',clause):continue
        if re.search(r'(?:买家(?:画像)?|客户(?:画像|群体)?|目标(?:客户|买家|企业)|只找|寻找|查找|找|核验|复核)[^，。；\n]{0,24}'+maker,clause):return True
    return False
