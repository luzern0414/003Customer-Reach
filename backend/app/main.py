"""DealRadar API。只负责参数校验与编排，业务逻辑在 services / research。"""
import asyncio
import logging
import time
from contextlib import asynccontextmanager
from urllib.parse import quote

from fastapi import FastAPI, File, HTTPException, Query, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse, Response, StreamingResponse
from pydantic import BaseModel, Field

from . import auth, crawl, llm, runner, services
from .config import WEB_DIST
from .db import get_settings, init_db, save_settings
from .documents import DocumentError
from .events import sse
from .sites import all_sites

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(name)s %(message)s')


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()
    auth.ensure_admin()
    runner.recover()
    yield


app = FastAPI(title='DealRadar', lifespan=lifespan)


# 无需登录的接口；其余 /api 均要求登录，配置类接口仅管理员可用
PUBLIC = {'/api/auth/login', '/api/auth/register', '/api/auth/logout', '/api/auth/me', '/api/health'}
ADMIN_PREFIXES = ('/api/settings', '/api/knowledge', '/api/discovered-sources', '/api/sources/sites', '/api/sources/test')


@app.middleware('http')
async def _authenticate(request: Request, call_next):
    response = await _gate(request, call_next)
    # 安全响应头：禁止被嵌入框架、禁止内容类型嗅探、跨站只发送来源域名
    response.headers.setdefault('X-Frame-Options', 'DENY')
    response.headers.setdefault('X-Content-Type-Options', 'nosniff')
    response.headers.setdefault('Referrer-Policy', 'strict-origin-when-cross-origin')
    return response


async def _gate(request: Request, call_next):
    path = request.url.path
    if path.startswith('/api/') and path not in PUBLIC:
        user = await asyncio.to_thread(auth.user_for, request.cookies.get(auth.COOKIE))
        if not user:
            return JSONResponse({'detail': '请先登录'}, 401)
        if (path == '/api/sources' or path.startswith(ADMIN_PREFIXES)) and not user['is_admin']:
            return JSONResponse({'detail': '仅管理员可用'}, 403)
        request.state.user = user
    return await call_next(request)


@app.exception_handler(auth.AuthError)
async def _auth_error(_, exc: auth.AuthError):
    return JSONResponse({'detail': str(exc)}, exc.status)


@app.exception_handler(services.NotFound)
async def _not_found(*_):
    return JSONResponse({'detail': '记录不存在'}, 404)


@app.exception_handler(ValueError)
async def _invalid(_, exc: ValueError):
    return JSONResponse({'detail': str(exc)}, 400)


@app.exception_handler(DocumentError)
async def _document(_, exc: DocumentError):
    return JSONResponse({'detail': exc.args[0]}, exc.args[1] if len(exc.args) > 1 else 400)


# ---------- 账号 ----------

class CredentialsIn(BaseModel):
    username: str = Field(min_length=1, max_length=32)
    password: str = Field(min_length=1, max_length=64)


def _signed_in(request: Request, user: dict, token: str) -> JSONResponse:
    response = JSONResponse(user)
    response.set_cookie(auth.COOKIE, token, max_age=auth.SESSION_DAYS * 86400, httponly=True, samesite='lax',
                        secure=request.url.scheme == 'https')
    return response


def _client(request: Request) -> str:
    return request.client.host if request.client else ''


@app.post('/api/auth/register')
def register(body: CredentialsIn, request: Request):
    return _signed_in(request, *auth.register(body.username, body.password, _client(request)))


@app.post('/api/auth/login')
def login(body: CredentialsIn, request: Request):
    return _signed_in(request, *auth.login(body.username, body.password))


@app.post('/api/auth/logout')
def logout(request: Request):
    if token := request.cookies.get(auth.COOKIE):
        auth.logout(token)
    response = JSONResponse({'ok': True})
    response.delete_cookie(auth.COOKIE)
    return response


@app.get('/api/auth/me')
def me(request: Request):
    # 未登录返回 null，前端据此跳转登录页（不产生 401 报错）
    return auth.user_for(request.cookies.get(auth.COOKIE))


# ---------- 会话与任务 ----------

class MessageIn(BaseModel):
    content: str = Field(min_length=1, max_length=8000)
    attachment_ids: list[str] = Field(default_factory=list, max_length=5)
    mode: str = ''
    company: str = ''


class ContinueIn(BaseModel):
    choice: str = ''
    skip: bool = False


@app.get('/api/conversations')
def list_conversations(request: Request):
    return services.conversations(request.state.user)


@app.post('/api/conversations')
def new_conversation(request: Request):
    return services.create_conversation(request.state.user)


@app.get('/api/conversations/{conversation_id}')
def get_conversation(conversation_id: str, request: Request):
    return services.conversation_detail(conversation_id, request.state.user)


@app.post('/api/conversations/{conversation_id}/messages', status_code=202)
async def send_message(conversation_id: str, body: MessageIn, request: Request):
    result = services.submit(conversation_id, body.content.strip(), body.attachment_ids, request.state.user,
                             body.mode, body.company)
    runner.start(result['job']['id'])
    return result


@app.get('/api/jobs/{job_id}')
def get_job(job_id: str, request: Request):
    services.check_job(job_id, request.state.user)
    return services.job_detail(job_id)


@app.get('/api/jobs/{job_id}/events')
async def job_events(job_id: str, request: Request, after: int = Query(0, ge=0)):
    services.check_job(job_id, request.state.user)
    last = request.headers.get('last-event-id')
    cursor = int(last) if last and last.isdigit() else after
    return StreamingResponse(sse(job_id, cursor, request.is_disconnected), media_type='text/event-stream',
                             headers={'Cache-Control': 'no-cache', 'X-Accel-Buffering': 'no'})


@app.get('/api/jobs/{job_id}/results')
def job_results(job_id: str, request: Request):
    services.check_job(job_id, request.state.user)
    return services.job_results(job_id)


@app.get('/api/jobs/{job_id}/report')
def job_report(job_id: str, request: Request):
    services.check_job(job_id, request.state.user)
    return services.job_report(job_id)


@app.post('/api/jobs/{job_id}/pause')
def pause_job(job_id: str, request: Request):
    services.check_job(job_id, request.state.user)
    if not runner.pause(job_id):
        raise HTTPException(409, '任务未在运行')
    return {'ok': True}


@app.post('/api/jobs/{job_id}/continue')
async def continue_job(job_id: str, body: ContinueIn, request: Request):
    services.check_job(job_id, request.state.user)
    job = services.job_detail(job_id)
    if job['status'] not in ('paused', 'awaiting_user', 'partial', 'failed') or runner.active(job_id):
        raise HTTPException(409, '任务当前不能继续')
    await runner.resume(job_id, body.choice, body.skip)
    return {'ok': True}


# ---------- 附件与来源 ----------

@app.post('/api/attachments')
async def upload(request: Request, file: UploadFile = File(...)):
    content = await file.read(10 * 1024 * 1024 + 1)
    return await asyncio.to_thread(services.save_attachment, file.filename or 'file', content, request.state.user)


@app.get('/api/attachments/{attachment_id}')
def get_attachment(attachment_id: str, request: Request):
    return services.attachment_detail(attachment_id, request.state.user)


@app.get('/api/sources/{source_id}')
def get_source(source_id: str):
    return services.source_detail(source_id)


# ---------- 企业 ----------

class ResearchIn(BaseModel):
    conversation_id: str = ''


def _xlsx(name: str, content: bytes) -> Response:
    return Response(content, media_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
                    headers={'Content-Disposition': f"attachment; filename*=UTF-8''{quote(name)}.xlsx"})


@app.get('/api/companies')
def list_companies(q: str = '', role: str = '', page: int = Query(1, ge=1), page_size: int = Query(12, ge=1, le=100)):
    return services.companies(q, role, page, page_size)


@app.get('/api/companies/{company_id}')
def get_company(company_id: str):
    return services.company_detail(company_id)


@app.get('/api/companies/{company_id}/export')
def export_company(company_id: str):
    name, content = services.export_company(company_id)
    return _xlsx(f'{name}_企业档案', content)


@app.post('/api/companies/{company_id}/research', status_code=202)
async def research_company(company_id: str, body: ResearchIn, request: Request):
    user = request.state.user
    name = services.company_detail(company_id)['name']
    if body.conversation_id:
        services.conversation_detail(body.conversation_id, user)
    elif not user['unlimited'] and not user['remaining']:
        raise auth.AuthError('使用次数已用完', 403)
    conversation_id = body.conversation_id or services.create_conversation(user)['id']
    result = services.submit(conversation_id, f'研究{name}的采购、中标与上下游', [], user, 'company', name)
    runner.start(result['job']['id'])
    return {**result, 'conversation_id': conversation_id}


@app.post('/api/companies/{company_id}/lead')
def company_to_lead(company_id: str, body: ResearchIn):
    return services.add_lead_for_company(company_id, body.conversation_id)


# ---------- 概览 ----------

@app.get('/api/overview')
def get_overview(request: Request, days: int = Query(30, ge=0, le=3650)):
    return services.overview(days, request.state.user)


# ---------- 线索 ----------

class LeadPatch(BaseModel):
    status: str | None = None
    owner: str | None = Field(None, max_length=64)
    next_followup_at: str | None = Field(None, max_length=32)
    tags: list[str] | None = None
    archived: int | None = Field(None, ge=0, le=1)


class NoteIn(BaseModel):
    kind: str = Field('note', max_length=16)
    content: str = Field('', max_length=4000)


class AnalysisIn(BaseModel):
    focus: str = Field('', max_length=2000)


@app.get('/api/leads')
def list_leads(q: str = '', status: str = '', owner: str = '', start: str = '', end: str = '',
               page: int = Query(1, ge=1), page_size: int = Query(20, ge=1, le=100)):
    return services.leads(q, status, owner, start, end, page, page_size)


@app.get('/api/leads/export')
def export_leads(q: str = '', status: str = '', owner: str = '', start: str = '', end: str = ''):
    content = services.export_leads(q=q, status=status, owner=owner, start=start, end=end)
    return _xlsx(f'获客线索_{time.strftime("%Y%m%d")}', content)


@app.get('/api/leads/{lead_id}')
def get_lead(lead_id: str):
    return services.lead_detail(lead_id)


@app.patch('/api/leads/{lead_id}')
def patch_lead(lead_id: str, body: LeadPatch):
    return services.update_lead(lead_id, body.model_dump(exclude_none=True))


@app.post('/api/leads/{lead_id}/followups')
def add_followup(lead_id: str, body: NoteIn):
    if not body.content.strip():
        raise HTTPException(400, '请填写跟进内容')
    return services.add_followup(lead_id, body.kind, body.content.strip())


@app.post('/api/leads/{lead_id}/feedback')
def add_feedback(lead_id: str, body: NoteIn):
    if body.kind not in ('relevant', 'not_buyer', 'wrong', 'stale'):
        raise HTTPException(400, '无效的反馈类型')
    return services.add_feedback(lead_id, body.kind, body.content.strip())


@app.post('/api/leads/{lead_id}/analysis')
async def analyze_lead(lead_id: str, body: AnalysisIn):
    return await services.analyze_lead(lead_id, body.focus)


# ---------- 数据来源与设置 ----------

class SettingsIn(BaseModel):
    company_name: str | None = Field(None, max_length=100)
    company_profile: str | None = Field(None, max_length=4000)
    target_regions: list[str] | None = None
    exclusions: list[str] | None = None
    default_days: int | None = Field(None, ge=1, le=730)
    max_queries: int | None = Field(None, ge=1, le=30)
    max_reads: int | None = Field(None, ge=1, le=60)
    max_enrich: int | None = Field(None, ge=0, le=30)
    target_leads: int | None = Field(None, ge=1, le=200)
    max_rounds: int | None = Field(None, ge=1, le=10)
    max_model_calls: int | None = Field(None, ge=5, le=200)
    max_minutes: int | None = Field(None, ge=3, le=120)
    crawl_profile: str | None = Field(None, max_length=64)
    sources: dict[str, bool] | None = None


class KnowledgeIn(BaseModel):
    kind: str = Field(pattern='^(preference|exclusion|product)$')
    title: str = Field('', max_length=200)
    body: str = Field(min_length=1, max_length=8000)


_doctor: dict = {'checked': 0.0, 'value': None}
CRAWLER_STATES = {
    'ready': '', 'profile_selection_required': '', 'opencli_missing': '未安装 OpenCLI',
    'opencli_version_unsupported': 'OpenCLI 版本不受支持', 'native_plugin_missing': '未安装 LuzCrawl 插件',
    'daemon_stopped': '浏览器桥未启动', 'profile_disconnected': 'Edge 未连接', 'extension_disconnected': 'Edge 中的 LuzCrawl 扩展未连接',
}


@app.get('/api/sources')
async def data_sources(refresh: bool = False):
    if refresh or not _doctor['value'] or time.time() - _doctor['checked'] > 300:
        _doctor.update(value=await crawl.doctor(), checked=time.time())
    doctor = _doctor['value']
    settings, stats = get_settings(), services.site_stats()
    switches = settings.get('sources') or {}
    daemon = doctor.get('daemon') or {}
    profiles = [p.get('contextId') for p in daemon.get('profiles') or [] if p.get('extensionConnected')]
    # 系统总是显式指定已连接的 Edge 资料，doctor 的“需要选择资料”不影响采集。
    ready = bool(doctor.get('ready')) or (doctor.get('state') == 'profile_selection_required' and bool(profiles))
    return {
        'crawler': {'ready': ready, 'state': doctor.get('state'), 'hint': CRAWLER_STATES.get(doctor.get('state') or '', '采集工具不可用'),
                    'version': (doctor.get('native_plugin') or {}).get('version'),
                    'profiles': profiles,
                    'profile': settings['crawl_profile'] or daemon.get('context_id') or (profiles[0] if profiles else '')},
        'sites': [{'id': s.id, 'name': s.name, 'kind': s.kind, 'login': s.login, 'note': s.note, 'custom': s.custom,
                   'mode': 'site_search' if s.platform and not s.template else 'template', 'template': s.template,
                   'domain': s.platform if s.custom else '', 'detail': s.detail if s.custom else '', 'by_company': s.by_company,
                   'enabled': switches.get(s.id, s.default_on), 'stats': stats.get(s.id),
                   'origin': s.origin, 'region': s.region} for s in all_sites().values()]}


class SiteIn(BaseModel):
    name: str = Field(max_length=100)
    kind: str = 'procurement'
    mode: str = 'template'
    template: str = Field('', max_length=1000)
    domain: str = Field('', max_length=200)
    detail: str = Field('', max_length=300)
    login: bool = False
    by_company: bool = False
    note: str = Field('', max_length=200)


class SiteTestIn(SiteIn):
    keyword: str = Field('采购', min_length=1, max_length=40)


@app.post('/api/sources/sites')
def create_site(body: SiteIn):
    return services.create_site(body.model_dump())


@app.patch('/api/sources/sites/{site_id}')
def update_site(site_id: str, body: SiteIn):
    return services.update_site(site_id, body.model_dump())


@app.delete('/api/sources/sites/{site_id}')
def delete_site(site_id: str):
    services.delete_site(site_id)
    return {'ok': True}


@app.get('/api/discovered-sources')
def discovered_sites():
    return services.discovered_sites()


@app.post('/api/discovered-sources/{domain}/dismiss')
def dismiss_discovered(domain: str):
    services.dismiss_discovered(domain)
    return {'ok': True}


@app.post('/api/sources/test')
async def test_site(body: SiteTestIn):
    return await services.test_site(body.model_dump(exclude={'keyword'}), body.keyword)


@app.get('/api/settings')
def read_settings():
    return get_settings()


@app.patch('/api/settings')
def patch_settings(body: SettingsIn):
    values = body.model_dump(exclude_none=True)
    if 'sources' in values:
        known = all_sites()
        values['sources'] = {k: v for k, v in values['sources'].items() if k in known}
    return save_settings(values)


@app.post('/api/settings/test-model')
async def test_model():
    try:
        return await llm.test_connection()
    except Exception as exc:
        raise HTTPException(502, f'模型连接失败：{str(exc)[:200]}') from exc


@app.get('/api/knowledge')
def list_knowledge(kind: str = ''):
    return services.knowledge(kind)


@app.post('/api/knowledge')
def add_knowledge(body: KnowledgeIn):
    return services.add_knowledge(body.kind, body.title, body.body)


@app.delete('/api/knowledge/{item_id}')
def remove_knowledge(item_id: str):
    services.disable_knowledge(item_id)
    return {'ok': True}


@app.get('/api/health')
def health():
    return {'ok': True}


@app.get('/{path:path}', include_in_schema=False)
def spa(path: str):
    target = (WEB_DIST / path).resolve()
    if path and target.is_file() and WEB_DIST.resolve() in target.parents:
        return FileResponse(target)
    index = WEB_DIST / 'index.html'
    if not index.exists():
        raise HTTPException(404, '前端尚未构建：cd web && npm run build')
    return FileResponse(index)
