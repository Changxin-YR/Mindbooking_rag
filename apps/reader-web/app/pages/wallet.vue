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
const showRealNamePrompt = ref(false)
const checkout = ref<{ payment_no: string; recharge_no: string; paid_cents: number; recharge_coin: number; gift_coin: number; status: string; provider?: string | null; checkout_url?: string | null } | null>(null)
const membershipPlanCode = ref('MONTHLY')
const membershipChannel = ref<'WECHAT' | 'ALIPAY'>('WECHAT')
const membershipOrder = ref<{ payment_no: string; price_cents: number; status: string; provider?: string | null; checkout_url?: string | null } | null>(null)
const membershipNotice = ref('')
const membershipSandboxStatus = ref<'SUCCESS' | 'FAILED' | 'CANCELLED' | 'TIMEOUT' | 'PROCESSING' | 'REJECTED'>('SUCCESS')
const membershipSandboxDelay = ref(0)
const membershipSandboxDuplicate = ref(false)
const membershipSandboxNotice = ref('')
const idempotencyKey = ref('')
const sandboxStatus = ref<'SUCCESS' | 'FAILED' | 'CANCELLED' | 'TIMEOUT' | 'PROCESSING' | 'REJECTED'>('SUCCESS')
const sandboxDelay = ref(0)
const sandboxDuplicate = ref(false)
const sandboxNotice = ref('')

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
    const code = cause && typeof cause === 'object' && 'data' in cause ? (cause.data as { error?: { code?: string } })?.error?.code : undefined
    if (code === 'REAL_NAME_REQUIRED') { rechargeNotice.value = '充值前需要完成实名认证。'; showRealNamePrompt.value = true }
    else rechargeNotice.value = '充值订单创建失败，请稍后重试。'
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

async function simulateSandboxMembershipPayment() {
  if (!session || !membershipOrder.value) return
  try {
    const result = await $fetch<{ status: string; processed: boolean }>(`${runtimeConfig.public.apiBaseUrl}/api/v1/membership/payments/sandbox/simulate`, {
      method: 'POST',
      headers: buildRequestHeaders(session.token),
      body: {
        account_id: accountId,
        payment_no: membershipOrder.value.payment_no,
        status: membershipSandboxStatus.value,
        delay_seconds: Number(membershipSandboxDelay.value),
        duplicate: membershipSandboxDuplicate.value,
      },
    })
    membershipSandboxNotice.value = result.processed ? `会员沙盒回调已处理：${result.status}` : '延迟回调已排队，稍后刷新会员状态。'
    await refreshNuxtData()
  } catch {
    membershipSandboxNotice.value = '会员沙盒回调处理失败，请确认订单仍处于待支付状态。'
  }
}

async function simulateSandboxPayment() {
  if (!session || !checkout.value) return
  try {
    const result = await $fetch<{ status: string; processed: boolean }>(`${runtimeConfig.public.apiBaseUrl}/api/v1/recharge/sandbox/simulate`, {
      method: 'POST',
      headers: buildRequestHeaders(session.token),
      body: {
        account_id: accountId,
        payment_no: checkout.value.payment_no,
        status: sandboxStatus.value,
        delay_seconds: Number(sandboxDelay.value),
        duplicate: sandboxDuplicate.value,
      },
    })
    sandboxNotice.value = result.processed ? `沙盒回调已处理：${result.status}` : '延迟回调已排队，稍后刷新钱包。'
    await refreshNuxtData()
  } catch {
    sandboxNotice.value = '沙盒回调处理失败，请确认订单仍处于待支付状态。'
  }
}
</script>

<template>
  <div class="reader-shell">
    <header class="reader-header"><NuxtLink class="reader-brand" to="/"><strong>墨页</strong><span>MINDBOOK</span></NuxtLink><nav class="reader-nav"><NuxtLink to="/">首页</NuxtLink><NuxtLink to="/library">书架</NuxtLink><NuxtLink class="active" to="/wallet">钱包</NuxtLink><NuxtLink to="/notifications">通知</NuxtLink><NuxtLink to="/support">客服</NuxtLink></nav><div class="reader-actions"><form class="search-box" action="/search" method="get"><input name="q" placeholder="搜索书名、作者或关键词..." aria-label="搜索作品" /><button type="submit" aria-label="搜索">⌕</button></form><NuxtLink class="icon-action" to="/notifications" aria-label="通知">♧</NuxtLink><NuxtLink class="avatar" to="/settings" aria-label="个人中心">读</NuxtLink><NuxtLink class="login-link" to="/settings">设置</NuxtLink></div></header>
    <main class="route-page-main wallet-page">
      <section class="route-hero"><div><p class="eyebrow">WALLET</p><h1>我的资产</h1><p>在阅读的世界里，每一份投入，都是遇见更好的自己的开始。</p></div></section><section class="wallet-content">
        <div v-if="!session" class="catalog-state">登录后查看资产。<br /><NuxtLink class="text-button" to="/settings">去登录</NuxtLink></div>
        <div v-else-if="pending" class="catalog-state">正在读取资产...</div>
        <template v-else>
          <p v-if="error" class="catalog-state error">钱包暂时不可用，请稍后重试。</p>
          <div class="wallet-grid"><div><span>可用充值币</span><strong>{{ wallet?.recharge_coin ?? 0 }}</strong></div><div><span>赠币</span><strong>{{ wallet?.gift_coin ?? 0 }}</strong></div><div><span>总资产</span><strong>{{ wallet?.total_coin ?? 0 }}</strong></div></div>
          <form class="support-form wallet-form" @submit.prevent="createRecharge">
            <label>充值产品<select v-model="productCode"><option value="RECHARGE_100">￥100，获得 10000 充值币</option><option value="RECHARGE_100_PROMO">￥100，获得 10000 充值币，赠送 2000 赠币</option></select></label>
            <label>支付渠道<select v-model="channel"><option value="WECHAT">微信支付</option><option value="ALIPAY">支付宝</option></select></label>
            <button class="primary-button" type="submit">创建充值订单</button><p v-if="rechargeNotice" role="status">{{ rechargeNotice }}</p>
            <div v-if="checkout" class="catalog-state"><strong>{{ checkout.recharge_no }}</strong><span>应付 {{ checkout.paid_cents / 100 }} 元 · {{ checkout.status }} · {{ checkout.provider || '渠道待分配' }}</span><a v-if="checkout.checkout_url" class="text-button" :href="checkout.checkout_url" target="_blank" rel="noopener">打开支付收银台</a><small v-else>沙盒订单已创建，等待渠道回调；生产支付需配置 Provider 凭据。</small>
              <div v-if="checkout.provider?.startsWith('SANDBOX')" class="sandbox-controls">
                <label>模拟结果<select v-model="sandboxStatus"><option value="SUCCESS">支付成功</option><option value="FAILED">支付失败</option><option value="CANCELLED">用户取消</option><option value="TIMEOUT">支付超时</option><option value="PROCESSING">处理中</option><option value="REJECTED">渠道拒绝</option></select></label>
                <label>延迟（秒）<input v-model.number="sandboxDelay" type="number" min="0" /></label>
                <label class="check-line"><input v-model="sandboxDuplicate" type="checkbox" />重复回调</label>
                <button class="text-button" type="button" @click="simulateSandboxPayment">发送沙盒回调</button>
                <p v-if="sandboxNotice" role="status">{{ sandboxNotice }}</p>
              </div>
            </div>
          </form>
          <section class="wallet-membership">
            <p class="eyebrow">Membership</p><h2>{{ membership?.active ? '会员有效' : '开通会员' }}</h2>
            <p>会员书库和票券权益按运营配置生效，不等于全站 VIP 免费。</p>
            <form class="support-form wallet-form" @submit.prevent="createMembershipOrder">
              <label>计划编码<input v-model="membershipPlanCode" required /></label>
              <label>支付渠道<select v-model="membershipChannel"><option value="WECHAT">微信支付</option><option value="ALIPAY">支付宝</option></select></label>
              <button class="primary-button" type="submit">创建会员订单</button><p v-if="membershipNotice" role="status">{{ membershipNotice }}</p>
              <div v-if="membershipOrder" class="catalog-state"><strong>{{ membershipOrder.payment_no }}</strong><span>应付 {{ membershipOrder.price_cents / 100 }} 元 · {{ membershipOrder.status }} · {{ membershipOrder.provider || '渠道待分配' }}</span><a v-if="membershipOrder.checkout_url" class="text-button" :href="membershipOrder.checkout_url" target="_blank" rel="noopener">打开会员收银台</a>
                <div v-if="membershipOrder.provider?.startsWith('SANDBOX')" class="sandbox-controls">
                  <label>模拟结果<select v-model="membershipSandboxStatus"><option value="SUCCESS">支付成功</option><option value="FAILED">支付失败</option><option value="CANCELLED">用户取消</option><option value="TIMEOUT">支付超时</option><option value="PROCESSING">处理中</option><option value="REJECTED">渠道拒绝</option></select></label>
                  <label>延迟（秒）<input v-model.number="membershipSandboxDelay" type="number" min="0" /></label>
                  <label class="check-line"><input v-model="membershipSandboxDuplicate" type="checkbox" />重复回调</label>
                  <button class="text-button" type="button" @click="simulateSandboxMembershipPayment">发送会员沙盒回调</button>
                  <p v-if="membershipSandboxNotice" role="status">{{ membershipSandboxNotice }}</p>
                </div>
              </div>
            </form>
          </section>
        </template>
        <NuxtLink v-if="session" class="primary-button" to="/support">充值遇到问题？联系支持</NuxtLink>
        <div v-if="showRealNamePrompt" class="modal-backdrop" role="dialog" aria-modal="true" aria-labelledby="real-name-title"><div class="modal-card"><h2 id="real-name-title">充值前需要完成实名认证</h2><p>完成实名认证后才能创建充值订单。</p><div class="detail-actions"><NuxtLink class="primary-button" to="/account/real-name">立即实名认证</NuxtLink><button class="quiet-action" type="button" @click="showRealNamePrompt = false">稍后处理</button></div></div></div>
      </section>
    </main>
  </div>
</template>
