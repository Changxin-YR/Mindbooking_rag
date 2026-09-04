import { describe, expect, it } from 'vitest'
import { catalogPath } from '../src/catalog'

describe('reader catalog path', () => {
  it('serializes only supplied filters for the public API', () => {
    expect(catalogPath({ channel: 'MALE', tag: '系统', q: '' })).toBe(
      '/api/v1/books?channel=MALE&tag=%E7%B3%BB%E7%BB%9F',
    )
  })
})
