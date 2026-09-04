<script setup lang="ts">
import type { ReaderBookDetailResponseDto } from '@mindbooking/api-types'
import { bookDetailPath } from '../../../src/catalog'

const route = useRoute()
const runtimeConfig = useRuntimeConfig()
const accountId = 'acct-demo'
const bookId = String(route.params.id)
const { data: book, pending, error } = await useFetch<ReaderBookDetailResponseDto>(
  bookDetailPath(bookId, runtimeConfig.public.apiBaseUrl),
  { server: false },
)
const notice = ref('')
const rating = reactive({ overall_score: 5, plot_score: 5, character_score: 5, writing_score: 5, update_score: 5, eligible_words: 1000 })

async function submitRating() {
  if (!book.value) return
  try {
    await $fetch(`${runtimeConfig.public.apiBaseUrl}/api/v1/books/${encodeURIComponent(book.value.id)}/ratings`, { method: 'POST', body: { account_id: accountId, ...rating } })
    notice.value = '评分已提交'
  } catch {
    notice.value = '当前阅读量未达到评分条件'
  }
}

async function followAuthor() {
  if (!book.value) return
  try {
    await $fetch(`${runtimeConfig.public.apiBaseUrl}/api/v1/social/follows`, { method: 'POST', body: { account_id: accountId, target_type: 'AUTHOR', target_id: book.value.author_id } })
    notice.value = '已关注作者'
  } catch {
    notice.value = '关注暂时不可用'
  }
}

async function addToShelf() {
  if (!book.value) return
  try {
    await $fetch(`${runtimeConfig.public.apiBaseUrl}/api/v1/books/${encodeURIComponent(book.value.id)}/bookshelf`, { method: 'POST', body: { account_id: accountId, group_name: 'default' } })
    notice.value = '已加入书架'
  } catch {
    notice.value = '加入书架暂时不可用'
  }
}
</script>

<template>
  <div class="reader-shell detail-shell">
    <header class="reader-header">
      <NuxtLink class="reader-brand" to="/">墨页 <span>MindBook</span></NuxtLink>
      <nav class="reader-nav" aria-label="读者导航">
        <NuxtLink to="/">首页</NuxtLink><NuxtLink to="/library">书架</NuxtLink><NuxtLink to="/wallet">钱包</NuxtLink><NuxtLink to="/support">客服</NuxtLink>
      </nav>
      <NuxtLink class="login-link" to="/settings">阅读设置</NuxtLink>
    </header>

    <main class="reader-detail-main">
      <div v-if="pending" class="catalog-state">正在加载作品详情...</div>
      <div v-else-if="error || !book" class="catalog-state error">作品不存在或暂时不可用。</div>
      <template v-else>
        <section class="detail-intro">
          <div class="detail-cover" aria-hidden="true">{{ book.title.slice(0, 4) }}</div>
          <div class="detail-copy"><p class="eyebrow">{{ book.channel }} · {{ book.category || '未分类' }}</p><h1>{{ book.title }}</h1><p>{{ book.synopsis || '作者还没有留下简介。' }}</p><div class="detail-meta"><span>{{ book.lifecycle === 'COMPLETED' ? '完本' : '连载中' }}</span><span>{{ book.chapters.length }} 章已发布</span><span v-for="tag in book.tags" :key="tag">#{{ tag }}</span></div><div class="detail-actions"><button class="primary-button" type="button" :disabled="!book.chapters.length" @click="book.chapters.length && navigateTo(`/read/${book.id}/${book.chapters[0].id}`)">开始阅读</button><button class="quiet-action" type="button" @click="addToShelf">加入书架</button><button class="quiet-action" type="button" @click="followAuthor">关注作者</button></div><p v-if="notice" class="action-notice" role="status">{{ notice }}</p></div>
        </section>

        <section class="reader-section detail-section" aria-labelledby="chapter-title">
          <div class="section-heading"><div><p class="eyebrow">Published versions</p><h2 id="chapter-title">章节目录</h2></div><span>{{ book.chapters.length }} 章</span></div>
          <ol class="chapter-list"><li v-for="chapter in book.chapters" :key="chapter.id"><span>第 {{ chapter.number }} 章</span><strong>{{ chapter.title }}</strong><small>{{ chapter.commercial_policy === 'FREE' ? '免费' : 'VIP' }}</small><NuxtLink :to="`/read/${book.id}/${chapter.id}`" aria-label="打开章节">打开</NuxtLink></li></ol>
        </section>

        <section class="reader-section rating-panel" aria-labelledby="rating-title">
          <div><p class="eyebrow">读完再评分</p><h2 id="rating-title">留下你的阅读感受</h2><p>评分资格以有效阅读字数计算，会员和粉丝等级彼此独立。</p></div>
          <form class="rating-form" @submit.prevent="submitRating"><label>总分 <input v-model.number="rating.overall_score" type="number" min="1" max="5" /></label><label>剧情 <input v-model.number="rating.plot_score" type="number" min="1" max="5" /></label><label>角色 <input v-model.number="rating.character_score" type="number" min="1" max="5" /></label><button class="primary-button" type="submit">提交评分</button></form>
        </section>
      </template>
    </main>
    <footer class="reader-footer"><span>墨页 MindBook</span><span>阅读记录由账号同步</span></footer>
  </div>
</template>
