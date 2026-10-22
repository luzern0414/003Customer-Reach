"""各数据源采集：统一输出 Notice 字典列表，并记录每个源的状态。

Notice 字段：
  source, source_label, notice_type, title, published_at, buyer, winner, agency, amount,
  role(buyer|winner|candidate|mentioned|related), region, summary, url, public_url, content_id, area_id,
  contacts(list), phones(str)

数据源（全部经 OpenCLI 插件 src/opencli-plugin 或 Exa）：
  yfbzb        乙方宝会员控制台（需登录）      招标/中标/采购意向/拟在建/前期商机
  yfbzb_public 乙方宝公开搜索（免登录）        招标
  qianlima     千里马公开接口                  全文检索，含招标人/中标人/代理/金额
  chinabidding 中国采购与招标网公开接口        标题/类型/日期
  jianyu       剑鱼标讯结果页（Edge）          含采购单位/联系人/电话
  ebnew        必联网                          预告/公告/结果
  ccgp         中国政府采购网（Edge）           全文检索
  ggzy         全国公共资源交易平台（Edge）     标题检索；验证码时等待用户
  cborg        中国国际招标网（检索后台不可用 → Exa site: 检索）
  exa          Exa 全网检索
"""

from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass, field

from . import opencli
from .config import Settings
from .exa import ExaMcp

YFBZB_TYPE_LABEL = {"zhaobiao": "招标", "zhongbiao": "中标", "caigou": "采购意向", "nijian": "拟在建", "qianqi": "前期商机"}

SOURCE_LABEL = {
    "yfbzb": "乙方宝会员", "yfbzb_public": "乙方宝公开", "qianlima": "千里马", "chinabidding": "中国采购与招标网",
    "jianyu": "剑鱼标讯", "ebnew": "必联网", "ccgp": "中国政府采购网", "ggzy": "全国公共资源交易平台",
    "cborg": "中国国际招标网", "exa": "Exa 网搜",
}

ALL_SOURCES = ["yfbzb", "yfbzb_public", "qianlima", "chinabidding", "jianyu", "ebnew", "ccgp", "ggzy", "cborg", "exa"]
BROWSER_SOURCES = {"yfbzb", "jianyu", "ccgp", "ggzy"}

_ORG = r"[一-龥A-Za-z0-9（）()·]{2,40}?(?:有限责任公司|股份有限公司|有限公司|研究院|研究所|大学|学院|医院|中心|局|公司)"
_AGENCY = re.compile(r"招标代理|招标有限|招标集团|招标股份|项目管理|工程管理|造价咨询|工程咨询|采购代理|交易中心|采购中心")


@dataclass
class SourceStatus:
    source: str
    status: str = "ok"  # ok | empty | auth_required | rate_limited | timeout | error | skipped
    count: int = 0
    message: str = ""
    seconds: float = 0.0


@dataclass
class Collected:
    notices: list[dict] = field(default_factory=list)
    statuses: list[SourceStatus] = field(default_factory=list)
    raw: dict = field(default_factory=dict)
    profile: dict = field(default_factory=dict)


# ---------------------------------------------------------------- 工具函数

def infer_role(company: str, title: str, summary: str, buyer: str, winner: str, notice_type: str = "") -> str:
    """与插件 lib/common.js#inferRole 同逻辑的 Python 版本。"""
    text = f"{title} {summary}"
    if buyer and company in buyer:
        return "buyer"
    if winner and company in winner:
        return "candidate" if "候选" in notice_type else "winner"
    idx = text.find(company)
    if idx < 0:
        return "related"
    before = text[max(0, idx - 40):idx]
    near = before[-8:]
    if (not buyer or company in buyer) and re.search(r"(采购企业|采购人|采购单位|招标人|招标单位|建设单位|业主(?:单位)?|发布企业)\s*(?:名称)?\s*[:：]?\s*$", before):
        return "buyer"
    if re.search(r"(拟从|拟向|从厂家|向厂家)[^。；;]{0,6}$", before):
        return "winner"  # 直接采购/单一来源：拟从某厂家采购
    # 标题以本企业开头且是采购类公告（“XX公司关于…采购公告”），排除“XX公司关于拟中标的提示性公告”
    if (title.startswith(company) and (not buyer or company in buyer) and not re.search(r"中标|成交|候选|提示性", title)
            and re.search(r"采购|询价|招标|比选|竞价|磋商|谈判|遴选", title[len(company):])):
        return "buyer"
    if re.search(r"(第[二三四五2-9]名|候选人)\s*[:：]?\s*$", near) or re.search(r"(^|\s)[1-9]\s*$", near):
        return "candidate"  # 评审排名表“2 某公司 …”
    other = winner and company not in winner
    if not other and re.search(r"(中标|成交|供应商|乙方|第[一1]名)[^。；;]{0,20}$", before):
        return "candidate" if "候选" in notice_type else "winner"
    if not other and re.search(r"\]\s*$", before) and "特此公告" in text[idx:idx + len(company) + 40]:
        return "winner"
    if re.search(r"中标|成交|结果", notice_type + title) and not other:
        return "winner"
    return "candidate" if other else "mentioned"


def _timed(fn):
    start = time.time()
    try:
        return fn(), time.time() - start, None
    except Exception as e:  # noqa: BLE001 —— 单个源失败不影响整体
        return None, time.time() - start, e


def _status_from_error(source: str, err: Exception, seconds: float) -> SourceStatus:
    if isinstance(err, opencli.AuthRequired):
        return SourceStatus(source, "auth_required", 0, err.message, seconds)
    if isinstance(err, opencli.RateLimited):
        return SourceStatus(source, "rate_limited", 0, err.message, seconds)
    if isinstance(err, opencli.OpenCliError) and err.code == "TIMEOUT":
        return SourceStatus(source, "timeout", 0, err.message, seconds)
    return SourceStatus(source, "error", 0, str(err)[:300], seconds)


def _notice(source: str, company: str, *, label: str | None = None, notice_type="", title="", published_at="", buyer="",
            winner="", agency="", amount="", region="", summary="", url="", role: str | None = None, **extra) -> dict:
    if buyer and _AGENCY.search(buyer):
        agency, buyer = agency or buyer, ""
    r = role or infer_role(company, title, summary, buyer, winner, notice_type)
    if r == "winner" and not winner:
        winner = company
    if r == "buyer" and not buyer:
        buyer = company
    n = {
        "source": source, "source_label": label or SOURCE_LABEL.get(source, source), "notice_type": notice_type,
        "title": title, "published_at": published_at, "buyer": buyer, "winner": winner, "agency": agency,
        "amount": amount, "role": r, "region": region, "summary": (summary or "")[:300], "url": url,
        "public_url": "", "content_id": "", "area_id": "", "contacts": [], "phones": "",
    }
    n.update(extra)
    return n


def _run_source(s: Settings, src: str, args: list[str], out: Collected, log, timeout: int | None = None) -> list[dict] | None:
    rows, sec, err = _timed(lambda: opencli.run(args, timeout=timeout or s.command_timeout, package_dir=s.opencli_package_dir))
    if err:
        st = _status_from_error(src, err, sec)
        out.statuses.append(st)
        log(f"    ✗ {st.status}: {st.message[:160]}")
        if st.status == "auth_required" and src == "yfbzb":
            raise err
        return None
    rows = rows or []
    out.raw[src] = rows
    out.statuses.append(SourceStatus(src, "ok" if rows else "empty", len(rows), "", sec))
    log(f"    ✓ {len(rows)} 条（{sec:.1f}s）")
    return rows


# ---------------------------------------------------------------- 各数据源

def collect_yfbzb(s: Settings, query: str, days: int, limit: int, types: list[str], out: Collected, log=print) -> None:
    for t in types:
        src = f"yfbzb:{t}"
        log(f"  - 乙方宝会员 {YFBZB_TYPE_LABEL.get(t, t)} …")
        rows = _run_source(s, src, ["yfbzb", "search", query, "--type", t, "--days", str(days), "--limit", str(limit)], out, log)
        for r in rows or []:
            out.notices.append(_notice(
                "yfbzb", query, label=f"乙方宝·{YFBZB_TYPE_LABEL.get(t, t)}", notice_type=r.get("notice_type", ""),
                title=r.get("title", ""), published_at=r.get("published_at", ""), buyer=r.get("buyer", ""),
                winner=r.get("winner", ""), agency=r.get("agency", ""), amount=r.get("amount", ""), region=r.get("area", ""),
                summary=r.get("summary", ""), url=r.get("url", ""), role=r.get("role") or None,
                public_url=r.get("public_url", ""), content_id=r.get("content_id", ""), area_id=r.get("area_id", ""), yfbzb_type=t,
            ))
        time.sleep(s.pause)


def collect_yfbzb_public(s: Settings, query: str, limit: int, out: Collected, log=print) -> None:
    log("  - 乙方宝公开搜索 …")
    for r in _run_source(s, "yfbzb_public", ["yfbzb", "public", query, "--limit", str(limit)], out, log) or []:
        out.notices.append(_notice("yfbzb_public", query, notice_type=r.get("notice_type", ""), title=r.get("title", ""),
                                   published_at=r.get("published_at", ""), buyer=r.get("buyer", ""), region=r.get("area", ""),
                                   url=r.get("url", ""), content_id=r.get("content_id", "")))


def collect_qianlima(s: Settings, query: str, days: int, limit: int, out: Collected, log=print) -> None:
    log("  - 千里马（全文检索）…")
    for r in _run_source(s, "qianlima", ["qianlima", "search", query, "--days", str(days), "--limit", str(limit)], out, log) or []:
        out.notices.append(_notice("qianlima", query, notice_type=r.get("notice_type", ""), title=r.get("title", ""),
                                   published_at=r.get("published_at", ""), buyer=r.get("buyer", ""), winner=r.get("winner", ""),
                                   agency=r.get("agency", ""), amount=r.get("amount") or r.get("budget", ""),
                                   region=r.get("area", ""), url=r.get("url", ""), content_id=r.get("content_id", "")))


def collect_chinabidding(s: Settings, query: str, limit: int, out: Collected, log=print) -> None:
    log("  - 中国采购与招标网 …")
    for r in _run_source(s, "chinabidding", ["chinabidding", "search", query, "--limit", str(limit)], out, log) or []:
        out.notices.append(_notice("chinabidding", query, notice_type=r.get("notice_type", ""), title=r.get("title", ""),
                                   published_at=r.get("published_at", ""), url=r.get("url", ""),
                                   role="related", content_id=r.get("notice_id", "")))


def collect_jianyu(s: Settings, query: str, limit: int, out: Collected, log=print) -> None:
    log("  - 剑鱼标讯（Edge 页面解析）…")
    for r in _run_source(s, "jianyu", ["jianyu", "list", query, "--limit", str(limit)], out, log, timeout=240) or []:
        try:
            contacts = json.loads(r.get("contacts") or "[]")
        except json.JSONDecodeError:
            contacts = []
        out.notices.append(_notice("jianyu", query, notice_type=r.get("notice_type", ""), title=r.get("title", ""),
                                   published_at=r.get("published_at", ""), buyer=r.get("buyer", ""), winner=r.get("winner", ""),
                                   agency=r.get("agency", ""), amount=r.get("budget", ""), region=r.get("region", ""),
                                   summary=r.get("summary", ""), url=r.get("url", ""), contacts=contacts, phones=r.get("phones", ""),
                                   content_id=r.get("notice_id", "")))


def collect_ebnew(s: Settings, query: str, limit: int, out: Collected, log=print) -> None:
    log("  - 必联网 …")
    for r in _run_source(s, "ebnew", ["ebnew", "search", query, "--limit", str(min(limit, 100))], out, log) or []:
        out.notices.append(_notice("ebnew", query, notice_type=r.get("notice_type", ""), title=r.get("title", ""),
                                   published_at=r.get("published_at", ""), region=r.get("region", ""),
                                   summary=f"招标方式：{r.get('method', '')} 产品：{r.get('product', '')}", url=r.get("url", "")))


def collect_ccgp(s: Settings, query: str, days: int, limit: int, out: Collected, log=print) -> None:
    log("  - 中国政府采购网（全文检索）…")
    for r in _run_source(s, "ccgp", ["ccgp", "search", query, "--days", str(days), "--limit", str(min(limit, 100))], out, log) or []:
        buyer = r.get("buyer", "")
        out.notices.append(_notice("ccgp", query, notice_type=r.get("notice_type", ""), title=r.get("title", ""),
                                   published_at=r.get("published_at", ""), buyer=buyer, agency=r.get("agency", ""),
                                   region=r.get("region", ""), summary=r.get("summary", ""), url=r.get("url", ""),
                                   role="buyer" if query in buyer else None))


def collect_ggzy(s: Settings, query: str, days: int, limit: int, out: Collected, log=print) -> None:
    log("  - 全国公共资源交易平台（如出现验证码，请在 Edge 中输入）…")
    for r in _run_source(s, "ggzy", ["ggzy", "search", query, "--days", str(min(days, 365)), "--limit", str(limit), "--timeout", "180"],
                         out, log, timeout=300) or []:
        out.notices.append(_notice("ggzy", query, notice_type=r.get("stage", ""), title=r.get("title", ""),
                                   published_at=r.get("published_at", ""), region=r.get("region", ""),
                                   summary=f"{r.get('classify', '')} {r.get('platform', '')}", url=r.get("url", "")))


def _exa_rows(client: ExaMcp, queries: list[str], n: int) -> list[dict]:
    rows, seen = [], set()
    for q in queries:
        for r in client.search(q, n):
            if r.get("url") and r["url"] not in seen:
                seen.add(r["url"])
                rows.append(r)
    return rows


def _exa_to_notice(src: str, query: str, r: dict) -> dict | None:
    text = f"{r.get('title', '')}\n{r.get('text', '')}"
    if query not in text:
        return None
    winner = (re.search(r"(?:中标单位|中标人|成交供应商|中标供应商|供应商名称)\s*[:：]\s*(" + _ORG + ")", text) or [None, ""])[1]
    buyer = (re.search(r"(?:采购人|采购单位|招标人|招标单位)\s*(?:名称)?\s*[:：]\s*(" + _ORG + ")", text) or [None, ""])[1]
    # 网页结果多为企业介绍/聚合页，只有明确写出采购方或中标方为本企业时才归类
    role = "mentioned"
    if (winner and query in winner) or re.search(re.escape(query) + r"\s*(?:中标|成交)", text):
        role = "winner"
    elif buyer and query in buyer:
        role = "buyer"
    published = r.get("published_at", "")
    return _notice(src, query, notice_type="网页", title=r.get("title", ""),
                   published_at=published if re.match(r"\d{4}-\d{2}-\d{2}", published) else "",
                   buyer=buyer, winner=winner, summary=re.sub(r"\s+", " ", r.get("text", ""))[:300], url=r.get("url", ""), role=role)


def collect_exa(s: Settings, query: str, out: Collected, log=print) -> None:
    log("  - Exa 全网检索 …")
    start = time.time()
    try:
        rows = _exa_rows(ExaMcp(s.exa_mcp_url), [f"{query} 中标公告", f"{query} 采购 招标公告"], s.exa_num_results)
        out.raw["exa"] = rows
        n = [x for x in (_exa_to_notice("exa", query, r) for r in rows) if x]
        out.notices.extend(n)
        out.statuses.append(SourceStatus("exa", "ok" if n else "empty", len(n), "", time.time() - start))
        log(f"    ✓ {len(n)} 条（{time.time() - start:.1f}s）")
    except Exception as e:  # noqa: BLE001
        out.statuses.append(SourceStatus("exa", "error", 0, str(e)[:300], time.time() - start))
        log(f"    ✗ error: {e}")


def collect_cborg(s: Settings, query: str, out: Collected, log=print) -> None:
    """中国国际招标网 chinabidding.org.cn：站内检索后台（114.112.188.22）不可达，改用 Exa 限定站点检索。"""
    log("  - 中国国际招标网（Exa site: 检索）…")
    start = time.time()
    try:
        rows = _exa_rows(ExaMcp(s.exa_mcp_url), [f"site:chinabidding.org.cn {query}", f"site:gov-cg.cn {query}"], s.exa_num_results)
        rows = [r for r in rows if re.search(r"chinabidding\.org\.cn|gov-cg\.cn", r.get("url", ""))]
        out.raw["cborg"] = rows
        n = [x for x in (_exa_to_notice("cborg", query, r) for r in rows) if x]
        out.notices.extend(n)
        out.statuses.append(SourceStatus("cborg", "ok" if n else "empty", len(n), "站内检索后台不可用，经 Exa 检索", time.time() - start))
        log(f"    ✓ {len(n)} 条（{time.time() - start:.1f}s）")
    except Exception as e:  # noqa: BLE001
        out.statuses.append(SourceStatus("cborg", "error", 0, str(e)[:300], time.time() - start))
        log(f"    ✗ error: {e}")


# ---------------------------------------------------------------- 企业信息

_PROFILE_PATTERNS = {
    "credit_code": r"统一社会信用代码[\s:：/|]*([0-9A-Z]{18})",
    "legal_person": r"法定代表人[\s:：/|]*([一-龥·]{2,10})",
    "established": r"成立(?:日期|时间)[\s:：/|]*(\d{4}[-年./]\d{1,2}[-月./]\d{1,2}日?)",
    "reg_capital": r"注册资本[\s:：/|]*([0-9.,]+\s*万?(?:元|人民币|美元)?(?:人民币)?)",
    "status": r"(?:登记状态|经营状态)[\s:：/|]*(存续|在业|开业|注销|吊销|迁出|停业)[^\s，,]{0,6}",
    "company_type": r"(?:企业类型|公司类型)[\s:：/|]*([一-龥（）()]{4,30})",
    "address": r"(?:注册地址|企业地址|通信地址|地址)\s*[:：]\s*([一-龥A-Za-z0-9（）()#\-号楼层室院区路街道镇乡村]{6,60})",
    "phone": r"(?:电话|联系电话)\s*[:：]\s*([0-9\-—()（） ]{7,20})",
    "email": r"(?:邮箱|电子邮箱)\s*[:：]\s*([\w.\-]+@[\w.\-]+)",
    "industry": r"(?:所属行业|国标行业)\s*[:：]\s*([一-龥、，,]{2,40})",
    "business_scope": r"经营范围\s*[:：]\s*([^\n]{10,400})",
    "shareholders": r"(?:股东(?:信息)?|投资人)\s*[:：]\s*([一-龥（）()、，,]{4,120})",
}


_QCC_LABELS = {
    "法定代表人": "legal_person", "成立时间": "established", "成立日期": "established", "登记状态": "status",
    "注册资本": "reg_capital", "实缴资本": "paid_capital", "企业类型": "company_type", "人员规模": "staff_size",
    "统一社会信用代码": "credit_code", "所属行业": "industry", "经营范围": "business_scope", "曾用名": "former_names",
    "注册地址": "address", "企业地址": "address",
}
_QCC_COUNTS = ("招投标", "开庭公告", "专利", "商标", "招聘信息", "企业年报", "新闻舆情")


def parse_qcc(text: str, company: str) -> dict:
    """解析企查查企业页（m.qcc.com/firm/*.html，经 Exa web_fetch 取到的文本）。

    页面结构为“标签行 + 值行”；头部区域含电话、股东列表、主要人员，“## 工商信息”段为标准工商字段。
    """
    if company not in text:
        return {}
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    prof: dict = {}
    head, _, body = text.partition("## 工商信息")
    sec = [ln.strip() for ln in body.splitlines() if ln.strip()] if body else lines
    for i, ln in enumerate(sec[:-1]):
        key = _QCC_LABELS.get(ln)
        if key and key not in prof:
            val = sec[i + 1]
            if val in _QCC_LABELS or val == "*":
                continue
            prof[key] = re.sub(r"他关联\s*\d+\s*家企业$", "", val).strip()
        elif ln == "参保人数":
            num = next((x for x in sec[i + 1:i + 4] if re.fullmatch(r"\d+", x)), "")
            src = re.search(r"来源于[:：](\S+?)，", sec[i + 1])
            if num:
                prof["insured"] = num + (f"（{src.group(1)}）" if src else "")
    if prof.get("legal_person") and not re.fullmatch(r"[一-龥·]{2,10}", prof["legal_person"]):
        prof.pop("legal_person")
    phones = re.findall(r"(?<!\d)(0\d{2,3}-\d{7,8}|1[3-9]\d{9})(?!\d)", head)
    if phones:
        prof["phone"] = "，".join(dict.fromkeys(phones))
    emails = re.findall(r"[\w.\-]+@[\w\-]+\.[\w.\-]+", head)
    if emails:
        prof["email"] = "，".join(dict.fromkeys(emails))
    holders = re.findall(r"(?:^|\n)(?:[一-龥] )?([一-龥A-Za-z（）()·]{2,40}) (?:大股东 )?持股比例 ([\d.]+%)", head)
    if holders:
        prof["shareholders"] = "；".join(f"{n} {p}" for n, p in holders[:10])
    people_block = re.search(r"主要人员\d*\n(.*?)(?:查看更多|\n产品|\n查查图谱)", head, re.S)
    if people_block:
        people = re.findall(r"(?:^|\n)(?:[一-龥] )?([一-龥·]{2,6}) ([^\n]+?) 关联企业", people_block.group(1))
        if people:
            prof["key_people"] = "；".join(f"{n}（{t}）" for n, t in people[:10])
    intro = re.search(r"简介[:：]\s*\n?(.+)", head)
    if intro:
        prof["intro"] = re.sub(r"收起$", "", intro.group(1).strip())[:500]
    tags = re.search(r"更新时间[:：][^\n]*\n+([^\n]+)", head)
    if tags:
        prof["tags"] = tags.group(1)[:120]
    counts = {k: m.group(1) for k in _QCC_COUNTS if (m := re.search(rf"(?:^|\n){k}\s*(\d+)\n", text))}
    if counts:
        prof["qcc_counts"] = "，".join(f"{k} {v}" for k, v in counts.items())
    return prof


def _fetch_qcc(client: ExaMcp, company: str, pages: list[dict]) -> tuple[dict, str]:
    """从 Exa 结果中找企查查企业页（没有则单独检索一次），抓全文并解析。"""
    url = next((p["url"] for p in pages if re.search(r"qcc\.com/firm/", p.get("url", "")) and company in p.get("title", "")), "")
    if not url:
        for r in client.search(f"{company} 企查查", 8):
            if re.search(r"qcc\.com/firm/", r.get("url", "")) and company in r.get("title", ""):
                url = r["url"]
                break
    if not url:
        return {}, ""
    return parse_qcc(client.fetch(url, 30000), company), url


def collect_profile(s: Settings, company: str, out: Collected, log=print) -> None:
    """企业基本信息：必联网企业库 + Exa（企查查/爱企查/天眼查/官网等公开页面摘要）抽取工商字段。"""
    log("  - 企业信息（必联网企业库 + Exa 工商信息检索）…")
    start = time.time()
    profile: dict = {"name": company, "sources": []}
    rows, _, err = _timed(lambda: opencli.run(["ebnew", "company", company], timeout=120, package_dir=s.opencli_package_dir))
    if not err and rows:
        hit = next((r for r in rows if r.get("name") == company), rows[0])
        profile.update({k: v for k, v in hit.items() if v and k not in ("name", "url")})
        profile["sources"].append({"source": "必联网企业库", "url": hit.get("url", "")})
    try:
        client = ExaMcp(s.exa_mcp_url)
        pages = _exa_rows(client, [f"{company} 统一社会信用代码 法定代表人 注册资本 成立日期", f"{company} 公司简介 主营业务"], 8)
        out.raw["profile_exa"] = pages
        for p in pages:
            text = f"{p.get('title', '')}\n{p.get('text', '')}"
            if company not in text:
                continue
            got = False
            for key, pat in _PROFILE_PATTERNS.items():
                if profile.get(key):
                    continue
                m = re.search(pat, text)
                if m:
                    profile[key] = re.sub(r"\s+", " ", m.group(1)).strip(" ，,")
                    got = True
            if got or re.search(r"qcc|tianyancha|aiqicha|qixin|11467|cbi360", p.get("url", "")):
                profile["sources"].append({"source": "Exa", "title": p.get("title", "")[:60], "url": p.get("url", "")})
        intro = next((p for p in pages if company in p.get("title", "") and re.search(r"简介|介绍|关于我们|公司概况", p.get("text", ""))
                      and p.get("text", "").count("/") < 15 and p.get("text", "").count("|") < 15), None)
        if intro:
            profile["intro"] = re.sub(r"\s+", " ", intro.get("text", ""))[:500]
        # 企查查企业页字段最全、最新（工商登记口径），覆盖前面从摘要中抽取的值
        qcc, qcc_url = _fetch_qcc(client, company, pages)
        if qcc:
            profile.update(qcc)
            profile["sources"].insert(0, {"source": "企查查", "url": qcc_url})
    except Exception as e:  # noqa: BLE001
        profile["error"] = str(e)[:200]
    out.profile = profile
    filled = [k for k in profile if k not in ("name", "sources", "error")]
    out.statuses.append(SourceStatus("profile", "ok" if filled else "empty", len(filled), "", time.time() - start))
    log(f"    ✓ 字段 {len(filled)} 个（{', '.join(filled[:8])}{'…' if len(filled) > 8 else ''}）")


def fetch_yfbzb_details(s: Settings, notices: list[dict], n: int, log=print) -> list[dict]:
    """对前 n 条乙方宝公告读取会员详情（每条消耗 1 次额度；额度不足自动回退公开页）。"""
    results = []
    for nt in [x for x in notices if x["source"] == "yfbzb" and x.get("content_id")][:n]:
        log(f"  - 详情 {nt['content_id']} {nt['title'][:30]} …")
        args = ["yfbzb", "detail", nt["content_id"], "--area", nt.get("area_id") or "2", "--type", nt.get("yfbzb_type", "zhaobiao")]
        if nt.get("public_url"):
            args += ["--public_url", nt["public_url"]]
        try:
            rows = opencli.run(args, timeout=s.command_timeout, package_dir=s.opencli_package_dir) or []
            if rows:
                row = rows[0]
                row["notice_title"] = nt["title"]
                results.append(row)
                log(f"    → {row.get('status')} {row.get('note', '')}")
        except opencli.OpenCliError as e:
            log(f"    ✗ {e}")
            results.append({"status": "error", "content_id": nt["content_id"], "note": str(e)})
        time.sleep(s.pause)
    return results
