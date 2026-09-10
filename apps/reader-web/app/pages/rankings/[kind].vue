<script setup lang="ts">
import { ref, watch } from 'vue'
import type { ReaderBookDetailResponseDto, ReaderRankingExplanationDto, ReaderRankingItemDto } from '@mindbooking/api-types'
import { bookDetailPath, rankingPath } from '../../../src/catalog'

const route = useRoute()
const runtimeConfig = useRuntimeConfig()
const kind = String(route.params.kind || 'hot')
const apiKind = ({ hot: 'ALGORITHM', recommend: 'RECOMMENDATION_SCORE', editorial: 'EDITORIAL' } as Record<string, string>)[kind] || 'ALGORITHM'
const labels: Record<string, string> = { hot: '热读', bestseller: '畅销', monthly: '月票', recommend: '推荐票', favorites: '收藏', gifts: '打赏', new: '新书', newcomer: '新人', completed: '完本', updates: '更新', free: '免费', member: '会员' }
const title = labels[kind] || '热读'
const explanationOpen = ref(false)
const explanation = ref<ReaderRankingExplanationDto | null>(null)
const { data: rankings, pending, error } = await useFetch<ReaderRankingItemDto[]>(rankingPath(apiKind, runtimeConfig.public.apiBaseUrl), { server: false, default: () => [] })
const titles = ref<Record<string, string>>({})
watch(rankings, (items) => { for (const item of items || []) if (!titles.value[item.book_id]) $fetch<ReaderBookDetailResponseDto>(bookDetailPath(item.book_id, runtimeConfig.public.apiBaseUrl)).then((book) => { titles.value[item.book_id] = book.title }).catch(() => undefined) }, { immediate: true })
async function openExplanation() {
  explanationOpen.value = true
  try { explanation.value = await $fetch(`${runtimeConfig.public.apiBaseUrl}/api/v1/rankings/${encodeURIComponent(kind)}/explanation`) } catch { explanation.value = null }
}
</script>

<template>
  <div class="reader-shell"><header class="reader-header"><NuxtLink class="reader-brand" to="/"><strong>墨页</strong><span>MINDBOOK</span></NuxtLink><nav class="reader-nav" aria-label="读者导航"><NuxtLink to="/">首页</NuxtLink><NuxtLink to="/library">书架</NuxtLink><NuxtLink class="active" to="/rankings/hot">排行榜</NuxtLink><NuxtLink to="/wallet">钱包</NuxtLink><NuxtLink to="/notifications">通知</NuxtLink><NuxtLink to="/support">客服</NuxtLink></nav><NuxtLink class="login-link" to="/settings">账户</NuxtLink></header>
    <main class="route-page-main"><section class="route-hero route-hero-inline"><div><p class="eyebrow">RANKING SNAPSHOT</p><h1>{{ title }}榜</h1><p>榜单数据来自已发布的 Ranking Snapshot。</p></div><button class="quiet-action" type="button" @click="openExplanation">榜单说明</button></section><nav class="ranking-tabs" aria-label="榜单类型"><NuxtLink v-for="(label, value) in labels" :key="value" :to="`/rankings/${value}`" :class="{ active: value === kind }">{{ label }}</NuxtLink></nav><section class="route-card"><div v-if="pending" class="catalog-state">正在加载榜单...</div><div v-else-if="error" class="catalog-state error">榜单暂时不可用，请稍后重试。</div><div v-else-if="!rankings?.length" class="catalog-state">暂无榜单数据。</div><ol v-else class="ranking-list"><li v-for="item in rankings" :key="item.book_id"><b>{{ String(item.rank).padStart(2, '0') }}</b><NuxtLink :to="`/books/${item.book_id}`">{{ titles[item.book_id] || item.book_id }}</NuxtLink><span>热度 {{ item.score.toLocaleString() }}</span></li></ol></section></main><div v-if="explanationOpen" class="modal-backdrop" role="dialog" aria-modal="true" aria-labelledby="ranking-explanation-title"><div class="modal-card"><h2 id="ranking-explanation-title">{{ explanation?.title || `${title}榜说明` }}</h2><p v-if="explanation">{{ explanation.rule }}，更新周期：{{ explanation.update_period }}，数据时间：{{ explanation.data_time }}。</p><p v-else>正在读取榜单规则...</p><button class="primary-button" type="button" @click="explanationOpen = false">知道了</button></div></div></div>
</template>
