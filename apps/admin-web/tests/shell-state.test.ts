import { describe, expect, it } from 'vitest'
import { buildAdminHeaders, parseShellState, readAdminAccessToken } from '../src/shell-state'

describe('admin shell state', () => {
  it('recognizes unauthorized access as a first-class state', () => {
    expect(parseShellState('unauthorized')).toBe('unauthorized')
    expect(parseShellState('loading')).toBe('loading')
    expect(parseShellState('unknown')).toBe('ready')
  })
})

describe('admin session', () => {
  it('reads the configured token and sends it as a Bearer header', () => {
    const storage = { getItem: (key: string) => key === 'admin_access_token' ? ' session-token ' : null }

    const token = readAdminAccessToken(storage)

    expect(token).toBe('session-token')
    expect(buildAdminHeaders(token).get('Authorization')).toBe('Bearer session-token')
  })

  it('does not reuse a reader token as an admin session', () => {
    const storage = { getItem: (key: string) => key === 'access_token' ? 'reader-session' : ' ' }

    expect(readAdminAccessToken(storage)).toBe('')
  })
})
