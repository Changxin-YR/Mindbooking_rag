export const shellStates = ['loading', 'empty', 'error', 'unauthorized', 'ready'] as const
export type ShellState = (typeof shellStates)[number]

type StorageReader = Pick<Storage, 'getItem'>

export function readAdminAccessToken(storage: StorageReader | null | undefined): string {
  try {
    return storage?.getItem('admin_access_token')?.trim() || ''
  } catch {
    return ''
  }
}

export function buildAdminHeaders(token: string, init?: HeadersInit): Headers {
  const headers = new Headers(init)
  headers.set('Accept', 'application/json')
  if (token) headers.set('Authorization', `Bearer ${token}`)
  return headers
}

export function parseShellState(value: unknown): ShellState {
  return typeof value === 'string' && shellStates.includes(value as ShellState) ? (value as ShellState) : 'ready'
}
