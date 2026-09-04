import { describe, expect, it } from 'vitest'
import { parseShellState } from '../src/shell-state'

describe('writer shell state', () => {
  it('keeps invalid URL state from leaking into the application state', () => {
    expect(parseShellState('empty')).toBe('empty')
    expect(parseShellState('error')).toBe('error')
    expect(parseShellState('deleted')).toBe('ready')
  })
})
