export interface CatalogFilters {
  channel?: string
  category?: string
  tag?: string
  lifecycle?: string
  commercial_policy?: string
  q?: string
  status?: string
  min_word_count?: string | number
  max_word_count?: string | number
  sort?: string
  page?: string | number
  page_size?: string | number
}

export function catalogPath(filters: CatalogFilters = {}, baseUrl = ''): string {
  const query = new URLSearchParams()
  for (const [key, value] of Object.entries(filters)) {
    const normalized = value === undefined || value === null ? '' : String(value).trim()
    if (normalized) query.set(key, normalized)
  }
  const suffix = query.toString()
  const path = `/api/v1/books${suffix ? `?${suffix}` : ''}`
  return baseUrl ? `${baseUrl.replace(/\/$/, '')}${path}` : path
}

export function bookDetailPath(bookId: string, baseUrl = ''): string {
  const path = `/api/v1/books/${encodeURIComponent(bookId)}`
  return baseUrl ? `${baseUrl.replace(/\/$/, '')}${path}` : path
}

export function chapterPath(bookId: string, chapterId: string, baseUrl = ''): string {
  const path = `/api/v1/books/${encodeURIComponent(bookId)}/chapters/${encodeURIComponent(chapterId)}`
  return baseUrl ? `${baseUrl.replace(/\/$/, '')}${path}` : path
}

export function progressPath(bookId: string, baseUrl = ''): string {
  const path = `/api/v1/books/${encodeURIComponent(bookId)}/progress`
  return baseUrl ? `${baseUrl.replace(/\/$/, '')}${path}` : path
}

export function searchPath(filters: CatalogFilters = {}, baseUrl = ''): string {
  const query = new URLSearchParams()
  for (const [key, value] of Object.entries(filters)) {
    if (value !== undefined && String(value).trim()) query.set(key, String(value))
  }
  const suffix = query.toString()
  const path = `/api/v1/search${suffix ? `?${suffix}` : ''}`
  return baseUrl ? `${baseUrl.replace(/\/$/, '')}${path}` : path
}

export function rankingPath(kind = 'ALGORITHM', baseUrl = ''): string {
  const query = new URLSearchParams({ kind })
  const path = `/api/v1/rankings?${query.toString()}`
  return baseUrl ? `${baseUrl.replace(/\/$/, '')}${path}` : path
}
