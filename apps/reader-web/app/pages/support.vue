<script setup lang="ts">
const category = ref('阅读')
const body = ref('')
const notice = ref('')
const runtimeConfig = useRuntimeConfig()
async function submit() {
  try {
    await $fetch(`${runtimeConfig.public.apiBaseUrl}/api/v1/support/tickets`, { method: 'POST', body: { account_id: 'acct-demo', category: category.value, priority: 'P2', description: body.value } })
    body.value = ''
    notice.value = '工单已提交，客服会在站内通知中回复。'
  } catch { notice.value = '提交失败，请稍后再试。' }
}
</script>

<template><div class="reader-shell"><header class="reader-header"><NuxtLink class="reader-brand" to="/">墨页 <span>MindBook</span></NuxtLink><nav class="reader-nav"><NuxtLink to="/">首页</NuxtLink><NuxtLink to="/library">书架</NuxtLink><NuxtLink to="/wallet">钱包</NuxtLink><NuxtLink class="active" to="/support">客服</NuxtLink></nav><NuxtLink class="login-link" to="/settings">设置</NuxtLink></header><main class="reader-detail-main"><section class="rating-panel"><div><p class="eyebrow">Support</p><h1>联系支持</h1><p>充值、权益、阅读和社区问题都可以提交工单。</p></div><form class="support-form" @submit.prevent="submit"><label>问题分类<select v-model="category"><option>阅读</option><option>充值</option><option>会员</option><option>举报/处罚申诉</option></select></label><label>问题描述<textarea v-model="body" required minlength="2" placeholder="请描述遇到的问题" /></label><button class="primary-button" type="submit">提交工单</button><p v-if="notice" role="status">{{ notice }}</p></form></section></main></div></template>
