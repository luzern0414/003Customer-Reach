import { ElMessage } from 'element-plus'

export class ApiError extends Error {
  constructor(message: string, readonly status: number) {
    super(message)
  }
}

/** 调用后端 /api 接口；非 2xx 抛 ApiError，默认弹出错误提示（notify:false 时由调用方处理）。 */
export async function api<T = any>(path: string, init: { method?: string; body?: unknown; notify?: boolean; signal?: AbortSignal } = {}): Promise<T> {
  const { method = 'GET', body, notify = true, signal } = init
  const form = body instanceof FormData
  try {
    const response = await fetch('/api' + path, {
      method, signal,
      headers: form || body === undefined ? undefined : { 'Content-Type': 'application/json' },
      body: body === undefined ? undefined : form ? body : JSON.stringify(body),
    })
    const data = response.status === 204 ? null : await response.json().catch(() => null)
    if (!response.ok) {
      const detail = data?.detail
      throw new ApiError(typeof detail === 'string' ? detail : '请求失败，请稍后重试', response.status)
    }
    return data as T
  } catch (error) {
    if (notify && !(error instanceof DOMException && error.name === 'AbortError')) {
      ElMessage.error(error instanceof ApiError ? error.message : '无法连接服务，请确认后端已启动')
    }
    throw error
  }
}

export const get = <T = any>(path: string, signal?: AbortSignal) => api<T>(path, { signal })
export const post = <T = any>(path: string, body: unknown = {}) => api<T>(path, { method: 'POST', body })
export const patch = <T = any>(path: string, body: unknown) => api<T>(path, { method: 'PATCH', body })
export const del = <T = any>(path: string) => api<T>(path, { method: 'DELETE' })

export function query(params: Record<string, string | number | undefined | null>): string {
  const search = new URLSearchParams()
  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined && value !== null && value !== '') search.set(key, String(value))
  }
  const text = search.toString()
  return text ? '?' + text : ''
}
