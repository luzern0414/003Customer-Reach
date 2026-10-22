"""隔离验证日志不与正式服务争用Windows轮转文件。"""
import uuid
import subprocess
import sys
from app import observability


def test_custom_data_logs_are_separate_and_rotate(monkeypatch):
    """monkeypatch为本地隔离配置；自定义DATA日志在自己的目录，实际小容量轮转可正常发生。"""
    folder=observability.DATA/('log-validation-'+uuid.uuid4().hex)
    monkeypatch.setattr(observability,'DATA',folder)
    name='validation-'+uuid.uuid4().hex
    log=observability.logger(name)
    handler=log.handlers[0]
    assert handler.baseFilename==str((folder/'logs'/f'{name}.jsonl').resolve())
    handler.maxBytes=50
    log.info('隔离日志验证第一项')
    log.info('隔离日志验证第二项')
    handler.flush()
    assert (folder/'logs'/f'{name}.jsonl.1').exists()
    handler.close()
    log.removeHandler(handler)


def test_production_processes_rotate_separate_files(tmp_path):
    """tmp_path为隔离目录；两个真实Python进程同时持有正式格式日志，分别轮转不得出现Windows锁冲突。"""
    script = '''
import sys
from pathlib import Path
from app import observability
observability.ROOT=Path(sys.argv[1])
observability.DATA=observability.ROOT/'data/app'
log=observability.logger('agent')
handler=log.handlers[0]
handler.maxBytes=80
for i in range(12): log.info('并发轮转验证'+str(i))
handler.close()
'''
    processes=[subprocess.Popen([sys.executable,'-c',script,str(tmp_path)],stdout=subprocess.PIPE,stderr=subprocess.PIPE) for _ in range(2)]
    for process in processes:
        _,errors=process.communicate(timeout=30)
        assert process.returncode==0 and not errors,errors.decode('utf-8',errors='replace')
    files=list((tmp_path/'log/web').glob('agent-*.jsonl.1'))
    assert len(files)==2 and len({file.name for file in files})==2
