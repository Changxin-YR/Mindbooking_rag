import { describe, expect, it } from 'vitest'
import {
  buildRequestHeaders,
  loadSession,
  saveSession,
  resolveApiBaseUrl,
  type StorageLike,
} from '../src/session'

class MemoryStorage implements StorageLike {
  private values = new Map<string, string>()

  getItem(key: string) {
    return this.values.get(key) ?? null
  }

  setItem(key: string, value: string) {
    this.values.set(key, value)
  }

  removeItem(key: string) {
    this.values.delete(key)
  }
}

describe('writer session', () => {
  it('persists the session and adds a bearer header to requests', () => {
    const storage = new MemoryStorage()

    saveSession({ token: '  signed-session  ', accountId: 'acct-1' }, storage)

    expect(loadSession(storage)).toEqual({ token: 'signed-session', accountId: 'acct-1' })
    expect(buildRequestHeaders('signed-session', { 'X-Request-Id': 'req-1' }).get('Authorization')).toBe(
      'Bearer signed-session',
    )
    expect(buildRequestHeaders('signed-session').get('Accept')).toBe('application/json')
  })

  it('ignores malformed stored sessions and normalizes the API base URL', () => {
    const storage = new MemoryStorage()
    storage.setItem('writer-web-session', '{bad json')

    expect(loadSession(storage)).toBeNull()
    expect(resolveApiBaseUrl(' https://api.example.test/// ')).toBe('https://api.example.test')
    expect(resolveApiBaseUrl('', 'https://fallback.example.test/')).toBe('https://fallback.example.test')
  })
})
