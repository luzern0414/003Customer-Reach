# DealRadar 通用搜索 Agent Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在现有采购与企业研究工作台上增加可澄清、可补充、支持中英文和任意目标域名的通用搜索 Agent，并让所有搜索研究结果以可核验表格呈现。

**Architecture:** 保留现有 FastAPI + SQLite + Vue 3 + Element Plus + SSE + LuzCrawl 运行底座。新增 `search` 计划模式和 Web 结果载荷；模型只生成意图、查询和抽取结果，Runner 决定阶段、来源、上限、暂停、重规划和恢复。通用网页结果保存在 Job 计划 JSON 与 Source 证据中，采购与企业结果继续使用现有领域表。

**Tech Stack:** Python 3.12、FastAPI、SQLAlchemy/SQLite、Pydantic、asyncio、Vue 3、TypeScript、Element Plus、Playwright E2E、LuzCrawl CLI。

## Global Constraints

- 采集统一走 LuzCrawl；不增加 Exa、OpenCLI、Playwright 或 HTTP 直读采集通道。
- 澄清阶段允许自然语言；搜索和研究结果只显示结构化表格、状态卡、路径表和来源链接。
- 目标网站不需要预登记；搜索引擎只作为发现入口，网页读取仍经 LuzCrawl。
- 中英文查询并行扩展；英文标题和引用保留原文。
- 运行期间允许补充；补充触发重规划，保留已抓取来源、证据和结果。
- 每个结果字段必须能在 LuzCrawl 保存的原文中找到 quote；未核验字段不入表。
- SSE 事件带 id、run_id、ts、elapsed_ms，支持 Last-Event-ID 续传、15 秒心跳和终态关闭。
- 状态颜色只作用于文字浅色底、状态点和卡片浅背景；卡片边框和表格边框保持中性细线。
- 后台正文与表格 14px、行高 22px；数据行 44–48px；日期列必须完整显示。
- 采购内容按原始分隔符拆成最多三条浅色列点，完整内容保留在 title 提示中。
- 全局侧栏把会话历史放在“系统设置”下方；工作台不再重复显示历史栏。
- 研究次数同一补充任务只扣一次；`request_id` 幂等。
- 不修改共享 Luz skill 规则或脚本；只写入各 skill 经验库和项目 BRIEF。

---

## 文件与模块地图

| 文件 | 责任 |
| --- | --- |
| `backend/app/research/schemas.py` | Plan、查询计划和网页抽取的结构化契约 |
| `backend/app/db.py` | Job/Message 兼容字段和索引迁移 |
| `backend/app/events.py` | SSE 终态和事件流 |
| `backend/app/services.py` | 会话提交、幂等、补充任务和报告载荷 |
| `backend/app/main.py` | 消息 API 请求体和任务接口编排 |
| `backend/app/runner.py` | 取消、补充重规划、暂停、恢复和任务状态 |
| `backend/app/research/pipeline.py` | 通用搜索阶段、LuzCrawl 路由、读取和核验 |
| `backend/app/research/store.py` | 通用 Source 证据与结果持久化辅助 |
| `backend/tests/test_search_agent.py` | 后端新契约、状态、结果和 API 回归 |
| `web/src/types.ts` | Job、事件、Report 的前端类型 |
| `web/src/jobStream.ts` | SSE 状态、阶段路径和结果行同步 |
| `web/src/components/ConversationHistory.vue` | 全局侧栏会话历史 |
| `web/src/App.vue` | 全局导航与历史位置 |
| `web/src/pages/Workbench.vue` | 补充输入、过程卡和路径表 |
| `web/src/components/ReportCard.vue` | 采购报告与通用搜索表格 |
| `web/src/format.ts`、`web/src/theme.css` | 列点拆分、日期和浅色状态视觉 |
| `web/tests/e2e/main.spec.ts` | 浏览器验收 |
| `D:\Codes\skill输出\` 下各 skill 的新会话目录 | 各 Luz skill 的本次经验与 BRIEF |

---

### Task 1: 扩展任务契约、兼容迁移与 SSE 状态

**Files:**
- Modify: `backend/app/research/schemas.py`
- Modify: `backend/app/db.py`
- Modify: `backend/app/events.py`
- Modify: `web/src/types.ts`
- Modify: `web/src/format.ts`
- Test: `backend/tests/test_search_agent.py`

**Interfaces:**
- Produces `Plan(mode='search', needs_clarification, questions, language, query, result_columns)`。
- Produces nullable `Message.request_id` and `Job.request_id` compatibility fields.
- Produces `JobStatus` values `awaiting_input` and `replanning`。

- [ ] **Step 1: Write failing schema and migration tests**

```python
def test_search_plan_and_new_status_fields():
    from app.research.schemas import Plan
    plan = Plan(mode='search', title='AI research', query='latest AI safety papers',
                language='en', needs_clarification=False, result_columns=['标题', '来源'])
    assert plan.mode == 'search'
    assert plan.language == 'en'
    assert plan.result_columns == ['标题', '来源']

def test_init_db_adds_request_id_columns(tmp_path, monkeypatch):
    from app import db
    monkeypatch.setattr(db, 'engine', db.create_engine('sqlite:///' + (tmp_path / 'test.db').as_posix()))
    db.init_db()
    names = {column['name'] for column in db.inspect(db.engine).get_columns('messages')}
    assert 'request_id' in names

def test_sse_treats_awaiting_input_as_terminal():
    from app.events import TERMINAL
    assert 'awaiting_input' in TERMINAL
```

- [ ] **Step 2: Run the new tests and verify they fail**

Run: `backend\.venv\Scripts\python.exe -m pytest backend/tests/test_search_agent.py -k "search_plan or init_db_adds or sse_treats" -q`

Expected: FAIL because the Plan fields, database column and terminal status do not exist.

- [ ] **Step 3: Add the structured fields and status literals**

In `backend/app/research/schemas.py`, change `Plan.mode` to `Literal['find_buyers', 'company', 'search', 'chat']` and add:

```python
needs_clarification: bool = Field(False, description='信息不足时先澄清，不启动搜索')
questions: list[str] = Field(default_factory=list, description='澄清阶段最多三个必要问题')
language: Literal['auto', 'zh', 'en', 'mixed'] = 'auto'
query: str = Field('', description='通用搜索的原始问题')
result_columns: list[str] = Field(default_factory=list, description='通用结果需要的列名')
```

In `web/src/types.ts`, add `search` to `Job.mode`, add `awaiting_input | replanning` to `JobStatus`, and add the same values to `JOB_STATUS` in `web/src/format.ts` with `warn` and `brand` tones respectively.

- [ ] **Step 4: Add nullable request-id columns and compatible initialization**

Add `request_id: Mapped[str | None] = mapped_column(String(96), nullable=True, index=True)` to `Message` and `Job`. In `init_db`, inspect both tables and run `ALTER TABLE messages ADD COLUMN request_id VARCHAR(96)` or `ALTER TABLE jobs ADD COLUMN request_id VARCHAR(96)` only when the respective column is missing. Create partial unique indexes named `uq_messages_conversation_request` and `uq_jobs_conversation_request` on `(conversation_id, request_id)` where `request_id IS NOT NULL`.

- [ ] **Step 5: Add the new SSE terminal state**

Update `backend/app/events.py`:

```python
TERMINAL = {'completed', 'partial', 'failed', 'paused', 'awaiting_user', 'awaiting_input'}
```

Keep the existing event cursor and heartbeat behavior unchanged.

- [ ] **Step 6: Run focused tests and commit**

Run: `backend\.venv\Scripts\python.exe -m pytest backend/tests/test_search_agent.py -k "search_plan or init_db_adds or sse_treats" -q`

Expected: PASS. Commit: `git add backend/app/research/schemas.py backend/app/db.py backend/app/events.py web/src/types.ts web/src/format.ts backend/tests/test_search_agent.py && git commit -m "feat: extend agent search contracts"`。

### Task 2: Allow clarification and in-run supplements with idempotency

**Files:**
- Modify: `backend/app/services.py`
- Modify: `backend/app/main.py`
- Modify: `backend/app/runner.py`
- Modify: `backend/app/research/pipeline.py`
- Test: `backend/tests/test_search_agent.py`

**Interfaces:**
- `services.submit(conversation_id, content, attachment_ids, user, mode='', company='', request_id=None)` returns `{message_id, job, supplemented}`。
- `runner.replan(job_id)` cancels an active task, sets `replanning`, preserves evidence and starts the same Job from `understand`。
- `Run.understand()` reads initial and supplement messages in chronological order.

- [ ] **Step 1: Add failing API tests for active supplements and duplicate request IDs**

```python
def test_active_message_becomes_supplement_and_does_not_consume_again(monkeypatch):
    from app import runner
    started = []
    monkeypatch.setattr(runner, 'start', started.append)
    client = signed_in()
    conversation = client.post('/api/conversations').json()
    first = client.post(f'/api/conversations/{conversation["id"]}/messages',
                        json={'content': 'search AI safety', 'request_id': 'r-first'})
    second = client.post(f'/api/conversations/{conversation["id"]}/messages',
                         json={'content': 'only English sources', 'request_id': 'r-second'})
    assert first.status_code == 202
    assert second.status_code == 202
    assert second.json()['supplemented'] is True
    assert second.json()['job']['id'] == first.json()['job']['id']
    assert started == [first.json()['job']['id'], first.json()['job']['id']]

def test_duplicate_request_id_returns_same_message(monkeypatch):
    from app import runner
    monkeypatch.setattr(runner, 'start', lambda job_id: None)
    client = signed_in()
    conversation = client.post('/api/conversations').json()
    body = {'content': 'find papers about retrieval', 'request_id': 'same-request'}
    first = client.post(f'/api/conversations/{conversation["id"]}/messages', json=body).json()
    second = client.post(f'/api/conversations/{conversation["id"]}/messages', json=body).json()
    assert second['message_id'] == first['message_id']
    assert second['job']['id'] == first['job']['id']
```

- [ ] **Step 2: Run the tests and verify the old busy rejection fails them**

Run: `backend\.venv\Scripts\python.exe -m pytest backend/tests/test_search_agent.py -k "active_message or duplicate_request" -q`

Expected: FAIL with the existing “当前对话还有进行中的任务” behavior.

- [ ] **Step 3: Implement request-id lookup before quota consumption**

In `services.submit`, query `Message.request_id` and `Job.request_id` within the conversation before calling `auth.consume`. Return the existing `message_id` and `job_view` when found. Only a new idle task calls `auth.consume`.

- [ ] **Step 4: Implement supplement persistence**

When a conversation has a Job in `queued`, `running`, `awaiting_user`, `awaiting_input`, `paused` or `partial`, create a user `Message` with the same `job_id`, `request_id`, and validated attachments. Append `{message_id, content, created_at}` to `job.plan['supplements']`, set `job.plan['replan_from'] = 'understand'`, set `job.status = 'replanning'`, and return `supplemented: True` without consuming quota.

- [ ] **Step 5: Add runner cancellation and restart**

Add this function to `backend/app/runner.py`:

```python
def replan(job_id: str) -> None:
    task = _tasks.get(job_id)
    if task:
        task.cancel()
    with Session.begin() as db:
        job = db.get(Job, job_id)
        state = dict(job.plan or {})
        state['replan_from'] = 'understand'
        state['done'] = [stage for stage in state.get('done', []) if stage == 'understand']
        job.plan = state
        job.status = 'replanning'
        job.handover = {}
    emit(job_id, 'status', {'status': 'replanning', 'stage': 'understand', 'metrics': job.metrics or {}, 'handover': {}, 'error': ''})
    start(job_id)
```

Call `runner.replan(result['job']['id'])` from `main.send_message` when `supplemented` is true; call `runner.start` for a new task.

- [ ] **Step 6: Make understand consume supplement context**

In `Run.understand`, query all user messages for the conversation ordered by `created_at`, combine them with explicit labels `原始任务` and `执行中补充`, and pass the combined text to the Plan prompt. Do not replace saved `lists`, `read`, `sources`, or `search_results`.

- [ ] **Step 7: Run focused tests and commit**

Run: `backend\.venv\Scripts\python.exe -m pytest backend/tests/test_search_agent.py -k "active_message or duplicate_request" -q`

Expected: PASS. Commit: `git add backend/app/services.py backend/app/main.py backend/app/runner.py backend/app/research/pipeline.py backend/tests/test_search_agent.py && git commit -m "feat: support in-run agent supplements"`。

### Task 3: Add the LuzCrawl-only universal search pipeline

**Files:**
- Modify: `backend/app/research/schemas.py`
- Modify: `backend/app/research/pipeline.py`
- Modify: `backend/app/research/store.py`
- Modify: `backend/app/sites.py`
- Create: `backend/tests/test_universal_search.py`

**Interfaces:**
- `WebQuery` has `query`, `language`, and `purpose`.
- `WebExtract` has `relevant`, `title`, `language`, `published_on`, `summary`, `points`, and `quote`.
- `Run.web_plan()`, `Run.web_discover()`, `Run.web_search()`, `Run.web_read()`, and `Run.web_verify()` mutate `state['search_*']` and emit route/result events.

- [ ] **Step 1: Write failing structured extraction and route tests**

```python
def test_web_extract_requires_quote_and_points():
    from app.research.schemas import WebExtract
    item = WebExtract(relevant=True, title='AI Safety', language='en', summary='Safety research',
                      points=['Robustness'], quote='Robustness is evaluated')
    assert item.points == ['Robustness']
    assert item.quote == 'Robustness is evaluated'

def test_universal_search_stage_order():
    from app.research.pipeline import STAGES
    assert STAGES['search'] == ['understand', 'web_plan', 'web_discover', 'web_search', 'web_read', 'web_verify', 'answer']

def test_web_candidate_dedupes_by_normalized_url():
    from app.research.pipeline import dedupe_web_candidates
    rows = [{'url': 'https://Example.com/a#section', 'title': 'A'}, {'url': 'https://example.com/a', 'title': 'A copy'}]
    assert len(dedupe_web_candidates(rows)) == 1
```

- [ ] **Step 2: Run the new tests and verify they fail**

Run: `backend\.venv\Scripts\python.exe -m pytest backend/tests/test_universal_search.py -q`

Expected: FAIL because the WebExtract model, search stages and dedupe helper do not exist.

- [ ] **Step 3: Add WebQuery and WebExtract schemas**

Add to `backend/app/research/schemas.py`:

```python
class WebQuery(BaseModel):
    query: str
    language: Literal['zh', 'en', 'mixed']
    purpose: str = ''

class WebExtract(BaseModel):
    relevant: bool
    title: str = ''
    language: Literal['zh', 'en', 'mixed'] = 'mixed'
    published_on: str = ''
    summary: str = ''
    points: list[str] = Field(default_factory=list, max_length=3)
    quote: str = ''
```

- [ ] **Step 4: Register universal stages and search入口**

Add `STAGES['search'] = ['understand', 'web_plan', 'web_discover', 'web_search', 'web_read', 'web_verify', 'answer']` and labels `生成查询计划`、`发现来源`、`通用检索`、`读取原文`、`引用核验`. Keep the existing `Run.plan` property unchanged; implement the new methods as `Run.web_plan`, `Run.web_discover`, `Run.web_search`, `Run.web_read`, and `Run.web_verify`. The `execute` loop invokes those method names only for `mode == 'search'`; existing procurement/company stages keep their current methods.

- [ ] **Step 5: Generate bilingual queries with bounded structured output**

`Run.plan` calls `llm.structured` with a schema containing at most three Chinese and three English `WebQuery` records. The prompt must say that the model may translate the query, may not invent a new topic, and must leave language `mixed` when both languages are needed. Save each query with `status='queued'` and emit a `stage.completed` count.

- [ ] **Step 6: Discover arbitrary domains through LuzCrawl**

`Run.web_discover` builds a search-engine URL from a single configured `web` Site template, calls `crawl.capture`, saves the search page with `store.save_source(page, 'web-search', 'search', job_id)`, filters search-engine URLs and links without `http/https`, and stores `{title, url, domain, snippet, language, source_id}` in `state['search_candidates']`. Do not check the domain against `known_domain`; only reject malformed URL schemes and the search engine’s own navigation URLs.

- [ ] **Step 7: Read candidates and persist evidence**

`Run.web_read` reads at most `settings['max_reads']` candidates with `crawl.capture`, saves each successful page as a `Source` with kind `web`, and calls `llm.structured(WebExtract, prompt)`. The prompt requires a quote copied as a continuous source passage and at most three points. Store the raw page id and extraction in `state['search_results']`; emit `result.row` only after the page is captured.

- [ ] **Step 8: Verify and deduplicate result rows**

Add `dedupe_web_candidates(rows)` using `urllib.parse.urlsplit`, lowercased host, removed fragment, and normalized trailing slash. In `Run.web_verify`, call `grounded(extract.quote, page.text)`, require `extract.relevant` and a non-empty title/url, normalize dates with the existing date helper, cap points at three, and set `status='verified'`. Rows that fail are stored only in the path error list and never returned in `rows`.

- [ ] **Step 9: Add unit tests with fake LuzCrawl pages**

In `backend/tests/test_universal_search.py`, monkeypatch `app.research.pipeline.crawl.capture` to return deterministic `Page` objects and monkeypatch `llm.structured` to return `WebExtract` instances. Assert that the report contains one verified English row, one Chinese row, no duplicate URL, and no row whose quote is absent from the page text.

- [ ] **Step 10: Run focused tests and commit**

Run: `backend\.venv\Scripts\python.exe -m pytest backend/tests/test_universal_search.py backend/tests/test_core.py -q`

Expected: PASS. Commit: `git add backend/app/research/schemas.py backend/app/research/pipeline.py backend/app/research/store.py backend/app/sites.py backend/tests/test_universal_search.py && git commit -m "feat: add universal LuzCrawl search pipeline"`。

### Task 4: Return table-only reports and preserve procurement formatting

**Files:**
- Modify: `backend/app/services.py`
- Modify: `backend/app/research/pipeline.py`
- Modify: `web/src/components/ReportCard.vue`
- Modify: `web/src/format.ts`
- Test: `backend/tests/test_search_agent.py`
- Test: `web/tests/markdown.test.ts`

**Interfaces:**
- `services.job_report(job_id)` returns the universal report shape for `mode == 'search'` and existing shapes for `find_buyers/company`.
- `splitPurchaseItems(text: string): string[]` returns at most three non-empty strings.
- `ReportCard` selects `UniversalSearchTable` behavior when `report.mode === 'search'`.

The `search_job` fixture creates a signed-in TestClient, a Conversation, a completed `search` Job whose `plan['search_results']` contains one verified row, and returns `(client, conversation_id, job_id)`.

- [ ] **Step 1: Write failing report and formatting tests**

```python
def test_search_report_has_rows_and_no_paragraph_reply(search_job):
    client, conversation_id, job_id = search_job
    report = client.get(f'/api/jobs/{job_id}/report').json()
    assert report['mode'] == 'search'
    assert report['columns'] == ['标题', '来源', '语言', '日期', '要点', '原文']
    assert report['rows'][0]['status'] == 'verified'
    detail = client.get(f'/api/conversations/{conversation_id}').json()
    assert not any(message['role'] == 'assistant' and message['content'].strip() for message in detail['messages'])
```

```typescript
import { splitPurchaseItems } from '../src/format'

test('purchase content is limited to three points', () => {
  assert.deepEqual(splitPurchaseItems('服务器；存储设备\n网络安全\n机房运维\n培训'), ['服务器', '存储设备', '网络安全'])
})
```

- [ ] **Step 2: Run focused tests and verify they fail**

Run: `backend\.venv\Scripts\python.exe -m pytest backend/tests/test_search_agent.py -k "search_report" -q` and `npm --prefix web test -- --test-name-pattern="purchase content"`.

Expected: FAIL because the report has no universal rows and the formatter does not exist.

- [ ] **Step 3: Add the search report branch**

In `services.job_report`, branch before procurement-specific `top` construction:

```python
if job.mode == 'search':
    rows = [row for row in (plan.get('search_results') or []) if row.get('status') == 'verified']
    return {'status': job.status, 'mode': 'search', 'columns': ['标题', '来源', '语言', '日期', '要点', '原文'],
            'rows': rows, 'path': plan.get('stage_history', []), 'sources': plan.get('source_ids', []),
            'problems': list(dict.fromkeys(plan.get('problems') or [])),
            'counts': {'searches': len(plan.get('search_queries') or []), 'candidates': len(plan.get('search_candidates') or []),
                       'read': sum(1 for row in rows if row.get('source_id'))}}
```

- [ ] **Step 4: Make search answer table-only**

In `Run.answer`, route `search`, `find_buyers`, and `company` through the report path without creating a paragraph assistant message. Keep the existing streamed `chat` branch and the clarification branch; clarification messages must contain only the model’s questions and set `awaiting_input` after emitting `message.completed`.

- [ ] **Step 5: Add the purchase-item splitter**

In `web/src/format.ts` add:

```typescript
export function splitPurchaseItems(text: string): string[] {
  const values = text.split(/[；;、|\n]+/).map((item) => item.trim()).filter(Boolean)
  return [...new Set(values)].slice(0, 3)
}
```

Use `splitPurchaseItems(t.items || t.notice)` in desktop and mobile procurement cells; render each result as a neutral light point and set the full source text in `title`.

- [ ] **Step 6: Add the universal table branch to ReportCard**

Extend the local `Report` interface with `columns`, `rows`, `path`, and `sources`. Render a table with columns “标题、来源、语言、日期、要点、原文”; use `row.points.slice(0, 3)` and an external link for `row.url`. Do not render a summary paragraph for this branch.

- [ ] **Step 7: Run focused tests and commit**

Run: `backend\.venv\Scripts\python.exe -m pytest backend/tests/test_search_agent.py -k "search_report" -q` and `npm --prefix web test`.

Expected: PASS. Commit: `git add backend/app/services.py backend/app/research/pipeline.py web/src/components/ReportCard.vue web/src/format.ts backend/tests/test_search_agent.py web/tests/markdown.test.ts && git commit -m "feat: render verified search results as tables"`。

### Task 5: Extend the frontend SSE model and move conversation history

**Files:**
- Modify: `web/src/types.ts`
- Modify: `web/src/jobStream.ts`
- Create: `web/src/components/ConversationHistory.vue`
- Modify: `web/src/App.vue`
- Modify: `web/src/pages/Workbench.vue`
- Test: `web/tests/e2e/main.spec.ts`

**Interfaces:**
- `JobState.path` stores stage history and `JobState.rows` stores verified result-row events.
- `ConversationHistory` accepts no props, reads `/conversations`, and emits navigation through `RouterLink`.

- [ ] **Step 1: Write failing TypeScript assertions for new event state**

```typescript
import assert from 'node:assert/strict'
import test from 'node:test'
import { emptyJob } from '../src/jobStream'

test('job state includes replanning and path events', () => {
  const state = emptyJob('j', 'replanning')
  assert.equal(state.status, 'replanning')
  assert.deepEqual(state.path, [])
  assert.deepEqual(state.rows, [])
})
```

- [ ] **Step 2: Run the test and verify it fails**

Run: `npm --prefix web test -- --test-name-pattern="job state includes"`.

Expected: FAIL because `JobState` has no `path` or `rows` fields and `replanning` is not a valid status.

- [ ] **Step 3: Extend JobState and SSE handlers**

Add `path: StagePath[]` and `rows: SearchRow[]` to `JobState` and initialize both as empty arrays. Handle `stage.started`, `stage.completed`, `search.route`, and `result.row` in `followJob`; update an existing path entry by `stage` and an existing row by URL. Treat `awaiting_input` as terminal for reconnect handling, but keep `replanning` connected.

- [ ] **Step 4: Create ConversationHistory**

Move the grouping logic currently in `Workbench.vue` into `ConversationHistory.vue`. The component fetches `/conversations`, renders “新建对话”, groups `今天/昨天/更早`, and renders the same running dot and awaiting-input tag. It must use `RouterLink` and close the mobile drawer after navigation through an emitted `close` event.

- [ ] **Step 5: Place history below system settings in App.vue**

Render `ConversationHistory` after the configuration group in the global sidebar, with a divider and label “会话历史”. Keep the settings link above it. On mobile, preserve the existing drawer and mask behavior. Remove the duplicate `.convs` markup and its fetch/watch code from `Workbench.vue`.

- [ ] **Step 6: Add the sidebar E2E assertion**

In `web/tests/e2e/main.spec.ts`, add a test that opens `/workbench`, asserts `.side` contains “系统设置” followed by “会话历史”, and asserts `.workbench` has no `.convs` element. Use the existing login helper.

- [ ] **Step 7: Run focused tests and commit**

Run: `npm --prefix web test` and `npm --prefix web run build`.

Expected: PASS. Commit: `git add web/src/types.ts web/src/jobStream.ts web/src/components/ConversationHistory.vue web/src/App.vue web/src/pages/Workbench.vue web/tests/e2e/main.spec.ts && git commit -m "feat: move history into global agent sidebar"`。

### Task 6: Make Workbench interruption and status visuals match the specification

**Files:**
- Modify: `web/src/pages/Workbench.vue`
- Modify: `web/src/theme.css`
- Modify: `web/src/types.ts`
- Test: `web/tests/e2e/main.spec.ts`

**Interfaces:**
- `send()` accepts an active task and sends a supplement with a generated `request_id`.
- `isJobTail(message)` ensures one process card per Job.
- `statusTone(status)` maps each status to neutral-border, light-surface CSS classes.

- [ ] **Step 1: Write failing interaction assertions**

```typescript
test('workbench keeps composer enabled while a job is running', async ({ page }) => {
  await page.goto('/workbench')
  await page.locator('textarea').fill('add English sources')
  await expect(page.locator('textarea')).toBeEnabled()
  await expect(page.locator('button[title="补充条件"]')).toBeEnabled()
})
```

- [ ] **Step 2: Run the test against the current UI**

Run: `npm --prefix web run e2e -- --grep "composer enabled"`.

Expected: FAIL because the current textarea and upload button are disabled while `busy` and the send control changes into the only stop control.

- [ ] **Step 3: Update send and stop controls**

Remove `busy` from the textarea and attachment `disabled` expressions. Add `crypto.randomUUID()` fallback `Date.now().toString(36)` as `request_id`. Keep a dedicated stop button in the input area and a send button titled “补充条件” while `busy`; call `post('/conversations/{id}/messages', {content, attachment_ids, request_id})`, then refresh and follow the same Job.

- [ ] **Step 4: Group messages by Job**

Add:

```typescript
function isJobTail(message: Message): boolean {
  const messages = conversation.value?.messages.filter((item) => item.job_id === message.job_id) || []
  return messages.at(-1)?.id === message.id
}
```

Render the process card and ReportCard only when `isJobTail(m)` is true; keep every user message bubble visible.

- [ ] **Step 5: Add the search path table**

Inside the expandable process card, render `live.path` as a table with “阶段、查询/来源、状态、耗时、结果数、失败原因”. Keep the current step summary above the table. Use `toolState` tones for status text only.

- [ ] **Step 6: Normalize status backgrounds and neutral borders**

Update `.proc`, `.state-label`, `.tool-status`, `.handover`, `.result-line`, `.tool-icon` and report styles so semantic colors appear only as light backgrounds and text; use `var(--line)` for borders. Add `.proc.replanning`, `.proc.awaiting_input`, `.state-label.replanning`, and `.state-label.awaiting_input`. Do not add colored `border-color` declarations.

- [ ] **Step 7: Run focused browser checks and commit**

Run: `npm --prefix web run build` and `npm --prefix web run e2e -- --grep "composer enabled|搜索路径|状态"`.

Expected: PASS at the configured desktop viewport. Commit: `git add web/src/pages/Workbench.vue web/src/theme.css web/src/types.ts web/tests/e2e/main.spec.ts && git commit -m "feat: support live agent supplements and paths"`。

### Task 7: Complete report layout, date visibility and responsive table behavior

**Files:**
- Modify: `web/src/components/ReportCard.vue`
- Modify: `web/src/theme.css`
- Modify: `web/tests/e2e/main.spec.ts`

**Interfaces:**
- Report table uses fixed date column width `120px` and source column width `88px`.
- Universal rows use three-point display with full `summary`/`quote` in title attributes and source links.

- [ ] **Step 1: Add failing desktop and mobile layout assertions**

```typescript
test('report date column stays readable', async ({ page }) => {
  await page.goto('/workbench')
  const dateCell = page.locator('.report .c-day').first()
  if (await dateCell.count()) {
    await expect(dateCell).toHaveCSS('width', '120px')
  }
})

test('mobile report can scroll without clipping dates', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 })
  await page.goto('/workbench')
  const report = page.locator('.report').first()
  if (await report.count()) {
    expect(await report.evaluate((el) => el.scrollWidth >= el.clientWidth)).toBe(true)
  }
})
```

- [ ] **Step 2: Run the tests and verify the current date clipping is detected**

Run: `npm --prefix web run e2e -- --grep "date column|mobile report"`.

Expected: FAIL or skip when no report fixture exists; when a report exists, the date width assertion exposes any regression below 120px.

- [ ] **Step 3: Implement fixed date and readable source columns**

Set `.grid col.c-day { width: 120px; }`, preserve `.grid td.c` centered alignment, and add `min-width: 120px` to date cells. Keep the existing 120px publication/deadline columns in the procurement table and add the same width to the generic table.

- [ ] **Step 4: Implement mobile horizontal table behavior**

Wrap wide tables in `.table-scroll` with `overflow-x: auto`, `min-width` on the table, and no viewport-level horizontal overflow. Keep the mobile purchase-card list only for procurement rows; generic search rows remain a horizontally scrollable table so title, language and date stay readable.

- [ ] **Step 5: Run desktop and mobile browser checks and commit**

Run: `npm --prefix web run e2e -- --grep "date column|mobile report"` and `npm --prefix web run build`.

Expected: PASS or explicit skip only when the local database has no completed report. Commit: `git add web/src/components/ReportCard.vue web/src/theme.css web/tests/e2e/main.spec.ts && git commit -m "fix: keep report dates and search columns readable"`。

### Task 8: Regression suite, browser acceptance and Luz skill experience notes

**Files:**
- Modify: `backend/tests/test_core.py` only when existing assertions need new status/mode values
- Modify: `web/tests/e2e/main.spec.ts`
- Create: the `raw/01-brief.md` files in the new session directories returned by each Luz skill's session command

**Interfaces:**
- Full suite keeps existing procurement behavior green.
- Skill notes record only reusable principles, never credentials, customer data or one-off paths.

- [ ] **Step 1: Run the complete backend and frontend unit suites**

Run: `cd backend; .venv\Scripts\python.exe -m pytest tests -q` and `cd web; npm test`.

Expected: all existing and new tests pass.

- [ ] **Step 2: Build the frontend**

Run: `cd web; npm run build`.

Expected: `vue-tsc` and Vite complete with exit code 0.

- [ ] **Step 3: Run E2E at desktop and mobile sizes**

Start the local API and frontend with the project commands, then run `cd web; npm run e2e`. Check 1440×900 and 390×844 screenshots for no clipping, no console errors, complete dates, table-only search results, global history placement, status background transitions, and an in-run supplement.

- [ ] **Step 4: Run static and rule checks**

Run: `git diff --check`, inspect `rg -n "border-color:.*(danger|warn|ok|accent)" web/src`, and verify no new采集 code calls `requests`, `httpx`, Exa, OpenCLI or Playwright. Inspect all new event names against the SSE contract.

- [ ] **Step 5: Write experience notes through the skill commands**

Use the registered skill commands to record these reusable rules:

```powershell
py -X utf8 D:\Codes\Luz-System\scripts\experience.py note --kind lesson --key universal-search-agent --text "搜索 Agent 的澄清、补充重规划、路径表和表格结果必须共用同一份 SSE 运行状态。"
py -X utf8 D:\Codes\Luz-Design\scripts\experience.py note --kind preference --key status-light-surface --text "语义色只放在状态文字浅色底和卡片浅背景，卡片边框保持中性细线。"
python -X utf8 D:\Codes\Luz-Dev\scripts\record_experience.py note --kind lesson --key agent-supplement-idempotency --text "执行中的补充消息复用同一 Job，request_id 幂等且只扣一次额度，重规划保留来源和证据。"
py -X utf8 D:\Codes\Luz-Writing\scripts\04-experience.py note --kind preference --key table-only-search-output --text "澄清允许自然语言；搜索结果和研究结果只输出表格、来源和状态信息，不写段落总结。"
node D:\Codes\Luz-Crawl\scripts\luz-crawl.mjs note --kind lesson --key universal-search-route --text "通用搜索只用 LuzCrawl 发现和读取任意域名，限流不重试，登录与验证码交给用户。" --why "DealRadar 通用搜索验收"
```

Create one new session with the registered session command for each skill, using the returned absolute directory as the session path. For example:

```powershell
py -X utf8 D:\Codes\Luz-System\scripts\new_session.py --name "DealRadar 通用搜索" --modes system --system-name "DealRadar" --modules "获客工作台,通用搜索 Agent" --card agent-ui --card agent-runtime-ui --card interaction --root D:\Codes\skill输出\Luz-System
py -X utf8 D:\Codes\Luz-Design\scripts\new_session.py --name "DealRadar 通用搜索" --card interface-visual --card palette --root D:\Codes\skill输出\Luz-Design
py -X utf8 D:\Codes\Luz-Writing\scripts\03-session.py new --topic "DealRadar 通用搜索" --card general --root D:\Codes\skill输出\Luz-Writing
node D:\Codes\Luz-Crawl\scripts\luz-crawl.mjs begin "DealRadar 通用搜索" --out D:\Codes\skill输出\Luz-Crawl --new
```

Use `python -X utf8 D:\Codes\Luz-Dev\scripts\record_experience.py note` for Luz-Dev because that skill stores notes through `record_experience.py`. Use the actual returned directories to write each `raw/01-brief.md` under “采用的规则” and “本次沉淀”; do not invent a numeric folder or write inside a skill directory.

- [ ] **Step 6: Review the final diff and commit the verification artifacts**

Run: `git status --short`, `git diff --stat`, and `git diff --check`. Confirm `config/apikey.txt` and `data/` are absent from the diff. Commit only project docs/tests and implementation changes with `git commit -m "feat: deliver universal search agent"` after all checks pass.

## Self-review checklist

- **Spec coverage:** Tasks 1–2 cover modes, clarification, supplements, status and idempotency; Task 3 covers LuzCrawl-only arbitrary-domain search, bilingual queries and evidence; Task 4 covers table-only reports and procurement bullets; Tasks 5–7 cover SSE, global history, status surfaces, dates and responsive tables; Task 8 covers regression, browser acceptance and skill notes.
- **Placeholder scan:** The plan contains no `TBD`, `TODO`, “implement later”, or unspecified error-handling steps. Every code change names an exact file, interface, test command and expected result.
- **Type consistency:** `search`, `awaiting_input`, `replanning`, `request_id`, `path`, `rows`, `WebQuery`, `WebExtract`, `dedupe_web_candidates`, `splitPurchaseItems`, `ConversationHistory` and `runner.replan` are defined before later tasks consume them.
- **Scope:** No task replaces the verified procurement storage model or introduces a second crawler; all changes fit the approved design and can be tested independently.
