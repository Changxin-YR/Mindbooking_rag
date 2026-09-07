<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import type { ReaderBookDetailResponseDto } from '@mindbooking/api-types'
import { bookDetailPath, progressPath } from '../../../src/catalog'
import { buildRequestHeaders, loadSession } from '../../../src/session'

const route = useRoute()
const runtimeConfig = useRuntimeConfig()
const session = loadSession()
const accountId = session?.accountId ?? ''
const headers = session ? buildRequestHeaders(session.token) : undefined
const bookId = String(route.params.id)
const { data: book, pending, error } = await useFetch<ReaderBookDetailResponseDto>(
  bookDetailPath(bookId, runtimeConfig.public.apiBaseUrl),
  { server: false },
)
const isInShelf = ref(false)
const isFollowing = ref(false)
const shelfBusy = ref(false)
const followBusy = ref(false)
const resumeChapterId = ref<string | null>(null)
const stateLoading = ref(false)
const firstReadableChapter = computed(() => book.value?.chapters.find((chapter) => chapter.title !== '作品简介与来源') || book.value?.chapters[0])
const notice = ref('')
const reportReason = ref('')
const correctionKind = ref('TYPO')
const correctionDescription = ref('')
const correctionPosition = ref(0)
const submittingReport = ref(false)
const giftCode = ref('ROSE')
const giftQuantity = ref(1)
const giftNotice = ref('')
const ticketType = ref<'RECOMMEND' | 'MONTHLY'>('RECOMMEND')
const ticketQuantity = ref(1)
const ticketNotice = ref('')
const rating = reactive({ overall_score: 5, plot_score: 5, character_score: 5, writing_score: 5, update_score: 5, eligible_words: 1000 })
const authorName = computed(() => book.value?.synopsis.match(/^作者：([^。]+)/)?.[1] || '作者资料见简介')
const readingLabel = computed(() => resumeChapterId.value ? '继续阅读' : '开始阅读')

async function loadReaderState() {
  if (!session || !book.value) return
  stateLoading.value = true
  try {
    const [shelf, follows, progress] = await Promise.all([
      $fetch<Array<{ book_id: string }>>(`${runtimeConfig.public.apiBaseUrl}/api/v1/bookshelf`, { query: { account_id: accountId }, headers }),
      $fetch<{ items: Array<[string, string] | { target_type: string; target_id: string }> }>(`${runtimeConfig.public.apiBaseUrl}/api/v1/accounts/${encodeURIComponent(accountId)}/follows`, { headers }),
      $fetch<{ last_chapter_id: string | null }>(progressPath(book.value.id, runtimeConfig.public.apiBaseUrl), { query: { account_id: accountId }, headers }),
    ])
    isInShelf.value = shelf.some((entry) => entry.book_id === book.value?.id)
    isFollowing.value = follows.items.some((item) => Array.isArray(item) ? item[0] === 'AUTHOR' && item[1] === book.value?.author_id : item.target_type === 'AUTHOR' && item.target_id === book.value?.author_id)
    resumeChapterId.value = progress.last_chapter_id
  } catch {
    // Availability of the detail page does not depend on optional social state.
  } finally {
    stateLoading.value = false
  }
}
watch(book, loadReaderState, { immediate: true })

async function submitRating() {
  if (!book.value) return
  try {
    if (!session) throw new Error('AUTHENTICATION_REQUIRED')
    await $fetch(`${runtimeConfig.public.apiBaseUrl}/api/v1/books/${encodeURIComponent(book.value.id)}/ratings`, { method: 'POST', headers, body: { account_id: accountId, ...rating } })
    notice.value = '评分已提交'
  } catch {
    notice.value = session ? '当前阅读量未达到评分条件' : '请先登录后评分'
  }
}

async function followAuthor() {
  if (!book.value) return
  try {
    if (!session) throw new Error('AUTHENTICATION_REQUIRED')
    followBusy.value = true
    const body = { account_id: accountId, target_type: 'AUTHOR', target_id: book.value.author_id }
    if (isFollowing.value) {
      await $fetch(`${runtimeConfig.public.apiBaseUrl}/api/v1/social/follows`, { method: 'DELETE', headers, body })
      isFollowing.value = false
      notice.value = '已取消关注'
    } else {
      await $fetch(`${runtimeConfig.public.apiBaseUrl}/api/v1/social/follows`, { method: 'POST', headers, body })
      isFollowing.value = true
      notice.value = '已关注作者'
    }
  } catch {
    notice.value = session ? '关注暂时不可用' : '请先登录后关注作者'
  } finally {
    followBusy.value = false
  }
}

async function addToShelf() {
  if (!book.value) return
  try {
    if (!session) throw new Error('AUTHENTICATION_REQUIRED')
    shelfBusy.value = true
    if (isInShelf.value) {
      await $fetch(`${runtimeConfig.public.apiBaseUrl}/api/v1/books/${encodeURIComponent(book.value.id)}/bookshelf`, { method: 'DELETE', headers, query: { account_id: accountId } })
      isInShelf.value = false
      notice.value = '已移出书架'
    } else {
      await $fetch(`${runtimeConfig.public.apiBaseUrl}/api/v1/books/${encodeURIComponent(book.value.id)}/bookshelf`, { method: 'POST', headers, body: { account_id: accountId, group_name: 'default' } })
      isInShelf.value = true
      notice.value = '已加入书架'
    }
  } catch {
    notice.value = session ? '加入书架暂时不可用' : '请先登录后加入书架'
  } finally {
    shelfBusy.value = false
  }
}

async function submitCorrection() {
  if (!session || !book.value || !book.value.chapters.length || !correctionDescription.value.trim() || submittingReport.value) return
  submittingReport.value = true
  try {
    await $fetch(`${runtimeConfig.public.apiBaseUrl}/api/v1/content-corrections`, { method: 'POST', headers, body: { account_id: accountId, book_id: book.value.id, chapter_id: book.value.chapters[0].id, kind: correctionKind.value, position: correctionPosition.value, description: correctionDescription.value.trim() } })
    notice.value = '纠错已提交，平台会在不暴露举报人身份的前提下处理。'
    correctionDescription.value = ''
  } catch { notice.value = '纠错提交失败，请稍后重试。' } finally { submittingReport.value = false }
}

async function submitReport() {
  if (!session || !book.value || !reportReason.value.trim() || submittingReport.value) return
  submittingReport.value = true
  try {
    await $fetch(`${runtimeConfig.public.apiBaseUrl}/api/v1/community/report-cases`, { method: 'POST', headers, body: { content_type: 'BOOK', content_id: book.value.id, reporter_id: accountId, reason: reportReason.value.trim() } })
    notice.value = '举报已受理，可在客服入口查询处理进度。'
    reportReason.value = ''
  } catch { notice.value = '举报提交失败，请稍后重试。' } finally { submittingReport.value = false }
}

async function sendGift() {
  if (!session || !book.value || submittingReport.value) return
  submittingReport.value = true
  try {
    const headersWithKey = new Headers(headers)
    headersWithKey.set('Idempotency-Key', globalThis.crypto?.randomUUID?.() || `gift-${Date.now()}`)
    await $fetch(`${runtimeConfig.public.apiBaseUrl}/api/v1/gifts`, { method: 'POST', headers: headersWithKey, body: { account_id: accountId, book_id: book.value.id, author_id: book.value.author_id, gift_code: giftCode.value.trim(), quantity: giftQuantity.value } })
    giftNotice.value = '礼物已送出，作者收益将按平台规则进入风控与结算。'
  } catch { giftNotice.value = '礼物发送失败，请确认余额、礼物编码和账号状态。' } finally { submittingReport.value = false }
}

async function castTicket() {
  if (!session || !book.value || submittingReport.value) return
  submittingReport.value = true
  try {
    const headersWithKey = new Headers(headers)
    headersWithKey.set('Idempotency-Key', globalThis.crypto?.randomUUID?.() || `vote-${Date.now()}`)
    await $fetch(`${runtimeConfig.public.apiBaseUrl}/api/v1/membership/tickets/votes`, { method: 'POST', headers: headersWithKey, body: { account_id: accountId, book_id: book.value.id, ticket_type: ticketType.value, quantity: ticketQuantity.value } })
    ticketNotice.value = '投票成功，风险状态以服务端返回为准。'
  } catch { ticketNotice.value = '投票失败，请检查票券余额或账号限制。' } finally { submittingReport.value = false }
}
</script>

<template>
  <div class="reader-shell detail-shell">
    <header class="reader-header">
      <NuxtLink class="reader-brand" to="/">墨页 <span>MindBook</span></NuxtLink>
      <nav class="reader-nav" aria-label="读者导航">
        <NuxtLink to="/">首页</NuxtLink><NuxtLink to="/library">书架</NuxtLink><NuxtLink to="/wallet">钱包</NuxtLink><NuxtLink to="/notifications">通知</NuxtLink><NuxtLink to="/support">客服</NuxtLink>
      </nav>
      <NuxtLink class="login-link" to="/settings">阅读设置</NuxtLink>
    </header>

    <main class="reader-detail-main">
      <div v-if="pending" class="catalog-state">正在加载作品详情...</div>
      <div v-else-if="error || !book" class="catalog-state error">作品不存在或暂时不可用。</div>
      <template v-else>
        <section class="detail-intro">
          <div class="detail-cover" aria-hidden="true">{{ book.title.slice(0, 4) }}</div>
          <div class="detail-copy"><p class="eyebrow">{{ book.channel }} · {{ book.category || '未分类' }}</p><h1>{{ book.title }}</h1><p class="detail-author">作者：{{ authorName }}</p><p>{{ book.synopsis || '作者还没有留下简介。' }}</p><div class="detail-meta"><span>{{ book.lifecycle === 'COMPLETED' ? '完本' : book.lifecycle === 'PAUSED' ? '暂停' : '连载中' }}</span><span>{{ book.chapters.length }} 章已发布</span><span v-for="tag in book.tags" :key="tag">#{{ tag }}</span></div><div class="detail-actions"><button class="primary-button" type="button" :disabled="!firstReadableChapter" @click="firstReadableChapter && navigateTo(`/read/${book.id}/${resumeChapterId || firstReadableChapter.id}`)">{{ readingLabel }}</button><button class="quiet-action" type="button" :disabled="shelfBusy || stateLoading" @click="addToShelf">{{ shelfBusy ? '处理中...' : isInShelf ? '已在书架' : '加入书架' }}</button><button class="quiet-action" type="button" :disabled="followBusy || stateLoading" @click="followAuthor">{{ followBusy ? '处理中...' : isFollowing ? '已关注作者' : '关注作者' }}</button></div><p v-if="notice" class="action-notice" role="status">{{ notice }}</p></div>
        </section>

        <section class="reader-section detail-section" aria-labelledby="chapter-title">
          <div class="section-heading"><div><p class="eyebrow">Published versions</p><h2 id="chapter-title">章节目录</h2></div><span>{{ book.chapters.length }} 章</span></div>
          <ol class="chapter-list"><li v-for="chapter in book.chapters" :key="chapter.id"><span>第 {{ chapter.number }} 章</span><strong>{{ chapter.title }}</strong><small>{{ chapter.commercial_policy === 'FREE' ? '免费' : 'VIP' }}</small><NuxtLink :to="`/read/${book.id}/${chapter.id}`" aria-label="打开章节">打开</NuxtLink></li></ol>
        </section>

        <section class="reader-section rating-panel" aria-labelledby="rating-title">
          <div><p class="eyebrow">读完再评分</p><h2 id="rating-title">留下你的阅读感受</h2><p>评分资格以有效阅读字数计算，会员和粉丝等级彼此独立。</p></div>
          <form class="rating-form" @submit.prevent="submitRating"><label>总分 <input v-model.number="rating.overall_score" type="number" min="1" max="5" /></label><label>剧情 <input v-model.number="rating.plot_score" type="number" min="1" max="5" /></label><label>角色 <input v-model.number="rating.character_score" type="number" min="1" max="5" /></label><button class="primary-button" type="submit">提交评分</button></form>
        </section>
        <section class="reader-section rating-panel" aria-labelledby="governance-title">
          <div><p class="eyebrow">Community safety</p><h2 id="governance-title">纠错与举报</h2><p>提交后进入 Governance/Report Case，平台不会向作者暴露你的身份。</p></div>
          <div class="support-form">
            <label>纠错类型<select v-model="correctionKind"><option value="TYPO">错别字</option><option value="MISSING_CHAPTER">章节缺失</option><option value="FORMATTING">排版错误</option><option value="POLICY">内容问题</option></select></label>
            <label>纠错说明<textarea v-model="correctionDescription" rows="3" placeholder="请描述章节和位置" /></label>
            <button class="primary-button" type="button" :disabled="!session || submittingReport" @click="submitCorrection">{{ session ? '提交纠错' : '登录后纠错' }}</button>
            <label>社区举报原因<textarea v-model="reportReason" rows="3" placeholder="广告、侵权或其他问题" /></label>
            <button class="quiet-action" type="button" :disabled="!session || submittingReport" @click="submitReport">{{ session ? '提交举报' : '登录后举报' }}</button>
          </div>
        </section>
        <section class="reader-section rating-panel" aria-labelledby="support-title">
          <div><p class="eyebrow">Fan actions</p><h2 id="support-title">礼物与票券</h2><p>消费由 Wallet/Membership 服务校验，重复提交不会重复扣减。</p></div>
          <div class="support-form">
            <label>礼物编码<input v-model="giftCode" required /></label><label>数量<input v-model.number="giftQuantity" type="number" min="1" required /></label>
            <button class="primary-button" type="button" :disabled="!session || submittingReport" @click="sendGift">{{ session ? '送出礼物' : '登录后送礼' }}</button><p v-if="giftNotice" role="status">{{ giftNotice }}</p>
            <label>票券类型<select v-model="ticketType"><option value="RECOMMEND">推荐票</option><option value="MONTHLY">月票</option></select></label><label>数量<input v-model.number="ticketQuantity" type="number" min="1" required /></label>
            <button class="quiet-action" type="button" :disabled="!session || submittingReport" @click="castTicket">{{ session ? '投票' : '登录后投票' }}</button><p v-if="ticketNotice" role="status">{{ ticketNotice }}</p>
          </div>
        </section>
      </template>
    </main>
    <footer class="reader-footer"><span>墨页 MindBook</span><span>阅读记录由账号同步</span></footer>
  </div>
</template>
