"""单实例独立Worker：持久任务领取、心跳和重启恢复，不依赖网页保持打开。"""
import asyncio
import os
import time
from sqlalchemy import select, update
from .config import DATA
from .db import Session, Job, Setting, initialize, now
from .agent import run_job
from .service import record_event, tick_clock, settle_interrupted_clock
from .observability import logger

LOG = logger('agent')


async def heartbeat() -> None:
    """每5秒写Worker心跳；取消时退出，原始附件与密钥不进入日志。"""
    while True:
        tick_clock()
        with Session.begin() as db:
            row = db.get(Setting, 'worker')
            value = {'last_seen': now(), 'pid': os.getpid(), 'heartbeat_epoch':time.time()}
            if row:
                row.value = value
            else:
                db.add(Setting(key='worker', value=value))
        await asyncio.sleep(5)


async def maintenance() -> None:
    """无参数；非关键资料在独立线程小批整理，持久pending保障重启恢复，不占Agent任务槽。"""
    from .research_dataset import drain_deferred
    while True:
        try:await asyncio.to_thread(drain_deferred,4)
        except Exception as exc:
            from .observability import safe_error
            LOG.warning('maintenance_failed',extra={'details':{'error_type':safe_error(exc)}})
        await asyncio.sleep(1)


async def loop() -> None:
    """恢复遗留任务后最多两个并发任务；业务路由统一交给图中的模型意图节点。"""
    initialize()
    with Session.begin() as db:
        # 新Worker进程不存在上一个进程的在途客户端；保留预算，但解除已失效的清理等待。
        for row in db.scalars(select(Job).where(Job.metrics['pending_cleanup'].as_integer()>0)):
            row.metrics={**(row.metrics or {}),'pending_cleanup':0}
        for row in db.scalars(select(Job).where(Job.status.in_(['running', 'cancelling']))):
            settle_interrupted_clock(row,db)
            row.status, row.stage, row.error = 'paused', '服务中断，等待恢复', 'Worker曾中断，可以恢复任务'
            row.clock_at=None
    beat = asyncio.create_task(heartbeat())
    background = asyncio.create_task(maintenance())
    LOG.info('worker_started', extra={'details': {'pid': os.getpid()}})
    running={}
    try:
        while True:
            for key,(task,kind) in list(running.items()):
                if task.done():
                    task.result();running.pop(key)
            job_id = None;selected_kind=None
            with Session.begin() as db:
                queued=list(db.scalars(select(Job).where(Job.status=='queued').order_by(Job.created_at).limit(50)))
                row=None
                if len(running)<2 and queued:row=queued[0];selected_kind='task'
                if row:
                    if row.cancel_requested:
                        row.status = 'paused'
                    else:
                        claimed = db.execute(update(Job).where(Job.id == row.id, Job.status == 'queued')
                                             .values(status='running', updated_at=now())).rowcount
                        if claimed:
                            job_id = row.id
            if job_id:
                running[job_id]=(asyncio.create_task(run_job(job_id)),selected_kind)
            else:
                await asyncio.sleep(.2)
    finally:
        tick_clock()
        beat.cancel()
        background.cancel()
        for task,kind in running.values():task.cancel()
        await asyncio.gather(*(task for task,kind in running.values()),return_exceptions=True)


def main() -> None:
    """启动本机单实例worker；另一个实例持有锁则退出，防止重复模型和搜索费用。"""
    lock = (DATA / 'worker.lock').open('a+b')
    if os.name == 'nt':
        import msvcrt
        lock.seek(0)
        try:
            msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
        except OSError:
            raise SystemExit('Worker already running')
    try:
        asyncio.run(loop())
    finally:
        lock.close()


if __name__ == '__main__':
    main()
