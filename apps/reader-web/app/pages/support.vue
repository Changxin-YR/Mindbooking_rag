<script setup lang="ts">
import type { SupportTicketDto } from '@mindbooking/api-types'
import { buildRequestHeaders, loadSession } from '../../src/session'

const category = ref('READING')
const categoryLabels: Record<string, string> = { READING: '阅读', RECHARGE: '充值', MEMBERSHIP: '会员', APPEAL: '举报/处罚申诉' }
const body = ref('')
const notice = ref('')
const session = loadSession()
const runtimeConfig = useRuntimeConfig()
const tickets = ref<SupportTicketDto[]>([])
const ticketsLoading = ref(false)
function submitSearch(event: Event) {
  const input = (event.currentTarget as HTMLFormElement).elements.namedItem('q') as HTMLInputElement | null
  navigateTo(input?.value.trim() ? `/search?q=${encodeURIComponent(input.value.trim())}` : '/search')
}
async function loadTickets() {
  if (!session) return
  ticketsLoading.value = true
  try { tickets.value = await $fetch(`${runtimeConfig.public.apiBaseUrl}/api/v1/support/tickets`, { query: { account_id: session.accountId }, headers: buildRequestHeaders(session.token) }) } catch { tickets.value = [] } finally { ticketsLoading.value = false }
}
async function submit() {
  if (!session) {
    notice.value = '请先登录后提交工单'
    return
  }
  try {
    const ticket = await $fetch<SupportTicketDto>(`${runtimeConfig.public.apiBaseUrl}/api/v1/support/tickets`, { method: 'POST', headers: buildRequestHeaders(session.token), body: { account_id: session.accountId, category: category.value, priority: 'P2', description: body.value.trim() } })
    body.value = ''
    notice.value = `工单提交成功，编号：${ticket.id}`
    await loadTickets()
  } catch { notice.value = '提交失败，请稍后再试。' }
}
onMounted(loadTickets)
</script>

<template><div class="reader-shell"><header class="reader-header"><NuxtLink class="reader-brand" to="/"><strong>墨页</strong><span>MINDBOOK</span></NuxtLink><nav class="reader-nav"><NuxtLink to="/">首页</NuxtLink><NuxtLink to="/library">书架</NuxtLink><NuxtLink to="/rankings/hot">排行榜</NuxtLink><NuxtLink to="/wallet">钱包</NuxtLink><NuxtLink to="/notifications">通知</NuxtLink><NuxtLink class="active" to="/support">客服</NuxtLink></nav><div class="reader-actions"><form class="search-box" @submit.prevent="submitSearch"><input name="q" placeholder="搜索书名、作者或关键词..." aria-label="搜索作品" /><button type="submit" aria-label="搜索">⌕</button></form><NuxtLink class="icon-action" to="/notifications" aria-label="通知">♧</NuxtLink><NuxtLink class="avatar" to="/settings" aria-label="个人中心">读</NuxtLink><NuxtLink class="login-link" to="/settings">设置</NuxtLink></div></header><main class="route-page-main support-page"><section class="support-layout"><div class="support-intro"><p class="eyebrow">SUPPORT</p><h1>联系支持</h1><p>充值、权益、阅读和社区问题都可以提交工单。<br />我们会尽快回复，并为你提供帮助。</p><span class="support-rule" /></div><form v-if="session" class="support-form support-form-large" @submit.prevent="submit"><label>问题分类<select v-model="category"><option value="READING">阅读</option><option value="RECHARGE">充值</option><option value="MEMBERSHIP">会员</option><option value="APPEAL">举报/处罚申诉</option></select></label><p class="selected-category" role="status">问题分类：{{ categoryLabels[category] }}</p><label>问题描述<textarea v-model="body" required minlength="2" placeholder="请描述遇到的问题" /></label><button class="primary-button" type="submit" :disabled="!category || body.trim().length < 2">提交工单　→</button><p v-if="notice" role="status">{{ notice }}</p></form><div v-else class="catalog-state support-login-state">登录后提交工单。<br /><NuxtLink class="text-button" to="/settings">去登录</NuxtLink></div></section><section v-if="session" class="route-card support-tickets"><h2>我的工单</h2><p v-if="ticketsLoading">正在读取工单...</p><p v-else-if="!tickets.length">暂无工单记录。</p><ul v-else class="shelf-list"><li v-for="ticket in tickets" :key="ticket.id"><strong>{{ ticket.id }}</strong><span>{{ categoryLabels[ticket.category] || ticket.category }} · {{ ticket.status }}</span><NuxtLink :to="`/support?ticket=${ticket.id}`">查看　→</NuxtLink></li></ul></section></main></div></template>
