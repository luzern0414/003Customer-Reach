"""公开业务资料的 AI 研究工具：MCP 采集、证据归档与事实校验。"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
SHANGHAI = timezone(timedelta(hours=8), "Asia/Shanghai")
STOP_MARKERS = ("429", "RATE_LIMIT", "RATE LIMIT", "CAPTCHA", "PAYWALL", "UNAUTHORIZED")


def read_json(path: Path) -> dict:
    """读取非空 UTF-8 JSON 路径；文件不存在或格式错误时传播异常。"""
    return json.loads(path.read_text(encoding="utf-8-sig"))


def compact(text: str) -> str:
    """仅归一化空白，保留数字和语义；空文本返回空串，供逐字证据匹配。"""
    return re.sub(r"\s+", "", text)


def public_url(url: str) -> bool:
    """检查来源 URL 为无凭据的公网 HTTP(S) 地址；为空或本地地址时返回 False。"""
    parsed = urlparse(url)
    host = parsed.hostname or ""
    return (parsed.scheme in {"https", "http"} and bool(host)
            and not parsed.username and not parsed.password
            and host.lower() not in {"localhost", "127.0.0.1", "::1"}
            and not re.match(r"^(10\.|192\.168\.|172\.(1[6-9]|2\d|3[01])\.)", host))


async def acquire(catalog: dict, destination: Path, mode: str, resume: bool = False) -> dict:
    """采集白名单来源并追加归档；catalog 必须含 queries/sources，mode 限 search/fetch/all。

    destination 必须为新目录，resume=True 时只复用 URL/参数完全相同的记录，不覆盖原文。
    错误以记录返回；限流、访问保护或三个连续连接失败时停止本轮。
    此函数只获取证据，不生成联系人、采购量或价格事实。
    """
    from mcp_probe import connect

    if destination.exists() and not resume:
        raise ValueError("Output directory already exists; choose a new run directory")
    destination.mkdir(parents=True, exist_ok=resume)
    jobs = []
    if mode in {"search", "all"}:
        for number, query in enumerate(catalog.get("queries", []), 1):
            jobs.append((f"Q{number:02d}", "web_search_exa", {
                "query": query, "objective": catalog["objective"],
                "numResults": min(10, max(1, catalog.get("num_results", 5))),
            }))
    if mode in {"fetch", "all"}:
        for source in catalog["sources"]:
            if source.get("fetch_policy") == "search_only":
                continue
            if not re.fullmatch(r"[A-Za-z0-9_-]+", source["id"]):
                raise ValueError("Source ID is not a safe archive filename")
            if not public_url(source["url"]):
                raise ValueError(f"Non-public source URL: {source['id']}")
            jobs.append((source["id"], "web_fetch_exa", {
                "urls": [source["url"]], "maxCharacters": 40000,
            }))
    summary = {"started_at": datetime.now(SHANGHAI).strftime("%Y-%m-%d %H:%M:%S"),
               "mode": mode, "records": [], "stopped": False}
    consecutive_failures = 0
    for source_id, tool_name, arguments in jobs:
        saved_path = destination / f"{source_id}.json"
        if resume and saved_path.exists():
            previous = read_json(saved_path)
            if previous.get("arguments") != arguments or previous.get("tool") != tool_name:
                raise ValueError(f"Resume arguments differ for immutable record {source_id}")
            record = previous
            encoded = saved_path.read_bytes()
            if any(word in previous.get("error", "").upper() for word in STOP_MARKERS):
                summary["stopped"] = True
        else:
            record = {"id": source_id, "tool": tool_name, "arguments": arguments,
                      "captured_at": datetime.now(SHANGHAI).strftime("%Y-%m-%d %H:%M:%S")}
            try:
                # 每个作业使用独立连接，避免一个站点超时使同一 MCP 会话后续作业全部失效。
                async with connect("exa") as session:
                    await asyncio.wait_for(session.initialize(), timeout=30)
                    result = await asyncio.wait_for(session.call_tool(tool_name, arguments), timeout=55)
                record["response"] = result.model_dump(mode="json", exclude_none=True)
                body = "\n".join(item.text for item in result.content if hasattr(item, "text"))
                record["text"] = body
                reported_error = result.isError or bool(re.search(
                    r"(?i)(UNSUPPORTED_URL|CRAWL_ERROR|FETCH_ERROR|NO_CONTENT|Failed to crawl|\"error\"\s*:)", body))
                record["status"] = "provider_error" if reported_error else "ok"
                # 只检查返回错误标识，不能把网页正常出现的登录链接误判为封锁。
                protected = reported_error and any(word in body.upper() for word in STOP_MARKERS)
                if protected:
                    summary["stopped"] = True
            except Exception as exc:
                details = repr(exc)
                record.update(status="transport_error", error=details, text="")
                consecutive_failures += 1
                if any(word in details.upper() for word in STOP_MARKERS) or consecutive_failures >= 3:
                    summary["stopped"] = True
            encoded = json.dumps(record, ensure_ascii=False, indent=2).encode("utf-8")
            saved_path.write_bytes(encoded)
        if record["status"] == "ok":
            consecutive_failures = 0
        entry = {"id": source_id, "status": record["status"], "sha256": hashlib.sha256(encoded).hexdigest(),
                 "characters": len(record.get("text", ""))}
        summary["records"].append(entry)
        # manifest 是可重建索引，每条原文写完即刷新，进程中断也保留可恢复状态。
        (destination / "manifest.json").write_text(
            json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps(entry, ensure_ascii=False), flush=True)
        if summary["stopped"]:
            break
        await asyncio.sleep(0.7)
    summary["finished_at"] = datetime.now(SHANGHAI).strftime("%Y-%m-%d %H:%M:%S")
    (destination / "manifest.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    return summary


def validate(dataset: dict, archive: Path | None = None) -> dict:
    """检查 dataset 的来源、主体、引用、价格和时间；无效引用抛 ValueError。

    archive 可为空，为空时不宣称正文复核。非空时逐字匹配采集正文，返回缺口而不补值。
    返回完整校验统计；此校验不等于工商存续、电话号码接通或报价有效期的验证。
    """
    sources = {item["id"]: item for item in dataset["sources"]}
    entities = {item["id"]: item for item in dataset["entities"]}
    if len(sources) != len(dataset["sources"]) or len(entities) != len(dataset["entities"]):
        raise ValueError("Duplicate source or entity IDs")
    cutoff = dataset["as_of"]
    if archive and (archive / "manifest.json").exists():
        for entry in read_json(archive / "manifest.json")["records"]:
            raw_path = archive / f"{entry['id']}.json"
            if not raw_path.exists() or hashlib.sha256(raw_path.read_bytes()).hexdigest() != entry["sha256"]:
                raise ValueError(f"Archive hash mismatch: {entry['id']}")
    for source in sources.values():
        if not public_url(source["url"]):
            raise ValueError(f"Invalid source URL: {source['id']}")
        if source.get("published_on") and source["published_on"] > cutoff:
            raise ValueError(f"Future source date: {source['id']}")
    fact_ids, counts, warnings = set(), {}, []
    for fact in dataset["facts"]:
        key = (fact["entity_id"], fact["field"])
        if key in fact_ids:
            raise ValueError(f"Duplicate fact key: {key}")
        fact_ids.add(key)
        if fact["entity_id"] not in entities:
            raise ValueError(f"Unknown entity: {fact['entity_id']}")
        if fact.get("value") is None:
            if not fact.get("missing_reason"):
                raise ValueError(f"Missing fact requires a reason: {key}")
            continue
        if not fact.get("evidence"):
            raise ValueError(f"Unsourced fact: {key}")
        if fact["field"] == "phone":
            quoted_digits = [re.sub(r"\D", "", e["quote"]) for e in fact["evidence"]]
            for number in re.findall(r"\d{7,}", str(fact["value"])):
                if not any(number in quoted for quoted in quoted_digits):
                    raise ValueError(f"Business phone not present in quote: {key}")
        for evidence in fact["evidence"]:
            sid, quote = evidence["source_id"], evidence["quote"]
            if sid not in sources or not quote.strip():
                raise ValueError(f"Invalid evidence: {key}")
            if archive:
                saved = archive / f"{sid}.json"
                matched = saved.exists() and compact(quote) in compact(read_json(saved).get("text", ""))
                if not matched:
                    warnings.append({"fact": list(key), "source": sid,
                                     "reason": "Citation retained from tool search; current snapshot not matched"})
        # 各数字保留统计年份与主体口径，防止用集团营收补充单店。
        if fact["field"] in {"revenue", "headcount"}:
            if not fact.get("scope") or not fact.get("as_of"):
                raise ValueError(f"Numeric company metric requires date and scope: {key}")
        if fact.get("as_of") and fact["as_of"] > cutoff:
            raise ValueError(f"Future fact date: {key}")
        counts[fact["field"]] = counts.get(fact["field"], 0) + 1
    for product in dataset["products"]:
        if product["source_id"] not in sources or not product.get("quotes"):
            raise ValueError(f"Unsourced product: {product['id']}")
        if product.get("price") is not None:
            if product["price"] < 0 or not product.get("price_kind") or not product.get("price_quote"):
                raise ValueError(f"Price lacks explicit kind/quote: {product['id']}")
            tokens = re.findall(r"\d+(?:\.\d+)?", product["price_quote"].replace(",", ""))
            if product["price"] not in [float(token) for token in tokens]:
                raise ValueError(f"Price not present in quote: {product['id']}")
    return {"entities": len(entities), "sources": len(sources), "facts": len(dataset["facts"]),
            "products": len(dataset["products"]), "known_fields": counts,
            "snapshot_warnings": warnings, "missing_values_preserved": True}


def main() -> int:
    """执行采集或校验 CLI；必需参数为空时 argparse 失败，异常返回非零退出码。"""
    sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    collect = commands.add_parser("collect")
    collect.add_argument("--catalog", type=Path, required=True)
    collect.add_argument("--output", type=Path, required=True)
    collect.add_argument("--mode", choices=["all", "search", "fetch"], default="all")
    collect.add_argument("--resume", action="store_true")
    check = commands.add_parser("validate")
    check.add_argument("--input", type=Path, required=True)
    check.add_argument("--archive", type=Path)
    options = parser.parse_args()
    try:
        if options.command == "collect":
            target = options.output.resolve()
            if not target.is_relative_to(ROOT / "data/raw") and not target.is_relative_to(ROOT / ".codex-tmp"):
                raise ValueError("Archive must remain in data/raw or .codex-tmp")
            result = asyncio.run(acquire(read_json(options.catalog), target, options.mode, options.resume))
            success = not result["stopped"] and all(r["status"] == "ok" for r in result["records"])
        else:
            result = validate(read_json(options.input), options.archive)
            success = True
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0 if success else 2
    except Exception as exc:
        print(json.dumps({"success": False, "error": str(exc)}, ensure_ascii=False))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
