"""任务调度：在 API 进程内以 asyncio 任务运行研究管线，支持暂停、继续与用户交接。"""
import asyncio
import logging

from sqlalchemy import select, update

from . import crawl
from .db import Job, Session, now
from .events import emit
from .research.pipeline import Handover, Run

log = logging.getLogger('dealradar.runner')
_tasks: dict[str, asyncio.Task] = {}
FAILURE_TEXT = {'ValueError': '模型配置无效或返回格式错误', 'CrawlError': '采集工具不可用，请检查 LuzCrawl'}


def _status(job_id: str, status: str, **fields) -> None:
    with Session.begin() as db:
        job = db.get(Job, job_id)
        job.status = status
        for key, value in fields.items():
            setattr(job, key, value)
        payload = {'status': status, 'stage': job.stage, 'metrics': job.metrics, 'handover': job.handover,
                   'error': job.error}
    emit(job_id, 'status', payload)


async def _run(job_id: str) -> None:
    _status(job_id, 'running', started_at=now(), handover={}, error='')
    try:
        final = await Run(job_id).execute()
        _status(job_id, final, finished_at=now())
    except Handover as exc:
        _status(job_id, 'awaiting_user', handover=exc.data)
    except asyncio.CancelledError:
        _status(job_id, 'paused')
        raise
    except Exception as exc:  # 任务失败要落库并通知前端，不能让后台任务静默结束
        log.exception('job %s failed', job_id)
        _status(job_id, 'failed', finished_at=now(), error=FAILURE_TEXT.get(type(exc).__name__, '') or str(exc)[:300])
    finally:
        _tasks.pop(job_id, None)


def start(job_id: str) -> None:
    if job_id not in _tasks:
        _tasks[job_id] = asyncio.create_task(_run(job_id))


def pause(job_id: str) -> bool:
    task = _tasks.get(job_id)
    if task:
        task.cancel()
        return True
    return False


async def resume(job_id: str, choice: str = '', skip: bool = False) -> None:
    """继续任务。identity 交接写入所选企业；login/verify 交接关闭 LuzCrawl 停放页后重读，skip 跳过该站点。"""
    with Session.begin() as db:
        job = db.get(Job, job_id)
        handover, plan = dict(job.handover or {}), dict(job.plan or {})
        if handover.get('kind') == 'identity' and choice:
            plan['identity_choice'] = choice
        if skip and handover.get('site'):
            plan['skip_sites'] = list({*plan.get('skip_sites', []), handover['site']})
        job.plan, job.handover = plan, {}
    if handover.get('task_id'):
        await crawl.cancel(handover['task_id'])
    start(job_id)


def recover() -> None:
    """进程重启：把中断的任务标记为已暂停，用户可点“继续”。"""
    with Session.begin() as db:
        db.execute(update(Job).where(Job.status.in_(['running', 'queued'])).values(status='paused'))


def active(job_id: str) -> bool:
    return job_id in _tasks


def queued_jobs() -> list[str]:
    with Session() as db:
        return list(db.scalars(select(Job.id).where(Job.status == 'queued')))
