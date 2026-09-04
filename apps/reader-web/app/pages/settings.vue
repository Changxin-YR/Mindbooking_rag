<script setup lang="ts">
const minor = ref(false)
const notice = ref('')
const runtimeConfig = useRuntimeConfig()
async function save() {
  try {
    await $fetch(`${runtimeConfig.public.apiBaseUrl}/api/v1/accounts/acct-demo/minor-protection`, { method: 'PUT', body: { is_minor: minor.value, policy_version: 'minor-v1' } })
    notice.value = '阅读保护设置已保存'
  } catch { notice.value = '保存失败，请稍后再试。' }
}
</script>

<template><div class="reader-shell"><header class="reader-header"><NuxtLink class="reader-brand" to="/">墨页 <span>MindBook</span></NuxtLink><nav class="reader-nav"><NuxtLink to="/">首页</NuxtLink><NuxtLink to="/library">书架</NuxtLink><NuxtLink to="/wallet">钱包</NuxtLink><NuxtLink to="/support">客服</NuxtLink></nav><NuxtLink class="login-link" to="/">返回首页</NuxtLink></header><main class="reader-detail-main"><section class="rating-panel"><div><p class="eyebrow">Privacy & safety</p><h1>账号与阅读设置</h1><p>未成年人保护策略会以版本记录，且不会改变已购买权益。</p></div><form class="support-form" @submit.prevent="save"><label class="toggle-row"><input v-model="minor" type="checkbox" /> 开启未成年人保护</label><button class="primary-button" type="submit">保存设置</button><p v-if="notice" role="status">{{ notice }}</p></form></section></main></div></template>
