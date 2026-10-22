"""Edge公开读取适配：固定Node与脚本、专用实例、预算和取消；不读取日常浏览器登录状态。"""
import asyncio
import json
import os
import subprocess
import uuid
from pathlib import Path
from .config import ROOT
from .db import Session, Setting, now
from .service import ServiceError
from .schemas import BrowserSettingsInput


def runtime_paths() -> dict:
    """无参数；只定位项目和已安装运行时，缺失返回空路径，不读取凭据或日常浏览器资料。"""
    candidates=[ROOT/'tools/browser/node.exe',Path('C:/Users/admin/.codex/nodejsv24.18.0/node.exe')]
    import shutil
    found=shutil.which('node')
    if found:candidates.append(Path(found))
    node=next((p for p in candidates if p.is_file()),None)
    edge=next((Path(base)/'Microsoft/Edge/Application/msedge.exe' for base in [os.getenv('ProgramFiles(x86)',''),os.getenv('ProgramFiles','')] if base and (Path(base)/'Microsoft/Edge/Application/msedge.exe').is_file()),None)
    return {'node':node,'edge':edge,'script':ROOT/'tools/browser/read-edge.cjs',
        'opencli':ROOT/'vendor/opencli/package.json',
        'playwright':ROOT/'tools/browser/node_modules/playwright/package.json'}


def browser_settings() -> dict:
    """无入参；返回固定结构的非敏感设置，缺配置使用明确默认值，不假称已实测。"""
    with Session() as db:row=db.get(Setting,'browser')
    return {**BrowserSettingsInput().model_dump(),**(row.value if row else {})}


def save_browser_settings(values: dict) -> dict:
    """values为完整非敏感设置；校验枚举及边界，禁止传任意执行路径，返回保存结果。"""
    checked=BrowserSettingsInput(**values).model_dump()
    with Session.begin() as db:
        row=db.get(Setting,'browser')
        if row:row.value=checked
        else:db.add(Setting(key='browser',value=checked))
    return checked


def browser_status() -> dict:
    """无入参；安装状态和最近真实读取分开返回，空记录标未验证，省略磁盘路径。"""
    paths=runtime_paths()
    with Session() as db:row=db.get(Setting,'browser_last_read')
    version=''
    if paths['opencli'].is_file():version=json.loads(paths['opencli'].read_text(encoding='utf-8')).get('version','')
    return {'settings':browser_settings(),'edge_installed':bool(paths['edge']),'node_installed':bool(paths['node']),
        'opencli_installed':paths['opencli'].is_file(),'opencli_version':version,'playwright_installed':paths['playwright'].is_file(),
        'last_read':row.value if row else None,'strategy':'专用 Edge · OpenCLI web/read CDP · Playwright 备用'}


async def read_edge(url: str, job_id: str = '', preference: str | None = None) -> dict:
    """url为已许可公网页面、job_id可空诊断、preference为空采用设置；返回真实正文，取消终止本次进程树，失败抛业务错误。"""
    from .research_tools import public_url
    if not await asyncio.to_thread(public_url,url):raise ServiceError('url_not_public')
    from .source_policy import reading_delay
    # 与HTTP读取器相同，robots/普通站点的返回值代表最小间隔；不能只检查而不等待。
    await asyncio.sleep(await reading_delay(url))
    options=browser_settings()
    if not options['enabled']:raise ServiceError('browser_disabled')
    paths=runtime_paths()
    if not paths['node'] or not paths['edge'] or not paths['playwright'].is_file():raise ServiceError('browser_runtime_unavailable')
    folder=ROOT/'.codex-tmp/browser-tasks'/(job_id or 'diagnostic')/uuid.uuid4().hex
    folder.mkdir(parents=True,exist_ok=True)
    flags=getattr(subprocess,'CREATE_NO_WINDOW',0)
    process=await asyncio.create_subprocess_exec(str(paths['node']),str(paths['script']),url,str(folder),preference or options['preferred_backend'],str(options['max_chars']),
        stdout=asyncio.subprocess.PIPE,stderr=asyncio.subprocess.PIPE,creationflags=flags)
    try:
        stdout,stderr=await asyncio.wait_for(process.communicate(),options['command_timeout'])
        if process.returncode:
            try:code=json.loads(stderr.decode('utf-8')).get('error','browser_read_failed')
            except ValueError:code='browser_read_failed'
            raise ServiceError(code[:160])
        result=json.loads(stdout.decode('utf-8'))
        if result.get('http_status',0)>=400:raise ServiceError('site_http_'+str(result['http_status']))
        from .source_access import access_issue
        issue=access_issue(result['url'],result['title'],result['body'])
        if issue:raise ServiceError(issue)
        if not await asyncio.to_thread(public_url,result['url']):raise ServiceError('redirect_not_public')
        if len(result['body'])<150:raise ServiceError('empty_body')
        with Session.begin() as db:
            row=db.get(Setting,'browser_last_read')
            verified={'checked_at':now(),'backend':result['backend'],'url':result['url'],'body_chars':result['body_chars'],
                'elapsed_ms':result['elapsed_ms'],'opencli_version':result['opencli_version'],'success':True}
            if row:row.value=verified
            else:db.add(Setting(key='browser_last_read',value=verified))
        return result
    finally:
        if process.returncode is None:
            # 仅终止本次Node创建的Edge子树，不影响API/Worker或用户浏览器。
            if os.name=='nt':
                killer=await asyncio.create_subprocess_exec('taskkill','/PID',str(process.pid),'/T','/F',stdout=asyncio.subprocess.DEVNULL,stderr=asyncio.subprocess.DEVNULL,creationflags=flags)
                await killer.wait()
            else:process.kill()
            await process.wait()
