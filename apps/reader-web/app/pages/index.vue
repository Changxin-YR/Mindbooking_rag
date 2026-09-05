<script setup lang="ts">
import { computed } from 'vue'
import type { ReaderCatalogResponseDto } from '@mindbooking/api-types'
import { catalogPath } from '../../src/catalog'
import { parseShellState } from '../../src/shell-state'
import { loadSession } from '../../src/session'

const route = useRoute()
const state = computed(() => parseShellState(route.query.state))
const view = computed(() => String(route.query.view || 'home'))
const filters = computed(() => ({ q: String(route.query.q || '') }))
const runtimeConfig = useRuntimeConfig()
const session = loadSession()
const { data: catalog, pending: catalogPending, error: catalogError } = await useFetch<ReaderCatalogResponseDto>(
  catalogPath(filters.value, runtimeConfig.public.apiBaseUrl),
  { server: false, default: () => ({ items: [], total: 0 }) },
)
const { data: rankings, pending: rankingsPending, error: rankingsError } = await useFetch<Array<{ book_id: string; score: number; rank: number }>>(
  `${runtimeConfig.public.apiBaseUrl}/api/v1/rankings`,
  { server: false, default: () => [] },
)
</script>

<template>
  <div class="reader-shell">
    <header class="reader-header">
      <NuxtLink class="reader-brand" to="/">墨页 <span>MindBook</span></NuxtLink>
      <nav class="reader-nav" aria-label="读者导航">
        <NuxtLink :class="{ active: view === 'home' }" to="/">首页</NuxtLink>
        <NuxtLink :class="{ active: view === 'library' }" to="/?view=library#library">书库</NuxtLink>
        <NuxtLink :class="{ active: view === 'ranking' }" to="/?view=ranking#ranking">排行榜</NuxtLink>
        <NuxtLink :class="{ active: view === 'finished' }" to="/?view=finished#library">完本</NuxtLink>
        <NuxtLink :class="{ active: view === 'free' }" to="/?view=free#library">免费</NuxtLink>
      </nav>
      <div class="reader-actions">
        <form class="search-box" action="/" method="get">
          <input name="q" aria-label="搜索作品" placeholder="搜索书名或作者" />
          <button type="submit">搜索</button>
        </form>
        <a class="login-link" href="?state=unauthorized">登录</a>
      </div>
    </header>

    <main v-if="state === 'ready'" class="reader-main">
      <section class="reader-hero" aria-labelledby="hero-title">
        <div>
          <p class="eyebrow">今日精选 · 读一本好故事</p>
          <h1 id="hero-title">在故事里，找到下一页。</h1>
          <p class="hero-copy">从连载、完本和免费作品中，继续你的阅读。</p>
          <div class="hero-actions"><a class="primary-button" href="#library">进入书库</a><a class="quiet-button" href="#free">看看免费作品</a></div>
        </div>
        <div class="hero-note" aria-label="阅读提示"><span>本周热读</span><strong>{{ catalog?.items[0]?.title ? `《${catalog.items[0].title}》` : '等待作品入库' }}</strong><small>{{ catalog?.items[0] ? `${catalog.items[0].channel} · ${catalog.items[0].lifecycle === 'COMPLETED' ? '完本' : '连载中'}` : '公开作品由内容服务提供' }}</small></div>
      </section>

      <section v-if="view !== 'home'" class="reader-section route-section" aria-labelledby="route-title">
        <div class="section-heading"><div><p class="eyebrow">真实业务入口</p><h2 id="route-title">{{ view === 'library' ? '书库' : view === 'ranking' ? '排行榜' : view === 'finished' ? '完本作品' : '免费阅读' }}</h2></div><a href="/">回到首页 →</a></div>
        <div class="route-grid"><article class="route-item"><strong>{{ view === 'ranking' ? '算法榜单快照' : '今日可读作品' }}</strong><span>{{ view === 'free' ? '无需购买，打开即读' : '内容、状态与访问权限由后端返回' }}</span></article><article class="route-item"><strong>{{ view === 'finished' ? '完整故事' : '个性化设置' }}</strong><span>{{ view === 'ranking' ? '编辑排序与算法分数分离' : '书架、进度和通知可同步' }}</span></article></div>
      </section>

      <section class="reader-section" aria-labelledby="continue-title">
        <div class="section-heading"><div><p class="eyebrow">只为你保留</p><h2 id="continue-title">继续阅读</h2></div><NuxtLink :to="session ? '/library' : '/settings'">{{ session ? '打开书架 →' : '登录同步书架 →' }}</NuxtLink></div>
        <div class="catalog-state">{{ session ? '当前暂无可继续阅读的同步进度。' : '登录后同步书架、阅读进度和互动记录。' }}</div>
      </section>

      <section id="library" class="reader-section" aria-labelledby="featured-title">
        <div class="section-heading"><div><p class="eyebrow">编辑精选</p><h2 id="featured-title">今天读什么</h2></div><a href="#library">查看全部 →</a></div>
        <ClientOnly fallback-tag="div" fallback="正在加载公开作品...">
          <div v-if="catalogPending" class="catalog-state" aria-live="polite">正在加载公开作品...</div>
          <div v-else-if="catalogError" class="catalog-state error" role="alert">作品目录暂时不可用，请稍后重试。</div>
          <div v-else-if="!catalog?.items.length" class="catalog-state">暂无符合条件的公开作品。</div>
          <div v-else class="book-grid"><NuxtLink v-for="book in catalog.items" :key="book.id" class="book-card" :to="`/books/${book.id}`"><div class="book-mark mark-teal">{{ book.title.slice(0, 4) }}</div><div><h3>《{{ book.title }}》</h3><p>{{ book.channel }} · {{ book.category || '未分类' }}</p><span class="tag">{{ book.lifecycle === 'COMPLETED' ? '完本' : '连载中' }}</span></div></NuxtLink></div>
        </ClientOnly>
      </section>

      <section id="ranking" class="reader-section ranking-section" aria-labelledby="ranking-title">
        <div class="section-heading"><div><p class="eyebrow">实时榜单</p><h2 id="ranking-title">热读上升</h2></div><a href="#ranking">完整榜单 →</a></div>
        <div v-if="rankingsPending" class="catalog-state">正在加载榜单...</div><div v-else-if="rankingsError" class="catalog-state error">榜单暂时不可用。</div><div v-else-if="!rankings?.length" class="catalog-state">暂无已发布榜单。</div><ol v-else class="ranking-list"><li v-for="ranking in rankings" :key="ranking.book_id"><b>{{ String(ranking.rank).padStart(2, '0') }}</b><span>{{ ranking.book_id }}</span><small>算法分 {{ ranking.score }}</small></li></ol>
      </section>
    </main>

    <main v-else class="reader-state" :data-state="state" aria-live="polite">
      <div v-if="state === 'loading'" class="state-card"><div class="spinner" /><h1>正在打开书库</h1><p>作品内容马上就到。</p></div>
      <div v-else-if="state === 'empty'" class="state-card"><div class="state-symbol">○</div><h1>这里还没有作品</h1><p>换个筛选条件，再试试看。</p><a class="primary-button" href="?state=ready">回到首页</a></div>
      <div v-else-if="state === 'error'" class="state-card"><div class="state-symbol">!</div><h1>书库暂时没有响应</h1><p>请稍后重试，阅读进度不会丢失。</p><a class="primary-button" href="?state=ready">重新加载</a></div>
      <div v-else class="state-card"><div class="state-symbol">↗</div><h1>登录后继续阅读</h1><p>登录即可同步书架、进度和互动记录。</p><a class="primary-button" href="?state=ready">返回游客首页</a></div>
    </main>

    <footer class="reader-footer"><span>墨页 MindBook</span><span>内容 · 社区 · 阅读</span></footer>
  </div>
</template>
