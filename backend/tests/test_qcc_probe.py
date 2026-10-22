import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[2] / "scripts"))
from mcp_probe import serialize_probe_report


def test_probe_report_redacts_auth_headers_and_key(monkeypatch):
    monkeypatch.setenv("QCC_MCP_API_KEY", "synthetic-qcc-key")
    report = serialize_probe_report({"headers": {"Authorization": "Bearer synthetic-qcc-key"}, "text": "qcc_mcp_key=synthetic-qcc-key"})
    assert "synthetic-qcc-key" not in report
    assert "Authorization" not in report


def test_probe_report_keeps_safe_metadata():
    report = serialize_probe_report({"server": "qcc-company", "success": True, "response_hash": "abc"})
    assert "qcc-company" in report and "response_hash" in report
