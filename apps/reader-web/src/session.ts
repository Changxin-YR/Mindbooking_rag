export const sessionStorageKey = 'reader-web-session'

export interface StorageLike {
  getItem(key: string): string | null
  setItem(key: string, value: string): void
  removeItem(key: string): void
}

export interface ReaderSession {
  token: string
  accountId: string
}

function browserStorage(): StorageLike | undefined {
  try {
    return globalThis.localStorage
  } catch {
    return undefined
  }
}

export function loadSession(storage = browserStorage()): ReaderSession | null {
  if (!storage) return null
  try {
    const value: unknown = JSON.parse(storage.getItem(sessionStorageKey) || 'null')
    if (!value || typeof value !== 'object') return null
    const { token, accountId } = value as Record<string, unknown>
    if (typeof token !== 'string' || typeof accountId !== 'string') return null
    const session = { token: token.trim(), accountId: accountId.trim() }
    return session.token && session.accountId ? session : null
  } catch {
    return null
  }
}

export function saveSession(session: ReaderSession, storage = browserStorage()): ReaderSession {
  const normalized = { token: session.token.trim(), accountId: session.accountId.trim() }
  if (!normalized.token || !normalized.accountId) throw new Error('session token and account id are required')
  storage?.setItem(sessionStorageKey, JSON.stringify(normalized))
  return normalized
}

export function clearSession(storage = browserStorage()): void {
  storage?.removeItem(sessionStorageKey)
}

export function buildRequestHeaders(token: string, init?: HeadersInit): Headers {
  const headers = new Headers(init)
  headers.set('Accept', 'application/json')
  if (token.trim()) headers.set('Authorization', `Bearer ${token.trim()}`)
  return headers
}

