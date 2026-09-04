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
