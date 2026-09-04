import { createApp, defineComponent, h, ref } from 'vue'
import { parseShellState, type ShellState } from './shell-state'
import './styles.css'

const item = (tag: string, className: string, children: Parameters<typeof h>[2] = []) => h(tag, { class: className }, children)
const link = (label: string, active = false) => h('a', { class: ['admin-side-link', active && 'active'], href: '#', onClick: (event: Event) => event.preventDefault() }, label)

function stateView(state: ShellState) {
  const content = { loading: ['admin-spinner', '正在加载控制台', '权限范围与任务队列即将出现。'], empty: ['admin-state-mark', '当前没有任务', '新的审核和治理任务会出现在这里。'], error: ['admin-state-mark', '控制台暂时不可用', '请稍后重试，原始业务事实不会被修改。'], unauthorized: ['admin-state-mark', '没有后台权限', '请使用 StaffAccount 登录，不要使用读者账号。'], ready: ['', '', ''] }[state]
  return item('main', 'admin-state', [item('div', 'admin-state-box', [item('div', content[0], content[0] === 'admin-spinner' ? '' : '!'), item('h1', '', content[1]), item('p', '', content[2]), h('a', { class: 'admin-state-action', href: '?state=ready' }, state === 'error' ? '重新加载' : '返回控制台')])])
}

const App = defineComponent({
  setup() {
    const state = ref(parseShellState(new URLSearchParams(window.location.search).get('state')))
    return () => state.value !== 'ready'
      ? stateView(state.value)
      : item('div', 'admin-shell', [
          item('aside', 'admin-sidebar', [item('div', 'admin-logo', [item('strong', '', '墨页'), item('small', '', 'ADMIN CONSOLE')]), item('div', 'scope-badge', 'STAFF / ASSIGNED'), item('nav', 'admin-nav', [link('总览', true), link('内容审核'), link('作者与作品'), link('用户 360'), link('社区治理'), link('财务查询'), link('风险与审批')]), item('div', 'admin-sidebar-foot', [item('span', '', 'v1.2 foundation'), link('退出登录')])]),
          item('div', 'admin-content', [item('header', 'admin-topbar', [item('div', '', [item('p', 'admin-kicker', 'ADMIN CONSOLE'), item('h1', '', '运营控制台')]), item('div', 'staff-chip', [item('span', 'staff-dot', ''), '审核员 · StaffAccount'])]), item('main', 'admin-main', [item('section', 'admin-intro', [item('div', '', [item('p', 'admin-kicker', '工作概览'), item('h2', '', '保持事实可追溯。'), item('p', '', '审核、风险与审批通过明确的业务命令进入对应 Domain。')]), item('span', 'readonly-note', '只读查询壳')]), item('section', 'admin-metrics', [item('article', 'metric-card', [item('span', '', '待领取审核'), item('strong', '', '0'), item('small', '', '当前范围：ASSIGNED')]), item('article', 'metric-card', [item('span', '', '风险待处理'), item('strong', '', '--'), item('small', '', '由 Risk Domain 提供')]), item('article', 'metric-card', [item('span', '', '今日举报'), item('strong', '', '--'), item('small', '', '由 Governance 提供')]), item('article', 'metric-card', [item('span', '', '审批中'), item('strong', '', '--'), item('small', '', '需 Maker / Checker')])]), item('section', 'admin-workspace', [item('article', 'admin-panel', [item('div', 'admin-panel-head', [item('div', '', [item('p', 'admin-kicker', 'REVIEW QUEUE'), item('h2', '', '待领取任务')]), h('a', { href: '#review' }, '审核中心 →')]), item('div', 'admin-empty', [item('div', 'queue-icon', '✓'), item('h3', '', '暂无待领取任务'), item('p', '', '任务会按风险等级、内容类型和权限范围路由。')])]), item('aside', 'admin-panel side-panel', [item('p', 'admin-kicker', '权限边界'), item('h2', '', '本次会话'), item('dl', '', [item('dt', '', '账号类型'), item('dd', '', 'StaffAccount'), item('dt', '', '数据范围'), item('dd', '', 'ASSIGNED'), item('dt', '', '高敏访问'), item('dd', '', '需要独立权限与原因')]), h('a', { href: '#permissions' }, '查看权限 →')])]), item('div', 'admin-footnote', '关键写操作使用明确 Command，并保留 Audit 与 RequestId。')])]),
        ])
  },
})

createApp(App).mount('#app')
