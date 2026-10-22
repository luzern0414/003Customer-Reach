"""统计字段的日期与口径原文校验；不以成立、发布时间或采集时间补统计周期。"""
import re
from datetime import date


def valid_statistics(scope: str, period: str, quote: str) -> bool:
    """scope/period为模型元数据、quote为连续原文，可空；日期须合法且原文支持、口径须原文字串，否则返回False，不补年月日。"""
    scope=(scope or '').strip();period=(period or '').strip();quote=quote or ''
    normalize=lambda value:re.sub(r'\s+','',value)
    if not scope or not period or normalize(scope) not in normalize(quote):return False
    match=re.fullmatch(r'(\d{4})(?:-(\d{2})(?:-(\d{2}))?)?',period)
    if not match:return False
    year=int(match[1]);month=int(match[2]) if match[2] else None;day=int(match[3]) if match[3] else None
    try:date(year,month or 1,day or 1)
    except ValueError:return False
    pattern=re.escape(match[1])
    if month is not None:pattern+=r'(?:年|[-/.])0?'+str(month)+r'(?!\d)'
    if day is not None:pattern+=r'(?:月|[-/.])0?'+str(day)+r'(?!\d)'
    text=normalize(quote)
    for occurrence in re.finditer(r'(?<!\d)'+pattern+r'(?!\d)',text):
        before=text[max(0,occurrence.start()-35):occurrence.start()]
        after=text[occurrence.end():occurrence.end()+15]
        if month is None and not (re.match(r'年|[-/.]\d{1,2}',after) or
            re.search(r'(?:年度|年份|统计期|报告期|截至|截止|统计日期)[：:]*$',before)):continue
        # 相邻登记/发布/页脚标签不是该字段的统计日期；不因它出现在同一引文就授予口径。
        if re.search(r'(?:成立|创建|注册|采集|发布|更新)(?:日期|时间|于)?[：:为于]*$|(?:型号|版本|编号)[：:为]*$|(?:版权所有|copyright|©)[^\d]*$',before,re.I):continue
        if re.match(r'(?:年|月|日)?(?:本公司|公司)?(?:成立|创建|注册)',after):continue
        return True
    return False
