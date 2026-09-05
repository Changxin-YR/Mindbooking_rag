<script setup lang="ts">
import { buildRequestHeaders, loadSession } from '../../src/session'

const runtimeConfig = useRuntimeConfig()
const session = loadSession()
const accountId = session?.accountId ?? ''
const { data: wallet, pending, error } = await useFetch<{ recharge_coin: number; gift_coin: number; total_coin: number }>(`${runtimeConfig.public.apiBaseUrl}/api/v1/wallet`, { query: { account_id: accountId }, headers: session ? buildRequestHeaders(session.token) : undefined, immediate: Boolean(session), server: false })
const { data: membership } = await useFetch<{ active: boolean }>(`${runtimeConfig.public.apiBaseUrl}/api/v1/membership/status`, { query: { account_id: accountId }, headers: session ? buildRequestHeaders(session.token) : undefined, immediate: Boolean(session), server: false })
const productCode = ref('RECHARGE_100')
const channel = ref('WECHAT')
const rechargeNotice = ref('')
const checkout = ref<{ payment_no: string; recharge_no: string; paid_cents: number; recharge_coin: number; gift_coin: number; status: string } | null>(null)
const membershipPlanCode = ref('MONTHLY')
const membershipChannel = ref<'WECHAT' | 'ALIPAY'>('WECHAT')
const membershipOrder = ref<{ payment_no: string; price_cents: number; status: string } | null>(null)
const membershipNotice = ref('')
const idempotencyKey = ref('')

async function createRecharge() {
  if (!session) {
    rechargeNotice.value = '请先登录'
    return
  }
  if (!idempotencyKey.value) idempotencyKey.value = globalThis.crypto?.randomUUID?.() || `reader-${Date.now()}`
  const headers = buildRequestHeaders(session.token)
  headers.set('Idempotency-Key', idempotencyKey.value)
  try {
    checkout.value = await $fetch(`${runtimeConfig.public.apiBaseUrl}/api/v1/recharge`, { method: 'POST', headers, body: { account_id: accountId, product_code: productCode.value, channel: channel.value } })
    idempotencyKey.value = ''
    rechargeNotice.value = '充值订单已创建，等待支付渠道回调。'
  } catch (cause: unknown) {
    rechargeNotice.value = cause && typeof cause === 'object' && 'data' in cause && (cause.data as { error?: { code?: string } })?.error?.code === 'REAL_NAME_REQUIRED' ? '完成实名认证后才能充值。' : '充值订单创建失败，请稍后重试。'
  }
}

async function createMembershipOrder() {
  if (!session) {
    membershipNotice.value = '请先登录'
    return
  }
  const headers = buildRequestHeaders(session.token)
  headers.set('Idempotency-Key', globalThis.crypto?.randomUUID?.() || `membership-${Date.now()}`)
  try {
    membershipOrder.value = await $fetch(`${runtimeConfig.public.apiBaseUrl}/api/v1/membership/orders`, { method: 'POST', headers, body: { account_id: accountId, plan_code: membershipPlanCode.value.trim(), channel: membershipChannel.value } })
    membershipNotice.value = '会员订单已创建，支付成功后由渠道回调激活。'
  } catch {
    membershipNotice.value = '会员订单创建失败，请确认计划已由运营配置。'
  }
}
</script>

<template>
  <div class="reader-shell">
    <header class="reader-header">
      <NuxtLink class="reader-brand" to="/">墨页 <span>MindBook</span></NuxtLink>
      <nav class="reader-nav"><NuxtLink to="/">首页</NuxtLink><NuxtLink to="/library">书架</NuxtLink><NuxtLink class="active" to="/wallet">钱包</NuxtLink><NuxtLink to="/support">客服</NuxtLink></nav>
      <NuxtLink class="login-link" to="/settings">设置</NuxtLink>
    </header>
    <main class="reader-detail-main">
      <section class="detail-section">
        <p class="eyebrow">Wallet</p><h1>我的资产</h1>
        <div v-if="!session" class="catalog-state">登录后查看资产。<br /><NuxtLink class="text-button" to="/settings">去登录</NuxtLink></div>
        <div v-else-if="pending" class="catalog-state">正在读取资产...</div>
        <div v-else-if="error" class="catalog-state error">钱包暂时不可用。</div>
        <template v-else>
          <div class="wallet-grid"><div><span>可用充值币</span><strong>{{ wallet?.recharge_coin ?? 0 }}</strong></div><div><span>赠币</span><strong>{{ wallet?.gift_coin ?? 0 }}</strong></div><div><span>总资产</span><strong>{{ wallet?.total_coin ?? 0 }}</strong></div></div>
          <form class="support-form wallet-form" @submit.prevent="createRecharge">
            <label>充值产品<select v-model="productCode"><option value="RECHARGE_100">RECHARGE_100</option><option value="RECHARGE_100_PROMO">RECHARGE_100_PROMO</option></select></label>
            <label>支付渠道<select v-model="channel"><option value="WECHAT">微信支付</option><option value="ALIPAY">支付宝</option></select></label>
            <button class="primary-button" type="submit">创建充值订单</button><p v-if="rechargeNotice" role="status">{{ rechargeNotice }}</p>
            <div v-if="checkout" class="catalog-state"><strong>{{ checkout.recharge_no }}</strong><span>应付 {{ checkout.paid_cents / 100 }} 元 · {{ checkout.status }}</span></div>
          </form>
          <section class="wallet-membership">
            <p class="eyebrow">Membership</p><h2>{{ membership?.active ? '会员有效' : '开通会员' }}</h2>
            <p>会员书库和票券权益按运营配置生效，不等于全站 VIP 免费。</p>
            <form class="support-form wallet-form" @submit.prevent="createMembershipOrder">
              <label>计划编码<input v-model="membershipPlanCode" required /></label>
              <label>支付渠道<select v-model="membershipChannel"><option value="WECHAT">微信支付</option><option value="ALIPAY">支付宝</option></select></label>
              <button class="primary-button" type="submit">创建会员订单</button><p v-if="membershipNotice" role="status">{{ membershipNotice }}</p>
              <div v-if="membershipOrder" class="catalog-state"><strong>{{ membershipOrder.payment_no }}</strong><span>应付 {{ membershipOrder.price_cents / 100 }} 元 · {{ membershipOrder.status }}</span></div>
            </form>
          </section>
        </template>
        <NuxtLink v-if="session" class="primary-button" to="/support">充值遇到问题？联系支持</NuxtLink>
      </section>
    </main>
  </div>
</template>
