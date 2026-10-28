import { reactive } from 'vue'
import { api, post } from './api'

export interface Account {
  id: string
  username: string
  is_admin: boolean
  unlimited: boolean
  quota: number | null
  used: number
  remaining: number | null
}

/** 当前登录账号；loaded 表示已向后端确认过登录状态。 */
export const session = reactive<{ me: Account | null; loaded: boolean }>({ me: null, loaded: false })

export async function loadMe(): Promise<Account | null> {
  try {
    session.me = await api<Account | null>('/auth/me', { notify: false })
  } catch {
    session.me = null
  }
  session.loaded = true
  return session.me
}

export function signIn(account: Account) {
  session.me = account
  session.loaded = true
}

export async function signOut() {
  await post('/auth/logout').catch(() => null)
  session.me = null
}

export const exhausted = () => !!session.me && !session.me.unlimited && !session.me.remaining
