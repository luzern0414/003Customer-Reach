"""实际PowerShell5.1验证固定日志归档，不启动或终止任何生产服务。"""
import subprocess
import uuid
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
HELPER=ROOT/'scripts/runtime-logs.ps1'


def test_runtime_log_archive_preserves_bytes_and_other_services():
    """唯一项目夹具验证原字节、另一服务日志与重复归档不覆盖；夹具全部保留供复核。"""
    folder=ROOT/'.codex-tmp'/('runtime-log-test-'+uuid.uuid4().hex)
    folder.mkdir()
    sample=b'isolated log fixture\r\n\xe4\xb8\xad\xe6\x96\x87\x00'
    for stream in ['stdout','stderr']:(folder/f'api.{stream}.log').write_bytes(sample)
    (folder/'worker.stdout.log').write_bytes(b'other service fixture')
    command=f". '{HELPER}'; Preserve-ServiceLogs -RuntimeDirectory '{folder}' -ServiceName api | Out-Null"
    for index in range(2):
        result=subprocess.run(['powershell.exe','-NoProfile','-Command',command],capture_output=True,timeout=20)
        assert result.returncode==0,result.stderr
        archived=list((folder/'archive').glob('api.*.log'))
        assert len(archived)==2*(index+1) and all(path.read_bytes()==sample for path in archived)
        assert not (folder/'api.stdout.log').exists() and not (folder/'api.stderr.log').exists()
        assert (folder/'worker.stdout.log').read_bytes()==b'other service fixture'
        if index==0:
            for stream in ['stdout','stderr']:(folder/f'api.{stream}.log').write_bytes(sample)


def test_startup_scripts_remain_powershell51_compatible():
    """启动/辅助脚本保留UTF8 BOM，并用原生Parser检查语法，不执行服务启动逻辑。"""
    for path in [HELPER,ROOT/'start.ps1']:
        assert path.read_bytes().startswith(b'\xef\xbb\xbf')
        command=f"$tokens=$null; $errors=$null; [System.Management.Automation.Language.Parser]::ParseFile('{path}',[ref]$tokens,[ref]$errors) | Out-Null; if($errors.Count -gt 0){{exit 1}}"
        result=subprocess.run(['powershell.exe','-NoProfile','-Command',command],capture_output=True,timeout=20)
        assert result.returncode==0,result.stderr
