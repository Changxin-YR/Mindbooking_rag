import { describe, expect, it } from 'vitest'
import { buildRequestHeaders, loadSession, saveSession, type StorageLike } from '../src/session'

class MemoryStorage implements StorageLike {
  private values = new Map<string, string>()

  getItem(key: string) { return this.values.get(key) ?? null }
  setItem(key: string, value: string) { this.values.set(key, value) }
  removeItem(key: string) { this.values.delete(key) }
}

describe('reader session', () => {
  it('persists a normalized session and builds bearer headers', () => {
    const storage = new MemoryStorage()
    saveSession({ token: ' signed-token ', accountId: ' acct-1 ' }, storage)
    expect(loadSession(storage)).toEqual({ token: 'signed-token', accountId: 'acct-1' })
    expect(buildRequestHeaders('signed-token').get('Authorization')).toBe('Bearer signed-token')
  })

  it('rejects malformed stored values', () => {
    const storage = new MemoryStorage()
    storage.setItem('reader-web-session', '{bad json')
    expect(loadSession(storage)).toBeNull()
  })
})
