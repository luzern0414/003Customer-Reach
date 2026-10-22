"""通过 MCP 协议验证搜索、网页读取和浏览器工具，不执行营销动作。"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
try:
    from mcp.client.streamable_http import streamablehttp_client
except ImportError:  # current MCP SDK spelling
    from mcp.client.streamable_http import streamable_http_client as streamablehttp_client


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
from app.qcc_mcp import QccMcpClient, resolve_binding
EXA_URL = "https://mcp.exa.ai/mcp?tools=web_search_exa,web_fetch_exa"
SHANGHAI = timezone(timedelta(hours=8), "Asia/Shanghai")


def serialize_probe_report(report: dict) -> str:
    """Serialize a report after removing credential-bearing fields and values."""
    import os
    import re
    text = json.dumps(report, ensure_ascii=False, indent=2, default=str)
    text = re.sub(r'(?i)"?authorization"?\s*:\s*"[^"]*"\s*,?', "", text)
    text = re.sub(r'(?i)(api[_-]?key|token|bearer)\s*[=:]\s*[^,\s}\"]+', "[REDACTED]", text)
    secret = os.environ.get("QCC_MCP_API_KEY", "")
    return text.replace(secret, "[REDACTED]") if secret else text


def _qcc_bindings(server: str) -> dict:
    import os
    path = Path(os.environ.get("QCC_MCP_BINDINGS", str(ROOT / "config/qcc_mcp_bindings.yaml")))
    if not path.exists():
        path=ROOT/'config/qcc_mcp_bindings.example.yaml'
    try:
        import yaml
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        return data.get("servers", {}).get(server, {}) if isinstance(data, dict) else {}
    except Exception:
        return {}


@asynccontextmanager
async def connect(server: str):
    """连接白名单服务。

    server 非空且必须为 exa/fetch/playwright；返回已连接会话。
    非法名称抛 ValueError，连接错误由调用方处理，离开上下文时关闭连接。
    """
    if server == "exa":
        async with streamablehttp_client(EXA_URL) as streams:
            read, write = streams[:2]
            async with ClientSession(read, write, read_timeout_seconds=timedelta(seconds=75)) as session:
                yield session
        return
    if server == "fetch":
        command = str(ROOT / "tools/mcp/.venv/Scripts/mcp-server-fetch.exe")
        args = []
    elif server == "playwright":
        command = r"C:\Users\admin\.codex\nodejsv24.18.0\node.exe"
        args = [str(ROOT / "tools/mcp/playwright/node_modules/@playwright/mcp/cli.js"), "--headless", "--isolated", "--output-dir", str(ROOT / ".codex-tmp/mcp-browser")]
    else:
        raise ValueError("Unknown MCP server")
    params = StdioServerParameters(command=command, args=args, cwd=str(ROOT))
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write, read_timeout_seconds=timedelta(seconds=75)) as session:
            yield session


async def probe(options: argparse.Namespace) -> dict:
    """执行只读协议测试。

    options 必须是已校验的非空 CLI 参数，包含服务/操作和必要 URL 或查询。
    返回协议/调用报告；参数组合错误抛 ValueError，连接/调用异常向上层传播。
    """
    if options.server.startswith("qcc-"):
        server = options.server[4:]
        client = QccMcpClient(server, bindings=_qcc_bindings(server))
        tools = await client.list_tools()
        report = {"checked_at": datetime.now(SHANGHAI).strftime("%Y-%m-%d %H:%M:%S"), "server": options.server,
                  "tools": [{"name": t.name, "description": t.description, "inputSchema": t.input_schema} for t in tools], "success": True}
        if options.operation == "list":
            return report
        if not options.company_name:
            raise ValueError("basic requires --company-name")
        tool_name = resolve_binding("basic", tools, client.bindings)
        result = await client.call(tool_name, {"searchKey": options.company_name})
        report["call"] = {"tool": tool_name, "result": result.response, "response_hash": result.response_hash}
        return report
    async with connect(options.server) as session:
        initialized = await session.initialize()
        tools = await session.list_tools()
        report = {
            "checked_at": datetime.now(SHANGHAI).strftime("%Y-%m-%d %H:%M:%S"),
            "server": options.server,
            "initialization": initialized.model_dump(mode="json", exclude_none=True),
            "tools": [{"name": tool.name, **({"inputSchema": tool.inputSchema} if options.operation == "list" else {})} for tool in tools.tools],
        }
        if options.operation == "list":
            return report
        if options.server == "exa" and options.operation == "search":
            tool_name, arguments = "web_search_exa", {"query": options.query, "numResults": options.limit, "objective": options.objective}
        elif options.server == "exa" and options.operation == "fetch":
            tool_name, arguments = "web_fetch_exa", {"urls": options.urls or [options.url], "maxCharacters": options.max_length}
        elif options.server == "fetch" and options.operation == "fetch":
            tool_name, arguments = "fetch", {"url": options.url, "max_length": options.max_length, "start_index": options.start_index}
        elif options.server == "playwright" and options.operation == "browser":
            tool_name, arguments = "browser_navigate", {"url": options.url}
        else:
            raise ValueError("Operation is not supported by this server")
        result = await session.call_tool(tool_name, arguments=arguments)
        report["call"] = {"tool": tool_name, "arguments": arguments, "result": result.model_dump(mode="json", exclude_none=True)}
        if options.server == "playwright":
            try:
                snapshot = await session.call_tool("browser_snapshot", {})
                report["snapshot"] = snapshot.model_dump(mode="json", exclude_none=True)
            finally:
                await session.call_tool("browser_close", {})
        report["success"] = not bool(result.isError) and not bool(report.get("snapshot", {}).get("isError"))
        return report


def main() -> int:
    """解析非空 CLI 参数并打印结果；返回 0 表示协议成功，2 表示调用报错。"""
    sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--server", required=True, choices=["exa", "fetch", "playwright", "qcc-company", "qcc-operation", "qcc-risk", "qcc-tender"])
    parser.add_argument("--operation", default="list", choices=["list", "search", "fetch", "browser", "basic"])
    parser.add_argument("--company-name")
    parser.add_argument("--query")
    parser.add_argument("--objective", default="Find official company pages and public business contacts; distinguish evidence from purchase-intent inference.")
    parser.add_argument("--url")
    parser.add_argument("--urls", nargs="+")
    parser.add_argument("--limit", type=int, default=5)
    parser.add_argument("--max-length", type=int, default=18000)
    parser.add_argument("--start-index", type=int, default=0)
    parser.add_argument("--save", type=Path)
    options = parser.parse_args()
    if options.operation == "search" and not options.query:
        parser.error("search requires --query")
    if options.server.startswith("qcc-") and options.operation not in {"list", "basic"}:
        parser.error("QCC supports only list/basic")
    if options.operation == "basic" and not options.company_name:
        parser.error("basic requires --company-name")
    if options.operation in {"fetch", "browser"} and not (options.url or options.urls and options.server == "exa"):
        parser.error("fetch/browser requires --url")
    if not 1 <= options.limit <= 15 or not 1 <= options.max_length <= 100000 or options.start_index < 0:
        parser.error("limit/max-length/start-index is out of range")
    if options.save:
        options.save = options.save.resolve()
        if not options.save.is_relative_to(ROOT / ".codex-tmp"):
            parser.error("--save must be inside the project .codex-tmp directory")
    try:
        report = asyncio.run(probe(options))
    except Exception as exc:
        report = {"server": options.server, "success": False, "error": str(exc)}
    serialized = serialize_probe_report(report)
    if options.save:
        options.save.parent.mkdir(parents=True, exist_ok=True)
        options.save.write_text(serialized + "\n", encoding="utf-8")
    print(serialized)
    return 0 if report.get("success", True) else 2


if __name__ == "__main__":
    raise SystemExit(main())
