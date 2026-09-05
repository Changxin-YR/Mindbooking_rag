<script setup lang="ts">
import type { ReaderChapterResponseDto, ReaderProgressDto } from '@mindbooking/api-types'
import { chapterPath, progressPath } from '../../../../src/catalog'
import { buildRequestHeaders, loadSession } from '../../../../src/session'

const route = useRoute()
const runtimeConfig = useRuntimeConfig()
const session = loadSession()
const accountId = session?.accountId ?? ''
const headers = session ? buildRequestHeaders(session.token) : undefined
const bookId = String(route.params.bookId)
const chapterId = String(route.params.chapterId)
const { data: chapter, pending, error } = await useFetch<ReaderChapterResponseDto>(chapterPath(bookId, chapterId, runtimeConfig.public.apiBaseUrl), { headers, server: false })
const { data: progress } = await useFetch<ReaderProgressDto>(progressPath(bookId, runtimeConfig.public.apiBaseUrl), { query: { account_id: accountId }, headers, immediate: Boolean(session), server: false })
const saved = ref(false)
async function saveProgress(position: number) {
  if (!session) return
  try {
    progress.value = await $fetch<ReaderProgressDto>(progressPath(bookId, runtimeConfig.public.apiBaseUrl), { method: 'PUT', query: { account_id: accountId }, headers, body: { chapter_id: chapterId, chapter_number: chapter.value?.number || 1, position, expected_revision: progress.value?.revision ?? 0, session_id: 'reader-web' } })
    saved.value = true
  } catch {
    try { progress.value = await $fetch<ReaderProgressDto>(progressPath(bookId, runtimeConfig.public.apiBaseUrl), { query: { account_id: accountId }, headers }) } catch { /* keep the current error state */ }
    saved.value = false
  }
}
</script>

<template>
  <div class="reader-shell reading-shell">
    <header class="reader-header reading-header"><NuxtLink class="reader-brand" to="/">墨页 <span>MindBook</span></NuxtLink><NuxtLink class="back-link" :to="`/books/${bookId}`">返回作品详情</NuxtLink><NuxtLink class="login-link" to="/settings">阅读设置</NuxtLink></header>
    <main class="reading-main">
      <div v-if="pending" class="catalog-state">正在打开章节...</div>
      <div v-else-if="error || !chapter" class="catalog-state error">章节暂时无法阅读，请返回作品详情。</div>
      <article v-else class="reading-article"><p class="eyebrow">{{ chapter.access }} · {{ chapter.commercial_policy }}</p><h1>{{ chapter.title }}</h1><div class="reading-content">{{ chapter.content }}</div><div class="reading-actions"><button class="primary-button" type="button" :disabled="!session" @click="saveProgress(chapter.content.length)">{{ session ? '保存阅读进度' : '登录后保存进度' }}</button><span v-if="saved" role="status">已保存</span></div></article>
    </main>
  </div>
</template>
