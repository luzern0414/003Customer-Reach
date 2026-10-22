"""Standard-library boundary to the independent BidMonitor raw-data runtime.

This module neither imports the CRM backend nor promotes returned notices to facts.
The external tool owns discovery, evidence, version state and source restrictions.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess

SCHEMA = "clientreach.bidmonitor.v1"
DEFAULT_HOME = Path("D:/Codes/000GithubProject/003_BidMonitor-AI")
SOURCE_KEYS = ("ccgp", "shenzhen", "csg")
EXIT_CODES = {"complete": 0, "partial": 2, "blocked": 3}


class BidMonitorError(RuntimeError):
    """A local invocation/contract failure, with bounded optional diagnostics."""

    def __init__(self, code: str, message: str, stderr: str = ""):
        self.code = code
        self.diagnostic = stderr[:1024].strip()
        super().__init__(message + (f"; stderr: {self.diagnostic}" if self.diagnostic else ""))


def _strings(value: object, name: str) -> list[str]:
    if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
        raise BidMonitorError("invalid_input", f"{name} must be a list of strings")
    return [item.strip() for item in value if item.strip()]


def _validate_response(result: object) -> dict:
    def require(container, name, types):
        if name not in container or not isinstance(container[name], types):
            raise BidMonitorError("invalid_schema", f"invalid BidMonitor schema field: {name}")

    if not isinstance(result, dict) or result.get("schema_version") != SCHEMA:
        raise BidMonitorError("invalid_schema", f"invalid BidMonitor schema; expected {SCHEMA}")
    if not isinstance(result.get("status"), str) or result["status"] not in EXIT_CODES:
        raise BidMonitorError("invalid_schema", "invalid BidMonitor schema status")
    for name in ("query", "coverage", "metrics"):
        require(result, name, dict)
    for name in ("results", "errors"):
        require(result, name, list)
    if any(not isinstance(item, dict) for item in result["errors"]):
        raise BidMonitorError("invalid_schema", "invalid BidMonitor schema errors entries")
    if any(not isinstance(item, dict) for item in result["coverage"].values()):
        raise BidMonitorError("invalid_schema", "invalid BidMonitor schema coverage entries")
    for notice in result["results"]:
        if not isinstance(notice, dict):
            raise BidMonitorError("invalid_schema", "invalid BidMonitor schema result entry")
        for name in ("source", "url", "title", "content", "event_id", "version_id", "change", "stage", "role", "evidence_status"):
            require(notice, name, str)
        for name in ("published_at", "deadline", "buyer_name", "agency_name", "project_number",
                     "project_name", "budget", "lot", "region"):
            require(notice, name, (str, type(None)))
        for name in ("winner_names", "candidate_names"):
            require(notice, name, list)
            if any(not isinstance(item, str) for item in notice[name]):
                raise BidMonitorError("invalid_schema", f"invalid BidMonitor schema field: {name}")
        for name in ("field_evidence", "conflicts", "date_filter", "actionability"):
            require(notice, name, dict)
        require(notice, "match_reasons", list)
        if any(not isinstance(item, dict) for item in notice["match_reasons"]):
            raise BidMonitorError("invalid_schema", "invalid BidMonitor schema match_reasons entries")
        for name in ("field_evidence", "conflicts"):
            if any(not isinstance(entries, list) or any(not isinstance(item, dict) for item in entries)
                   for entries in notice[name].values()):
                raise BidMonitorError("invalid_schema", f"invalid BidMonitor schema {name} entries")
    return result


def search(query: str, *, company: str = "", keywords: list[str] | None = None,
           sources: list[str] | None = None, days: int = 30, limit: int = 10,
           max_requests: int = 40, max_details: int = 12, timeout: int = 180,
           include_existing: bool = True) -> dict:
    """Return the complete external JSON, including partial/blocked evidence.

    ``keywords=None`` uses query as the single product term; an explicit list
    replaces it. Terms are OR conditions and company is an additional filter.
    """
    if not isinstance(query, str) or not isinstance(company, str):
        raise BidMonitorError("invalid_input", "query and company filters must be strings")
    terms = _strings([query] if keywords is None else keywords, "keywords")
    company = company.strip()
    if not terms and not company:
        raise BidMonitorError("invalid_input", "at least one nonempty product or company filter is required")
    selected = _strings(list(SOURCE_KEYS) if sources is None else sources, "sources")
    if not selected or any(source not in SOURCE_KEYS for source in selected):
        raise BidMonitorError("invalid_input", "sources must contain known keys: " + ",".join(SOURCE_KEYS))
    bounds = dict(days=days, limit=limit, max_requests=max_requests, max_details=max_details)
    for name, value in {**bounds, "timeout": timeout}.items():
        if type(value) is not int or value < (1 if name == "timeout" else 0):
            raise BidMonitorError("invalid_input", f"{name} must be a {'positive' if name == 'timeout' else 'nonnegative'} integer")
    if type(include_existing) is not bool:
        raise BidMonitorError("invalid_input", "include_existing must be a boolean")

    home = Path(os.environ.get("CLIENTREACH_BIDMONITOR_HOME", str(DEFAULT_HOME))).resolve()
    candidates = [home / ".venv" / "Scripts" / "python.exe", home / ".venv" / "bin" / "python"]
    runtime = next((path for path in candidates if path.is_file()), None)
    if runtime is None or not (home / "clientreach_bidmonitor" / "__main__.py").is_file():
        raise BidMonitorError("missing_runtime", f"BidMonitor runtime missing at {home}; install its isolated .venv and package")
    argv = [str(runtime), "-X", "utf8", "-m", "clientreach_bidmonitor", "search"]

    def option(flag: str, value: str):
        # Leading hyphens remain literal filter text rather than argparse flags.
        if value.startswith("-"):
            argv.append(f"--{flag}={value}")
        else:
            argv.extend([f"--{flag}", value])

    for term in terms:
        option("keyword", term)
    if company:
        option("company", company)
    argv.extend(["--sources", ",".join(selected)])
    for name, value in bounds.items():
        argv.extend(["--" + name.replace("_", "-"), str(value)])
    # Leave time for startup, state/output serialization and process shutdown.
    argv.extend(["--max-seconds", str(timeout - min(10, max(1, timeout // 10)))])
    if include_existing:
        argv.append("--include-existing")
    env = os.environ.copy()
    env.pop("PYTHONPATH", None)
    env.pop("PYTHONHOME", None)
    env.update(PYTHONUTF8="1", PYTHONIOENCODING="utf-8")
    try:
        completed = subprocess.run(argv, cwd=home, shell=False, capture_output=True,
                                   encoding="utf-8", env=env, timeout=timeout, check=False)
    except subprocess.TimeoutExpired:
        raise BidMonitorError("timeout", f"BidMonitor subprocess timeout after {timeout} seconds") from None
    except (OSError, UnicodeError):
        raise BidMonitorError("execution_error", "BidMonitor runtime could not execute or return UTF-8 output") from None
    try:
        result = json.loads(completed.stdout)
    except (ValueError, TypeError):
        raise BidMonitorError("invalid_json", "BidMonitor returned invalid JSON", completed.stderr) from None
    result = _validate_response(result)
    if completed.returncode != 0 and result["status"] == "complete":
        raise BidMonitorError("process_exit", f"BidMonitor process exit {completed.returncode} conflicts with complete JSON", completed.stderr)
    return result
