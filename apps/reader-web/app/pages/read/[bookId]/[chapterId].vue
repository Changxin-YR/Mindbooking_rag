<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue'
import type { ReaderBookDetailResponseDto, ReaderChapterResponseDto, ReaderPreferencesDto, ReaderProgressDto } from '@mindbooking/api-types'
import { bookDetailPath, chapterPath, progressPath } from '../../../../src/catalog'
import { buildRequestHeaders, loadSession } from '../../../../src/session'

type ReadingMode = 'scroll' | 'paged'
type ReaderBackground = 'white' | 'cream' | 'eye' | 'gray' | 'dark'
type ReaderSettings = { mode: ReadingMode; fontFamily: 'serif' | 'sans'; fontSize: number; fontWeight: 400 | 500 | 600; lineHeight: number; paragraphSpacing: number; contentWidth: number; background: ReaderBackground; autoScrollSpeed: number; autoSubscribe: boolean }
const defaultSettings: ReaderSettings = { mode: 'scroll', fontFamily: 'serif', fontSize: 18, fontWeight: 400, lineHeight: 2, paragraphSpacing: 1.25, contentWidth: 760, background: 'cream', autoScrollSpeed: 1, autoSubscribe: false }

const route = useRoute()
const router = useRouter()
const runtimeConfig = useRuntimeConfig()
const apiBase = runtimeConfig.public.apiBaseUrl
const session = loadSession()
const accountId = session?.accountId ?? ''
const headers = session ? buildRequestHeaders(session.token) : undefined
const bookId = computed(() => String(route.params.bookId))
const chapterId = computed(() => String(route.params.chapterId))
const settingsKey = computed(() => `reader-settings:${session?.accountId || 'guest'}`)
const bookmarkKey = computed(() => `reader-bookmarks:${session?.accountId || 'guest'}:${bookId.value}`)
const settingsOpen = ref(false)
const tocOpen = ref(false)
const saved = ref(false)
const saveError = ref('')
const guestPosition = ref(0)
const currentPosition = ref(0)
const purchaseNotice = ref('')
const purchasing = ref(false)
const purchaseIdempotencyKey = ref('')
const ttsNotice = ref('')
const ttsPlaying = ref(false)
const bookmarkNotice = ref('')
const isBookmarked = ref(false)
const autoScrolling = ref(false)
let saveTimer: ReturnType<typeof setTimeout> | undefined
let autoScrollTimer: ReturnType<typeof setInterval> | undefined
const settings = reactive<ReaderSettings>({ ...defaultSettings })

const { data: book } = await useFetch<ReaderBookDetailResponseDto>(() => bookDetailPath(bookId.value, apiBase), { headers, server: false })
const { data: chapter, pending, error } = await useFetch<ReaderChapterResponseDto>(() => chapterPath(bookId.value, chapterId.value, apiBase), { headers, server: false })
const { data: progress } = await useFetch<ReaderProgressDto>(() => progressPath(bookId.value, apiBase), { query: { account_id: accountId }, headers, immediate: Boolean(session), server: false })
const chapterIndex = computed(() => Math.max(0, book.value?.chapters.findIndex((item) => item.id === chapterId.value) ?? -1))
const previousChapter = computed(() => book.value?.chapters[chapterIndex.value - 1])
const nextChapter = computed(() => book.value?.chapters[chapterIndex.value + 1])
const settingsStyle = computed(() => ({
  '--reader-font-family': settings.fontFamily === 'serif' ? "'Songti SC', 'STSong', serif" : "system-ui, sans-serif",
  '--reader-font-size': `${settings.fontSize}px`,
  '--reader-font-weight': settings.fontWeight,
  '--reader-line-height': settings.lineHeight,
  '--reader-paragraph-gap': `${settings.paragraphSpacing}em`,
  '--reader-content-width': `${settings.contentWidth}px`,
}))
const contentStyle = computed(() => ({ maxWidth: `${settings.contentWidth}px`, fontFamily: settingsStyle.value['--reader-font-family'], fontSize: settingsStyle.value['--reader-font-size'], fontWeight: settings.fontWeight, lineHeight: settings.lineHeight }))

function backgroundClass() {
  return `reader-bg-${settings.background}`
}

function openChapter(id: string) {
  return navigateTo(`/read/${bookId.value}/${id}`)
}

function changeChapter(event: Event) {
  const id = (event.target as HTMLSelectElement).value
  if (id) openChapter(id)
}

async function saveSettings() {
  try { globalThis.localStorage?.setItem(settingsKey.value, JSON.stringify(settings)) } catch { /* local storage may be disabled */ }
  if (session) {
    try {
      await $fetch<ReaderPreferencesDto>(`${apiBase}/api/v1/accounts/${encodeURIComponent(accountId)}/reading-preferences`, { method: 'PUT', headers, body: { mode: settings.mode, font_family: settings.fontFamily, font_size: settings.fontSize, font_weight: settings.fontWeight, line_height: settings.lineHeight, paragraph_spacing: settings.paragraphSpacing, content_width: settings.contentWidth, background: settings.background, auto_scroll_speed: settings.autoScrollSpeed, auto_subscribe: settings.autoSubscribe } })
      saveError.value = ''
    } catch { saveError.value = '云端阅读设置同步失败，已保留本机设置。' }
  }
  settingsOpen.value = false
}

function restoreSettings() {
  try {
    const value = JSON.parse(globalThis.localStorage?.getItem(settingsKey.value) || 'null') as Partial<ReaderSettings> | null
    if (value) Object.assign(settings, { ...defaultSettings, ...value })
    isBookmarked.value = globalThis.localStorage?.getItem(bookmarkKey.value) === '1'
  } catch { /* malformed local state uses defaults */ }
  if (session) void syncCloudSettings()
}

async function syncCloudSettings() {
  try {
    const remote = await $fetch<ReaderPreferencesDto>(`${apiBase}/api/v1/accounts/${encodeURIComponent(accountId)}/reading-preferences`, { headers })
    Object.assign(settings, { ...defaultSettings, mode: remote.mode, fontFamily: remote.font_family, fontSize: remote.font_size, fontWeight: remote.font_weight, lineHeight: remote.line_height, paragraphSpacing: remote.paragraph_spacing, contentWidth: remote.content_width, background: remote.background, autoScrollSpeed: remote.auto_scroll_speed, autoSubscribe: remote.auto_subscribe })
    try { globalThis.localStorage?.setItem(settingsKey.value, JSON.stringify(settings)) } catch { /* local storage may be disabled */ }
  } catch { /* a missing cloud row keeps the local settings */ }
}

function updatePosition() {
  if (!chapter.value) return
  const element = document.documentElement
  const max = Math.max(1, element.scrollHeight - window.innerHeight)
  currentPosition.value = Math.min(chapter.value.content.length, Math.round((window.scrollY / max) * chapter.value.content.length))
  if (settings.mode === 'scroll') scheduleSave()
}

function scheduleSave() {
  if (saveTimer) clearTimeout(saveTimer)
  saveTimer = setTimeout(() => saveProgress(currentPosition.value), 900)
}

async function saveProgress(position: number) {
  const safePosition = Math.max(0, Math.min(position, chapter.value?.content.length || position))
  if (!session) {
    guestPosition.value = safePosition
    try { globalThis.localStorage?.setItem(`reader-guest-progress:${bookId.value}`, JSON.stringify({ chapterId: chapterId.value, position: safePosition })) } catch { /* private browsing may disable storage */ }
    saved.value = true
    saveError.value = ''
    return
  }
  try {
    progress.value = await $fetch<ReaderProgressDto>(progressPath(bookId.value, apiBase), { method: 'PUT', query: { account_id: accountId }, headers, body: { chapter_id: chapterId.value, chapter_number: chapter.value?.number || 1, position: safePosition, expected_revision: progress.value?.revision ?? 0, session_id: 'reader-web' } })
    saved.value = true
    saveError.value = ''
  } catch (cause: unknown) {
    saveError.value = cause && typeof cause === 'object' && 'data' in cause ? '阅读进度发生冲突，请刷新后重试。' : '阅读进度暂时无法同步。'
    saved.value = false
  }
}

function toggleAutoScroll() {
  if (autoScrolling.value) {
    if (autoScrollTimer) clearInterval(autoScrollTimer)
    autoScrollTimer = undefined
    autoScrolling.value = false
    return
  }
  autoScrolling.value = true
  autoScrollTimer = setInterval(() => window.scrollBy({ top: settings.autoScrollSpeed, behavior: 'auto' }), 40)
}

async function toggleFullscreen() {
  try {
    if (document.fullscreenElement) await document.exitFullscreen()
    else await document.documentElement.requestFullscreen()
  } catch { /* browser denied fullscreen */ }
}

function toggleBookmark() {
  isBookmarked.value = !isBookmarked.value
  try { globalThis.localStorage?.setItem(bookmarkKey.value, isBookmarked.value ? '1' : '0') } catch { /* local storage may be disabled */ }
  bookmarkNotice.value = isBookmarked.value ? '书签已保存' : '书签已移除'
}

function speakChapter() {
  if (!chapter.value || !('speechSynthesis' in globalThis)) {
    ttsNotice.value = '当前浏览器不支持朗读。'
    return
  }
  if (ttsPlaying.value) {
    speechSynthesis.cancel()
    ttsPlaying.value = false
    return
  }
  ttsNotice.value = ''
  ttsPlaying.value = true
  $fetch<{ segments: Array<{ text: string }> }>(`${apiBase}/api/v1/books/${encodeURIComponent(bookId.value)}/chapters/${encodeURIComponent(chapterId.value)}/tts`, { query: { account_id: accountId }, headers }).then((result) => {
    const text = result.segments.map((segment) => segment.text).join(' ') || chapter.value?.content || ''
    const utterance = new SpeechSynthesisUtterance(text)
    utterance.rate = 1
    utterance.onend = () => { ttsPlaying.value = false }
    speechSynthesis.speak(utterance)
  }).catch(() => {
    ttsPlaying.value = false
    ttsNotice.value = '朗读需要先通过章节权限检查，请登录或购买后重试。'
  })
}

async function purchaseChapter() {
  if (!session || !chapter.value || purchasing.value) return
  purchasing.value = true
  purchaseNotice.value = ''
  purchaseIdempotencyKey.value ||= globalThis.crypto?.randomUUID?.() || `purchase-${Date.now()}`
  try {
    const purchaseHeaders = new Headers(headers)
    purchaseHeaders.set('Idempotency-Key', purchaseIdempotencyKey.value)
    await $fetch(`${apiBase}/api/v1/purchases`, { method: 'POST', headers: purchaseHeaders, body: { account_id: accountId, chapter_id: chapterId.value } })
    purchaseNotice.value = '购买成功，正在刷新章节权限。'
    await refreshNuxtData()
  } catch (cause: unknown) {
    const code = cause && typeof cause === 'object' && 'data' in cause ? (cause.data as { error?: { code?: string }; detail?: { code?: string } })?.error?.code || (cause.data as { detail?: { code?: string } })?.detail?.code : undefined
    purchaseNotice.value = code === 'INSUFFICIENT_BALANCE' ? '余额不足，请先充值。' : code === 'REVISION_CONFLICT' ? '订单状态发生变化，请刷新后重试。' : '购买失败，请稍后重试。'
  } finally { purchasing.value = false }
}

watch(() => route.params.chapterId, () => {
  saved.value = false
  currentPosition.value = 0
  ttsPlaying.value = false
  speechSynthesis?.cancel?.()
})
onMounted(() => {
  restoreSettings()
  window.addEventListener('scroll', updatePosition, { passive: true })
  try {
    const value = JSON.parse(globalThis.localStorage?.getItem(`reader-guest-progress:${bookId.value}`) || 'null') as { chapterId?: string; position?: number } | null
    if (value?.chapterId === chapterId.value && typeof value.position === 'number') {
      guestPosition.value = value.position
      currentPosition.value = value.position
    }
  } catch { /* malformed guest state is discarded */ }
})
onBeforeUnmount(() => {
  window.removeEventListener('scroll', updatePosition)
  if (saveTimer) clearTimeout(saveTimer)
  if (autoScrollTimer) clearInterval(autoScrollTimer)
  speechSynthesis?.cancel?.()
})
</script>

<template>
  <div class="reader-shell reading-shell" :class="backgroundClass()" :style="settingsStyle">
    <header class="reader-header reading-header"><NuxtLink class="reader-brand" to="/">墨页 <span>MindBook</span></NuxtLink><span class="reading-book-name">{{ book?.title || '正在阅读' }}</span><NuxtLink class="back-link" :to="`/books/${bookId}`">返回作品详情</NuxtLink><div class="reading-header-actions"><button class="quiet-action" type="button" @click="tocOpen = !tocOpen">目录</button><button class="quiet-action" type="button" @click="settingsOpen = !settingsOpen">设置</button></div></header>
    <aside v-if="tocOpen" class="reader-toc" aria-label="章节目录"><div class="reader-drawer-heading"><strong>章节目录</strong><button type="button" aria-label="关闭目录" @click="tocOpen = false">×</button></div><ol><li v-for="item in book?.chapters" :key="item.id" :class="{ active: item.id === chapterId }"><button type="button" @click="openChapter(item.id)">第 {{ item.number }} 章 · {{ item.title }}<small>{{ item.commercial_policy === 'FREE' ? '免费' : 'VIP' }}</small></button></li></ol></aside>
    <aside v-if="settingsOpen" class="reader-settings-panel" aria-label="阅读设置"><div class="reader-drawer-heading"><strong>阅读设置</strong><button type="button" aria-label="关闭设置" @click="settingsOpen = false">×</button></div><label>阅读模式<select v-model="settings.mode"><option value="scroll">滚动阅读</option><option value="paged">分页阅读</option></select></label><label>字体<select v-model="settings.fontFamily"><option value="serif">宋体</option><option value="sans">无衬线</option></select></label><label>字号<input v-model.number="settings.fontSize" type="range" min="14" max="28" step="1" /><output>{{ settings.fontSize }} px</output></label><label>字重<select v-model.number="settings.fontWeight"><option :value="400">常规</option><option :value="500">中等</option><option :value="600">粗体</option></select></label><label>行高<input v-model.number="settings.lineHeight" type="range" min="1.5" max="2.5" step="0.1" /><output>{{ settings.lineHeight }}</output></label><label>段距<input v-model.number="settings.paragraphSpacing" type="range" min="0.5" max="2" step="0.25" /><output>{{ settings.paragraphSpacing }}em</output></label><label>正文宽度<input v-model.number="settings.contentWidth" type="range" min="560" max="960" step="20" /><output>{{ settings.contentWidth }} px</output></label><label>背景<select v-model="settings.background"><option value="white">白色</option><option value="cream">米黄</option><option value="eye">护眼</option><option value="gray">灰色</option><option value="dark">深色</option></select></label><label>自动订阅<select v-model="settings.autoSubscribe"><option :value="false">关闭</option><option :value="true">开启</option></select></label><button class="primary-button" type="button" @click="saveSettings">保存阅读设置</button></aside>
    <main class="reading-main" :class="{ 'reading-paged': settings.mode === 'paged' }">
      <div v-if="pending" class="catalog-state">正在打开章节...</div>
      <div v-else-if="error || !chapter" class="catalog-state error">章节暂时无法阅读，请返回作品详情。</div>
      <div v-else-if="chapter.access === 'VIP_REQUIRED'" class="catalog-state access-required"><h1>本章需要购买</h1><p>当前访问原因：VIP_REQUIRED。购买后永久获得本章权益，会员过期不影响已购章节。</p><button class="primary-button" type="button" :disabled="!session || purchasing" @click="purchaseChapter">{{ !session ? '登录后购买' : purchasing ? '正在创建订单...' : '购买本章' }}</button><NuxtLink v-if="!session" class="text-button" to="/settings">去登录</NuxtLink><NuxtLink class="text-button" to="/wallet">去充值</NuxtLink><p v-if="purchaseNotice" class="action-notice" role="status">{{ purchaseNotice }}</p></div>
      <article v-else class="reading-article" :style="contentStyle"><div class="reading-toolbar"><label>目录<select :value="chapterId" @change="changeChapter"><option v-for="item in book?.chapters" :key="item.id" :value="item.id">第 {{ item.number }} 章 · {{ item.title }}</option></select></label><span>第 {{ chapter.number }} 章 · {{ chapter.access }}</span></div><div class="reading-progress-bar" role="progressbar" :aria-valuenow="currentPosition" :aria-valuemax="chapter.content.length"><span :style="{ width: `${chapter.content.length ? Math.min(100, currentPosition / chapter.content.length * 100) : 0}%` }" /></div><p class="eyebrow">当前访问：{{ chapter.access }} · {{ chapter.commercial_policy }}</p><h1>{{ chapter.title }}</h1><div class="reading-content">{{ chapter.content }}</div><div class="reading-actions"><button class="primary-button" type="button" @click="saveProgress(currentPosition || chapter.content.length)">{{ session ? '保存阅读进度' : '保存本机进度' }}</button><button class="quiet-action" type="button" @click="toggleAutoScroll">{{ autoScrolling ? '停止自动阅读' : '自动阅读' }}</button><button class="quiet-action" type="button" @click="toggleBookmark">{{ isBookmarked ? '移除书签' : '添加书签' }}</button><button class="quiet-action" type="button" @click="speakChapter">{{ ttsPlaying ? '停止朗读' : 'TTS朗读' }}</button><button class="quiet-action" type="button" @click="toggleFullscreen">全屏</button><span v-if="saved" role="status">{{ session ? '已同步' : '已保存在本机' }}</span><span v-else-if="!session && guestPosition" role="status">已读 {{ guestPosition }} 字</span><span v-if="saveError" class="catalog-inline-warning" role="alert">{{ saveError }}</span><span v-if="ttsNotice" role="status">{{ ttsNotice }}</span><span v-if="bookmarkNotice" role="status">{{ bookmarkNotice }}</span></div><nav class="chapter-navigation" aria-label="章节切换"><NuxtLink v-if="previousChapter" :to="`/read/${bookId}/${previousChapter.id}`">上一章</NuxtLink><span v-else>已是第一章</span><NuxtLink v-if="nextChapter" :to="`/read/${bookId}/${nextChapter.id}`">下一章</NuxtLink><span v-else>已读完本书</span></nav></article>
    </main>
  </div>
</template>
