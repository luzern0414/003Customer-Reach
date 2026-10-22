"""汇总：去重、角色分组、上下游关系、采购品类，输出 JSON + Markdown。"""

from __future__ import annotations

import json
import re
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

ROLE_LABEL = {"buyer": "采购方", "winner": "中标/成交方", "candidate": "候选人", "mentioned": "提及", "related": "相关"}

_NOISE = re.compile(r"(招标公告|采购公告|询价单|询比价公告|中标(?:（成交）)?结果公告|结果公告|中标公告|成交公告|候选人公示|合同公告|合同书|公开招标|招标|采购|项目|【产品】|【服务】|【工程】|\(原标题.*?\)|（原标题.*?）)")


def _norm_title(t: str) -> str:
    return re.sub(r"[\s【】\[\]（）()：:，,。.-]+", "", t or "")


def _dedupe_key(n: dict, company: str) -> str:
    t = (n.get("title") or "").replace(company, "")
    t = re.sub(r"^北京|^.{2,20}?(?:有限公司|研究院|研究所|大学|学院)", "", t)
    t = _NOISE.sub("", t)
    return f"{_norm_title(t)[:30]}|{n.get('published_at', '')}"


def dedupe(notices: list[dict], company: str = "") -> list[dict]:
    """同一公告在多个源出现时合并（去企业名/公告类型词后的标题 + 日期），保留来源列表。"""
    merged: dict[str, dict] = {}
    for n in notices:
        key = _dedupe_key(n, company) if company else f"{_norm_title(n['title'])[:40]}|{n.get('published_at', '')}"
        if key in merged:
            m = merged[key]
            m["sources"].append({"source": n["source_label"], "url": n["url"]})
            for f in ("buyer", "winner", "agency", "amount", "region", "summary", "phones"):
                if not m.get(f) and n.get(f):
                    m[f] = n[f]
            if n.get("contacts"):
                m["contacts"] = (m.get("contacts") or []) + n["contacts"]
            if len(n.get("title", "")) > len(m.get("title", "")) and not re.fullmatch(r"[A-Z0-9]+", n.get("title", "")):
                m["title"], m["url"] = n["title"], n["url"] or m["url"]
            if m.get("role") in ("", "related", "mentioned") and n.get("role") in ("buyer", "winner", "candidate"):
                m["role"] = n["role"]
        else:
            m = dict(n)
            m["sources"] = [{"source": n["source_label"], "url": n["url"]}]
            merged[key] = m
    out = list(merged.values())
    out.sort(key=lambda x: x.get("published_at") or "", reverse=True)
    return out


def _category(title: str, company: str) -> str:
    t = (title or "").replace(company, "")
    t = re.sub(r"^.{2,30}?(?:有限公司|研究院|研究所|大学|学院)", "", t)
    t = _NOISE.sub("", t)
    t = re.sub(r"[\s,，、]+", " ", t).strip(" -_")
    # 去掉纯编号（询价单号等）与无信息量的词
    if not t or re.fullmatch(r"[A-Za-z0-9\-_ ]{6,}", t) or re.search(r"中标通知|结果确认|^产品$|^服务$", t):
        return ""
    words = t.split(" ")
    if len(words) > 1 and len(set(words)) == 1:  # “天线罩 天线罩”
        t = words[0]
    return t[:30]


# 合法的单位名称结尾（用于过滤从摘要里误抽出的“双方合同的一部”之类片段）
_ORG_TAIL = re.compile(r"(公司|集团|研究院|研究所|大学|学院|医院|中心|局|厅|委员会|办公室|学校|银行|事务所|分公司|部|站|所|院|处|社|厂|馆)$")
_AGENCY = re.compile(r"招标代理|招标有限|招标集团|招标股份|招标中心|项目管理|工程管理|造价咨询|工程咨询|咨询集团|咨询有限|采购代理|交易中心|采购中心")


def analyze(company: str, notices: list[dict]) -> dict:
    as_buyer = [n for n in notices if n.get("role") == "buyer"]
    as_winner = [n for n in notices if n.get("role") == "winner"]
    as_candidate = [n for n in notices if n.get("role") == "candidate"]

    # 上游供应商：本企业作为采购方的公告中的中标方
    suppliers = Counter(n["winner"] for n in as_buyer if n.get("winner") and company not in n["winner"])
    # 下游客户：本企业作为中标方的公告中的采购方
    customers = Counter(n["buyer"] for n in as_winner if n.get("buyer") and company not in n["buyer"]
                        and not _AGENCY.search(n["buyer"]) and _ORG_TAIL.search(n["buyer"]))
    agencies = Counter(re.sub(r"^[在由经于]", "", a) for n in notices for a in (n.get("agency"), n.get("buyer")) if a and _AGENCY.search(a))
    # 竞争对手：本企业为候选人/未中标时的中标方
    competitors = Counter(n["winner"] for n in as_candidate if n.get("winner") and company not in n["winner"] and _ORG_TAIL.search(n["winner"]))

    categories = Counter(_category(n["title"], company) for n in as_buyer if _category(n["title"], company))
    by_month: dict[str, int] = defaultdict(int)
    for n in as_buyer:
        if n.get("published_at"):
            by_month[n["published_at"][:7]] += 1

    contacts: dict[str, dict] = {}
    for n in as_buyer:
        for c in n.get("contacts") or []:
            name, phone = (c.get("name") or "").strip(), (c.get("phone") or "").strip()
            if not name and not phone:
                continue
            key = f"{name}|{phone}"
            item = contacts.setdefault(key, {"name": name, "phone": phone, "count": 0, "last_seen": "", "example": "", "source": n.get("source_label", "")})
            item["count"] += 1
            if (n.get("published_at") or "") > item["last_seen"]:
                item["last_seen"] = n.get("published_at") or ""
                item["example"] = n.get("title", "")[:40]
    by_source = Counter(src["source"] for n in notices for src in n.get("sources", []))

    return {
        "buyer_contacts": sorted(contacts.values(), key=lambda x: (-x["count"], x["name"]))[:30],
        "by_source": dict(by_source.most_common()),
        "counts": {
            "total": len(notices),
            "as_buyer": len(as_buyer),
            "as_winner": len(as_winner),
            "as_candidate": len(as_candidate),
            "other": len(notices) - len(as_buyer) - len(as_winner) - len(as_candidate),
        },
        "procurement_by_month": dict(sorted(by_month.items(), reverse=True)),
        "top_purchase_items": categories.most_common(20),
        "upstream_suppliers": suppliers.most_common(20),
        "downstream_customers": customers.most_common(20),
        "competitors": competitors.most_common(10),
        "agencies": agencies.most_common(10),
        "latest_purchase": as_buyer[0]["published_at"] if as_buyer else "",
        "latest_win": as_winner[0]["published_at"] if as_winner else "",
    }


def _md_table(rows: list[dict], cols: list[tuple[str, str]], limit: int = 50) -> str:
    if not rows:
        return "_无_\n"
    head = "| " + " | ".join(c[1] for c in cols) + " |\n|" + "---|" * len(cols) + "\n"
    body = ""
    for r in rows[:limit]:
        cells = []
        for key, _ in cols:
            v = r.get(key, "")
            if key == "title":
                url = r.get("url") or ""
                v = f"[{(v or '')[:50].replace('|', '/')}]({url})" if url else (v or "")
            cells.append(str(v or "").replace("|", "/").replace("\n", " "))
        body += "| " + " | ".join(cells) + " |\n"
    more = f"\n_共 {len(rows)} 条，表中显示前 {limit} 条，完整数据见 JSON。_\n" if len(rows) > limit else ""
    return head + body + more


def render_markdown(result: dict) -> str:
    c = result["company"]
    a = result["analysis"]
    notices = result["notices"]
    cols = [("published_at", "日期"), ("notice_type", "类型"), ("title", "标题"), ("buyer", "采购方"), ("winner", "中标方"), ("region", "地区"), ("source_label", "来源")]
    lines = [
        f"# {c} · 招投标信息报告",
        "",
        f"> 生成时间：{result['generated_at']} · 时间范围：近 {result['params']['days']} 天 · 数据源：{', '.join(result['params']['sources'])}",
        "",
        "## 概览",
        "",
        f"- 公告总数（去重后）：**{a['counts']['total']}**",
        f"- 作为**采购方**：{a['counts']['as_buyer']} 条（最近 {a['latest_purchase'] or '-'}）",
        f"- 作为**中标/成交方**：{a['counts']['as_winner']} 条（最近 {a['latest_win'] or '-'}）",
        f"- 作为候选人：{a['counts']['as_candidate']} 条；其他相关：{a['counts']['other']} 条",
        "",
        "### 数据源状态",
        "",
        "| 源 | 状态 | 条数 | 耗时 | 说明 |",
        "|---|---|---|---|---|",
    ]
    for st in result["source_status"]:
        lines.append(f"| {st['source']} | {st['status']} | {st['count']} | {st['seconds']:.1f}s | {st['message'][:80]} |")
    prof = result.get("profile") or {}
    if prof:
        labels = [("credit_code", "统一社会信用代码"), ("legal_person", "法定代表人"), ("established", "成立日期"), ("reg_capital", "注册资本"),
                  ("paid_capital", "实缴资本"), ("status", "登记状态"), ("company_type", "企业类型"), ("staff_size", "人员规模"),
                  ("insured", "参保人数"), ("nature", "企业性质"), ("industry", "所属行业"), ("region", "所属地区"),
                  ("address", "地址"), ("business_mode", "经营模式"), ("main_products", "主营产品"), ("phone", "电话"), ("email", "邮箱"),
                  ("shareholders", "股东"), ("key_people", "主要人员"), ("former_names", "曾用名"), ("tags", "标签"),
                  ("qcc_counts", "企查查统计"), ("business_scope", "经营范围"), ("intro", "简介")]
        lines += ["", "## 企业基本信息", "", "| 字段 | 内容 |", "|---|---|"]
        for k, lab in labels:
            if prof.get(k):
                lines.append(f"| {lab} | {str(prof[k]).replace('|', '/')[:300]} |")
        if prof.get("sources"):
            lines += ["", "来源：" + "；".join(f"[{x.get('source')}{(' · ' + x['title']) if x.get('title') else ''}]({x.get('url', '')})" for x in prof["sources"][:6])]
        lines.append("")
    if a.get("by_source"):
        lines += ["", "**各来源公告数（去重前归属）**：" + "，".join(f"{k} {v}" for k, v in a["by_source"].items())]
    lines += ["", "## 客户画像（采购侧）", ""]
    if a["procurement_by_month"]:
        lines.append("**月度采购公告数**：" + "，".join(f"{k}: {v}" for k, v in list(a["procurement_by_month"].items())[:12]))
        lines.append("")
    if a["top_purchase_items"]:
        lines.append("**主要采购品类/项目**（按出现次数）：")
        lines.append("")
        for item, cnt in a["top_purchase_items"][:15]:
            lines.append(f"- {item}（{cnt}）")
        lines.append("")
    if a.get("buyer_contacts"):
        lines += ["**采购联系人**（来自公开公告摘要，使用前请核实）：", "", "| 姓名 | 电话 | 出现次数 | 最近 | 示例公告 | 来源 |", "|---|---|---|---|---|---|"]
        for c in a["buyer_contacts"][:15]:
            lines.append(f"| {c['name']} | {c['phone']} | {c['count']} | {c['last_seen']} | {c['example']} | {c['source']} |")
        lines.append("")
    lines += ["## 上下游关系", "", "**上游 · 供应商**（本企业采购、对方中标）：", ""]
    lines += [f"- {k}（{v} 次）" for k, v in a["upstream_suppliers"]] or ["- _暂无（采购公告摘要中未披露中标方，可用 `--details` 读取详情补全）_"]
    lines += ["", "**下游 · 客户**（本企业中标、对方采购）：", ""]
    lines += [f"- {k}（{v} 次）" for k, v in a["downstream_customers"]] or ["- _暂无_"]
    if a.get("agencies"):
        lines += ["", "**常合作的招标代理机构**：", ""]
        lines += [f"- {k}（{v} 次）" for k, v in a["agencies"]]
    if a["competitors"]:
        lines += ["", "**竞争对手**（本企业为候选人时的中标方）：", ""]
        lines += [f"- {k}（{v} 次）" for k, v in a["competitors"]]
    lines += ["", "## 采购动态（作为采购方）", "", _md_table([n for n in notices if n.get("role") == "buyer"], cols)]
    lines += ["## 中标记录（作为供应商）", "", _md_table([n for n in notices if n.get("role") in ("winner", "candidate")], cols)]
    lines += ["## 其他相关公告", "", _md_table([n for n in notices if n.get("role") not in ("buyer", "winner", "candidate")], cols, 30)]
    if result.get("details"):
        lines += ["## 公告详情", ""]
        for d in result["details"]:
            lines += [
                f"### {d.get('title') or d.get('notice_title', '')}",
                "",
                f"- 状态：{d.get('status')}（{d.get('note', '')}）",
                f"- 采购方：{d.get('buyer', '')}；中标方：{d.get('winner', '')}；金额：{d.get('amount', '')}",
                f"- 联系人：{d.get('contacts', '')}；电话：{d.get('phones', '')}",
                f"- 来源：{d.get('source_url', '')}",
                "",
                "<details><summary>正文</summary>",
                "",
                (d.get("text") or "")[:3000],
                "",
                "</details>",
                "",
            ]
    lines += ["---", "", "_角色判定基于公告摘要的规则抽取（采购企业/采购人/中标人等字段），重要结论请点开原文核对。_", ""]
    return "\n".join(lines)


def safe_name(name: str) -> str:
    return re.sub(r'[\\/:*?"<>|\s]+', "_", name).strip("_")[:60] or "unnamed"


def save(result: dict, processed_dir: Path) -> tuple[Path, Path]:
    folder = processed_dir / safe_name(result["company"])
    folder.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    jp = folder / f"{stamp}.json"
    mp = folder / f"{stamp}.md"
    jp.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    mp.write_text(render_markdown(result), encoding="utf-8")
    (folder / "latest.md").write_text(render_markdown(result), encoding="utf-8")
    return jp, mp
