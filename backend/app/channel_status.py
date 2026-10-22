"""渠道能力与最近工具实测分开展示；不将一次读页成功泛化为整个平台可访问。"""
import time
from sqlalchemy import select,func
from .db import Session,ToolCall
from .source_catalog import CHANNELS


def channel_status(enabled: list[str], options: dict | None = None) -> list[dict]:
    """enabled为设置中的渠道ID（可为空）；返回白名单最近检索/读取结果，不联网、不返回凭据或正文。

    记录仅代表该次调用；供应商冷却作用于检索，站点限制只保留所属读取记录，不覆盖其他渠道。
    """
    clock=time.time()
    with Session() as db:
        ranked=select(ToolCall.id,func.row_number().over(partition_by=(ToolCall.channel,ToolCall.tool),
            order_by=(ToolCall.last_attempt_epoch.desc(),ToolCall.updated_at.desc(),ToolCall.id.desc())).label('rank')).where(
                ToolCall.tool.in_(['search_accounts','fetch_source','search_tenders','get_tender_detail','qcc_company_lookup','qcc_operation_lookup','qcc_risk_lookup','qcc_tender_lookup']),ToolCall.attempts>0).subquery()
        rows=list(db.scalars(select(ToolCall).join(ranked,ToolCall.id==ranked.c.id).where(ranked.c.rank==1)))
        provider_until=db.scalar(select(func.max(ToolCall.retry_after_epoch)).where(ToolCall.status=='rate_limited',
            ToolCall.result['error'].as_string()=='provider_rate_limited',ToolCall.retry_after_epoch>clock)) or 0
    recent={(row.channel,row.tool):row for row in rows}
    labels={'completed':'最近成功','rate_limited':'最近受限','unavailable':'最近读取失败',
        'rejected':'最近未通过','failed':'最近失败','paused':'最近已暂停','running':'执行中'}
    result=[]
    for key,capability in CHANNELS.items():
        runtime={}
        for operation,tool in [('search','search_accounts'),('read','fetch_source')]:
            row=recent.get((key,tool));value=row.result or {} if row else {}
            sources=value.get('sources') or []
            status=(row.status if row else 'unverified')
            label=labels.get(status,'未使用过')
            if status=='completed' and not sources:label='最近无结果'
            runtime[operation]={'status':status,'label':label,'checked_at':row.updated_at if row else None,
                'source_count':len(sources),'elapsed_ms':row.elapsed_ms if row else None}
        # 供应商冷却不等于站点拒绝，公开HTTP读取继续独立保留最近结果。
        runtime['search']['cooling_down']=bool(provider_until and capability.get('objective'))
        if runtime['search']['cooling_down']:runtime['search']['label']='检索服务冷却中'
        result.append({**capability,'id':key,'enabled':key in enabled,'runtime':runtime})
    from .config import qcc_mcp_configured
    from .bidresearch_mcp import runtime_status
    import os
    options=options or {}
    for key,name,configured,mode,enabled_key,description in [
        ('qcc_mcp','企查查授权 MCP',qcc_mcp_configured(),'authorized_mcp','qcc_enabled','企业主体与工商字段；仅使用已配置的官方授权接口'),
        ('bidresearch','公开采购检索',runtime_status()['installed'],'local_mcp','bidresearch_enabled','优先公共资源与必联网；保留公告原文、买方、金额及来源限制')]:
        matches=[row for row in rows if row.channel==key or key=='bidresearch' and row.channel=='bidresearch_detail']
        latest=next(iter(matches),None)
        if latest:
            latest=max(matches,key=lambda row:(row.last_attempt_epoch or 0,row.updated_at,row.id))
        value=latest.result or {} if latest else {}
        state=latest.status if latest else 'unverified'
        observation={'status':state,'label':labels.get(state,'未使用过'),'checked_at':latest.updated_at if latest else None,
                     'source_count':len(value.get('sources') or []),'elapsed_ms':latest.elapsed_ms if latest else None,'cooling_down':False}
        if latest and state=='completed' and not observation['source_count']:observation['label']='最近无结果'
        available=options.get(enabled_key,True) and os.getenv('CLIENTREACH_QCC_ENABLED' if key=='qcc_mcp' else 'CLIENTREACH_BIDRESEARCH_ENABLED','').lower() not in {'0','false','off'}
        read=dict(observation)
        if key=='bidresearch':
            detail=max((row for row in matches if row.tool=='get_tender_detail'),key=lambda row:(row.last_attempt_epoch or 0,row.updated_at,row.id),default=None)
            if detail:read={'status':detail.status,'label':labels.get(detail.status,'未使用过'),'checked_at':detail.updated_at,
                'source_count':len((detail.result or {}).get('sources') or []),'elapsed_ms':detail.elapsed_ms,'cooling_down':False}
        result.append({'id':key,'name':name,'status':'ready' if configured else 'authorization_required' if key=='qcc_mcp' else 'not_installed',
            'description':description,'mode':mode,'configured':configured,'enabled':bool(available),'runtime':{'search':observation,'read':read}})
    return result
