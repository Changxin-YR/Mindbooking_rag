import type { ApiErrorEnvelope } from '@mindbooking/api-types'

export type ApiFetcher = (input: RequestInfo | URL, init?: RequestInit) => Promise<Response>

export interface ApiClientOptions {
  baseUrl?: string
  fetcher?: ApiFetcher
}

export class ApiError extends Error {
  constructor(
    public readonly status: number,
    public readonly code: string,
    message: string,
    public readonly requestId?: string,
  ) {
    super(message)
    this.name = 'ApiError'
  }
}

function isErrorEnvelope(value: unknown): value is ApiErrorEnvelope {
  if (!value || typeof value !== 'object' || !('error' in value)) return false
  const error = value.error
  return Boolean(error && typeof error === 'object' && 'code' in error && 'message' in error)
}

export function createApiClient(options: ApiClientOptions = {}) {
  const { baseUrl, fetcher = fetch } = options

  async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
    const headers: Record<string, string> = {}
    new Headers(init.headers).forEach((value, key) => { headers[key] = value })
    headers.Accept ??= 'application/json'
    if (init.body && !headers['Content-Type']) headers['Content-Type'] = 'application/json'
    const url = baseUrl ? new URL(path, baseUrl).toString() : path
    const response = await fetcher(url, { ...init, headers })
    const text = await response.text()
    const data: unknown = text ? JSON.parse(text) : undefined

    if (!response.ok) {
      if (isErrorEnvelope(data)) {
        throw new ApiError(response.status, data.error.code, data.error.message, data.error.request_id)
      }
      throw new ApiError(response.status, 'HTTP_ERROR', `Request failed with status ${response.status}`)
    }

    return data as T
  }

  return {
    get: <T>(path: string, init?: RequestInit) => request<T>(path, { ...init, method: 'GET' }),
    post: <TBody, TResponse>(path: string, body: TBody, init?: RequestInit) =>
      request<TResponse>(path, { ...init, method: 'POST', body: JSON.stringify(body) }),
  }
}
