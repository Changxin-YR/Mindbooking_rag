<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import type { ReaderBookDetailResponseDto, ReaderCatalogResponseDto, ReaderRankingItemDto } from '@mindbooking/api-types'
import { bookDetailPath, catalogPath, progressPath, rankingPath } from '../../src/catalog'
import { buildRequestHeaders, loadSession } from '../../src/session'

type DisplayBook = { id: string; title: string; synopsis?: string; tags?: string[]; channel: string; category?: string; lifecycle: string }

const route = useRoute()
const router = useRouter()
const runtimeConfig = useRuntimeConfig()
const session = loadSession()
const apiBase = runtimeConfig.public.apiBaseUrl
const searchQuery = ref(String(route.query.q || ''))
const rankingTitles = ref<Record<string, string>>({})
const filters = computed(() => ({
  q: String(route.query.q || ''),
  channel: String(route.query.channel || ''),
  category: String(route.query.category || ''),
  lifecycle: String(route.query.lifecycle || ''),
  commercial_policy: String(route.query.commercial_policy || ''),
}))
const view = computed(() => String(route.query.view || 'home'))
const recommendationPage = computed(() => Math.max(0, Number(route.query.recommendation_page || 0)))

const { data: catalog, pending: catalogPending, error: catalogError } = await useFetch<ReaderCatalogResponseDto>(
  () => catalogPath(filters.value, apiBase),
  { server: false, default: () => ({ items: [], total: 0 }) },
)
const { data: rankings, pending: rankingsPending, error: rankingsError } = await useFetch<ReaderRankingItemDto[]>(
  () => rankingPath('ALGORITHM', apiBase),
  { server: false, default: () => [] },
)

const coverClasses = ['cover-mist', 'cover-night', 'cover-paper', 'cover-crimson', 'cover-sky', 'cover-stone', 'cover-forest', 'cover-sand']
const displayBooks = computed<DisplayBook[]>(() => (catalog.value?.items || []).slice(0, 8).map((book) => ({
  id: book.id,
  title: book.title,
  synopsis: book.synopsis,
  tags: book.tags,
  channel: book.channel,
  category: book.category,
  lifecycle: book.lifecycle,
})))
const displayRecommendations = computed(() => {
  const items = displayBooks.value
  if (!items.length) return items
  const offset = (recommendationPage.value * 4) % items.length
  return items.map((_, index) => items[(offset + index) % items.length]).slice(0, Math.min(8, items.length))
})
const displayRankings = computed(() => (rankings.value || []).slice(0, 9))
const bookTitle = (ranking: ReaderRankingItemDto) => rankingTitles.value[ranking.book_id] || ranking.book_id
const bookMark = (title: string) => title.slice(0, 4)
const bookAuthor = (book: DisplayBook) => book.synopsis?.match(/^作者：([^。]+)/)?.[1] || '作者资料见详情'
const bookSynopsis = (book: DisplayBook) => book.synopsis?.replace(/^作者：[^。]+。/, '').replace(/资料来源：https?:\/\/\S+$/, '').trim() || '公开资料作品，查看详情了解更多。'

function submitSearch() {
  const q = searchQuery.value.trim()
  navigateTo(q ? `/search?q=${encodeURIComponent(q)}` : '/search')
}

function applyFilters(event: Event) {
  const form = event.currentTarget as HTMLFormElement
  const query: Record<string, string> = {}
  for (const [key, value] of new FormData(form).entries()) {
    if (typeof value === 'string' && value.trim()) query[key] = value
  }
  router.push({ path: '/', query })
}

function refreshRecommendations() {
  router.push({ path: '/', query: { ...route.query, recommendation_page: recommendationPage.value + 1 } })
}

async function startReading() {
  if (!session) return navigateTo('/library?mode=discover')
  try {
    const shelf = await $fetch<Array<{ book_id: string }>>(`${apiBase}/api/v1/bookshelf`, {
      query: { account_id: session.accountId },
      headers: buildRequestHeaders(session.token),
    })
    const progressEntries = await Promise.all(shelf.map(async (entry) => {
      try {
        const progress = await $fetch<{ last_chapter_id: string | null }>(progressPath(entry.book_id, apiBase), {
          query: { account_id: session.accountId },
          headers: buildRequestHeaders(session.token),
        })
        return { entry, progress }
      } catch {
        return { entry, progress: null }
      }
    }))
    const recent = progressEntries.find((item) => item.progress?.last_chapter_id)
    if (recent?.progress?.last_chapter_id) return navigateTo(`/read/${recent.entry.book_id}/${recent.progress.last_chapter_id}`)
    const first = shelf[0]
    if (first) {
      const detail = await $fetch<ReaderBookDetailResponseDto>(bookDetailPath(first.book_id, apiBase))
      const chapter = detail.chapters[0]
      if (chapter) return navigateTo(`/read/${first.book_id}/${chapter.id}`)
    }
  } catch {
    // A failed resume falls through to the discover page.
  }
  return navigateTo('/library?mode=discover')
}

watch(() => rankings.value, (items) => {
  for (const item of (items || []).slice(0, 9)) {
    if (rankingTitles.value[item.book_id]) continue
    $fetch<ReaderBookDetailResponseDto>(bookDetailPath(item.book_id, apiBase)).then((book) => {
      rankingTitles.value[item.book_id] = book.title
    }).catch(() => undefined)
  }
}, { immediate: true })
</script>

<template>
  <div class="reader-shell home-shell">
    <header class="reader-header home-header">
      <NuxtLink class="reader-brand" to="/"><strong>墨页</strong><span>MINDBOOK</span></NuxtLink>
      <nav class="reader-nav" aria-label="读者导航">
        <NuxtLink :class="{ active: view === 'home' }" to="/">首页</NuxtLink>
        <NuxtLink :class="{ active: view === 'library' }" to="/library">书架</NuxtLink>
        <NuxtLink to="/rankings/hot">排行榜</NuxtLink>
        <NuxtLink to="/wallet">钱包</NuxtLink>
        <NuxtLink to="/notifications">通知</NuxtLink>
        <NuxtLink to="/support">客服</NuxtLink>
      </nav>
      <div class="reader-actions">
        <form class="search-box home-search" @submit.prevent="submitSearch"><span aria-hidden="true">⌕</span><input v-model="searchQuery" aria-label="搜索作品" placeholder="搜索书名、作者或关键词..." /></form>
        <NuxtLink class="icon-action home-bell" to="/notifications" aria-label="通知">♧</NuxtLink>
        <NuxtLink class="avatar home-avatar" to="/settings" aria-label="个人中心">{{ session ? '读' : '' }}</NuxtLink>
        <NuxtLink class="login-link home-settings" to="/settings">{{ session ? '个人中心' : '登录' }}</NuxtLink>
      </div>
    </header>

    <main class="home-main">
      <section class="home-hero">
        <div class="home-hero-copy"><h1>在故事里，找到下一页。</h1><p>从此刻，读见更大的世界，也读见更好的自己。</p><div class="home-hero-actions"><button class="home-primary" type="button" @click="startReading">开始阅读　→</button><NuxtLink class="home-secondary" to="/library?mode=discover">探索更多好书</NuxtLink></div></div>
      </section>

      <section class="home-filter-bar" aria-label="书库筛选">
        <form class="home-filter-form" @submit.prevent="applyFilters">
          <label><span>按题材分类</span><select name="category" :value="filters.category"><option value="">全部分类</option><option value="文学">文学</option><option value="小说">小说</option><option value="科幻">科幻</option><option value="散文">散文</option><option value="玄幻">玄幻</option></select></label>
          <label><span>频道</span><select name="channel" :value="filters.channel"><option value="">全部频道</option><option value="MALE">男频</option><option value="FEMALE">女频</option></select></label>
          <label><span>状态</span><select name="lifecycle" :value="filters.lifecycle"><option value="">全部状态</option><option value="SERIALIZING">连载</option><option value="COMPLETED">完本</option><option value="PAUSED">暂停</option></select></label>
          <label><span>商业</span><select name="commercial_policy" :value="filters.commercial_policy"><option value="">全部章节</option><option value="FREE">免费</option><option value="VIP">VIP</option></select></label>
          <button type="submit" class="home-reset">筛选</button><button type="button" class="home-reset" aria-label="重置筛选" @click="navigateTo('/')">重置</button>
        </form>
      </section>

      <section id="library" class="home-section home-recommend" aria-labelledby="today-title">
        <div class="home-section-heading"><div><h2 id="today-title">今天读什么</h2><p>为你精选优质内容，遇见值得一读的好书。</p></div><button class="home-link-button" type="button" aria-label="换一批推荐" @click="refreshRecommendations">换一批　⟳</button></div>
        <div v-if="catalogPending" class="catalog-state">正在加载公开作品...</div>
        <div v-else-if="catalogError" class="catalog-state error">作品目录暂时不可用，请稍后重试。</div>
        <div v-else-if="!displayRecommendations.length" class="catalog-state">暂无符合条件的作品。</div>
        <div v-else class="home-book-grid"><NuxtLink v-for="(book, index) in displayRecommendations" :key="book.id" class="home-book-card" :to="`/books/${book.id}`"><div class="home-cover" :class="coverClasses[index % coverClasses.length]"><span>{{ bookMark(book.title) }}</span></div><div class="home-book-copy"><div class="home-book-title"><strong>{{ book.title }}</strong><b>{{ book.lifecycle === 'COMPLETED' ? '完本' : book.lifecycle === 'PAUSED' ? '暂停' : '连载' }}</b></div><small>{{ bookAuthor(book) }}　|　{{ book.category || '文学' }}</small><p>{{ bookSynopsis(book) }}</p><div class="home-book-meta"><span v-for="tag in (book.tags || []).slice(0, 2)" :key="tag">{{ tag }}</span><em>查看详情</em></div></div></NuxtLink></div>
      </section>

      <section id="ranking" class="home-section home-ranking" aria-labelledby="ranking-title">
        <div class="home-section-heading"><div><h2 id="ranking-title">热度上升 <small>大家都在读的热门内容</small></h2></div><NuxtLink to="/rankings/hot">查看完整榜单　→</NuxtLink></div>
        <div v-if="rankingsPending" class="catalog-state">正在加载榜单...</div>
        <div v-else-if="rankingsError" class="catalog-state error">榜单暂时不可用，请稍后重试。</div>
        <div v-else-if="!displayRankings.length" class="catalog-state">暂无榜单数据。</div>
        <ol v-else class="home-ranking-grid"><li v-for="ranking in displayRankings" :key="ranking.book_id"><b>{{ String(ranking.rank).padStart(2, '0') }}</b><NuxtLink :to="`/books/${ranking.book_id}`">{{ bookTitle(ranking) }}</NuxtLink><small>热度 {{ ranking.score.toLocaleString() }}</small></li></ol>
      </section>
    </main>
    <footer class="reader-footer home-footer"><span>墨页 MINDBOOK</span><span>让阅读成为一种生活方式</span></footer>
  </div>
</template>
