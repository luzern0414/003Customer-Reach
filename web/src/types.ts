// 与 backend/app/services.py、main.py 的响应结构一一对应。

export type JobStatus = 'queued' | 'running' | 'awaiting_user' | 'paused' | 'completed' | 'partial' | 'failed'
export type LeadStatus = 'new' | 'verifying' | 'contacted' | 'following' | 'won' | 'invalid'

export interface Handover {
  kind?: 'login' | 'verify' | 'identity'
  message?: string
  site?: string
  site_name?: string
  url?: string
  candidates?: string[]
}

export interface JobMetrics {
  elapsed_ms?: number
  first_result_ms?: number
  model_calls?: number
  tokens?: number
}

export interface Job {
  id: string
  mode: '' | 'find_buyers' | 'company' | 'chat'
  status: JobStatus
  stage: string
  metrics: JobMetrics
  handover: Handover
  error: string
  reply_message_id: string | null
  created_at: string
  finished_at: string | null
}

export interface Attachment {
  id: string
  filename: string
  size: number
  chars: number
  meta: { warnings?: string[]; limited?: boolean; [key: string]: unknown }
  text?: string
}

export interface Message {
  id: string
  role: 'user' | 'assistant'
  content: string
  job_id: string | null
  created_at: string
  attachments: Attachment[]
}

export interface ConversationItem { id: string; title: string; updated_at: string; status: JobStatus | '' }
export interface Conversation extends ConversationItem { messages: Message[]; jobs: Job[] }

export interface ToolCall {
  id: string
  tool: string
  label: string
  site: string
  url: string
  status: string
  count?: number
  summary?: string
  error?: string
  elapsed_ms?: number
}

export interface CompanyCard {
  id: string
  name: string
  industry: string
  region: string
  business_status: string
  registered_capital: string
  legal_person: string
  phone: string
  scope: string
  contact: { person: string; phone: string } | null
  researched_at: string | null
  updated_at: string
  purchases: number
  wins: number
  latest_notice: { title: string; kind: string; date: string } | null
  lead: { id: string; status: LeadStatus; score: number } | null
  role?: 'target' | 'buyer' | 'related'
}

export interface Party { company_id: string; name: string; role: string; amount: number | null; quote: string }
export interface Contact { person: string; phone: string; address: string; quote: string }

export interface Notice {
  id: string
  title: string
  kind: string
  kind_label: string
  project_code: string
  region: string
  published_on: string
  deadline: string
  budget: number | null
  amount: number | null
  items: string
  url: string
  source_id: string
  contact: Contact | null
  quotes: Record<string, string>
  parties: Party[]
  role?: string
}

export interface Relation { company_id: string; name: string; count: number; amount: number; last_date: string }
export interface Evidence { quote: string; source_id: string; url: string; title: string }
export interface SourceItem { id: string; url: string; title: string; site: string; kind: string; fetched_at: string }

export interface CompanyDetail {
  id: string
  name: string
  short_name: string
  industry: string
  region: string
  address: string
  researched_at: string | null
  updated_at: string
  profile: { field: string; label: string; value: string; evidence: Evidence | null }[]
  stats: { purchases: number; wins: number; customers: number; suppliers: number; competitors: number; budget_total: number }
  purchases: Notice[]
  wins: Notice[]
  relations: { customers: Relation[]; suppliers: Relation[]; competitors: Relation[] }
  purchase_items: string[]
  sources: SourceItem[]
  lead: { id: string; status: LeadStatus; archived: boolean } | null
}

export interface LeadItem {
  id: string
  status: LeadStatus
  status_label: string
  owner: string
  next_followup_at: string
  tags: string[]
  score: number
  match_reason: string
  created_at: string
  updated_at: string
  company: { id: string; name: string; region: string }
  notice: { id: string; title: string; kind_label: string; published_on: string; deadline: string; budget: number | null; amount: number | null } | null
}

export interface LeadList {
  total: number
  counts: Record<LeadStatus | 'all', number>
  owners: string[]
  items: LeadItem[]
}

export interface MatchAnalysis {
  items: { product: string; fit: '相关' | '能力缺口' | '待核验'; evidence: string; judgement: string }[]
  questions: string[]
  analyzed_at: string
}

export interface LeadDetail extends Omit<LeadItem, 'company'> {
  company: CompanyCard & { address: string; phone: string }
  analysis: MatchAnalysis | Record<string, never>
  notices: Notice[]
  contacts: (Contact & { notice_id: string; notice_title: string; url: string })[]
  followups: { id: string; kind: string; content: string; created_at: string }[]
  feedback: { id: string; kind: string; content: string; created_at: string }[]
}

export interface SourceDetail { id: string; url: string; title: string; site: string; kind: string; status: string; text: string; fetched_at: string }

export interface SiteInfo {
  id: string
  name: string
  kind: 'procurement' | 'business'
  login: boolean
  note: string
  enabled: boolean
  custom: boolean
  mode: 'template' | 'site_search'
  template: string
  domain: string
  detail: string
  by_company: boolean
  stats: { attempts: number; successes: number; adopted: number; last_status: string; last_at: string } | null
  origin: 'builtin' | 'luzcrawl' | 'custom'
  region: string
}

export interface DataSources {
  crawler: { ready: boolean; state: string; hint: string; version: string | null; profiles: string[]; profile: string }
  sites: SiteInfo[]
}

export interface Settings {
  company_name: string
  company_profile: string
  target_regions: string[]
  exclusions: string[]
  default_days: number
  max_queries: number
  max_reads: number
  max_enrich: number
  target_leads: number
  max_rounds: number
  max_model_calls: number
  max_minutes: number
  cache_hours: number
  crawl_profile: string
  sources: Record<string, boolean>
}

export interface KnowledgeItem { id: string; kind: 'preference' | 'exclusion' | 'product'; title: string; body: string; hits: number; updated_at: string }
