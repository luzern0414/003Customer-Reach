"""工具账本到界面的最小投影，避免把整页正文或模型内部输出重复传给浏览器。"""


def tool_arguments(arguments: dict | None) -> dict:
    """arguments为可空工具入参；返回渠道/查询/URL等可见参数，忽略凭据与任意额外字段。"""
    args = arguments or {}
    result = {key: str(args[key])[:2000] for key in ['query', 'url', 'channel', 'schema'] if args.get(key)}
    if isinstance(args.get('candidate'), dict):
        result['customer'] = args['candidate'].get('display_name', '')
    if isinstance(args.get('snapshot'), dict): result['company'] = args['snapshot'].get('name', '')
    for key in ('name','company','action','mode','source'):
        if isinstance(args.get(key),str) and args[key]:result[key]=args[key][:200]
    if isinstance(args.get('keywords'),list):result['keywords']=[str(k)[:100] for k in args['keywords'][:3]]
    return result


def tool_result(result: dict | None) -> dict:
    """result为可空真实结果；返回来源数/链接/知识命中/错误，不返回正文或模型输出。"""
    value = result or {}
    sources = value.get('sources') or []
    return {'source_count': len(sources), 'sources': [{'title': x.get('title', ''), 'url': x.get('url', '')}
            for x in sources[:5]], 'knowledge_count': len(value.get('knowledge') or []),
            'error': str(value.get('error') or '')[:240], 'reused': bool(value.get('reused')),
            'read_summary':read_summary(value.get('read_outcome')), 'company_id':value.get('company_id'),
            'accepted_fields':value.get('accepted_fields',0),'rejected_count':len(value.get('rejected') or []),
            'fresh_source_count':len(value.get('fresh_source_ids') or []),'cached_source_count':len(value.get('cached_source_ids') or []),
            'local_dataset_count':len(value.get('datasets') or []),'network_attempted':bool(value.get('network_attempted')),
            'diagnostics':diagnostic_view(value.get('diagnostics'))}


def diagnostic_view(value):
    """Only bounded scalar counters; never expose arbitrary upstream fields."""
    if not isinstance(value,dict):return {}
    result={key:val for key,val in value.items() if key in {'raw_count','date_rejected','subject_rejected','access_rejected','duplicate_count','limit_rejected','full_text_count','navigation_count','confirmed_count','missing_body_count','details_attempted','details_failed','unique_record_count'} and isinstance(val,int) and not isinstance(val,bool) and 0<=val<=10000}
    if value.get('mode') in {'history','recent'}:result['mode']=value['mode']
    return result


def read_summary(outcome: dict | None) -> str:
    """outcome为可空读取状态/计数；仅映射已知主/备用状态为简短文本，未知或成功返回空，不输出原文/URL/任意键值。"""
    if not isinstance(outcome,dict):return ''
    if not isinstance(outcome.get('primary_status'),str) or not isinstance(outcome.get('fallback_status'),str):return ''
    primary={'empty_body':'网页无可用正文','failed':'网页读取失败','unsupported_content':'页面内容无法直接解析','redirect_limit':'网页跳转未完成'}.get(outcome.get('primary_status'))
    fallback={'provider_rate_limited':'备用读取服务受限','empty_body':'备用读取也未取得正文'}.get(outcome.get('fallback_status'))
    return primary+'，'+fallback if primary and fallback else ''


def tool_view(row) -> dict:
    """row须为真实ToolCall行；返回UI轨迹、时间、受限参数及结果摘要，不存在由调用方处理。"""
    return {'id': row.id, 'operation_id': row.operation_id, 'tool': row.tool, 'channel': row.channel,
            'arguments': tool_arguments(row.arguments), 'status': row.status, 'elapsed_ms': row.elapsed_ms,
            'created_at': row.created_at, 'attempts': row.attempts or 1, **tool_result(row.result)}


def trace_tool_inputs(inputs: dict) -> dict:
    """inputs为LangSmith绑定后的工具方法参数；仅保留白名单摘要，不序列化self/凭据。"""
    return {'tool': inputs.get('name', ''), **tool_arguments(inputs.get('arguments'))}
