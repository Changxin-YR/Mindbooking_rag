<script setup lang="ts">
const runtimeConfig = useRuntimeConfig()
const accountId = 'acct-demo'
const { data: shelf, pending, error } = await useFetch<Array<{ book_id: string; group_name: string }>>(`${runtimeConfig.public.apiBaseUrl}/api/v1/bookshelf`, { query: { account_id: accountId }, server: false, default: () => [] })
</script>

<template>
  <div class="reader-shell"><header class="reader-header"><NuxtLink class="reader-brand" to="/">墨页 <span>MindBook</span></NuxtLink><nav class="reader-nav"><NuxtLink to="/">首页</NuxtLink><NuxtLink class="active" to="/library">书架</NuxtLink><NuxtLink to="/wallet">钱包</NuxtLink><NuxtLink to="/support">客服</NuxtLink></nav><NuxtLink class="login-link" to="/settings">设置</NuxtLink></header><main class="reader-detail-main"><section class="detail-section"><p class="eyebrow">Your shelf</p><h1>我的书架</h1><div v-if="pending" class="catalog-state">正在同步书架...</div><div v-else-if="error" class="catalog-state error">书架暂时不可用。</div><div v-else-if="!shelf?.length" class="catalog-state">还没有加入书架的作品。</div><ul v-else class="chapter-list"><li v-for="item in shelf" :key="item.book_id"><strong>{{ item.book_id }}</strong><span>{{ item.group_name }}</span><NuxtLink :to="`/books/${item.book_id}`">查看</NuxtLink></li></ul></section></main></div>
</template>
