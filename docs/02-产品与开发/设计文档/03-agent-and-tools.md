# 03 Agent 与工具设计

## 1. LangGraph 图结构

```
                    ┌──────────────┐
  user msg ───────▶ │  supervisor  │  意图识别 + 生成计划（结构化 Plan）
                    └──────┬───────┘
         ┌─────────────┬───┴────────┬──────────────┬──────────────┐
         ▼             ▼            ▼              ▼              ▼
 tender_research  company_profile  relation_map  supplier_find   chitchat/clarify
   (子图)           (子图)          (子图)         (子图)           │
         └─────────────┴──────┬─────┴──────────────┘              │
                              ▼                                    │
                        ┌──────────┐   数字/实体对原文校验           │
                        │ verifier │──────────────┐                │
                        └────┬─────┘              │失败→回退重抽   │
                             ▼                                    │
                        ┌──────────┐                               │
                        │ reporter │  汇总 + 评分 + 建议 + UI 载荷 ◀─┘
                        └──────────┘
```

- **supervisor**：输出 `Plan{steps:[{agent, goal, args}], need_confirm_cost}`。
  - 能并行的步骤用 LangGraph `Send` 扇出。例如对 Top N 采购单位，并行生成画像。
  - 信息不足时（比如没给地区或时间）先补默认值，并在回答中说明用了哪些默认值。只有关键歧义才追问。
- **子图**：每个子图都是"工具调用 → 归一化 → 写 state"的 ReAct 小循环，最多 6 步，防止死循环。
- **verifier**：金额、日期、企业名必须能在 `evidence` 原文中找到。找不到的标记为 `unverified`，不允许当作事实输出。
- **reporter**：生成最终 Markdown 回答，同时生成 `ui_blocks`（卡片、表格、图），通过 custom stream 推给前端。

### 1.1 State（核心字段）

```python
class AcqState(TypedDict):
    messages: Annotated[list, add_messages]
    plan: Plan | None
    query: QuerySpec            # 关键词/地区/时间/金额/公告类型/目标企业
    tenders: list[TenderNotice]  # 归一化后的公告
    companies: dict[str, CompanyProfile]  # key = 统一社会信用代码 or 名称
    relations: list[RelationEdge]
    suppliers_1688: list[Offer1688]
    leads: list[LeadScore]
    cost_ledger: list[CostItem]  # 本 run 的额度/费用消耗
    ui_blocks: list[UIBlock]
    errors: list[SourceError]    # 不可用源，前端显示"部分源不可用"
```

### 1.2 HITL（人工确认）节点

| 触发条件 | 交互 |
|---|---|
| 预估付费成本超过阈值（默认 ¥2），或要消耗会员详情额度 | `interrupt({"type":"cost_confirm", items, est_cost})`，前端弹出确认卡：确认 / 只用免费源 / 取消 |
| 企业名歧义（同名或模糊匹配有多个结果） | `interrupt({"type":"entity_pick", candidates})` |
| 读取时需要用户操作（登录过期、页面要求人工确认） | `interrupt({"type":"browser_action", site, url, hint})`，提示用户在 Agent 专用 Edge 中完成后点"继续" |
| 内容不完整（字段被占位或打码） | Fetch Router 自动升级通道：Exa → OpenCLI 已登录会话；如需消耗会员额度，走 `cost_confirm` |

## 2. 工具清单（Agent 可见）

工具统一由 Tool Gateway 注册。命名规则是 `<domain>_<verb>`。每个工具都返回下面的结构，`data` 的形状按 `type` 区分：

```json
{"type":"tender_list","data":[...],"sources":[{"source":"ccgp","url":"...","fetched_at":"..."}],
 "cost":{"amount":0,"quota":{"yfbzb_detail":0}},"partial":false,"errors":[]}
```

| 工具 | 入参（要点） | 后端实现 / 数据源顺序 | 成本 |
|---|---|---|---|
| `tender_search` | kw[], region, date_from/to, notice_types[]（意向/招标/中标/合同）, budget_min/max, buyer, limit | ① 本地招采库（PG 全文 + 向量）② 企查查 958 招投标（结构化）③ 乙方宝控制台列表（OpenCLI）④ ccgp 实时搜索 ⑤ Exa/博查网搜补全 | ①④⑤ 免费；②1 元/次；③ 不耗额度 |
| `tender_detail` | notice_id 或 url | 本地快照 → 原始平台公开页 → 乙方宝详情（**消耗会员额度，需确认**） | 0 或 1 次额度 |
| `tender_history` | company（作为 buyer 或 winner）, years | 本地库 + 企查查 958（按企业名）+ 乙方宝按采购企业搜索 | 1 元/次 |
| `company_resolve` | name 或关键词 | 企查查 886 模糊搜索 → 返回候选（信用代码、法人、地区、状态） | 0.1 元 |
| `company_profile` | credit_code, sections[]（basic/shareholders/invest/risk/signals/ip） | 企查查 410/735/731/884/739/740/741/718/514/701/950，按 section 按需调用，缓存 7–30 天 | 约 2–8 元，需确认 |
| `company_relations` | credit_code, depth（1–2）, kinds[]（equity/group/tender/supply） | 股权、对外投资、集团（企查查）+ 招中标边（本地库）+ 724/723 供应商客户（仅上市或发债主体） | 按调用计 |
| `supplier_search_1688` | kw, region, min_years, limit | 1688 开放平台 `alibaba.product.search` → 兜底 OpenCLI `1688 search` | 免费或低 |
| `supplier_store_1688` | store_url 或 member_id | OpenCLI `1688 store` → 公开信息（主营、年限、联系方式）→ `company_resolve` 关联工商主体 | 免费 |
| `web_search` | query, site?, freshness | Exa `web_search_exa` + 博查 `/v1/web-search`，合并去重 | 低 |
| `web_read` | url, need_fields[] | Fetch Router：本地快照 → Exa `web_fetch_exa` → HTTP → OpenCLI 已登录真实浏览器（extract / network XHR），并做完整性校验 | 低 |
| `browser_read` | url, wait_for?, actions[]?（搜索、翻页、展开） | OpenCLI 直接驱动 Agent 专用 Edge，返回 Markdown 或结构化 JSON | 0 |
| `lead_save` | company/notice, tags, note | 写入线索库 | 0 |
| `lead_score` | company + 上下文 | 规则分 + LLM 解释（见 §4） | LLM |

> 原则：工具描述（docstring）要写清**适用场景、返回字段、成本**。LLM 据此自行权衡调用顺序。

## 3. 归一化模型（工具输出 → 领域对象）

### TenderNotice
`id, source, source_url, origin_url, title, notice_type, stage, region_code, publish_date, deadline, buyer{name, credit_code}, agency, winners[{name, amount}], budget, amount, currency, items[{name, category, spec, qty, unit, brand}], contacts[{name, phone_masked, phone_full?, role}], raw_ref, evidence{field: snippet}, dedup_key`

去重键：`hash(normalize(buyer) + normalize(title) + project_code? + publish_date±3天)`。同一公告可能出现在多个源，合并为一条，`sources[]` 保留所有来源。

### CompanyProfile
`credit_code, name, aliases, status, reg_capital, est_date, industry, region, scale, legal_person, shareholders[], investments[], group, risks{abnormal, dishonest, penalties}, signals{hiring[], financing[], news[], patents_cnt, qualifications[]}, procurement{top_categories[], freq_per_month, budget_total_12m, preferred_brands[], top_suppliers[]}, sources[]`

### RelationEdge
`from, to, type(equity|invest|group|tender_award|supply|customer|agency), weight(金额/次数), first_seen, last_seen, evidence[]`

## 4. 线索评分（MVP 规则版）

| 维度 | 信号 | 权重 |
|---|---|---|
| 需求匹配 | 采购品目与"我方产品词表"相似度（向量 + 关键词） | 30 |
| 时效 | 处于意向或招标阶段且未截止 30；已中标 10；超过 90 天 5 | 20 |
| 金额 | 预算或年度采购额分档 | 15 |
| 频次 | 近 12 个月同类采购次数 | 15 |
| 可触达 | 有公开联系人或采购代理 | 10 |
| 风险扣分 | 经营异常、失信、被执行 | -20 |
| 竞争 | 历史中标方集中度高（被锁定供应商） | -10 |

LLM 负责输出评分理由（引用证据），**分数由规则计算**，可复现。

## 5. Prompt 要点

- **System**：角色是 B2B 获客分析师。必须基于工具结果作答，所有数字都要附来源。无法验证的信息要明确说明。不输出个人敏感信息，除非用户明确请求，且该信息来自合规来源。
- **Supervisor**：Few-shot 示范 5 类意图：找采购方、查某企业、查上下游、找供应商、汇总线索。
- **抽取 prompt**：给出 JSON Schema，要求每个字段返回 `evidence` 原文片段；缺失的字段填 null，禁止猜测。

## 6. 模型路由（config/models.yaml）

| 任务 | 模型档位 | 说明 |
|---|---|---|
| supervisor / reporter | strong | 例如 DeepSeek-V3.x、Qwen-Max、Kimi K2、GLM-4.x、Claude（可选） |
| 抽取 / 归一化 | cheap | Qwen-Plus/Turbo、DeepSeek 非思考模式 |
| embedding | bge-m3 或厂商 embedding | 用于公告与品目向量 |

注意事项：
- **不依赖 parallel_tool_calls**：由图层面用 `Send` 实现并行。
- 每个模型都要跑工具调用回归测试（`tests/agent_eval/`）。
