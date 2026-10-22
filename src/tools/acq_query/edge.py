"""Agent 专用 Edge 的启动与 OpenCLI Browser Bridge 连通保障。"""

from __future__ import annotations

import json
import subprocess
import time

from . import opencli
from .config import Settings


def _enable_developer_mode(s: Settings) -> None:
    """Edge 再次启动时会停用“命令行加载的解压扩展”，除非配置中开启了开发人员模式。
    在启动前写入 extensions.ui.developer_mode=true（仅 Edge 未运行时修改才生效）。"""
    prefs = s.profile_dir / "Default" / "Preferences"
    if not prefs.exists():
        return  # 全新配置首次启动无需处理
    try:
        data = json.loads(prefs.read_text(encoding="utf-8"))
        ui = data.setdefault("extensions", {}).setdefault("ui", {})
        if ui.get("developer_mode") is True:
            return
        ui["developer_mode"] = True
        prefs.write_text(json.dumps(data, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    except Exception:  # noqa: BLE001 —— 写失败不阻塞启动，用户可在 edge://extensions 手动开启
        pass


def edge_running_with_profile(s: Settings) -> bool:
    """是否已有使用 Agent 配置目录的 Edge 进程（Windows：通过 PowerShell 查询命令行）。"""
    try:
        out = subprocess.run(
            ["powershell", "-NoProfile", "-Command",
             "Get-CimInstance Win32_Process -Filter \"Name='msedge.exe'\" | Select-Object -ExpandProperty CommandLine"],
            capture_output=True, timeout=30,
        ).stdout.decode("utf-8", errors="replace")
        return str(s.profile_dir).lower() in out.lower()
    except Exception:  # noqa: BLE001
        return False


def launch_edge(s: Settings, url: str | None = None) -> None:
    if not s.edge_exe.exists():
        raise FileNotFoundError(f"未找到 Edge：{s.edge_exe}（请修改 config/acq_tool.toml 的 browser.edge_exe）")
    if not (s.extension_dir / "manifest.json").exists():
        raise FileNotFoundError(
            f"未找到 OpenCLI 扩展：{s.extension_dir}。请从 https://github.com/jackwener/OpenCLI/releases 下载 "
            "opencli-extension-*.zip 解压到该目录（见 docs/02-产品与开发/设计文档/10-env-setup.md）"
        )
    s.profile_dir.mkdir(parents=True, exist_ok=True)
    if not edge_running_with_profile(s):
        _enable_developer_mode(s)
    args = [
        str(s.edge_exe),
        f"--user-data-dir={s.profile_dir}",
        f"--load-extension={s.extension_dir}",
        "--no-first-run",
        "--no-default-browser-check",
        url or s.start_url,
    ]
    flags = 0
    if hasattr(subprocess, "DETACHED_PROCESS"):
        flags = subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP
    subprocess.Popen(args, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, creationflags=flags, close_fds=True)


def ensure_bridge(s: Settings, log=print) -> dict:
    """确保 Edge 已打开且扩展已连接；未连接时自动启动 Agent 专用 Edge 并等待。"""
    st = opencli.safe_doctor(s.opencli_package_dir)
    if st["extension"] and st["connectivity"]:
        return st
    if edge_running_with_profile(s):
        log("• Agent 专用 Edge 已在运行但扩展未连接，正在打开新窗口唤醒扩展 …")
    else:
        log("• OpenCLI 扩展未连接，正在启动 Agent 专用 Edge …")
    launch_edge(s)
    deadline = time.time() + s.connect_timeout
    while time.time() < deadline:
        time.sleep(3)
        st = opencli.safe_doctor(s.opencli_package_dir)
        if st["extension"] and st["connectivity"]:
            log("• Edge 已连接 OpenCLI Browser Bridge")
            return st
    raise RuntimeError(
        "Edge 已启动但 OpenCLI 扩展未连接。请在该 Edge 中打开 edge://extensions 确认 OpenCLI 扩展已启用，"
        "然后重试（或执行 opencli daemon restart）。\n" + st.get("text", "")[-600:]
    )
