import { describe, expect, it } from 'vitest'
import { parseShellState } from '../src/shell-state'

describe('admin shell state', () => {
  it('recognizes unauthorized access as a first-class state', () => {
    expect(parseShellState('unauthorized')).toBe('unauthorized')
    expect(parseShellState('loading')).toBe('loading')
    expect(parseShellState('unknown')).toBe('ready')
  })
})
