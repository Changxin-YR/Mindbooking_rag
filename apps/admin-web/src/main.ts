import { createApp, defineComponent, h, onMounted, ref } from 'vue'
import { parseShellState, type ShellState } from './shell-state'
import './styles.css'
import './route.css'

type Review = { id: string; book_id: string; status: string; fixed_version_ids: string[] }
type Rule = { code: string; severity: string; recommended_action: string; version: string }
type Dashboard = { csat_count: number; open_alert_count: number }

const apiBase = 'http://localhost:8000'
async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${apiBase}${path}`, { ...init, headers: { Accept: 'application/json', ...(init?.body ? { 'Content-Type': 'application/json' } : {}) } })
  if (!response.ok) throw new Error(`HTTP ${response.status}`)
  return response.json() as Promise<T>
}

const item = (tag: string, className: string, children: Parameters<typeof h>[2] = []) => h(tag, { class: className }, children)
const navLink = (label: string, active: boolean) => h('a', { class: ['admin-side-link', active && 'active'], href: `?view=${encodeURIComponent(label)}` }, label)

function stateView(state: ShellState) {
  const content = { loading: ['admin-spinner', '正在加载控制台', '权限范围与任务队列即将出现。'], empty: ['admin-state-mark', '当前没有任务', '新的审核和治理任务会出现在这里。'], error: ['admin-state-mark', '控制台暂时不可用', '请稍后重试，原始业务事实不会被修改。'], unauthorized: ['admin-state-mark', '没有后台权限', '请使用 StaffAccount 登录，不要使用读者账号。'], ready: ['', '', ''] }[state]
  return item('main', 'admin-state', [item('div', 'admin-state-box', [item('div', content[0], content[0] === 'admin-spinner' ? '' : '!'), item('h1', '', content[1]), item('p', '', content[2]), h('a', { class: 'admin-state-action', href: '?state=ready' }, state === 'error' ? '重新加载' : '返回控制台')])])
}

const Console = defineComponent({
  setup() {
    const state = ref(parseShellState(new URLSearchParams(window.location.search).get('state')))
    const view = ref(new URLSearchParams(window.location.search).get('view') || '总览')
    const reviews = ref<Review[]>([])
    const rules = ref<Rule[]>([])
    const dashboard = ref<Dashboard>({ csat_count: 0, open_alert_count: 0 })
    const user = ref<{ phone: string; real_name: string; asset_cents: number | null } | null>(null)
    const key = ref('vip.price')
    const value = ref('199')
    const message = ref('')

    async function load() {
      try {
        if (view.value === '内容审核') reviews.value = await request<Review[]>('/admin/api/v1/reviews')
        if (view.value === '参数中心') rules.value = await request<Rule[]>('/admin/api/v1/review-rules')
        dashboard.value = await request<Dashboard>('/admin/api/v1/support/dashboard')
      } catch { message.value = '查询暂时不可用，请检查后端服务。' }
    }
    async function loadUser(event: Event) {
      event.preventDefault()
      try {
        user.value = await request('/admin/api/v1/user-360', { method: 'POST', body: JSON.stringify({ account_id: 'acct-demo', phone: '13812345678', real_name: '实名用户', asset_cents: 0, membership_level: 0, growth_level: 1 }) })
        message.value = '已返回脱敏 User360 视图。'
      } catch { message.value = 'User360 查询失败。' }
    }
    async function draftParameter(event: Event) {
      event.preventDefault()
      try { await request('/admin/api/v1/parameters', { method: 'POST', body: JSON.stringify({ key: key.value, value: value.value, maker_id: 'staff-demo' }) }); message.value = '参数草案已保存，等待 Checker 审批。' } catch { message.value = '参数草案保存失败。' }
    }
    onMounted(load)

    function workspace() {
      if (view.value === '内容审核') return item('section', 'admin-card', [item('p', 'admin-kicker', 'REVIEW QUEUE'), item('h2', '', '结构化审核结果'), reviews.value.length ? item('ul', 'admin-list', reviews.value.map((review) => h('li', { key: review.id }, [h('strong', {}, review.book_id), h('span', {}, `${review.status} · ${review.fixed_version_ids.length} 个固定版本`), h('a', { href: `#${review.id}` }, '打开')]))) : item('admin-empty', 'admin-empty', [item('div', 'queue-icon', '✓'), item('h3', '', '暂无审核任务'), item('p', '', '队列按风险、内容类型、频道和 SLA 路由。')])])
      if (view.value === '用户 360') return item('section', 'admin-card', [item('p', 'admin-kicker', 'QUERY SERVICE'), item('h2', '', '用户 360'), h('form', { class: 'admin-inline-form', onSubmit: loadUser }, [h('span', {}, '查询示例账号 acct-demo'), h('button', { class: 'admin-action', type: 'submit' }, '查询')]), user.value ? item('div', 'user-facts', [item('div', '', [h('span', {}, '手机号'), h('strong', {}, user.value.phone)]), item('div', '', [h('span', {}, '实名状态'), h('strong', {}, user.value.real_name)]), item('div', '', [h('span', {}, '资产金额'), h('strong', {}, user.value.asset_cents === null ? '已脱敏' : `${user.value.asset_cents} 分` )])]) : item('div', 'admin-empty', [item('div', 'queue-icon', '◎'), item('h3', '', '字段默认脱敏'), item('p', '', '敏感字段需独立权限、原因和审计。')])])
      if (view.value === '参数中心') return item('section', 'admin-card', [item('p', 'admin-kicker', 'PARAMETER CENTER'), item('h2', '', '关键参数版本'), h('form', { class: 'admin-inline-form', onSubmit: draftParameter }, [h('input', { value: key.value, 'aria-label': '参数键', onInput: (event: Event) => { key.value = (event.target as HTMLInputElement).value } }), h('input', { value: value.value, 'aria-label': '参数值', onInput: (event: Event) => { value.value = (event.target as HTMLInputElement).value } }), h('button', { class: 'admin-action', type: 'submit' }, '保存草案')]), item('p', 'admin-note', '草案 -> Domain 校验 -> Maker/Checker -> effective_at -> Activate。'), rules.value.length ? item('ul', 'admin-list', rules.value.map((rule) => h('li', { key: `${rule.code}-${rule.version}` }, [h('strong', {}, rule.code), h('span', {}, `${rule.severity} · ${rule.recommended_action} · v${rule.version}`)]))) : item('div', 'admin-empty compact', [item('h3', '', '规则库待配置'), item('p', '', '规则版本和参数版本独立管理。')])])
      if (view.value === '社区治理') return item('section', 'admin-card', [item('p', 'admin-kicker', 'GOVERNANCE'), item('h2', '', '社区与客服看板'), item('div', 'metric-strip', [item('div', '', [h('span', {}, 'CSAT 回收'), h('strong', {}, String(dashboard.value.csat_count))]), item('div', '', [h('span', {}, '作者告警'), h('strong', {}, String(dashboard.value.open_alert_count))]), item('div', '', [h('span', {}, '举报人身份'), h('strong', {}, '隔离')])]), item('p', 'admin-note', '同一内容的多次举报聚合为一个 Case；原始内容进入证据快照后受 Legal Hold 保护。')])
      if (view.value === '财务查询') return item('section', 'admin-card', [item('p', 'admin-kicker', 'FINANCE'), item('h2', '', '支付与账务修复'), item('div', 'finance-state', [h('strong', {}, 'CREDIT_PENDING'), h('span', {}, '渠道支付成功但业务入账失败时，保留支付事实并进入对账修复。')]), h('a', { class: 'admin-action', href: '#reconciliation' }, '进入日对账')])
      if (view.value === '风险与审批') return item('section', 'admin-card', [item('p', 'admin-kicker', 'RISK / APPROVAL'), item('h2', '', '风险和关键动作'), item('div', 'admin-list static-list', ['登录信号先 OBSERVE，再按证据冻结', '高敏访问需要独立权限与原因', '资金与参数动作使用 Maker / Checker'].map((text) => h('div', {}, text))), h('a', { class: 'admin-action', href: '#risk' }, '查看风控队列')])
      if (view.value === '文件与审计') return item('section', 'admin-card', [item('p', 'admin-kicker', 'DATA CENTER'), item('h2', '', '只读数据与文件治理'), item('div', 'admin-list static-list', ['公开文件：公开访问', '高敏文件：短时 Signed URL + Audit', '指标修正：走对应 Domain 正式流程'].map((text) => h('div', {}, text)))])
      return item('section', 'admin-card', [item('p', 'admin-kicker', 'PLATFORM OVERVIEW'), item('h2', '', '保持事实可追溯。'), item('p', 'admin-note', '审核、运营、治理、财务、风险与审批通过明确 Command 进入对应 Domain。'), item('div', 'quick-actions', [h('a', { class: 'admin-action', href: '?view=内容审核' }, '审核队列'), h('a', { class: 'secondary-action', href: '?view=用户%20360' }, 'User360')])])
    }

    const navigation = ['总览', '内容审核', '作者与作品', '用户 360', '社区治理', '财务查询', '风险与审批', '参数中心', '文件与审计']
    return () => state.value !== 'ready' ? stateView(state.value) : item('div', 'admin-shell', [item('aside', 'admin-sidebar', [item('div', 'admin-logo', [item('strong', '', '墨页'), item('small', '', 'ADMIN CONSOLE')]), item('div', 'scope-badge', 'STAFF / ASSIGNED'), item('nav', 'admin-nav', navigation.map((label) => navLink(label, label === view.value))), item('div', 'admin-sidebar-foot', [item('span', '', 'v1.2'), navLink('退出登录', false)])]), item('div', 'admin-content', [item('header', 'admin-topbar', [item('div', '', [item('p', 'admin-kicker', 'ADMIN CONSOLE'), item('h1', '', view.value)]), item('div', 'staff-chip', [item('span', 'staff-dot', ''), '审核员 · StaffAccount'])]), item('main', 'admin-main', [item('section', 'admin-intro', [item('div', '', [item('p', 'admin-kicker', 'CONTROL PLANE'), item('h2', '', view.value === '总览' ? '运营事实总览' : view.value), item('p', '', message.value || '当前会话只显示授权范围内的业务事实。')]), item('span', 'readonly-note', 'READ / COMMAND')]), item('section', 'admin-metrics', [item('article', 'metric-card', [h('span', {}, '客服 CSAT'), h('strong', {}, String(dashboard.value.csat_count)), h('small', {}, '仅作 Support QA')]), item('article', 'metric-card', [h('span', {}, '开放告警'), h('strong', {}, String(dashboard.value.open_alert_count)), h('small', {}, '不暴露 L3 敏感细节')]), item('article', 'metric-card', [h('span', {}, '数据范围'), h('strong', {}, 'ASSIGNED'), h('small', {}, '由 StaffAccount 决定')]), item('article', 'metric-card', [h('span', {}, '审批模式'), h('strong', {}, 'M / C'), h('small', {}, 'Maker / Checker')])]), workspace(), item('div', 'admin-footnote', '只读指标不能直接改阅读量、充值额或作者收入；修正必须进入对应 Domain。')])])])
  },
})

createApp(Console).mount('#app')
