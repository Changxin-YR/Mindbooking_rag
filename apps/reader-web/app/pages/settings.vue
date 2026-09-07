<script setup lang="ts">
import type { AccountProfileDto } from '@mindbooking/api-types'
import { buildRequestHeaders, clearSession, loadSession, saveSession, type ReaderSession } from '../../src/session'

const minor = ref(false)
const notice = ref('')
const authNotice = ref('')
const mode = ref<'login' | 'register'>('login')
const phone = ref('')
const password = ref('')
const session = ref<ReaderSession | null>(loadSession())
const runtimeConfig = useRuntimeConfig()
const growth = ref<{ level: number; points: number } | null>(null)
const follows = ref<{ items: Array<{ target_type: string; target_id: string }> } | null>(null)
const marketingEnabled = ref(false)
const profileLoading = ref(false)
const profile = ref<AccountProfileDto | null>(null)
const nickname = ref('')
const loginName = ref('')
const profileNotice = ref('')
const profileSaving = ref(false)

async function loadProfileData() {
  if (!session.value) return
  profileLoading.value = true
  const headers = buildRequestHeaders(session.value.token)
  try {
    const [growthResult, followsResult, profileResult] = await Promise.all([
      $fetch<{ level: number; points: number }>(`${runtimeConfig.public.apiBaseUrl}/api/v1/accounts/${encodeURIComponent(session.value.accountId)}/growth`, { headers }),
      $fetch<{ items: Array<{ target_type: string; target_id: string }> }>(`${runtimeConfig.public.apiBaseUrl}/api/v1/accounts/${encodeURIComponent(session.value.accountId)}/follows`, { headers }),
      $fetch<AccountProfileDto>(`${runtimeConfig.public.apiBaseUrl}/api/v1/iam/accounts/${encodeURIComponent(session.value.accountId)}/profile`, { headers }),
    ])
    growth.value = growthResult
    follows.value = followsResult
    profile.value = profileResult
    nickname.value = profileResult.nickname || ''
    loginName.value = profileResult.login_name || ''
  } catch { /* profile widgets stay in empty state */ } finally { profileLoading.value = false }
}
async function saveProfile() {
  if (!session.value || (!nickname.value.trim() && !loginName.value.trim())) return
  profileSaving.value = true
  profileNotice.value = ''
  try {
    const updated = await $fetch<AccountProfileDto>(`${runtimeConfig.public.apiBaseUrl}/api/v1/iam/accounts/${encodeURIComponent(session.value.accountId)}/profile`, { method: 'PATCH', headers: buildRequestHeaders(session.value.token), body: { nickname: nickname.value.trim() || undefined, login_name: loginName.value.trim() || undefined } })
    profile.value = updated
    nickname.value = updated.nickname || ''
    loginName.value = updated.login_name || ''
    profileNotice.value = '资料已保存'
  } catch { profileNotice.value = '资料保存失败，请检查昵称或登录名后重试。' } finally { profileSaving.value = false }
}

async function authenticate() {
  authNotice.value = ''
  try {
    if (mode.value === 'register') await $fetch(`${runtimeConfig.public.apiBaseUrl}/api/v1/iam/accounts`, { method: 'POST', body: { phone: phone.value, password: password.value } })
    const response = await $fetch<{ account_id: string; access_token: string }>(`${runtimeConfig.public.apiBaseUrl}/api/v1/iam/sessions`, { method: 'POST', body: { phone: phone.value, password: password.value } })
    session.value = saveSession({ token: response.access_token, accountId: response.account_id })
    password.value = ''
    authNotice.value = mode.value === 'register' ? '账号已创建并登录' : '登录成功'
    await loadProfileData()
  } catch { authNotice.value = mode.value === 'register' ? '注册失败，请检查手机号或密码是否符合要求。' : '登录失败，请检查手机号和密码。' }
}
function signOut() { clearSession(); session.value = null; authNotice.value = '已退出登录' }
async function save() {
  if (!session.value) { notice.value = '请先登录'; return }
  try { await $fetch(`${runtimeConfig.public.apiBaseUrl}/api/v1/accounts/${encodeURIComponent(session.value.accountId)}/minor-protection`, { method: 'PUT', headers: buildRequestHeaders(session.value.token), body: { is_minor: minor.value, policy_version: 'minor-v1' } }); notice.value = '阅读保护设置已保存' } catch { notice.value = '保存失败，请稍后再试。' }
}
async function saveMarketingPreference() {
  if (!session.value) return
  try { await $fetch(`${runtimeConfig.public.apiBaseUrl}/api/v1/notifications/marketing-preference`, { method: 'PUT', headers: buildRequestHeaders(session.value.token), body: { account_id: session.value.accountId, enabled: marketingEnabled.value } }); notice.value = '通知偏好已保存' } catch { notice.value = '通知偏好保存失败，请稍后再试。' }
}
onMounted(loadProfileData)
</script>

<template>
  <div class="reader-shell">
    <header class="reader-header"><NuxtLink class="reader-brand" to="/"><strong>墨页</strong><span>MINDBOOK</span></NuxtLink><nav class="reader-nav"><NuxtLink to="/">首页</NuxtLink><NuxtLink to="/library">书架</NuxtLink><NuxtLink to="/wallet">钱包</NuxtLink><NuxtLink to="/notifications">通知</NuxtLink><NuxtLink to="/support">客服</NuxtLink></nav><div class="reader-actions"><form class="search-box" action="/search" method="get"><input name="q" placeholder="搜索书名、作者或关键词..." aria-label="搜索作品" /><button type="submit" aria-label="搜索">⌕</button></form><span class="icon-action">♧</span><span class="avatar">读</span><NuxtLink class="login-link" to="/">返回首页</NuxtLink></div></header>
    <main class="route-page-main settings-page">
      <div class="settings-layout">
        <div class="settings-intro"><p class="eyebrow">ACCOUNT & READING</p><h1>账号与阅读设置</h1><p>管理你的账号信息与阅读偏好，<br />打造更适合自己的阅读体验。</p><span class="support-rule" /><div v-if="session" class="session-summary"><span>账号</span><strong>{{ profile?.account_no || '读取中...' }}</strong><button class="quiet-action" type="button" @click="signOut">退出登录</button></div><form v-else class="support-form" @submit.prevent="authenticate"><label>手机号<input v-model="phone" type="tel" inputmode="numeric" autocomplete="username" required /></label><label>密码<input v-model="password" type="password" minlength="8" autocomplete="current-password" required /></label><button class="primary-button" type="submit">{{ mode === 'register' ? '注册并登录' : '登录' }}</button><button class="quiet-action" type="button" @click="mode = mode === 'login' ? 'register' : 'login'">{{ mode === 'login' ? '没有账号？注册' : '已有账号？登录' }}</button><p v-if="authNotice" role="status">{{ authNotice }}</p></form></div>
        <section v-if="session" class="settings-card"><h2>个人资料</h2><p>账号：{{ profile?.account_no || '读取中...' }}</p><form class="support-form" @submit.prevent="saveProfile"><label>昵称<input v-model="nickname" minlength="1" maxlength="32" placeholder="设置昵称" /></label><label>登录名<input v-model="loginName" minlength="3" maxlength="32" pattern="[a-z][a-z0-9_]{2,31}" placeholder="例如 changxin" /></label><button class="primary-button" type="submit" :disabled="profileSaving">{{ profileSaving ? '保存中...' : '保存个人资料' }}</button><p v-if="profileNotice" role="status">{{ profileNotice }}</p></form></section>
        <section class="settings-card"><h2>账号安全</h2><p>管理账号安全与个人偏好设置</p><form v-if="session" class="support-form" @submit.prevent="save"><label class="toggle-row"><input v-model="minor" type="checkbox" /> 开启未成年人保护</label><button class="primary-button" type="submit">保存设置</button><p v-if="notice" role="status">{{ notice }}</p></form></section>
        <section class="settings-card"><h2>通知设置</h2><p>选择你希望接收的服务通知</p><form v-if="session" class="support-form" @submit.prevent="saveMarketingPreference"><label class="toggle-row"><input v-model="marketingEnabled" type="checkbox" /> 接收活动与运营通知</label><button class="quiet-action" type="submit">保存通知偏好</button></form></section>
        <section v-if="session" class="settings-card profile-facts" aria-labelledby="profile-title"><h2 id="profile-title">成长与关注</h2><p>记录你在墨页的阅读足迹</p><p v-if="profileLoading" class="catalog-state">正在读取个人资料...</p><template v-else><div class="wallet-grid"><div><span>成长等级</span><strong>{{ growth?.level ?? 0 }}</strong></div><div><span>成长积分</span><strong>{{ growth?.points ?? 0 }}</strong></div><div><span>关注数量</span><strong>{{ follows?.items?.length ?? 0 }}</strong></div></div><p v-if="!follows?.items?.length" class="catalog-state">暂无关注，去作品详情关注作者。</p></template></section>
      </div>
    </main>
    <section v-if="session" class="settings-card settings-links"><h2>账户中心</h2><div class="detail-actions"><NuxtLink class="quiet-action" to="/account/real-name">实名认证</NuxtLink><NuxtLink class="quiet-action" to="/library">我的书架</NuxtLink><NuxtLink class="quiet-action" to="/support">联系客服</NuxtLink></div><p class="catalog-state">账号编号不可修改；昵称和登录名可按规则管理。</p></section>
  </div>
</template>
