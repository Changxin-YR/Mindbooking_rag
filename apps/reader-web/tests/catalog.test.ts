import { describe, expect, it } from 'vitest'
import { bookDetailPath, catalogPath, chapterPath, progressPath, rankingPath, searchPath } from '../src/catalog'

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

  it('supports the frozen library dimensions without constructing SQL in the browser', () => {
    expect(catalogPath({ channel: 'FEMALE', lifecycle: 'COMPLETED', commercial_policy: 'FREE' })).toBe(
      '/api/v1/books?channel=FEMALE&lifecycle=COMPLETED&commercial_policy=FREE',
    )
  })

  it('serializes numeric catalog filters without throwing', () => {
    expect(catalogPath({ min_word_count: 1000000, max_word_count: 2000000 })).toBe(
      '/api/v1/books?min_word_count=1000000&max_word_count=2000000',
    )
  })
})

describe('reader search and ranking paths', () => {
  it('keeps search inside the reader API and preserves filters', () => {
    expect(searchPath({ q: '斗破', category: '玄幻', status: 'SERIALIZING' })).toBe(
      '/api/v1/search?q=%E6%96%97%E7%A0%B4&category=%E7%8E%84%E5%B9%BB&status=SERIALIZING',
    )
  })

  it('builds ranking route without an external host', () => {
    expect(rankingPath('hot', 'http://localhost:8000')).toBe('http://localhost:8000/api/v1/rankings?kind=hot')
  })
})
