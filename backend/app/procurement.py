"""采购公告的保留与展示投影；原文阶段不重写，时效状态按上海业务时间计算。"""
import re
from datetime import datetime


def closed_notice(title: str, body: str) -> bool:
    """已结束/暂停/撤回的公告不产生开放采购分，不以尚未到期的旧日期覆盖明确状态。"""
    if re.search('中标|成交结果|合同公告|终止|废标|流标|已结束|暂停|撤销|撤回|取消',title or ''):return True
    for match in re.finditer(r'(?:本项目|本次采购|本次招标)(?:现|已|决定|予以)?(?:暂停|取消|停止|终止|废标|撤回|成交|结束)'
            r'(?:(?:采购|招标)(?:活动|流程)?)?(?=[，。；;！\n]|$)',body or ''):
        prefix=re.split(r'[。；;！\n]',body[:match.start()])[-1]
        if not re.search(r'(?:^|[，,\s])(?:若|如|如果|假如|倘若|一旦)[^。；;\n]{0,80}$',prefix):return True
    return False


def open_buyer_signal(name, signal, source, stamp):
    """原文证明买方、正式提交期限与开放状态，模型建议不单独构成当前采购机会。"""
    if not signal or not source or signal.stage!='open' or signal.participant_role!='buyer' or signal.buyer!=name:return False
    if not signal.deadline or signal.deadline<=stamp:return False
    from .evidence_role import buyer_identity
    from .procurement_accounts import submission_deadline
    buyer_quote=signal.buyer_quote or signal.quote
    deadline_quote=signal.deadline_quote or signal.quote
    body=source['body'];compact=lambda value:re.sub(r'\s+','',value)
    return bool(buyer_identity(name,buyer_quote) and compact(buyer_quote) in compact(body)
        and compact(deadline_quote) in compact(body) and deadline_in_quote(signal.deadline,deadline_quote)
        and submission_deadline(body)[0]==signal.deadline and not closed_notice(source.get('title',''),body))


def deadline_in_quote(value: str, quote: str) -> bool:
    """value为规范截止时间、quote为同源原文；验证日期和时分秒可追溯，缺时间不猜午夜，坏值返回False。"""
    try:stamp=datetime.strptime(value,'%Y-%m-%d %H:%M:%S')
    except ValueError:return False
    date=fr'{stamp.year}[-年/]0?{stamp.month}[-月/]0?{stamp.day}(?:日)?'
    seconds=fr'(?:[:：]0?{stamp.second})?' if stamp.second==0 else fr'[:：]0?{stamp.second}'
    time=fr'(?<!\d)0?{stamp.hour}[:：]0?{stamp.minute}{seconds}(?![:：\d])'
    return bool(re.search(date,quote) and re.search(time,quote))


def signals(qualification: dict | None) -> list[dict]:
    """qualification为可空资格JSON；返回保留公告，兼容旧单条字段，不推断缺失日期或来源。"""
    value=qualification or {}
    rows=[dict(x) for x in value.get('procurement_signals',[]) if isinstance(x,dict)]
    primary=value.get('procurement_signal')
    if primary and not any(x.get('source_id')==primary.get('source_id') and x.get('quote')==primary.get('quote') for x in rows):
        rows.append({**primary,'intent_score':value.get('signal_score',0)})
    return rows


def signal_status(record: dict, stamp: str) -> str:
    """record为已校验公告，stamp为上海当前时间；返回展示状态，原始stage/deadline不改动。"""
    verification=record.get('verification')
    if verification=='disputed':return '争议'
    if verification=='inactive':return '失效'
    stage=record.get('stage')
    if stage=='open':
        deadline=record.get('deadline','')
        if not re.fullmatch(r'\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}',deadline):return '期限待核验'
        if deadline<=stamp:return '已过期'
        return '公开采购' if record.get('intent_score',0)==10 else '待核验公告'
    return {'awarded':'中标历史','closed':'已结束','historical':'历史公告'}.get(stage,'待核验')


def signal_score(qualification: dict, facts: dict, stamp: str) -> int:
    """资格JSON及事实可空，stamp非空；只按选中已校验买方公告加分，争议/失效/过期均返回0。"""
    primary=qualification.get('procurement_signal') or {}
    if not qualification.get('eligible') or any(facts.get(key,{}).get('verification') in {'disputed','inactive'} for key in ['buyer_role','procurement']):return 0
    record=next((x for x in reversed(signals(qualification)) if x.get('source_id')==primary.get('source_id') and x.get('quote')==primary.get('quote')),primary)
    return 10 if record.get('intent_score',qualification.get('signal_score',0))==10 and record.get('participant_role')=='buyer' and signal_status(record,stamp)=='公开采购' else 0


def procurement_views(qualification: dict | None, stamp: str) -> list[dict]:
    """qualification可空、stamp为业务当前时间；同源同买方同截止只展示完整项，历史JSON不改写。"""
    primary=(qualification or {}).get('procurement_signal') or {}
    grouped={}
    for record in reversed(signals(qualification)):
        selected=all(record.get(key)==primary.get(key) for key in ['source_id','quote','stage','deadline'])
        # 同一公告在补查轮次可能换项目/日期引文，不能向销售重复展示为多个采购机会。
        key=tuple(record.get(field,'') for field in ['source_id','buyer','participant_role','deadline'])
        previous=grouped.get(key)
        size=lambda row:(bool(re.search('项目|招标公告|采购公告',row.get('quote','') or '')),
            sum(len(row.get(field,'') or '') for field in ['quote','buyer_quote','deadline_quote']))
        if previous is not None:
            selected=selected or previous['selected']
            verification=next((row.get('verification') for row in [previous,record] if row.get('verification') in {'inactive','disputed'}),None)
            record=dict(record if size(record)>size(previous) else previous)
            if verification:record['verification']=verification
        grouped[key]={**record,'selected':selected}
    result=[]
    for record in grouped.values():
        status=signal_status(record,stamp)
        result.append({**record,'display_status':'历史公告' if not record['selected'] and status=='公开采购' else status})
    return result
