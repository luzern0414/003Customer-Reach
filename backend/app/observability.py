"""结构化运行日志；敏感字段在写盘前统一过滤。"""
import json
import logging
import os
import re
from logging.handlers import RotatingFileHandler
from .config import ROOT, DATA, credentials
from .db import now


class JsonFormatter(logging.Formatter):
    """JSONL格式化器，记录关联ID和阶段，不输出HTTP授权头。"""
    def format(self, record):
        """record必须为LogRecord；返回已过滤的单行JSON，异常不记录正文。"""
        payload = {'time': now(), 'level': record.levelname, 'event': record.getMessage(),
                   **getattr(record, 'details', {})}
        text = json.dumps(payload, ensure_ascii=False, default=str)
        try:
            text = text.replace(credentials()[1], '[REDACTED]')
        except ValueError:
            pass
        text = re.sub(r'sk-[A-Za-z0-9_-]+', '[REDACTED]', text)
        text = re.sub(r'(?<!\d)1[3-9]\d{9}(?!\d)', '[PHONE]', text)
        return text


def logger(name: str) -> logging.Logger:
    """name为程序固定日志名；正式多进程运行按PID分流，避免Windows跨进程轮转冲突。"""
    target = logging.getLogger(f'clientreach.{name}')
    if not target.handlers:
        production = DATA.resolve() == (ROOT / 'data/app').resolve()
        directory = ROOT / 'log/web' if production else DATA / 'logs'
        directory.mkdir(parents=True, exist_ok=True)
        # API 与 Worker 是独立进程；Windows 无法在另一个进程持有轮转目标时重命名它。
        # 正式运行按进程写独立文件，保留每个进程自己的2MB轮转；隔离测试继续使用稳定文件名。
        filename = f'{name}-{os.getpid()}.jsonl' if production else f'{name}.jsonl'
        handler = RotatingFileHandler(directory / filename, maxBytes=2_000_000,
                                      backupCount=3, encoding='utf-8')
        handler.setFormatter(JsonFormatter())
        target.addHandler(handler)
        target.setLevel(logging.INFO)
        target.propagate = False
    return target


def safe_error(exc: Exception) -> str:
    """从非空异常提取类型和状态；不返回provider请求正文、密钥或产品附件内容。"""
    # MCP网络错误通常被TaskGroup包裹；仅提取首个叶子异常类型/HTTP状态，不输出原始报文。
    while isinstance(exc, BaseExceptionGroup) and exc.exceptions:
        exc = exc.exceptions[0]
    status = getattr(exc, 'status_code', None) or getattr(getattr(exc, 'response', None), 'status_code', None)
    return f'{type(exc).__name__}' + (f'（HTTP {status}）' if status else '')


def error_details(exc: Exception) -> dict:
    """exc为运行异常；返回类型链、系统码和栈位置，不读取异常正文/源码行/局部变量，便于安全定位。"""
    from pathlib import Path
    chain=[];seen=set();current=exc
    while current is not None and id(current) not in seen:
        seen.add(id(current))
        if isinstance(current,BaseExceptionGroup) and current.exceptions:
            current=current.exceptions[0];continue
        frames=[];trace=current.__traceback__
        while trace:
            frames.append({'file':Path(trace.tb_frame.f_code.co_filename).name,'function':trace.tb_frame.f_code.co_name,'line':trace.tb_lineno})
            trace=trace.tb_next
        chain.append({'type':type(current).__name__,'errno':getattr(current,'errno',None),
            'winerror':getattr(current,'winerror',None),'frames':frames[-8:]})
        current=current.__cause__ or current.__context__
    return {'errors':chain[:5]}
