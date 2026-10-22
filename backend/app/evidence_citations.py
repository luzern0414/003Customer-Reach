"""纯引用合并工具；不猜来源、不拼接片段，不依赖模型或数据库。"""


def append_citations(payload: dict | None, source_id: str, spans: dict, url='') -> dict:
    """合并一个真实来源本次各角色原文，返回新字典，不修改输入。

    参数：payload为既有JSON元信息，可空；source_id为已核验Evidence ID，不可空；
    spans为value/metadata/publication/deadline/budget/buyer/quantity到原文字符串，空片段跳过；
    url为实际Evidence原站地址，空时不补造。返回：带去重source_citations的JSON。
    异常：source_id为空抛ValueError；片段只原样保存，连续原文/主体校验由调用者负责。
    """
    if not source_id:raise ValueError('来源ID不可为空')
    result={**(payload or {})}
    citations=[item for item in (result.get('source_citations') or []) if isinstance(item,dict)]
    for role,quote in spans.items():
        if role not in {'value','metadata','publication','deadline','budget','buyer','quantity','project_number'} or not isinstance(quote,str) or not quote.strip():continue
        key=(source_id,quote,role)
        if any((item.get('source_id'),item.get('quote'),item.get('role','value'))==key for item in citations):continue
        citations.append({'source_id':source_id,'quote':quote,'role':role,**({'url':url} if url else {})})
    return {**result,'source_citations':citations}
