"""OpenCLI 调用封装。

- 直接用 node 执行 opencli 入口脚本（不经过 opencli.cmd / cmd.exe），保证中文参数在 Windows 上不乱码。
- 统一 `-f json` 输出；失败时解析 OpenCLI 的错误结构（code / exitCode）。
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from functools import lru_cache
from pathlib import Path

EXIT_AUTH_REQUIRED = 77


class OpenCliError(RuntimeError):
    def __init__(self, code: str, message: str, exit_code: int, raw: str = ""):
        super().__init__(f"[{code}] {message}")
        self.code = code
        self.message = message
        self.exit_code = exit_code
        self.raw = raw


class AuthRequired(OpenCliError):
    pass


class RateLimited(OpenCliError):
    pass


PROJECT_ROOT = Path(__file__).resolve().parents[3]
VENDOR_DIR = PROJECT_ROOT / "vendor" / "opencli"
PLUGIN_DIR = PROJECT_ROOT / "src" / "opencli-plugin"


@lru_cache(maxsize=1)
def _entry(package_dir: str = "") -> list[str]:
    """返回 [node, main.js]；找不到时退回 opencli 可执行文件。"""
    node = shutil.which("node") or "node"
    candidates: list[Path] = []
    if package_dir:
        candidates.append(Path(package_dir))
    # 项目内置的定制版 OpenCLI（vendor/opencli）优先于全局安装。
    candidates.append(VENDOR_DIR)
    try:
        npm = shutil.which("npm") or "npm"
        root = subprocess.run([npm, "root", "-g"], capture_output=True, text=True, timeout=30, shell=os.name == "nt").stdout.strip()
        if root:
            candidates.append(Path(root) / "@jackwener" / "opencli")
    except Exception:
        pass
    for pkg in candidates:
        manifest = pkg / "package.json"
        if not manifest.exists():
            continue
        meta = json.loads(manifest.read_text(encoding="utf-8"))
        bin_field = meta.get("bin")
        rel = bin_field.get("opencli") if isinstance(bin_field, dict) else bin_field
        if rel and (pkg / rel).exists():
            return [node, str(pkg / rel)]
    exe = shutil.which("opencli")
    if exe:
        return [exe]
    raise FileNotFoundError("未找到 OpenCLI，请先执行: npm install -g @jackwener/opencli")


def _parse_error(text: str, exit_code: int) -> OpenCliError:
    code, message = "ERROR", text.strip()[-800:]
    # OpenCLI 失败输出为 YAML 风格：error:\n  code: X\n  message: Y
    for line in text.splitlines():
        s = line.strip()
        if s.startswith("code:"):
            code = s.split(":", 1)[1].strip()
        elif s.startswith("message:"):
            message = s.split(":", 1)[1].strip()
    if exit_code == EXIT_AUTH_REQUIRED or code == "AUTH_REQUIRED":
        return AuthRequired(code, message, exit_code, text)
    if "RATE_LIMITED" in text or "访问过于频繁" in text:
        return RateLimited("RATE_LIMITED", message, exit_code, text)
    return OpenCliError(code, message, exit_code, text)


# 浏览器命令的站点会话模式：persistent 的复用 tab 在 Edge/daemon 重启后可能失效并卡到超时，
# 因此 acq 默认使用 ephemeral（每条命令使用独立的一次性窗口，登录态来自同一 Edge 配置的 cookie，不受影响）。
SITE_SESSION = os.environ.get("ACQ_SITE_SESSION", "ephemeral")


def run(args: list[str], *, timeout: int = 300, package_dir: str = "", fmt_json: bool = True):
    """执行 opencli 子命令，返回解析后的 JSON（fmt_json=False 时返回文本）。"""
    cmd = _entry(package_dir) + list(args)
    if fmt_json and "-f" not in args:
        cmd += ["-f", "json"]
    env = dict(os.environ, NO_COLOR="1", FORCE_COLOR="0")
    env.setdefault("OPENCLI_SITE_SESSION", SITE_SESSION)
    # 定制版从项目目录加载 acq 插件，不依赖 ~/.opencli/plugins 中的链接。
    env.setdefault("OPENCLI_PLUGIN_DIRS", str(PLUGIN_DIR))
    env.setdefault("OPENCLI_BROWSER_COMMAND_TIMEOUT", str(max(60, timeout - 10)))
    proc = subprocess.run(cmd, capture_output=True, timeout=timeout, env=env)
    out = proc.stdout.decode("utf-8", errors="replace")
    err = proc.stderr.decode("utf-8", errors="replace")
    if proc.returncode != 0:
        raise _parse_error(out + "\n" + err, proc.returncode)
    if not fmt_json:
        return out
    text = out.strip()
    if not text:
        return []
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        # 某些版本会在 JSON 前输出提示行，取第一个 [ 或 { 开始解析
        for i, ch in enumerate(text):
            if ch in "[{":
                try:
                    return json.loads(text[i:])
                except json.JSONDecodeError:
                    continue
        raise OpenCliError("BAD_JSON", text[:500], proc.returncode, text)


def doctor(package_dir: str = "") -> dict:
    text = run(["doctor"], fmt_json=False, timeout=60, package_dir=package_dir)
    return {
        "daemon": "[OK] Daemon" in text,
        "extension": "[OK] Extension" in text,
        "connectivity": "[OK] Connectivity" in text,
        "text": text,
    }


def safe_doctor(package_dir: str = "") -> dict:
    try:
        return doctor(package_dir)
    except OpenCliError as e:  # doctor 在未连接时返回非 0
        text = e.raw
        return {
            "daemon": "[OK] Daemon" in text,
            "extension": "[OK] Extension" in text,
            "connectivity": "[OK] Connectivity" in text,
            "text": text,
        }
