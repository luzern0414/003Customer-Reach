"""复用LangSmith原生LangGraph追踪；只读独立追踪凭据，是否上传输入/输出由config/langsmith.json或环境变量决定（默认隐藏）。"""
import json
import os
import re
from functools import lru_cache
from .config import ROOT,langsmith_key


def tracing_status() -> dict:
    """无参数；返回追踪开关/配置状态/项目名，永不返回密钥；损坏配置视为关闭。"""
    path = ROOT / 'config/langsmith.json'
    try:
        options = json.loads(path.read_text(encoding='utf-8-sig')) if path.exists() else {}
    except (ValueError, OSError):
        options = {}
    if not isinstance(options, dict):
        options = {}
    flag = os.getenv('LANGSMITH_TRACING', str(options.get('enabled', False))).lower() in {'true','1','yes'}
    configured = bool(langsmith_key(ROOT/'config/apikey.txt'))
    return {'provider': 'LangSmith', 'configured': configured, 'enabled': flag and configured,
            'project': str(os.getenv('LANGSMITH_PROJECT') or options.get('project') or 'client-reach')[:128],
            'hide_inputs': os.getenv('LANGSMITH_HIDE_INPUTS', str(options.get('hide_inputs', True))).lower() not in {'false', '0', 'no'},
            'hide_outputs': os.getenv('LANGSMITH_HIDE_OUTPUTS', str(options.get('hide_outputs', True))).lower() not in {'false', '0', 'no'}}


def trace_scope(job_id: str, conversation_id: str):
    """两个ID均非空；返回官方追踪上下文，缺少key或关闭时无网络，元信息只含关联ID。"""
    status = tracing_status()
    from langsmith import tracing_context
    if not status['enabled']:
        return tracing_context(enabled=False)
    try:
        client = _client(langsmith_key(ROOT/'config/apikey.txt'), os.getenv('LANGSMITH_ENDPOINT', 'https://api.smith.langchain.com'),
                         status['hide_inputs'], status['hide_outputs'], os.getenv('LANGSMITH_WORKSPACE_ID'))
    except Exception as exc:
        # 追踪是辅助能力，配置/SDK初始化故障不能使正常回答失败；只记异常类型。
        from .observability import logger
        logger('tracing').warning('tracing_unavailable', extra={'details': {'error_type': type(exc).__name__}})
        return tracing_context(enabled=False)
    return tracing_context(enabled=True, client=client, project_name=status['project'],
        metadata={'job_id': job_id, 'conversation_id': conversation_id}, tags=['client-reach'])


@lru_cache(maxsize=4)
def _client(key: str, endpoint: str, hide_inputs: bool, hide_outputs: bool, workspace: str | None):
    from langsmith import Client
    return Client(api_key=key, api_url=endpoint, hide_inputs=hide_inputs, hide_outputs=hide_outputs, workspace_id=workspace)


def research_trace(job_id: str) -> dict:
    """job_id非空；只读云端安全元数据及真实轨迹URL，缺任务404，追踪不可用不使资料研究回滚。"""
    from .db import Session, Job
    from .service import ServiceError
    with Session() as db:
        job=db.get(Job,job_id)
        if not job:raise ServiceError('任务不存在',404)
        trace_id=(job.metrics or {}).get('langsmith_trace_id')
    status=tracing_status()
    result={'provider':'LangSmith','enabled':status['enabled'],'available':False,'trace_id':trace_id,'url':'','runs':[]}
    if not status['enabled'] or not trace_id:return result
    stage='read_root'
    try:
        client=_client(langsmith_key(ROOT/'config/apikey.txt'),os.getenv('LANGSMITH_ENDPOINT','https://api.smith.langchain.com'),True,True,os.getenv('LANGSMITH_WORKSPACE_ID'))
        root=client.read_run(trace_id)
        stage='list_children'
        # 当前云端单次查询上限为100；不以客户端更大limit导致整条链路预览失败。
        runs=list(client.list_runs(trace_id=trace_id,limit=100))
        stage='run_url'
        result.update(available=True,url=client.get_run_url(run=root),truncated=len(runs)>=100,runs=[{'id':str(run.id),'name':run.name,'type':run.run_type,
            'parent_id':str(run.parent_run_id) if run.parent_run_id else None,
            'elapsed_ms':round((run.end_time-run.start_time).total_seconds()*1000) if run.end_time and run.start_time else None,
            'has_error':bool(run.error),'tool_name':((run.extra or {}).get('metadata') or {}).get('tool_name'),
            'phase':((run.extra or {}).get('metadata') or {}).get('phase')} for run in runs])
    except Exception as exc:result.update(error_type=type(exc).__name__,error_stage=stage)
    return result


def run_config(job_id: str, prompt: str, intent: str, query_mode: str) -> dict:
    """job_id/prompt为当前任务、intent/query_mode可空；返回LangGraph根运行的名称、标签与元数据，便于在LangSmith按任务检索。"""
    title = re.sub(r'\s+', ' ', prompt or '').strip()[:28]
    return {'run_name': 'Client Reach · ' + (title or job_id[:8]),
            'tags': ['client-reach', 'intent:' + (intent or 'auto'), 'mode:' + (query_mode or 'auto')],
            'metadata': {'job_id': job_id, 'query_mode': query_mode or 'auto'}}


def record_quality(job_id: str) -> dict:
    """job_id非空；任务结束后汇总可核验产出并作为feedback写入LangSmith根运行，追踪关闭或失败时只返回本地指标。"""
    from sqlalchemy import select, func
    from .db import Session, Job
    from .company_models import CompanyFact, TenderRecord, TenderRelation
    with Session() as db:
        job = db.get(Job, job_id)
        if not job: return {}
        metrics = job.metrics or {}
        ids = list(job.company_ids or [])
        count = lambda model, *where: db.scalar(select(func.count()).select_from(model).where(*where)) or 0
        quality = {'company_count': len(ids),
                   'verified_facts': count(CompanyFact, CompanyFact.company_id.in_(ids)) if ids else 0,
                   'tender_purchases': count(TenderRecord, TenderRecord.job_id == job_id, TenderRecord.role == 'buyer'),
                   'tender_wins': count(TenderRecord, TenderRecord.job_id == job_id, TenderRecord.role == 'winner'),
                   'tender_details': count(TenderRecord, TenderRecord.job_id == job_id, TenderRecord.confidence == 'detail'),
                   'counterparties': count(TenderRelation, TenderRelation.company_id.in_(ids)) if ids else 0,
                   'model_calls': (metrics.get('model_budget') or {}).get('calls', 0),
                   'elapsed_seconds': round((job.elapsed_ms or 0) / 1000)}
        trace_id, status = metrics.get('langsmith_trace_id'), job.status
    status_info = tracing_status()
    if not status_info['enabled'] or not trace_id: return quality
    try:
        client = _client(langsmith_key(ROOT/'config/apikey.txt'), os.getenv('LANGSMITH_ENDPOINT', 'https://api.smith.langchain.com'),
                         status_info['hide_inputs'], status_info['hide_outputs'], os.getenv('LANGSMITH_WORKSPACE_ID'))
        for key, value in quality.items():
            client.create_feedback(trace_id, key=key, score=value)
        client.create_feedback(trace_id, key='job_status', value=status, score=1 if status == 'completed' else 0.5 if status == 'partial' else 0)
    except Exception as exc:
        from .observability import logger
        logger('tracing').warning('quality_feedback_failed', extra={'details': {'error_type': type(exc).__name__}})
    return quality
