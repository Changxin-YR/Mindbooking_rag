<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import type { ReaderBookDetailResponseDto, ReaderCatalogResponseDto, ReaderShelfEntryDto } from '@mindbooking/api-types'
import { bookDetailPath, catalogPath } from '../../src/catalog'
import { buildRequestHeaders, loadSession } from '../../src/session'

const route = useRoute()
const router = useRouter()
const runtimeConfig = useRuntimeConfig()
const apiBase = runtimeConfig.public.apiBaseUrl
const session = loadSession()
const searchQuery = ref(String(route.query.q || ''))
const filters = computed(() => ({
  q: String(route.query.q || ''),
  channel: String(route.query.channel || ''),
  category: String(route.query.category || ''),
  lifecycle: String(route.query.lifecycle || ''),
  commercial_policy: String(route.query.commercial_policy || ''),
}))
const isDiscover = computed(() => route.query.mode === 'discover')

const { data: shelf, pending: shelfPending, error: shelfError } = await useFetch<ReaderShelfEntryDto[]>(
  `${apiBase}/api/v1/bookshelf`,
  { query: { account_id: session?.accountId || '' }, headers: session ? buildRequestHeaders(session.token) : undefined, immediate: Boolean(session), server: false, default: () => [] },
)
const { data: catalog, pending: catalogPending, error: catalogError } = await useFetch<ReaderCatalogResponseDto>(
  () => catalogPath(filters.value, apiBase),
  { server: false, default: () => ({ items: [], total: 0 }) },
)
const shelfDetails = ref<Record<string, ReaderBookDetailResponseDto>>({})
const detailLoading = ref<Record<string, boolean>>({})

watch(shelf, (items) => {
  for (const item of (items || [])) {
    if (shelfDetails.value[item.book_id] || detailLoading.value[item.book_id]) continue
    detailLoading.value[item.book_id] = true
    $fetch<ReaderBookDetailResponseDto>(bookDetailPath(item.book_id, apiBase)).then((book) => {
      shelfDetails.value[item.book_id] = book
    }).catch(() => undefined).finally(() => {
      detailLoading.value[item.book_id] = false
    })
  }
}, { immediate: true })

function submitSearch() {
  const q = searchQuery.value.trim()
  navigateTo(q ? `/search?q=${encodeURIComponent(q)}` : '/search')
}

function applyFilters(event: Event) {
  const form = event.currentTarget as HTMLFormElement
  const query: Record<string, string> = { mode: 'discover' }
  for (const [key, value] of new FormData(form).entries()) {
    if (typeof value === 'string' && value.trim()) query[key] = value
  }
  router.push({ path: '/library', query })
}

function clearFilters() {
  router.push({ path: '/library', query: { mode: 'discover' } })
}
</script>

<template>
  <div class="reader-shell">
    <header class="reader-header">
      <NuxtLink class="reader-brand" to="/"><strong>墨页</strong><span>MINDBOOK</span></NuxtLink>
      <nav class="reader-nav" aria-label="读者导航"><NuxtLink to="/">首页</NuxtLink><NuxtLink class="active" to="/library">书架</NuxtLink><NuxtLink to="/rankings/hot">排行榜</NuxtLink><NuxtLink to="/wallet">钱包</NuxtLink><NuxtLink to="/notifications">通知</NuxtLink><NuxtLink to="/support">客服</NuxtLink></nav>
      <div class="reader-actions"><form class="search-box" @submit.prevent="submitSearch"><input v-model="searchQuery" placeholder="搜索书名、作者或关键词..." aria-label="搜索作品" /><button type="submit" aria-label="搜索">⌕</button></form><NuxtLink class="icon-action" to="/notifications" aria-label="通知">♧</NuxtLink><NuxtLink class="avatar" to="/settings" aria-label="个人中心">{{ session ? '读' : '' }}</NuxtLink><NuxtLink class="login-link" to="/settings">{{ session ? '个人中心' : '登录' }}</NuxtLink></div>
    </header>

    <main class="route-page-main library-page">
      <section class="route-hero route-hero-inline"><div><p class="eyebrow">YOUR SHELF</p><h1>我的书架</h1><p>在文字的陪伴里，遇见更大的世界。</p></div><NuxtLink class="primary-button" to="/library?mode=discover">发现好书</NuxtLink></section>
      <section class="route-card shelf-card"><div class="route-card-heading"><h2>我的书架 <span>{{ shelf?.length || 0 }} 本作品</span></h2><NuxtLink class="text-button" to="/library?mode=discover">去书库</NuxtLink></div><div v-if="!session" class="catalog-state">登录后同步你的书架。<br /><NuxtLink class="text-button" to="/settings">去登录</NuxtLink></div><div v-else-if="shelfPending" class="catalog-state">正在同步书架...</div><div v-else-if="shelfError" class="catalog-state error">书架暂时不可用，请稍后重试。</div><div v-else-if="!shelf?.length" class="catalog-state">书架还是空的，去发现好书吧。<br /><NuxtLink class="text-button" to="/library?mode=discover">浏览书库</NuxtLink></div><ul v-else class="shelf-list"><li v-for="item in shelf" :key="item.book_id"><div class="book-cover cover-ink">{{ shelfDetails[item.book_id]?.title?.slice(0, 4) || '墨页' }}</div><div><strong>{{ shelfDetails[item.book_id]?.title || (detailLoading[item.book_id] ? '正在读取作品...' : '作品暂不可用') }}</strong><span>{{ item.group_name === 'default' ? '默认书架' : item.group_name }}</span><p>{{ shelfDetails[item.book_id]?.synopsis || (shelfDetails[item.book_id] ? '暂无简介' : '作品信息加载失败，请稍后重试。') }}</p></div><NuxtLink :to="`/books/${item.book_id}`">查看　→</NuxtLink></li></ul></section>

      <section v-if="isDiscover" class="route-card shelf-card discover-card"><div class="route-card-heading"><div><p class="eyebrow">DISCOVER</p><h2>书库</h2></div><span>{{ catalog?.total || 0 }} 部作品</span></div><form class="home-filter-form" @submit.prevent="applyFilters"><label><span>题材</span><select name="category" :value="filters.category"><option value="">全部分类</option><option value="文学">文学</option><option value="小说">小说</option><option value="科幻">科幻</option><option value="散文">散文</option><option value="玄幻">玄幻</option></select></label><label><span>频道</span><select name="channel" :value="filters.channel"><option value="">全部频道</option><option value="MALE">男频</option><option value="FEMALE">女频</option></select></label><label><span>状态</span><select name="lifecycle" :value="filters.lifecycle"><option value="">全部状态</option><option value="SERIALIZING">连载</option><option value="COMPLETED">完本</option><option value="PAUSED">暂停</option></select></label><label><span>商业</span><select name="commercial_policy" :value="filters.commercial_policy"><option value="">全部章节</option><option value="FREE">免费</option><option value="VIP">VIP</option></select></label><button class="home-reset" type="submit">筛选</button><button class="home-reset" type="button" @click="clearFilters">清空</button></form><div v-if="catalogPending" class="catalog-state">正在加载书库...</div><div v-else-if="catalogError" class="catalog-state error">书库暂时不可用，请稍后重试。</div><div v-else-if="!catalog?.items?.length" class="catalog-state">暂无符合条件的作品。</div><div v-else class="home-book-grid discover-grid"><NuxtLink v-for="book in catalog.items" :key="book.id" class="home-book-card" :to="`/books/${book.id}`"><div class="home-cover cover-mist"><span>{{ book.title.slice(0, 4) }}</span></div><div class="home-book-copy"><div class="home-book-title"><strong>{{ book.title }}</strong><b>{{ book.lifecycle === 'COMPLETED' ? '完本' : book.lifecycle === 'PAUSED' ? '暂停' : '连载' }}</b></div><small>{{ book.category || '未分类' }} · {{ book.channel === 'FEMALE' ? '女频' : '男频' }}</small><p>{{ book.synopsis || '暂无简介' }}</p><div class="home-book-meta"><span v-for="tag in book.tags.slice(0, 2)" :key="tag">{{ tag }}</span><em>查看详情</em></div></div></NuxtLink></div></section>
    </main>
  </div>
</template>
