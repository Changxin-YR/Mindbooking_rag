import { describe, expect, it } from 'vitest'
import { parseShellState } from '../src/shell-state'

describe('reader shell state', () => {
  it('accepts only supported preview states and falls back to ready', () => {
    expect(parseShellState('loading')).toBe('loading')
    expect(parseShellState('unauthorized')).toBe('unauthorized')
    expect(parseShellState('unexpected')).toBe('ready')
    expect(parseShellState(undefined)).toBe('ready')
  })
})
