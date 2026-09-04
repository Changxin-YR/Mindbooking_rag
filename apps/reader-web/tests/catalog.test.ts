import { describe, expect, it } from 'vitest'
import { bookDetailPath, catalogPath, chapterPath, progressPath } from '../src/catalog'

describe('reader catalog path', () => {
  it('serializes only supplied filters for the public API', () => {
    expect(catalogPath({ channel: 'MALE', tag: '系统', q: '' })).toBe(
      '/api/v1/books?channel=MALE&tag=%E7%B3%BB%E7%BB%9F',
    )
  })
})

describe('reader domain paths', () => {
  it('builds encoded public detail and chapter paths', () => {
    expect(bookDetailPath('book-1')).toBe('/api/v1/books/book-1')
    expect(chapterPath('book-1', 'chapter-1')).toBe('/api/v1/books/book-1/chapters/chapter-1')
    expect(progressPath('book-1', 'http://localhost:8000')).toBe(
      'http://localhost:8000/api/v1/books/book-1/progress',
    )
  })
})
