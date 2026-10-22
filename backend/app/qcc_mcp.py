"""受限的企查查官方 MCP Streamable HTTP 适配器。

业务层只接触固定 server、已发现并绑定的工具和安全的响应摘要；认证头永远只存在于
HTTP 客户端内，不进入结果、异常或持久化投影。
"""

from __future__ import annotations

import hashlib
import json
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Callable
from urllib.parse import urlparse

from .config import qcc_mcp_key


def _bounded_json(value: Any, budget: int = 180000) -> Any:
    """Bound nested provider data before serialization while preserving valid JSON."""
    if isinstance(value, dict):
        result = {}
        used = 2
        for key in sorted(value, key=lambda item: str(item)):
            item = _bounded_json(value[key], max(256, budget // max(1, len(value))))
            encoded = json.dumps({str(key): item}, ensure_ascii=False, separators=(",", ":"), default=str)
            if used + len(encoded) > budget:
                continue
            result[str(key)] = item
            used += len(encoded)
        return result
    if isinstance(value, list):
        result = []
        for item in value[:200]:
            candidate = _bounded_json(item, max(256, budget // max(1, min(len(value), 200))))
            if len(json.dumps(result + [candidate], ensure_ascii=False, separators=(",", ":"), default=str)) > budget:
                break
            result.append(candidate)
        return result
    if isinstance(value, str):
        return value[: min(len(value), max(64, budget))]
    if value is None or isinstance(value, (bool, int, float)):
        return value
    return str(value)[:256]


def archive_qcc_result(job_id: str, call_result: "QccCallResult", title: str, body: Any = None) -> dict:
    """Persist a bounded, deterministic projection of an authorized QCC response."""
    from sqlalchemy import select
    from .db import Session, Evidence
    projection = call_result.response if body is None else body
    bounded = _bounded_json(projection)
    encoded = json.dumps(bounded if isinstance(bounded, (dict, list)) else {"value": bounded},
                         ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)
    digest = hashlib.sha256(encoded.encode("utf-8")).hexdigest()
    meta = {"origin": "qcc_mcp", "server": call_result.server, "tool": call_result.tool,
            "authorized": bool(call_result.authorized), "response_hash": call_result.response_hash}
    with Session.begin() as db:
        row = db.scalar(select(Evidence).where(Evidence.job_id == job_id, Evidence.channel == "qcc_mcp",
            Evidence.source_meta["response_hash"].as_string() == call_result.response_hash))
        if not row:
            row = Evidence(job_id=job_id, channel="qcc_mcp", kind="授权数据", url="", title=title,
                body=encoded, content_hash=digest, source_meta=meta)
            db.add(row); db.flush()
        return {"id": row.id, "job_id": row.job_id, "channel": row.channel, "kind": row.kind,
                "url": row.url, "title": row.title, "body": row.body, "content_hash": row.content_hash,
                "source_meta": row.source_meta}


class QccConfigurationError(ValueError):
    """QCC 配置不满足固定官方端点或业务白名单约束。"""


QCC_SERVER_URLS = {
    "company": "https://agent.qcc.com/mcp/company/stream",
    "operation": "https://agent.qcc.com/mcp/operation/stream",
    "risk": "https://agent.qcc.com/mcp/risk/stream",
    "tender": "https://agent.qcc.com/mcp/tender/stream",
}


def qcc_server_url(server: str) -> str:
    """返回首期允许的官方 QCC MCP URL，拒绝未知 server。"""
    url = QCC_SERVER_URLS.get(server)
    parsed = urlparse(url or "")
    if parsed.scheme != "https" or parsed.hostname != "agent.qcc.com":
        raise QccConfigurationError("qcc_server_not_allowed")
    return url


@dataclass(frozen=True)
class QccTool:
    name: str
    description: str
    input_schema: dict[str, Any]


@dataclass(frozen=True)
class QccCallResult:
    server: str
    tool: str
    response: Any
    response_hash: str
    retrieved_at: str
    authorized: bool = True


def canonical_arguments(arguments: dict | None) -> dict:
    """将参数规范化为稳定 JSON 对象，不包含任何认证信息。"""
    if not isinstance(arguments, dict):
        return {}
    return json.loads(json.dumps(arguments, ensure_ascii=False, sort_keys=True, separators=(",", ":")))


def operation_key(server: str, tool: str, arguments: dict | None) -> str:
    value = {"server": server, "tool": tool, "arguments": canonical_arguments(arguments)}
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _tool_binding(bindings: dict | None, action: str) -> Any:
    configured = bindings or {}
    candidate = configured.get(action)
    if candidate is None:
        candidate = configured.get("actions", {}).get(action) if isinstance(configured.get("actions", {}), dict) else None
    if isinstance(candidate, dict):
        return candidate.get("tool")
    return candidate


def resolve_binding(action: str, tools: list[QccTool], bindings: dict | None) -> str:
    """要求非空、精确匹配 tools/list 的绑定；不根据名称猜测工具。"""
    name = _tool_binding(bindings, action)
    if not isinstance(name, str) or not name or not any(tool.name == name for tool in tools):
        from .source_errors import qcc_error
        raise qcc_error("qcc_tool_unmapped")
    return name


def _project_tool(tool: Any) -> QccTool:
    schema = getattr(tool, "inputSchema", getattr(tool, "input_schema", {})) or {}
    return QccTool(str(getattr(tool, "name", "")), str(getattr(tool, "description", "") or ""), dict(schema))


def _project_tools(listed: Any) -> list[QccTool]:
    return [_project_tool(item) for item in getattr(listed, "tools", listed or [])]


def _project_response(result: Any) -> Any:
    structured = getattr(result, 'structured_content', getattr(result, 'structuredContent', None))
    if isinstance(structured, (dict, list)):
        return structured
    parts = [getattr(item, 'text', '') for item in getattr(result, 'content', []) if getattr(item, 'text', '')]
    if len(parts) == 1:
        try:
            value = json.loads(parts[0])
            if isinstance(value, (dict, list)):
                return value
        except ValueError:
            pass
    if hasattr(result, "model_dump"):
        try:
            return result.model_dump(mode="json", exclude_none=True)
        except TypeError:
            return result.model_dump()
    if isinstance(result, (dict, list, str, int, float, bool)) or result is None:
        return result
    return {"value": str(result)}


def _response_hash(response: Any) -> str:
    raw = json.dumps(response, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


class QccMcpClient:
    """每次调用先 initialize/tools/list，再执行一个已发现的只读工具。"""

    def __init__(self, server: str, key_loader: Callable[[], str] = qcc_mcp_key,
                 http_client_factory: Callable | None = None, session_factory: Callable | None = None,
                 bindings: dict | None = None):
        qcc_server_url(server)
        self.server = server
        self.key_loader = key_loader
        self.http_client_factory = http_client_factory
        self.session_factory = session_factory
        self.bindings = bindings or {}

    def _http_client(self, key: str):
        import httpx2
        factory = self.http_client_factory or httpx2.AsyncClient
        timeout = httpx2.Timeout(connect=10.0, read=45.0, write=20.0, pool=10.0)
        return factory(headers={"Authorization": "Bearer " + key}, verify=True, timeout=timeout)

    @asynccontextmanager
    async def _session(self, client):
        if self.session_factory is not None:
            session = self.session_factory(None, None)
            if hasattr(session, "__aenter__"):
                async with session:
                    yield session
            else:
                yield session
            return
        from mcp import ClientSession
        from mcp.client.streamable_http import streamable_http_client
        async with streamable_http_client(qcc_server_url(self.server), http_client=client) as (read, write):
            async with ClientSession(read, write, read_timeout_seconds=45.0) as session:
                yield session

    async def list_tools(self) -> list[QccTool]:
        key = (self.key_loader() or "").strip()
        if not key:
            from .source_errors import qcc_error
            raise qcc_error("qcc_not_configured")
        client = self._http_client(key)
        try:
            async with self._session(client) as session:
                await session.initialize()
                return _project_tools(await session.list_tools())
        except Exception as exc:
            from .source_errors import QccError, qcc_error
            if isinstance(exc, QccError):
                raise
            raise qcc_error(exc) from None
        finally:
            if self.http_client_factory is None and hasattr(client, "aclose"):
                await client.aclose()

    async def call(self, tool_name: str, arguments: dict, action: bool = False) -> QccCallResult:
        if not isinstance(tool_name, str) or not tool_name:
            from .source_errors import qcc_error
            raise qcc_error("qcc_tool_not_allowed")
        configured = self.bindings.get("actions", self.bindings) if isinstance(self.bindings, dict) else {}
        allowed = {
            item.get("tool") if isinstance(item, dict) else item
            for item in configured.values()
        }
        if not action and tool_name not in {value for value in allowed if isinstance(value, str) and value}:
            from .source_errors import qcc_error
            raise qcc_error("qcc_tool_not_allowed")
        key = (self.key_loader() or "").strip()
        if not key:
            from .source_errors import qcc_error
            raise qcc_error("qcc_not_configured")
        client = self._http_client(key)
        try:
            async with self._session(client) as session:
                await session.initialize()
                discovered = _project_tools(await session.list_tools())
                if action:
                    tool_name = resolve_binding(tool_name, discovered, self.bindings)
                if not any(item.name == tool_name for item in discovered):
                    from .source_errors import qcc_error
                    raise qcc_error("qcc_tool_not_allowed")
                result = await session.call_tool(tool_name, arguments=canonical_arguments(arguments))
                if getattr(result, "is_error", getattr(result, 'isError', False)):
                    from .source_errors import qcc_error
                    text = " ".join(str(getattr(item, "text", "")) for item in getattr(result, "content", []) if hasattr(item, "text"))
                    raise qcc_error(text or "qcc_invalid_response")
                payload = _project_response(result)
                return QccCallResult(self.server, tool_name, payload, _response_hash(payload), datetime.now(timezone.utc).isoformat(), True)
        except Exception as exc:
            from .source_errors import QccError, qcc_error
            if isinstance(exc, QccError):
                raise
            raise qcc_error(exc) from None
        finally:
            if self.http_client_factory is None and hasattr(client, "aclose"):
                await client.aclose()
