<script setup lang="ts">
import { buildRequestHeaders, clearSession, loadSession, saveSession, type ReaderSession } from '../../src/session'

const minor = ref(false)
const notice = ref('')
const authNotice = ref('')
const mode = ref<'login' | 'register'>('login')
const phone = ref('')
const password = ref('')
const session = ref<ReaderSession | null>(loadSession())
const runtimeConfig = useRuntimeConfig()

async function authenticate() {
  authNotice.value = ''
  try {
    if (mode.value === 'register') {
      await $fetch(`${runtimeConfig.public.apiBaseUrl}/api/v1/iam/accounts`, {
        method: 'POST',
        body: { phone: phone.value, password: password.value },
      })
    }
    const response = await $fetch<{ account_id: string; access_token: string }>(`${runtimeConfig.public.apiBaseUrl}/api/v1/iam/sessions`, {
      method: 'POST',
      body: { phone: phone.value, password: password.value },
    })
    session.value = saveSession({ token: response.access_token, accountId: response.account_id })
    password.value = ''
    authNotice.value = mode.value === 'register' ? '账号已创建并登录' : '登录成功'
  } catch {
    authNotice.value = mode.value === 'register' ? '注册失败，请检查手机号或密码是否符合要求。' : '登录失败，请检查手机号和密码。'
  }
}

function signOut() {
  clearSession()
  session.value = null
  authNotice.value = '已退出登录'
}

async function save() {
  if (!session.value) {
    notice.value = '请先登录'
    return
  }
  try {
    await $fetch(`${runtimeConfig.public.apiBaseUrl}/api/v1/accounts/${encodeURIComponent(session.value.accountId)}/minor-protection`, { method: 'PUT', headers: buildRequestHeaders(session.value.token), body: { is_minor: minor.value, policy_version: 'minor-v1' } })
    notice.value = '阅读保护设置已保存'
  } catch { notice.value = '保存失败，请稍后再试。' }
}
</script>

<template><div class="reader-shell"><header class="reader-header"><NuxtLink class="reader-brand" to="/">墨页 <span>MindBook</span></NuxtLink><nav class="reader-nav"><NuxtLink to="/">首页</NuxtLink><NuxtLink to="/library">书架</NuxtLink><NuxtLink to="/wallet">钱包</NuxtLink><NuxtLink to="/support">客服</NuxtLink></nav><NuxtLink class="login-link" to="/">返回首页</NuxtLink></header><main class="reader-detail-main"><section class="rating-panel"><div><p class="eyebrow">Account & safety</p><h1>账号与阅读设置</h1><p>未成年人保护策略会以版本记录，且不会改变已购买权益。</p><div v-if="session" class="session-summary"><span>当前账号</span><strong>{{ session.accountId }}</strong><button class="quiet-action" type="button" @click="signOut">退出登录</button></div><form v-else class="support-form" @submit.prevent="authenticate"><label>手机号<input v-model="phone" type="tel" inputmode="numeric" autocomplete="username" required /></label><label>密码<input v-model="password" type="password" minlength="8" autocomplete="current-password" required /></label><button class="primary-button" type="submit">{{ mode === 'register' ? '注册并登录' : '登录' }}</button><button class="quiet-action" type="button" @click="mode = mode === 'login' ? 'register' : 'login'">{{ mode === 'login' ? '没有账号？注册' : '已有账号？登录' }}</button><p v-if="authNotice" role="status">{{ authNotice }}</p></form><p v-if="authNotice && session" role="status">{{ authNotice }}</p></div><form v-if="session" class="support-form" @submit.prevent="save"><label class="toggle-row"><input v-model="minor" type="checkbox" /> 开启未成年人保护</label><button class="primary-button" type="submit">保存设置</button><p v-if="notice" role="status">{{ notice }}</p></form></section></main></div></template>
