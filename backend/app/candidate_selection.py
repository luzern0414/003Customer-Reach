"""候选预排序只服务读取/保存顺序，不能代替角色、主体和持久事实校验。"""
import re
from .contact_view import contact_view


def candidate_priority(candidate: dict, sources: dict) -> tuple:
    """candidate为模型原候选、sources为本任务真实来源映射；按有原文的联系格式排序，空/冲突低优先，无写入及接通保证。"""
    facts={};values={}
    normalize=lambda text:re.sub(r'\s+','',text or '')
    for fact in candidate.get('facts',[]):
        field=fact.get('field');value=fact.get('value','');quote=fact.get('quote','')
        source=sources.get(fact.get('source_id'),{})
        # 无本任务原文或伪造引文不能凭看起来完整的号码抢占候选排序。
        if not value or not quote or normalize(value) not in normalize(quote) or normalize(quote) not in normalize(source.get('body','')):continue
        values.setdefault(field,set()).add(value)
        facts[field]=fact
    # 不在预排序中替冲突候选择某一值；并存联系的完整语义仍交持久校验判断。
    facts={field:fact for field,fact in facts.items() if len(values[field])==1}
    usable=contact_view(facts,[])['usable_fields']
    return (bool({'phone','email','wechat'}&set(usable)),bool(usable),sum(field in facts for field in ['address','categories']))
