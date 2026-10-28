import { reactive } from 'vue'
import type { Handover, JobMetrics, JobStatus, ToolCall } from './types'

const TERMINAL: JobStatus[] = ['completed', 'partial', 'failed', 'paused', 'awaiting_user']

export interface JobState {
  id: string
  status: JobStatus
  stage: string
  stageLabel: string
  tools: ToolCall[]
  draft: string
  replyId: string
  final: boolean
  handover: Handover
  error: string
  metrics: JobMetrics
  progress: { candidates?: number; to_read?: number }
  resultVersion: number
  title: string
  syncedAt: number
}

export function emptyJob(id: string, status: JobStatus = 'queued'): JobState {
  return reactive({ id, status, stage: '', stageLabel: '', tools: [], draft: '', replyId: '', final: false,
    handover: {}, error: '', metrics: {}, progress: {}, resultVersion: 0, title: '', syncedAt: Date.now() }) as JobState
}

export function isTerminal(status: JobStatus): boolean {
  return TERMINAL.includes(status)
}

/** 订阅任务事件。事件按 id 递增，断线后从最后一个 id 续读；任务进入终态后服务端结束流，onEnd 被调用。 */
export function followJob(state: JobState, onEnd: () => void): () => void {
  let cursor = 0
  let source: EventSource | null = null
  let closed = false
  let retry: number | undefined

  const handlers: Record<string, (data: any) => void> = {
    status: (data) => {
      Object.assign(state, { status: data.status, stage: data.stage, metrics: data.metrics || {}, handover: data.handover || {}, error: data.error || '', syncedAt: Date.now() })
    },
    stage: (data) => { state.stage = data.stage; state.stageLabel = data.label },
    title: (data) => { state.title = data.title },
    progress: (data) => { state.progress = data },
    result: () => { state.resultVersion++ },
    'tool.started': (data) => { upsertTool(state, { ...data, status: 'running' }) },
    'tool.finished': (data) => { upsertTool(state, data) },
    'message.delta': (data) => {
      if (state.replyId !== data.message_id) { state.replyId = data.message_id; state.draft = '' }
      state.draft += data.text
    },
    'message.completed': (data) => { state.replyId = data.message_id; state.draft = data.content; state.final = true },
  }

  const open = () => {
    if (closed) return
    source = new EventSource(`/api/jobs/${state.id}/events?after=${cursor}`)
    for (const [type, handle] of Object.entries(handlers)) {
      source.addEventListener(type, (event) => {
        const message = event as MessageEvent
        cursor = Math.max(cursor, Number(message.lastEventId) || cursor)
        handle(JSON.parse(message.data))
      })
    }
    source.onerror = () => {
      source?.close()
      if (closed) return
      if (isTerminal(state.status)) { closed = true; onEnd(); return }
      retry = window.setTimeout(open, 1500)
    }
  }
  open()
  return () => { closed = true; source?.close(); window.clearTimeout(retry) }
}

function upsertTool(state: JobState, call: ToolCall) {
  const index = state.tools.findIndex((item) => item.id === call.id)
  if (index < 0) state.tools.push(call)
  else state.tools[index] = { ...state.tools[index], ...call }
}
