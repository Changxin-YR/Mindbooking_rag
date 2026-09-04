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

export interface ReaderCatalogItemDto {
  id: string
  title: string
  synopsis: string
  author_id: string
  channel: string
  category: string
  tags: string[]
  lifecycle: string
  visibility: string
}

export interface ReaderCatalogResponseDto {
  items: ReaderCatalogItemDto[]
  total: number
}

export interface ReaderChapterSummaryDto {
  id: string
  number: number
  title: string
  commercial_policy: string
}

export interface ReaderBookDetailResponseDto {
  id: string
  title: string
  synopsis: string
  author_id: string
  channel: string
  category: string
  tags: string[]
  lifecycle: string
  visibility: string
  chapters: ReaderChapterSummaryDto[]
}

export interface ReaderChapterResponseDto {
  id: string
  book_id: string
  number?: number
  title: string
  content: string
  commercial_policy: string
  access: string
}

export interface ReaderProgressDto {
  account_id: string
  book_id: string
  last_chapter_id: string | null
  last_chapter_number: number
  last_position: number
  furthest_chapter_id: string | null
  furthest_chapter_number: number
  furthest_position: number
  revision: number
  current_session_id: string | null
}

export interface PrivacyRequestDto {
  id: string
  account_id: string
  kind: string
  status: string
}

export interface WritingStatDto {
  author_id: string
  business_date: string
  words: number
  goal: number
}

export interface TaskProgressDto {
  author_id: string
  task_id: string
  progress: number
  claimed: boolean
}

export interface User360ViewDto {
  account_id: string
  phone: string
  real_name: string
  asset_cents: number | null
  membership_level: number
  growth_level: number
}

export interface PlatformHealthDto {
  service: string
  status: 'ok' | 'degraded'
  checked_at: string
}
