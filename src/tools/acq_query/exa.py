"""Exa 托管 MCP（https://mcp.exa.ai/mcp）的最小 JSON-RPC 客户端（免 key 可用；设置 EXA_API_KEY 可提升额度）。"""

from __future__ import annotations

import json
import os
import re
import urllib.request

PROTOCOL_VERSION = "2025-06-18"


class ExaMcp:
    def __init__(self, url: str, timeout: int = 60):
        key = os.environ.get("EXA_API_KEY", "").strip()
        self.url = url + (("&" if "?" in url else "?") + f"exaApiKey={key}" if key else "")
        self.timeout = timeout
        self.session_id: str | None = None
        self._id = 0

    def _post(self, payload: dict) -> dict | None:
        headers = {"Content-Type": "application/json", "Accept": "application/json, text/event-stream", "User-Agent": "acq-query/0.1 (mcp-client)"}
        if self.session_id:
            headers["mcp-session-id"] = self.session_id
            headers["mcp-protocol-version"] = PROTOCOL_VERSION
        req = urllib.request.Request(self.url, data=json.dumps(payload).encode("utf-8"), headers=headers, method="POST")
        with urllib.request.urlopen(req, timeout=self.timeout) as resp:
            sid = resp.headers.get("mcp-session-id")
            if sid:
                self.session_id = sid
            body = resp.read().decode("utf-8", errors="replace")
            ctype = resp.headers.get("Content-Type", "")
        if not body.strip():
            return None
        if "text/event-stream" in ctype or body.lstrip().startswith(("event:", "data:")):
            msgs = [json.loads(line[5:].strip()) for line in body.splitlines() if line.startswith("data:") and line[5:].strip()]
            for m in msgs:
                if "result" in m or "error" in m:
                    return m
            return msgs[-1] if msgs else None
        return json.loads(body)

    def _rpc(self, method: str, params: dict | None = None) -> dict:
        self._id += 1
        resp = self._post({"jsonrpc": "2.0", "id": self._id, "method": method, "params": params or {}})
        if resp is None:
            return {}
        if "error" in resp:
            raise RuntimeError(f"Exa MCP 错误：{resp['error']}")
        return resp.get("result", {})

    def connect(self) -> None:
        self._rpc("initialize", {
            "protocolVersion": PROTOCOL_VERSION,
            "capabilities": {},
            "clientInfo": {"name": "acq-query", "version": "0.1.0"},
        })
        self._post({"jsonrpc": "2.0", "method": "notifications/initialized", "params": {}})

    def call(self, tool: str, arguments: dict) -> str:
        if not self.session_id:
            self.connect()
        result = self._rpc("tools/call", {"name": tool, "arguments": arguments})
        parts = [c.get("text", "") for c in result.get("content", []) if c.get("type") == "text"]
        return "\n".join(parts)

    def search(self, query: str, num_results: int = 10) -> list[dict]:
        text = self.call("web_search_exa", {"query": query, "numResults": num_results})
        return parse_search_text(text)

    def fetch(self, url: str, max_chars: int = 20000) -> str:
        return self.call("web_fetch_exa", {"urls": [url], "maxCharacters": max_chars})


def parse_search_text(text: str) -> list[dict]:
    """解析 web_search_exa 的文本输出（JSON 或 'Title:/URL:/Published Date:/Text:' 分段）。"""
    text = (text or "").strip()
    if not text:
        return []
    try:
        data = json.loads(text)
        items = data.get("results", data) if isinstance(data, dict) else data
        if isinstance(items, list):
            return [{
                "title": it.get("title", ""),
                "url": it.get("url", ""),
                "published_at": (it.get("publishedDate") or "")[:10],
                "text": (it.get("text") or it.get("highlights") or it.get("summary") or "")[:1500]
                if isinstance(it.get("text") or it.get("highlights") or "", str) else json.dumps(it.get("highlights"), ensure_ascii=False)[:1500],
            } for it in items if isinstance(it, dict)]
    except json.JSONDecodeError:
        pass
    rows: list[dict] = []
    for block in re.split(r"\n(?=Title:)", text):
        title = re.search(r"^Title:\s*(.*)$", block, re.M)
        url = re.search(r"^URL:\s*(\S+)", block, re.M)
        if not url:
            continue
        date = re.search(r"^Published(?: Date)?:\s*(\S+)", block, re.M)
        body = re.split(r"^(?:Text|Highlights|Summary):\s*", block, maxsplit=1, flags=re.M)
        rows.append({
            "title": title.group(1).strip() if title else "",
            "url": url.group(1).strip(),
            "published_at": (date.group(1) if date else "")[:10],
            "text": (body[1] if len(body) > 1 else "").strip()[:1500],
        })
    return rows
