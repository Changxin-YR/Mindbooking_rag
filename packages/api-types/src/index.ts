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

export interface ReaderShelfEntryDto {
  account_id: string
  book_id: string
  group_name: string
  title?: string | null
  synopsis?: string | null
  author_id?: string | null
  lifecycle?: string | null
  visibility?: string | null
  availability?: 'AVAILABLE' | 'UNAVAILABLE' | 'NOT_FOUND' | string | null
}

export interface ReaderBookshelfStatusDto {
  account_id: string
  book_id: string
  in_bookshelf: boolean
}

export interface ReaderSearchItemDto {
  book_id: string
  title: string
  synopsis: string
  author_name: string
  category: string
  channel: string
  status: string
  tags: string[]
  word_count: number
  popularity: number
  updated_at: string | number
}

export interface ReaderSearchResponseDto {
  items: ReaderSearchItemDto[]
  total: number
  page: number
  page_size: number
  degraded: boolean
}

export interface ReaderRankingItemDto {
  id: string
  book_id: string
  kind: string
  score: number
  rank: number
  snapshot_id: string
}

export interface ReaderRankingExplanationDto {
  kind: string
  title: string
  rule: string
  update_period: string
  data_time: string
}

export interface SupportTicketDto {
  id: string
  account_id: string
  category: string
  priority: 'P0' | 'P1' | 'P2' | 'P3' | string
  status: string
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

export interface AdminBookDto {
  id: string
  author_id: string
  title: string
  lifecycle: string
  visibility: string
}

export type BookLifecycle = 'DRAFT' | 'SERIALIZING' | 'PAUSED' | 'COMPLETION_PENDING' | 'COMPLETED'

export interface AdminBookLifecycleRequestDto {
  lifecycle: BookLifecycle
}

export interface ReaderChapterResponseDto {
  id: string
  book_id: string
  number: number
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

export interface ReaderPreferencesDto {
  account_id: string
  mode: 'scroll' | 'paged' | string
  font_family: 'serif' | 'sans' | string
  font_size: number
  font_weight: number
  line_height: number
  paragraph_spacing: number
  content_width: number
  background: 'white' | 'cream' | 'eye' | 'gray' | 'dark' | string
  auto_scroll_speed: number
  auto_subscribe: boolean
}

export interface AccountProfileDto {
  account_id: string
  account_no: string
  status: string
  nickname: string | null
  login_name: string | null
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

export interface WalletDto {
  account_id: string
  recharge_coin: number
  gift_coin: number
  total_coin: number
}

export interface RechargeOrderDto {
  payment_no: string
  recharge_no: string
  paid_cents: number
  recharge_coin: number
  gift_coin: number
  status: string
  provider?: string | null
  checkout_url?: string | null
}

export interface SandboxPaymentSimulationDto {
  payment_no: string
  recharge_no?: string | null
  provider: string
  event_id: string
  status: string
  processed: boolean
  available_at: string
}

export interface PurchaseOrderDto {
  purchase_no: string
  chapter_id: string
  price_coin: number
  status: string
}

export interface MembershipStatusDto {
  account_id: string
  active: boolean
}

export interface TicketBalanceDto {
  account_id: string
  recommend: number
  monthly: number
}

export interface MembershipOrderDto {
  id: string
  payment_no: string
  account_id: string
  plan_code: string
  plan_version: number
  channel: string
  price_cents: number
  status: string
  provider?: string | null
  checkout_url?: string | null
}

export interface MembershipSandboxPaymentSimulationDto {
  payment_no: string
  order_id?: string | null
  provider: string
  event_id: string
  status: string
  processed: boolean
  available_at: string
}

export interface NotificationDto {
  id: string
  account_id: string
  category: 'SYSTEM' | 'SECURITY' | 'MARKETING'
  priority: 'NORMAL' | 'P0'
  channels: string[]
  is_read: boolean
}

export interface NotificationUnreadCountDto {
  account_id: string
  unread_count: number
}

export interface SandboxPayoutSimulationDto {
  payout_no: string
  provider: string
  event_id: string
  status: string
  processed: boolean
  available_at: string
}

export interface GiftSendDto {
  id: string
  account_id: string
  book_id: string
  author_id: string
  gift_code: string
  quantity: number
  total_coin: number
  fan_value: number
  status: string
}

export interface AuthorProfileDto {
  id: string
  account_id: string
  pen_name: string
  normalized_pen_name: string
}

export interface ContractDto {
  id: string
  author_id: string
  book_id: string
  status: string
  policy_version: string
  document_text: string
  document_hash: string
  signed_by?: string | null
  signed_at?: string | null
  signature_hash?: string | null
}

export interface SettlementDto {
  id: string
  author_id: string
  period: string
  amount_cents: number
  status: string
  withdrawn_cents: number
}

export interface WithdrawalDto {
  id: string
  settlement_id: string
  amount_cents: number
  status: string
}

export interface RiskSignalDto {
  id: string
  account_id: string
  signal_type: string
  order_id: string
  status: string
}

export interface ReconciliationBatchDto {
  id: string
  business_date: string
  status: string
}

export interface PaymentCreditPendingDto {
  id: string
  payment_id: string
  account_id: string
  amount_cents: number
  status: 'CREDIT_PENDING' | 'REPAIRING' | 'REPAIR_REQUIRED' | 'RESOLVED'
  attempts: number
  last_error?: string | null
  last_attempted_at?: string | null
  resolved_at?: string | null
  repair_actor_id?: string | null
}

export interface OutboxEventDto {
  id: string
  event_type: string
  aggregate_id: string
  payload: Record<string, unknown>
  status: string
}
