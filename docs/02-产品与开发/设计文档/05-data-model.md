# 05 数据模型（PostgreSQL 18 + pgvector）

> 命名规则：snake_case；主键统一用 `uuid`（v7）；所有业务表都有 `created_at`、`updated_at`。
> MVP 阶段用单租户；为二期多租户预留 `org_id`。

## 1. ER 概览

```
users ─┬─ threads ─ runs ─ tool_calls ─ cost_ledger
       └─ leads ──┬─ companies ─┬─ company_snapshots (按 api_code 缓存原始返回)
                  │             ├─ relations (边表: from_company → to_company)
                  └─ tenders ───┼─ tender_items
                                ├─ tender_parties (buyer/agency/winner → companies)
                                ├─ tender_sources (同一公告的多来源)
                                └─ contacts (个人信息，单独存储/可删除)
raw_snapshots (原文快照索引)   source_health (源/会话状态)   subscriptions (二期)
```

## 2. 核心表

### companies
| 字段 | 类型 | 说明 |
|---|---|---|
| id | uuid PK | |
| credit_code | varchar(18) UNIQUE NULL | 统一社会信用代码；未解析出时为空 |
| name | text | 规范名称 |
| aliases | text[] | 曾用名、简称 |
| status, reg_capital, est_date, industry, region_code, scale, legal_person | … | 工商基本信息 |
| profile | jsonb | CompanyProfile 的聚合字段，包括 signals 和 procurement |
| profile_updated_at | timestamptz | |
| name_embedding | vector(1024) | 用于模糊匹配 |

索引：`gin(name gin_trgm_ops)`、`credit_code`。

### tenders
| 字段 | 类型 | 说明 |
|---|---|---|
| id | uuid PK | |
| dedup_key | text UNIQUE | 去重键 |
| title | text | |
| notice_type | enum(intent, plan, bid, change, award, contract, inquiry, other) | |
| stage | text | |
| region_code | varchar(12) | |
| publish_date, deadline | date / timestamptz | |
| project_code | text | |
| budget, amount | numeric(18,2) | |
| currency | char(3) | |
| summary | text | |
| content_text | text | 正文，用于全文检索 |
| content_tsv | tsvector | 中文分词，使用 zhparser 或 pg_jieba |
| embedding | vector(1024) | |
| extract_meta | jsonb | 抽取模型、版本、置信度、`unverified_fields[]` |

### tender_items
`tender_id, seq, name, category, spec, qty, unit, brand, model, budget`

### tender_parties
`tender_id, company_id NULL, role(buyer|agency|winner|candidate), name_raw, amount, rank`

### tender_sources
`tender_id, source, source_url, origin_url, fetched_at, snapshot_id`

### relations（上下游边表）
| 字段 | 说明 |
|---|---|
| from_company_id, to_company_id | |
| type | equity / invest / group / tender_award（buyer→winner）/ supply / customer / agency |
| weight_amount, weight_count | 关系强度：金额 / 次数 |
| first_seen, last_seen | |
| evidence | jsonb[]，记录 tender_id、api 快照、URL |
| source | |

唯一键：`(from, to, type)`。
`tender_award` 边由 `tender_parties` 自动派生：每次中标都累加 count 和 amount，并更新 last_seen。

### contacts（个人信息，隔离存储）
| 字段 | 说明 |
|---|---|
| id, company_id, tender_id NULL | |
| name, role | |
| phone_masked | 默认只展示这一列 |
| phone_enc | 加密存储（AES-GCM，密钥来自环境变量） |
| email_enc | 同上 |
| source, source_url, obtained_at, legal_basis | 来源与依据，如"公开招标公告"或"会员权益查看" |
| deleted_at | 支持删除请求 |

### company_snapshots（付费 API 缓存）
`company_id, provider(qcc|qixin|tyc), api_code, args_hash, payload jsonb, cost, fetched_at, expires_at`

### leads
`id, owner_id, company_id, tender_id NULL, score, score_detail jsonb, status(new|following|won|lost|ignored), tags text[], note, created_from_thread_id`

### 运行与审计
- `threads`：`id, user_id, title, created_at`。LangGraph checkpoint 使用官方表，由 `langgraph-checkpoint-postgres` 自动创建。
- `runs`：`id, thread_id, status, started_at, ended_at, total_cost, model_usage jsonb`
- `tool_calls`：`id, run_id, tool, args jsonb, result_summary jsonb, source, latency_ms, cache_hit, cost, status, error`
- `cost_ledger`：`id, run_id, provider, unit(yuan|quota), amount, api_code, confirmed_by, ts`
- `source_health`：`source, status(ok|degraded|login_required|need_user_action), channel_stats jsonb, last_error, last_ok_at`
- `raw_snapshots`：`id, source, url, path(data/raw/...), sha256, http_status, fetched_at, account`

## 3. 关系查询（MVP 用递归 CTE）

查询某企业 2 跳内的上下游：

```sql
WITH RECURSIVE g AS (
  SELECT from_company_id, to_company_id, type, 1 AS depth FROM relations
  WHERE from_company_id = :cid OR to_company_id = :cid
  UNION
  SELECT r.from_company_id, r.to_company_id, r.type, g.depth+1 FROM relations r
  JOIN g ON r.from_company_id IN (g.from_company_id, g.to_company_id)
         OR r.to_company_id   IN (g.from_company_id, g.to_company_id)
  WHERE g.depth < 2
) SELECT DISTINCT * FROM g LIMIT 500;
```

二期迁移 Neo4j 时，节点为 `(:Company {credit_code})`、`(:Product)`、`(:Industry)`，关系类型与 `relations.type` 对齐，本体参考 ChainKnowledgeGraph。

## 4. 种子数据（data/seeds）

| 文件 | 内容 |
|---|---|
| `regions.csv` | 行政区划编码，用于地区归一 |
| `notice_type_map.yaml` | 各源公告类型 → 统一枚举 |
| `product_lexicon.yaml` | 我方产品词表与同义词，用于需求匹配评分 |
| `industry_chain/` | 产业链本体，从 ChainKnowledgeGraph 导入，用于上下游推断 |
| `source_samples/` | 实测样例，用于解析器单测，例如 `data/raw/samples/yfbzb_*` |
