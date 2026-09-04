export type AppErrorCode =
  | 'UNAUTHORIZED'
  | 'FORBIDDEN'
  | 'NOT_FOUND'
  | 'CONFLICT'
  | 'VALIDATION_FAILED'
  | 'DEPENDENCY_UNAVAILABLE'
  | 'INTERNAL_ERROR'
  | (string & {})

export interface ApiActionDto {
  type: string
  href?: string
}

export interface ApiErrorDto {
  code: AppErrorCode
  message: string
  request_id: string
  action?: ApiActionDto
}

export interface ApiErrorEnvelope {
  error: ApiErrorDto
}

export interface ApiListDto<T> {
  items: T[]
  total: number
}

export interface ReaderBookSummaryDto {
  book_no: string
  title: string
  author_pen_name: string
  cover_file_id?: string
  lifecycle: 'SERIALIZING' | 'PAUSED' | 'COMPLETED'
  visibility: 'PUBLIC' | 'TEMP_OFFLINE' | 'PERMANENT_OFFLINE'
}

export interface PlatformHealthDto {
  service: string
  status: 'ok' | 'degraded'
  checked_at: string
}
