<script setup lang="ts">
import { buildRequestHeaders, loadSession, type ReaderSession } from '../../src/session'

type Notification = {
  id: string
  category: 'SYSTEM' | 'SECURITY' | 'MARKETING'
  priority: 'NORMAL' | 'P0'
  channels: string[]
  is_read: boolean
}

const runtimeConfig = useRuntimeConfig()
const session = ref<ReaderSession | null>(loadSession())
const notifications = ref<Notification[]>([])
const unreadCount = ref(0)
const pending = ref(false)
const notice = ref('')

async function loadNotifications() {
  if (!session.value) return
  pending.value = true
  notice.value = ''
  try {
    const headers = buildRequestHeaders(session.value.token)
    const [history, count] = await Promise.all([
      $fetch<Notification[]>(`${runtimeConfig.public.apiBaseUrl}/api/v1/notifications`, {
        query: { account_id: session.value.accountId, limit: 100 }, headers,
      }),
      $fetch<{ unread_count: number }>(`${runtimeConfig.public.apiBaseUrl}/api/v1/notifications/unread-count`, {
        query: { account_id: session.value.accountId }, headers,
      }),
    ])
    notifications.value = history
    unreadCount.value = count.unread_count
  } catch {
    notice.value = '通知暂时不可用，请稍后重试。'
  } finally { pending.value = false }
}

async function markRead(notification: Notification) {
  if (!session.value || notification.is_read) return
  try {
    const updated = await $fetch<Notification>(`${runtimeConfig.public.apiBaseUrl}/api/v1/notifications/${encodeURIComponent(notification.id)}/read`, {
      method: 'POST', headers: buildRequestHeaders(session.value.token), body: { account_id: session.value.accountId },
    })
    notification.is_read = updated.is_read
    unreadCount.value = Math.max(0, unreadCount.value - 1)
  } catch { notice.value = '标记已读失败，请稍后重试。' }
}

onMounted(loadNotifications)
</script>

<template>
  <div class="reader-shell">
    <header class="reader-header"><NuxtLink class="reader-brand" to="/"><strong>墨页</strong><span>MINDBOOK</span></NuxtLink><nav class="reader-nav"><NuxtLink to="/">首页</NuxtLink><NuxtLink to="/library">书架</NuxtLink><NuxtLink to="/wallet">钱包</NuxtLink><NuxtLink class="active" to="/notifications">通知</NuxtLink><NuxtLink to="/support">客服</NuxtLink></nav><div class="reader-actions"><form class="search-box" action="/search" method="get"><input name="q" placeholder="搜索书名、作者或关键词..." aria-label="搜索作品" /><button type="submit" aria-label="搜索">⌕</button></form><span class="icon-action">♧</span><span class="avatar">读</span><NuxtLink class="login-link" to="/settings">设置</NuxtLink></div></header>
    <main class="route-page-main notification-page">
      <section class="route-hero route-hero-inline"><div><p class="eyebrow">INBOX</p><h1>通知中心</h1><p>这里会显示与你相关的系统通知、互动消息和重要更新。</p></div><strong v-if="session">{{ unreadCount }} 条未读</strong></section><section class="route-card notification-card">
        <div v-if="!session" class="catalog-state">登录后查看通知。<br><NuxtLink class="text-button" to="/settings">去登录</NuxtLink></div>
        <div v-else-if="pending" class="catalog-state">正在加载通知...</div>
        <div v-else-if="notice && notifications.length" class="catalog-state error">{{ notice }}</div>
        <div v-else-if="!notifications.length" class="empty-route-state"><div class="empty-art">♧</div><h2>暂无通知</h2><p>这里暂时没有新的通知，去阅读一本好书，发现更大的世界吧。</p><span>—　M I N D B O O K　—</span></div>
        <ul v-else class="chapter-list notification-list">
          <li v-for="notification in notifications" :key="notification.id" :class="{ unread: !notification.is_read }">
            <strong>{{ notification.category }}</strong><span>{{ notification.priority }} · {{ notification.channels.join('、') }}</span><button v-if="!notification.is_read" class="quiet-action" type="button" @click="markRead(notification)">标记已读</button><small v-else>已读</small>
          </li>
        </ul>
      </section>
    </main>
  </div>
</template>
