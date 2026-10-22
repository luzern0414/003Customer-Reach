"""acq 命令行入口。

用法（在项目根目录）：
  scripts/acq doctor                          # 检查 Edge / OpenCLI 扩展 / 插件 / 各站点登录状态
  scripts/acq login yfbzb                     # 打开 Edge 登录乙方宝（等待你完成登录）
  scripts/acq company "北京航天广通科技有限公司"  # 按企业查询招投标信息并生成报告
  scripts/acq company "XX公司" --days 180 --sources yfbzb,ccgp --details 3 --yes
  scripts/acq bidmonitor "软件" --keyword 人工智能  # 独立公开源原始数据 JSON
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from dataclasses import asdict
from datetime import datetime

from . import __version__, bidmonitor, edge, opencli, report, sources
from .config import load_settings

LOGIN_SITES = {
    "yfbzb": "乙方宝/千里马会员控制台",
    "jianyu": "剑鱼标讯",
    "1688": "1688",
}


def _print(msg: str = "") -> None:
    print(msg, flush=True)


def ensure_plugin(s) -> None:
    """确认 acq 插件可用：内置 OpenCLI 通过 OPENCLI_PLUGIN_DIRS 直接加载 src/opencli-plugin，无需全局安装。"""
    listing = opencli.run(["list"], fmt_json=False, timeout=60, package_dir=s.opencli_package_dir)
    if "qianlima" in listing and "yfbzb" in listing:
        return
    raise opencli.OpenCliError("PLUGIN_MISSING", f"OpenCLI 未加载 acq 插件，请确认 {s.plugin_dir} 存在且 vendor/opencli 依赖已安装（npm install --omit=dev）。", 1)


def ensure_login(s, site: str, *, interactive: bool = True, timeout: int = 600) -> dict:
    """检查站点登录；未登录时在 Edge 前台打开登录页并等待用户完成。"""
    try:
        rows = opencli.run([site, "whoami"], timeout=120, package_dir=s.opencli_package_dir)
        return rows[0] if isinstance(rows, list) and rows else rows
    except opencli.AuthRequired as e:
        if not interactive:
            raise
        _print(f"\n⚠ 需要登录 {LOGIN_SITES.get(site, site)}：{e.message}")
        _print(f"  已在 Agent 专用 Edge 中打开登录页，请完成登录（扫码或账号密码），最多等待 {timeout // 60} 分钟 …")
        rows = opencli.run([site, "login", "--timeout", str(timeout), "--window", "foreground"],
                           timeout=timeout + 60, package_dir=s.opencli_package_dir)
        row = rows[0] if isinstance(rows, list) and rows else rows
        _print(f"✓ 登录完成：{json.dumps(row, ensure_ascii=False)}")
        return row


def cmd_doctor(s, args) -> int:
    _print(f"acq {__version__} · 项目配置 config/acq_tool.toml")
    _print(f"• Edge：{s.edge_exe}（{'存在' if s.edge_exe.exists() else '不存在'}）")
    _print(f"• Agent 浏览器配置：{s.profile_dir}")
    _print(f"• OpenCLI 扩展目录：{s.extension_dir}（{'OK' if (s.extension_dir / 'manifest.json').exists() else '缺少 manifest.json'}）")
    st = edge.ensure_bridge(s, log=_print) if not args.no_launch else opencli.safe_doctor(s.opencli_package_dir)
    _print(f"• OpenCLI daemon={st['daemon']} extension={st['extension']} connectivity={st['connectivity']}")
    ensure_plugin(s)
    _print("• 插件 acq：已安装（yfbzb search/detail/login/whoami, ccgp search）")
    for site in ("yfbzb",):
        try:
            who = ensure_login(s, site, interactive=False)
            _print(f"• {LOGIN_SITES[site]}：已登录 {json.dumps(who, ensure_ascii=False)}")
        except opencli.AuthRequired as e:
            _print(f"• {LOGIN_SITES[site]}：未登录（{e.message}）→ 运行 scripts/acq login {site}")
        except opencli.OpenCliError as e:
            _print(f"• {LOGIN_SITES[site]}：检查失败 {e}")
    return 0


def cmd_login(s, args) -> int:
    edge.ensure_bridge(s, log=_print)
    ensure_plugin(s)
    ensure_login(s, args.site, interactive=True, timeout=args.timeout)
    return 0


def cmd_company(s, args) -> int:
    company = args.name.strip()
    srcs = [x.strip() for x in (args.sources or ",".join(s.sources)).split(",") if x.strip()]
    types = [x.strip() for x in (args.types or ",".join(s.yfbzb_types)).split(",") if x.strip()]
    days, limit = args.days or s.days, args.limit or s.limit
    _print(f"▶ 查询企业：{company}（近 {days} 天，每类最多 {limit} 条，数据源：{', '.join(srcs)}）")

    unknown = [x for x in srcs if x not in sources.ALL_SOURCES]
    if unknown:
        raise RuntimeError(f"未知数据源：{unknown}，可选：{','.join(sources.ALL_SOURCES)}")
    if any(x in srcs for x in sources.BROWSER_SOURCES):
        edge.ensure_bridge(s, log=_print)
    ensure_plugin(s)
    if "yfbzb" in srcs:
        try:
            ensure_login(s, "yfbzb", interactive=not args.no_login_prompt)
        except opencli.AuthRequired:
            _print("  ⚠ 乙方宝未登录，跳过会员控制台（改用乙方宝公开搜索）")
            srcs = [x for x in srcs if x != "yfbzb"] + ([] if "yfbzb_public" in srcs else ["yfbzb_public"])

    col = sources.Collected()
    t0 = time.time()
    if not args.no_profile:
        sources.collect_profile(s, company, col, log=_print)
    for src in srcs:
        if src == "yfbzb":
            try:
                sources.collect_yfbzb(s, company, days, limit, types, col, log=_print)
            except opencli.AuthRequired:
                ensure_login(s, "yfbzb", interactive=not args.no_login_prompt)
                sources.collect_yfbzb(s, company, days, limit, types, col, log=_print)
        elif src == "yfbzb_public":
            sources.collect_yfbzb_public(s, company, limit, col, log=_print)
        elif src == "qianlima":
            sources.collect_qianlima(s, company, days, limit, col, log=_print)
        elif src == "chinabidding":
            sources.collect_chinabidding(s, company, limit, col, log=_print)
        elif src == "jianyu":
            sources.collect_jianyu(s, company, limit, col, log=_print)
        elif src == "ebnew":
            sources.collect_ebnew(s, company, limit, col, log=_print)
        elif src == "ccgp":
            sources.collect_ccgp(s, company, days, limit, col, log=_print)
        elif src == "ggzy":
            sources.collect_ggzy(s, company, days, limit, col, log=_print)
        elif src == "cborg":
            sources.collect_cborg(s, company, col, log=_print)
        elif src == "exa":
            sources.collect_exa(s, company, col, log=_print)

    notices = report.dedupe(col.notices, company)
    details = []
    if args.details:
        candidates = [n for n in notices if n["source"] == "yfbzb" and n.get("role") == "buyer"] or [n for n in notices if n["source"] == "yfbzb"]
        n = min(args.details, len(candidates))
        if n:
            ok = args.yes
            if not ok:
                ans = input(f"\n将读取 {n} 条乙方宝详情（每条消耗 1 次会员查看额度，不足时回退公开页），继续？[y/N] ").strip().lower()
                ok = ans in ("y", "yes")
            if ok:
                details = sources.fetch_yfbzb_details(s, candidates, n, log=_print)

    result = {
        "company": company,
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "params": {"days": days, "limit": limit, "sources": srcs, "yfbzb_types": types},
        "elapsed_seconds": round(time.time() - t0, 1),
        "source_status": [asdict(x) for x in col.statuses],
        "profile": col.profile,
        "analysis": report.analyze(company, notices),
        "notices": notices,
        "details": details,
    }
    # 原始数据快照
    raw_dir = s.raw_dir / "acq_query" / datetime.now().strftime("%Y%m%d")
    raw_dir.mkdir(parents=True, exist_ok=True)
    (raw_dir / f"{report.safe_name(company)}-{datetime.now().strftime('%H%M%S')}.json").write_text(
        json.dumps(col.raw, ensure_ascii=False, indent=2), encoding="utf-8")

    jp, mp = report.save(result, s.processed_dir)
    a = result["analysis"]
    _print("\n✓ 完成："
           f"共 {a['counts']['total']} 条｜采购方 {a['counts']['as_buyer']}｜中标 {a['counts']['as_winner']}｜候选 {a['counts']['as_candidate']}"
           f"｜上游供应商 {len(a['upstream_suppliers'])}｜下游客户 {len(a['downstream_customers'])}")
    _print(f"  报告：{mp}\n  数据：{jp}")
    if args.json:
        print(json.dumps(result, ensure_ascii=False))
    return 0


def _bidmonitor_failure(query: dict, code: str, message: str) -> dict:
    return {
        "schema_version": bidmonitor.SCHEMA, "query": query,
        "status": "blocked", "coverage": {}, "metrics": {}, "results": [],
        "errors": [{"code": code, "message": message}],
    }


def cmd_bidmonitor(args) -> int:
    """Raw-data lookup before legacy settings, browser or CRM initialization."""
    try:
        result = bidmonitor.search(
            args.query, company=args.company, keywords=[args.query, *args.keyword],
            sources=None if args.sources is None else args.sources.split(","),
            days=args.days, limit=args.limit, max_requests=args.max_requests,
            max_details=args.max_details, timeout=args.timeout, include_existing=not args.new_only)
    except bidmonitor.BidMonitorError as exc:
        result = _bidmonitor_failure({"keywords": [args.query, *args.keyword], "company": args.company}, exc.code, str(exc))
        print(str(exc), file=sys.stderr)
    print(json.dumps(result, ensure_ascii=False))
    return bidmonitor.EXIT_CODES[result["status"]]


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="acq", description="AI 获客系统 · 定制信息查询工具（OpenCLI + Edge + Exa）")
    p.add_argument("--version", action="version", version=f"acq {__version__}")
    sub = p.add_subparsers(dest="cmd", required=True)

    bm = sub.add_parser("bidmonitor", help="独立公开采购情报原始数据（JSON；不启动浏览器）")
    bm.add_argument("query", help="首个产品关键词（与 --keyword 为 OR 条件）")
    bm.add_argument("--keyword", action="append", default=[], help="额外产品关键词，可重复")
    bm.add_argument("--company", default="", help="附加企业全文过滤条件")
    bm.add_argument("--sources", help="逗号分隔：" + ",".join(bidmonitor.SOURCE_KEYS))
    for name, default in (("days", 30), ("limit", 10), ("max-requests", 40), ("max-details", 12), ("timeout", 180)):
        bm.add_argument("--" + name, type=int, default=default)
    bm.add_argument("--new-only", action="store_true", help="只返回本查询条件下未见的版本；默认包含已见公告")

    d = sub.add_parser("doctor", help="检查 Edge、OpenCLI 扩展、插件与登录状态（未连接时自动启动 Edge）")
    d.add_argument("--no-launch", action="store_true", help="只检查，不自动启动 Edge")

    lg = sub.add_parser("login", help="在 Agent 专用 Edge 中登录站点并等待完成")
    lg.add_argument("site", choices=sorted(LOGIN_SITES))
    lg.add_argument("--timeout", type=int, default=600)

    c = sub.add_parser("company", help="按企业名查询招投标信息（采购动态、中标记录、上下游）")
    c.add_argument("name", help="企业全称，如：北京航天广通科技有限公司")
    c.add_argument("--days", type=int, help="时间范围（天），默认 365")
    c.add_argument("--limit", type=int, help="每个源/类型最多条数，默认 60")
    c.add_argument("--sources", help="逗号分隔：" + ",".join(sources.ALL_SOURCES) + "（默认见 config/acq_tool.toml）")
    c.add_argument("--no-profile", action="store_true", help="不查询企业基本信息")
    c.add_argument("--types", help="乙方宝类型：zhaobiao,zhongbiao,caigou,nijian,qianqi")
    c.add_argument("--details", type=int, default=0, help="读取前 N 条乙方宝详情（消耗会员额度）")
    c.add_argument("--yes", action="store_true", help="读取详情时不再询问")
    c.add_argument("--no-login-prompt", action="store_true", help="未登录时直接失败，不等待用户登录（供无人值守任务）")
    c.add_argument("--json", action="store_true", help="同时把完整结果 JSON 打印到 stdout")
    return p


def main(argv: list[str] | None = None) -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8")  # Windows 控制台中文
    except Exception:
        pass
    raw_argv = sys.argv[1:] if argv is None else argv
    try:
        args = build_parser().parse_args(raw_argv)
    except SystemExit as exc:
        if raw_argv[:1] != ["bidmonitor"] or not exc.code:
            raise
        # argparse already writes the specific diagnostic to stderr. Keep the
        # raw-data command's stdout parseable even for malformed CLI options.
        print(json.dumps(_bidmonitor_failure({"arguments": raw_argv[1:]}, "invalid_arguments",
                                            "invalid bidmonitor arguments; see stderr"), ensure_ascii=False))
        return int(exc.code)
    if args.cmd == "bidmonitor":
        return cmd_bidmonitor(args)
    s = load_settings()
    try:
        return {"doctor": cmd_doctor, "login": cmd_login, "company": cmd_company}[args.cmd](s, args)
    except opencli.AuthRequired as e:
        _print(f"✗ 需要登录：{e.message}（运行 scripts/acq login yfbzb）")
        return 77
    except (opencli.OpenCliError, RuntimeError, FileNotFoundError) as e:
        _print(f"✗ {e}")
        return 1
    except KeyboardInterrupt:
        _print("已取消")
        return 130
