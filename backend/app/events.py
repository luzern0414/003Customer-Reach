"""任务事件：写入 job_events 表并通过 SSE 推送；客户端用 after 游标断点续读。"""
import asyncio
import json
from collections.abc import AsyncIterator

from sqlalchemy import select

from .db import Job, JobEvent, Session

TERMINAL = {'completed', 'partial', 'failed', 'paused', 'awaiting_user'}
_waiters: dict[str, asyncio.Event] = {}


def emit(job_id: str, type_: str, data: dict) -> None:
    with Session.begin() as db:
        db.add(JobEvent(job_id=job_id, type=type_, data=data))
    waiter = _waiters.get(job_id)
    if waiter:
        waiter.set()


def events_after(job_id: str, after: int, limit: int = 200) -> list[JobEvent]:
    with Session() as db:
        return list(db.scalars(select(JobEvent).where(JobEvent.job_id == job_id, JobEvent.id > after)
                               .order_by(JobEvent.id).limit(limit)))


def _job_status(job_id: str) -> str:
    with Session() as db:
        job = db.get(Job, job_id)
        return job.status if job else 'failed'


async def sse(job_id: str, after: int, is_disconnected) -> AsyncIterator[str]:
    """先补发 after 之后的历史事件，再等待新事件；任务进入终态且事件排空后结束。"""
    cursor = after
    waiter = _waiters.setdefault(job_id, asyncio.Event())
    while not await is_disconnected():
        waiter.clear()
        batch = events_after(job_id, cursor)
        for item in batch:
            cursor = item.id
            yield f'id: {item.id}\nevent: {item.type}\ndata: {json.dumps(item.data, ensure_ascii=False)}\n\n'
        if batch:
            continue
        if _job_status(job_id) in TERMINAL:
            break
        try:
            await asyncio.wait_for(waiter.wait(), 15)
        except asyncio.TimeoutError:
            yield ': keepalive\n\n'
