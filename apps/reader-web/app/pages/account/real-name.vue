<script setup lang="ts">
import { buildRequestHeaders, loadSession } from '../../../src/session'
const runtimeConfig = useRuntimeConfig()
const session = loadSession()
const name = ref('')
const identityDocument = ref('')
const notice = ref('')
const submitting = ref(false)
const status = ref('未实名')
const statusLoading = ref(false)

async function loadStatus() {
  if (!session) return
  statusLoading.value = true
  try {
    const result = await $fetch<{ slot_status?: string }>(`${runtimeConfig.public.apiBaseUrl}/api/v1/iam/accounts/${encodeURIComponent(session.accountId)}/real-name`, { headers: buildRequestHeaders(session.token) })
    status.value = result.slot_status === 'ACTIVE' ? '已实名' : result.slot_status || '未实名'
  } catch { status.value = '未实名' } finally { statusLoading.value = false }
}
async function submit() {
  if (!session || submitting.value) return
  submitting.value = true; notice.value = ''
  try {
    const result = await $fetch<{ slot_status: string }>(`${runtimeConfig.public.apiBaseUrl}/api/v1/iam/accounts/${encodeURIComponent(session.accountId)}/real-name`, { method: 'POST', headers: buildRequestHeaders(session.token), body: { name: name.value.trim(), identity_document: identityDocument.value.trim() } })
    status.value = result.slot_status === 'ACTIVE' ? '已实名' : result.slot_status
    notice.value = '实名认证已完成，现在可以返回钱包充值。'
  } catch (cause: unknown) {
    const code = cause && typeof cause === 'object' && 'data' in cause ? (cause.data as { error?: { code?: string } })?.error?.code : undefined
    notice.value = code === 'ACCOUNT_ALREADY_REAL_NAMED' ? '该账号已完成实名认证。' : '认证信息校验失败，请检查姓名和身份证号。'
  } finally { submitting.value = false }
}
onMounted(loadStatus)
</script>

<template>
  <div class="reader-shell"><header class="reader-header"><NuxtLink class="reader-brand" to="/"><strong>墨页</strong><span>MINDBOOK</span></NuxtLink><nav class="reader-nav" aria-label="读者导航"><NuxtLink to="/">首页</NuxtLink><NuxtLink to="/library">书架</NuxtLink><NuxtLink to="/wallet">钱包</NuxtLink><NuxtLink to="/support">客服</NuxtLink></nav><NuxtLink class="login-link" to="/settings">账户设置</NuxtLink></header><main class="route-page-main"><section class="route-hero"><p class="eyebrow">REAL NAME</p><h1>实名认证</h1><p>当前状态：<strong>{{ statusLoading ? '读取中...' : status }}</strong></p></section><section v-if="!session" class="route-card catalog-state">请先登录后进行实名认证。<br /><NuxtLink class="text-button" to="/settings">去登录</NuxtLink></section><section v-else class="route-card"><form class="support-form" @submit.prevent="submit"><label>姓名<input v-model="name" required minlength="2" autocomplete="name" /></label><label>身份证号<input v-model="identityDocument" required minlength="18" maxlength="18" autocomplete="off" /></label><p class="catalog-state">开发环境使用 FakeRealNameAdapter，认证结果仍会写入实名关联记录。</p><button class="primary-button" type="submit" :disabled="submitting || status === '已实名'">{{ submitting ? '提交中...' : status === '已实名' ? '已完成认证' : '完成实名认证' }}</button><p v-if="notice" role="status">{{ notice }}</p></form><NuxtLink class="text-button" to="/wallet">返回钱包</NuxtLink></section></main></div>
</template>
