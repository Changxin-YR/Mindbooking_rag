<script setup lang="ts">
import { ref } from 'vue'
import type { ReaderSearchResponseDto } from '@mindbooking/api-types'
import { searchPath } from '../../src/catalog'

const route = useRoute()
const router = useRouter()
const runtimeConfig = useRuntimeConfig()
const q = ref(String(route.query.q || ''))
const filters = ref({ category: String(route.query.category || ''), channel: String(route.query.channel || ''), status: String(route.query.status || ''), tag: String(route.query.tag || '') })
const { data, pending, error } = await useFetch<ReaderSearchResponseDto>(() => searchPath({ q: q.value, ...filters.value }, runtimeConfig.public.apiBaseUrl), { server: false, default: () => ({ items: [], total: 0, page: 1, page_size: 20, degraded: false }) })

function submit() {
  const query: Record<string, string> = {}
  if (q.value.trim()) query.q = q.value.trim()
  for (const [key, value] of Object.entries(filters.value)) if (value) query[key] = value
  router.push({ path: '/search', query })
}
function clear() { q.value = ''; filters.value = { category: '', channel: '', status: '', tag: '' }; submit() }
</script>

<template>
  <div class="reader-shell">
    <header class="reader-header"><NuxtLink class="reader-brand" to="/"><strong>墨页</strong><span>MINDBOOK</span></NuxtLink><nav class="reader-nav" aria-label="读者导航"><NuxtLink to="/">首页</NuxtLink><NuxtLink to="/library">书架</NuxtLink><NuxtLink to="/rankings/hot">排行榜</NuxtLink><NuxtLink to="/wallet">钱包</NuxtLink><NuxtLink to="/notifications">通知</NuxtLink><NuxtLink to="/support">客服</NuxtLink></nav><NuxtLink class="login-link" to="/settings">账户</NuxtLink></header>
    <main class="route-page-main"><section class="route-hero"><p class="eyebrow">SEARCH</p><h1>搜索作品</h1><p>搜索书名、作者、标签与简介，结果来自当前 Reader 内容索引。</p></section>
      <section class="route-card"><form class="support-form" @submit.prevent="submit"><label>关键词<input v-model="q" name="q" aria-label="搜索关键词" placeholder="搜索书名、作者或关键词" /></label><div class="home-filter-form"><label><span>频道</span><select v-model="filters.channel"><option value="">全部频道</option><option value="MALE">男频</option><option value="FEMALE">女频</option></select></label><label><span>分类</span><input v-model="filters.category" placeholder="例如：玄幻" /></label><label><span>状态</span><select v-model="filters.status"><option value="">全部状态</option><option value="SERIALIZING">连载</option><option value="COMPLETED">完本</option></select></label><label><span>标签</span><input v-model="filters.tag" placeholder="例如：系统" /></label></div><div class="detail-actions"><button class="primary-button" type="submit">搜索</button><button class="quiet-action" type="button" @click="clear">清空</button></div></form></section>
      <section class="route-card"><div v-if="pending" class="catalog-state">正在搜索...</div><div v-else-if="error" class="catalog-state error">搜索暂时不可用，请稍后重试。</div><div v-else-if="!data?.items.length" class="catalog-state">暂无结果</div><ul v-else class="shelf-list"><li v-for="item in data.items" :key="item.book_id"><div class="book-cover cover-ink">{{ item.title.slice(0, 4) }}</div><div><strong>{{ item.title }}</strong><span>{{ item.author_name }} · {{ item.category || '未分类' }}</span><p>{{ item.synopsis || '暂无简介' }}</p><small>{{ item.tags.join(' · ') }}</small></div><NuxtLink :to="`/books/${item.book_id}`">查看　→</NuxtLink></li></ul></section>
    </main>
  </div>
</template>
