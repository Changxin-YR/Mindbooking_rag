import { createApp, defineComponent, h, onMounted, ref } from 'vue'
import { buildAdminHeaders, parseShellState, readAdminAccessToken, type ShellState } from './shell-state'
import './styles.css'
import './route.css'

type Review = { id: string; book_id: string; status: string; fixed_version_ids: string[] }
type Rule = { code: string; severity: string; recommended_action: string; version: string }
type Dashboard = { csat_count: number; open_alert_count: number }

const apiBase = ((import.meta as ImportMeta & { env?: { VITE_API_BASE_URL?: string } }).env?.VITE_API_BASE_URL || 'http://localhost:8000').replace(/\/+$/, '')
function sessionToken() {
  try { return readAdminAccessToken(window.localStorage) } catch { return '' }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const headers = buildAdminHeaders(sessionToken(), init?.headers)
  if (init?.body && !headers.has('Content-Type')) headers.set('Content-Type', 'application/json')
  const response = await fetch(`${apiBase}${path}`, { ...init, headers })
  if (response.status === 401) {
    window.localStorage.removeItem('admin_access_token')
    throw new Error('UNAUTHORIZED')
  }
  if (!response.ok) throw new Error(`HTTP ${response.status}`)
  return response.json() as Promise<T>
}

const item = (tag: string, className: string, children: Parameters<typeof h>[2] = []) => h(tag, { class: className }, children)
const navLink = (label: string, active: boolean) => h('a', { class: ['admin-side-link', active && 'active'], href: label === '退出登录' ? '#sign-out' : `?view=${encodeURIComponent(label)}`, onClick: label === '退出登录' ? (event: Event) => { event.preventDefault(); window.localStorage.removeItem('admin_access_token'); window.location.reload() } : undefined }, label)

function stateView(state: ShellState) {
  if (state === 'unauthorized') return h('main', { class: 'admin-state' }, [h('form', { class: 'admin-state-box admin-login', onSubmit: async (event: Event) => {
    event.preventDefault()
    const fields = new FormData(event.currentTarget as HTMLFormElement)
    const response = await fetch(`${apiBase}/admin/api/v1/auth/staff/sessions`, { method: 'POST', headers: { 'Content-Type': 'application/json', Accept: 'application/json' }, body: JSON.stringify({ employee_code: fields.get('employee_code'), password: fields.get('password') }) })
    if (!response.ok) return
    const result = await response.json() as { access_token: string }
    window.localStorage.setItem('admin_access_token', result.access_token)
    window.location.reload()
  } }, [item('div', 'admin-state-mark', '墨页'), item('p', 'admin-kicker', 'STAFF ACCESS'), item('h1', '', '登录运营后台'), item('p', '', '使用 StaffAccount 会话进入授权范围。'), h('label', { class: 'admin-login-field' }, [h('span', {}, '工号'), h('input', { name: 'employee_code', required: true, autocomplete: 'username' })]), h('label', { class: 'admin-login-field' }, [h('span', {}, '密码'), h('input', { name: 'password', required: true, type: 'password', autocomplete: 'current-password' })]), h('button', { class: 'admin-state-action', type: 'submit' }, '登录')])])
  const content = { loading: ['admin-spinner', '正在加载控制台', '权限范围与任务队列即将出现。'], empty: ['admin-state-mark', '当前没有任务', '新的审核和治理任务会出现在这里。'], error: ['admin-state-mark', '控制台暂时不可用', '请稍后重试，原始业务事实不会被修改。'], unauthorized: ['admin-state-mark', '没有后台权限', '请使用 StaffAccount 登录，不要使用读者账号。'], ready: ['', '', ''] }[state]
  return item('main', 'admin-state', [item('div', 'admin-state-box', [item('div', content[0], content[0] === 'admin-spinner' ? '' : '!'), item('h1', '', content[1]), item('p', '', content[2]), h('a', { class: 'admin-state-action', href: '?state=ready' }, state === 'error' ? '重新加载' : '返回控制台')])])
}

const Console = defineComponent({
  setup() {
    const state = ref(sessionToken() ? parseShellState(new URLSearchParams(window.location.search).get('state')) : 'unauthorized')
    const view = ref(new URLSearchParams(window.location.search).get('view') || '总览')
    const reviews = ref<Review[]>([])
    const rules = ref<Rule[]>([])
    const dashboard = ref<Dashboard>({ csat_count: 0, open_alert_count: 0 })
    const user = ref<{ phone: string; real_name: string; asset_cents: number | null } | null>(null)
    const accountId = ref('')
    const accountPhone = ref('')
    const key = ref('vip.price')
    const value = ref('199')
    const staffId = ref('')
    const reviewerId = ref('')
    const reviewDecision = ref('APPROVE')
    const membershipPlanCode = ref('MONTHLY')
    const membershipPlanName = ref('月度会员')
    const membershipDuration = ref('30')
    const membershipPrice = ref('999')
    const membershipDailyTickets = ref('2')
    const membershipMonthlyTickets = ref('5')
    const message = ref('')
    const employeeCode = ref('')
    const password = ref('')
    const loginError = ref('')

    async function login(event: Event) {
      event.preventDefault()
      loginError.value = ''
      try {
        const response = await fetch(`${apiBase}/admin/api/v1/auth/staff/sessions`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json', Accept: 'application/json' },
          body: JSON.stringify({ employee_code: employeeCode.value.trim(), password: password.value }),
        })
        if (!response.ok) throw new Error('INVALID_STAFF_CREDENTIALS')
        const result = await response.json() as { access_token: string }
        window.localStorage.setItem('admin_access_token', result.access_token)
        password.value = ''
        state.value = 'ready'
        await load()
      } catch {
        loginError.value = 'Staff 登录失败，请检查工号和密码。'
      }
    }

    async function signOut(event?: Event) {
      event?.preventDefault()
      const token = sessionToken()
      try {
        if (token) await fetch(`${apiBase}/admin/api/v1/auth/staff/sessions/current`, { method: 'DELETE', headers: buildAdminHeaders(token) })
      } finally {
        window.localStorage.removeItem('admin_access_token')
        state.value = 'unauthorized'
        message.value = ''
      }
    }

    async function load() {
      if (!sessionToken()) {
        message.value = '未检测到 StaffAccount 会话，请先完成登录。'
        return
      }
      try {
        if (view.value === '内容审核') reviews.value = await request<Review[]>('/admin/api/v1/reviews')
        if (view.value === '参数中心') rules.value = await request<Rule[]>('/admin/api/v1/review-rules')
        dashboard.value = await request<Dashboard>('/admin/api/v1/support/dashboard')
      } catch { message.value = '查询暂时不可用，请检查后端服务。' }
    }
    async function loadUser(event: Event) {
      event.preventDefault()
      const queryAccountId = accountId.value.trim()
      const queryPhone = accountPhone.value.trim()
      if (!queryAccountId || !queryPhone) {
        message.value = '请填写查询账号 ID 和手机号。'
        return
      }
      try {
        user.value = await request('/admin/api/v1/user-360', { method: 'POST', body: JSON.stringify({ account_id: queryAccountId, phone: queryPhone, real_name: '', asset_cents: 0, membership_level: 0, growth_level: 0 }) })
        message.value = '已返回脱敏 User360 视图。'
      } catch { message.value = 'User360 查询失败。' }
    }
    async function draftParameter(event: Event) {
      event.preventDefault()
      const makerId = staffId.value.trim()
      if (!makerId) {
        message.value = '请填写 Staff 操作者 ID。'
        return
      }
      try { await request('/admin/api/v1/parameters', { method: 'POST', body: JSON.stringify({ key: key.value, value: value.value, maker_id: makerId }) }); message.value = '参数草案已保存，等待 Checker 审批。' } catch { message.value = '参数草案保存失败。' }
    }
    async function decideReview(review: Review, event: Event) {
      event.preventDefault()
      const reviewer = reviewerId.value.trim()
      if (!reviewer) {
        message.value = '请填写审核员 ID。'
        return
      }
      try {
        await request(`/admin/api/v1/reviews/${encodeURIComponent(review.id)}/decisions`, { method: 'POST', body: JSON.stringify({ reviewer_id: reviewer, decision: reviewDecision.value, actor_type: 'human' }) })
        review.status = reviewDecision.value === 'APPROVE' ? 'APPROVED' : reviewDecision.value === 'REJECT' || reviewDecision.value === 'OFFLINE' ? 'REJECTED' : 'RETURNED'
        message.value = '审核决定已记录。'
      } catch { message.value = '审核决定提交失败，请检查权限和任务状态。' }
    }
    async function createMembershipPlan(event: Event) {
      event.preventDefault()
      try {
        await request('/admin/api/v1/membership/plans', {
          method: 'POST',
          body: JSON.stringify({
            plan_code: membershipPlanCode.value.trim(),
            name: membershipPlanName.value.trim(),
            duration_days: Number(membershipDuration.value),
            price_cents: Number(membershipPrice.value),
            daily_recommend_tickets: Number(membershipDailyTickets.value),
            monthly_chapter_tickets: Number(membershipMonthlyTickets.value),
            version: 1,
          }),
        })
        message.value = '会员计划草案已写入配置中心。'
      } catch {
        message.value = '会员计划保存失败，请确认版本号和计划编码未重复。'
      }
    }
    onMounted(load)

    function workspace() {
      if (view.value === '内容审核') {
        const reviewerField = h('label', { class: 'admin-form-field' }, [
          h('span', {}, '审核员 ID'),
          h('input', { value: reviewerId.value, 'aria-label': '审核员 ID', onInput: (event: Event) => { reviewerId.value = (event.target as HTMLInputElement).value } }),
        ])
        const decisionField = h('label', { class: 'admin-form-field' }, [
          h('span', {}, '决定'),
          h('select', { value: reviewDecision.value, 'aria-label': '审核决定', onChange: (event: Event) => { reviewDecision.value = (event.target as HTMLSelectElement).value } }, ['APPROVE', 'RETURN_FOR_CHANGES', 'REJECT', 'OFFLINE'].map((decision) => h('option', { value: decision }, decision))),
        ])
        const reviewList = reviews.value.length
          ? item('ul', 'admin-list', reviews.value.map((review) => h('li', { key: review.id }, [
              h('strong', {}, review.book_id),
              h('span', {}, `${review.status} · ${review.fixed_version_ids.length} 个固定版本`),
              h('button', { class: 'admin-action', type: 'button', onClick: (event: Event) => decideReview(review, event) }, '提交决定'),
            ])))
          : item('div', 'admin-empty', [item('div', 'queue-icon', '✓'), item('h3', '', '暂无审核任务'), item('p', '', '队列按风险、内容类型、频道和 SLA 路由。')])
        return item('section', 'admin-card', [item('p', 'admin-kicker', 'REVIEW QUEUE'), item('h2', '', '结构化审核结果'), item('div', 'admin-inline-form', [reviewerField, decisionField]), reviewList])
      }
      if (view.value === '用户 360') return item('section', 'admin-card', [item('p', 'admin-kicker', 'QUERY SERVICE'), item('h2', '', '用户 360'), h('form', { class: 'admin-inline-form', onSubmit: loadUser }, [h('label', { class: 'admin-form-field' }, [h('span', {}, '查询账号 ID'), h('input', { value: accountId.value, required: true, 'aria-label': '查询账号 ID', onInput: (event: Event) => { accountId.value = (event.target as HTMLInputElement).value } })]), h('label', { class: 'admin-form-field' }, [h('span', {}, '查询手机号'), h('input', { value: accountPhone.value, required: true, inputmode: 'tel', 'aria-label': '查询手机号', onInput: (event: Event) => { accountPhone.value = (event.target as HTMLInputElement).value } })]), h('button', { class: 'admin-action', type: 'submit' }, '查询')]), user.value ? item('div', 'user-facts', [item('div', '', [h('span', {}, '手机号'), h('strong', {}, user.value.phone)]), item('div', '', [h('span', {}, '实名状态'), h('strong', {}, user.value.real_name)]), item('div', '', [h('span', {}, '资产金额'), h('strong', {}, user.value.asset_cents === null ? '已脱敏' : `${user.value.asset_cents} 分` )])]) : item('div', 'admin-empty', [item('div', 'queue-icon', '◎'), item('h3', '', '字段默认脱敏'), item('p', '', '敏感字段需独立权限、原因和审计。')])])
      if (view.value === '参数中心') return item('section', 'admin-card', [item('p', 'admin-kicker', 'PARAMETER CENTER'), item('h2', '', '关键参数版本'), h('form', { class: 'admin-inline-form', onSubmit: draftParameter }, [h('label', { class: 'admin-form-field' }, [h('span', {}, '参数键'), h('input', { value: key.value, required: true, 'aria-label': '参数键', onInput: (event: Event) => { key.value = (event.target as HTMLInputElement).value } })]), h('label', { class: 'admin-form-field' }, [h('span', {}, '参数值'), h('input', { value: value.value, required: true, 'aria-label': '参数值', onInput: (event: Event) => { value.value = (event.target as HTMLInputElement).value } })]), h('label', { class: 'admin-form-field' }, [h('span', {}, 'Staff 操作者 ID'), h('input', { value: staffId.value, required: true, 'aria-label': 'Staff 操作者 ID', onInput: (event: Event) => { staffId.value = (event.target as HTMLInputElement).value } })]), h('button', { class: 'admin-action', type: 'submit' }, '保存草案')]), item('p', 'admin-note', '草案 -> Domain 校验 -> Maker/Checker -> effective_at -> Activate。'), rules.value.length ? item('ul', 'admin-list', rules.value.map((rule) => h('li', { key: `${rule.code}-${rule.version}` }, [h('strong', {}, rule.code), h('span', {}, `${rule.severity} · ${rule.recommended_action} · v${rule.version}`)]))) : item('div', 'admin-empty compact', [item('h3', '', '规则库待配置'), item('p', '', '规则版本和参数版本独立管理。')])])
      if (view.value === '会员配置') return item('section', 'admin-card', [item('p', 'admin-kicker', 'MEMBERSHIP CENTER'), item('h2', '', '会员权益配置'), item('p', 'admin-note', '周期、价格、推荐票和章节券由运营配置，会员书库通过独立入口绑定作品。'), h('form', { class: 'admin-inline-form', onSubmit: createMembershipPlan }, [h('label', { class: 'admin-form-field' }, [h('span', {}, '计划编码'), h('input', { value: membershipPlanCode.value, required: true, 'aria-label': '计划编码', onInput: (event: Event) => { membershipPlanCode.value = (event.target as HTMLInputElement).value } })]), h('label', { class: 'admin-form-field' }, [h('span', {}, '计划名称'), h('input', { value: membershipPlanName.value, required: true, 'aria-label': '计划名称', onInput: (event: Event) => { membershipPlanName.value = (event.target as HTMLInputElement).value } })]), h('label', { class: 'admin-form-field' }, [h('span', {}, '周期天数'), h('input', { value: membershipDuration.value, type: 'number', min: 1, required: true, 'aria-label': '周期天数', onInput: (event: Event) => { membershipDuration.value = (event.target as HTMLInputElement).value } })]), h('label', { class: 'admin-form-field' }, [h('span', {}, '价格（分）'), h('input', { value: membershipPrice.value, type: 'number', min: 1, required: true, 'aria-label': '价格（分）', onInput: (event: Event) => { membershipPrice.value = (event.target as HTMLInputElement).value } })]), h('label', { class: 'admin-form-field' }, [h('span', {}, '每日推荐票'), h('input', { value: membershipDailyTickets.value, type: 'number', min: 0, required: true, 'aria-label': '每日推荐票', onInput: (event: Event) => { membershipDailyTickets.value = (event.target as HTMLInputElement).value } })]), h('label', { class: 'admin-form-field' }, [h('span', {}, '月度章节券'), h('input', { value: membershipMonthlyTickets.value, type: 'number', min: 0, required: true, 'aria-label': '月度章节券', onInput: (event: Event) => { membershipMonthlyTickets.value = (event.target as HTMLInputElement).value } })]), h('button', { class: 'admin-action', type: 'submit' }, '保存会员计划')])])
      if (view.value === '社区治理') return item('section', 'admin-card', [item('p', 'admin-kicker', 'GOVERNANCE'), item('h2', '', '社区与客服看板'), item('div', 'metric-strip', [item('div', '', [h('span', {}, 'CSAT 回收'), h('strong', {}, String(dashboard.value.csat_count))]), item('div', '', [h('span', {}, '作者告警'), h('strong', {}, String(dashboard.value.open_alert_count))]), item('div', '', [h('span', {}, '举报人身份'), h('strong', {}, '隔离')])]), item('p', 'admin-note', '同一内容的多次举报聚合为一个 Case；原始内容进入证据快照后受 Legal Hold 保护。')])
      if (view.value === '财务查询') return item('section', 'admin-card', [item('p', 'admin-kicker', 'FINANCE'), item('h2', '', '支付与账务修复'), item('div', 'finance-state', [h('strong', {}, 'CREDIT_PENDING'), h('span', {}, '渠道支付成功但业务入账失败时，保留支付事实并进入对账修复。')]), h('a', { class: 'admin-action', href: '#reconciliation' }, '进入日对账')])
      if (view.value === '风险与审批') return item('section', 'admin-card', [item('p', 'admin-kicker', 'RISK / APPROVAL'), item('h2', '', '风险和关键动作'), item('div', 'admin-list static-list', ['登录信号先 OBSERVE，再按证据冻结', '高敏访问需要独立权限与原因', '资金与参数动作使用 Maker / Checker'].map((text) => h('div', {}, text))), h('a', { class: 'admin-action', href: '#risk' }, '查看风控队列')])
      if (view.value === '文件与审计') return item('section', 'admin-card', [item('p', 'admin-kicker', 'DATA CENTER'), item('h2', '', '只读数据与文件治理'), item('div', 'admin-list static-list', ['公开文件：公开访问', '高敏文件：短时 Signed URL + Audit', '指标修正：走对应 Domain 正式流程'].map((text) => h('div', {}, text)))])
      return item('section', 'admin-card', [item('p', 'admin-kicker', 'PLATFORM OVERVIEW'), item('h2', '', '保持事实可追溯。'), item('p', 'admin-note', '审核、运营、治理、财务、风险与审批通过明确 Command 进入对应 Domain。'), item('div', 'quick-actions', [h('a', { class: 'admin-action', href: '?view=内容审核' }, '审核队列'), h('a', { class: 'secondary-action', href: '?view=用户%20360' }, 'User360')])])
    }

    const navigation = ['总览', '内容审核', '作者与作品', '用户 360', '社区治理', '财务查询', '风险与审批', '参数中心', '会员配置', '文件与审计']
    return () => state.value !== 'ready' ? stateView(state.value) : item('div', 'admin-shell', [item('aside', 'admin-sidebar', [item('div', 'admin-logo', [item('strong', '', '墨页'), item('small', '', 'ADMIN CONSOLE')]), item('div', 'scope-badge', 'STAFF / ASSIGNED'), item('nav', 'admin-nav', navigation.map((label) => navLink(label, label === view.value))), item('div', 'admin-sidebar-foot', [item('span', '', 'v1.2'), navLink('退出登录', false)])]), item('div', 'admin-content', [item('header', 'admin-topbar', [item('div', '', [item('p', 'admin-kicker', 'ADMIN CONSOLE'), item('h1', '', view.value)]), item('div', 'staff-chip', [item('span', 'staff-dot', ''), '审核员 · StaffAccount'])]), item('main', 'admin-main', [item('section', 'admin-intro', [item('div', '', [item('p', 'admin-kicker', 'CONTROL PLANE'), item('h2', '', view.value === '总览' ? '运营事实总览' : view.value), item('p', '', message.value || '当前会话只显示授权范围内的业务事实。')]), item('span', 'readonly-note', 'READ / COMMAND')]), item('section', 'admin-metrics', [item('article', 'metric-card', [h('span', {}, '客服 CSAT'), h('strong', {}, String(dashboard.value.csat_count)), h('small', {}, '仅作 Support QA')]), item('article', 'metric-card', [h('span', {}, '开放告警'), h('strong', {}, String(dashboard.value.open_alert_count)), h('small', {}, '不暴露 L3 敏感细节')]), item('article', 'metric-card', [h('span', {}, '数据范围'), h('strong', {}, 'ASSIGNED'), h('small', {}, '由 StaffAccount 决定')]), item('article', 'metric-card', [h('span', {}, '审批模式'), h('strong', {}, 'M / C'), h('small', {}, 'Maker / Checker')])]), workspace(), item('div', 'admin-footnote', '只读指标不能直接改阅读量、充值额或作者收入；修正必须进入对应 Domain。')])])])
  },
})

createApp(Console).mount('#app')
