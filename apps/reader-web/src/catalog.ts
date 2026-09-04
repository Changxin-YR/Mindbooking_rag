export interface CatalogFilters {
  channel?: string
  category?: string
  tag?: string
  q?: string
}

export function catalogPath(filters: CatalogFilters = {}, baseUrl = ''): string {
  const query = new URLSearchParams()
  for (const [key, value] of Object.entries(filters)) {
    if (value?.trim()) query.set(key, value)
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
