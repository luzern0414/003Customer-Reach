"""加载 config/acq_tool.toml，并把相对路径解析到项目根目录。"""

from __future__ import annotations

import tomllib
from dataclasses import dataclass, field
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[3]
CONFIG_PATH = PROJECT_ROOT / "config" / "acq_tool.toml"


def _abs(p: str) -> Path:
    path = Path(p)
    return path if path.is_absolute() else PROJECT_ROOT / path


@dataclass
class Settings:
    edge_exe: Path
    profile_dir: Path
    extension_dir: Path
    start_url: str
    connect_timeout: int
    opencli_package_dir: str
    command_timeout: int
    plugin_dir: Path
    days: int
    limit: int
    sources: list[str]
    yfbzb_types: list[str]
    pause: float
    exa_mcp_url: str
    exa_num_results: int
    processed_dir: Path
    raw_dir: Path
    raw: dict = field(default_factory=dict)


def load_settings(path: Path = CONFIG_PATH) -> Settings:
    data = tomllib.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    b, o, q, e, out = (data.get(k, {}) for k in ("browser", "opencli", "query", "exa", "output"))
    return Settings(
        edge_exe=Path(b.get("edge_exe", r"C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe")),
        profile_dir=_abs(b.get("profile_dir", "data/browser-profile/edge-agent")),
        extension_dir=_abs(b.get("extension_dir", str(Path.home() / ".opencli" / "browser-extension"))),
        start_url=b.get("start_url", "about:blank"),
        connect_timeout=int(b.get("connect_timeout", 60)),
        opencli_package_dir=str(_abs(o["package_dir"])) if o.get("package_dir") else "",
        command_timeout=int(o.get("command_timeout", 300)),
        plugin_dir=_abs(o.get("plugin_dir", "src/opencli-plugin")),
        days=int(q.get("days", 365)),
        limit=int(q.get("limit", 60)),
        sources=list(q.get("sources", ["yfbzb", "ccgp", "exa"])),
        yfbzb_types=list(q.get("yfbzb_types", ["zhaobiao", "zhongbiao", "caigou"])),
        pause=float(q.get("pause", 2.0)),
        exa_mcp_url=e.get("mcp_url", "https://mcp.exa.ai/mcp"),
        exa_num_results=int(e.get("num_results", 10)),
        processed_dir=_abs(out.get("processed_dir", "data/processed/companies")),
        raw_dir=_abs(out.get("raw_dir", "data/raw")),
        raw=data,
    )
