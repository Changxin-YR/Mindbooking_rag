import { createApp, defineComponent, h, ref } from 'vue'
import { parseShellState, type ShellState } from './shell-state'
import './styles.css'

const item = (tag: string, className: string, children: Parameters<typeof h>[2] = []) => h(tag, { class: className }, children)
const link = (label: string, active = false) => h('a', { class: ['side-link', active && 'active'], href: '#', onClick: (event: Event) => event.preventDefault() }, label)

function stateView(state: ShellState) {
  const content = {
    loading: ['state-spinner', '正在加载工作台', '作品、审核和收益信息即将出现。'],
    empty: ['state-mark', '还没有作品', '创建第一本作品，开始你的连载。'],
    error: ['state-mark', '工作台暂时不可用', '请稍后重试，草稿内容不会受影响。'],
    unauthorized: ['state-mark', '需要作者权限', '请登录作者账号后继续使用 Writer Center。'],
    ready: ['', '', ''],
  }[state]
  return item('main', 'writer-state', [item('div', 'state-box', [item('div', content[0], content[0] === 'state-spinner' ? '' : '!'), item('h1', '', content[1]), item('p', '', content[2]), h('a', { class: 'state-action', href: state === 'unauthorized' ? '?state=ready' : '?state=ready' }, state === 'error' ? '重新加载' : '回到工作台')])])
}

const App = defineComponent({
  setup() {
    const state = ref(parseShellState(new URLSearchParams(window.location.search).get('state')))
    return () => state.value !== 'ready'
      ? stateView(state.value)
      : item('div', 'writer-shell', [
          item('aside', 'writer-sidebar', [item('div', 'writer-logo', ['墨页', item('small', '', 'WRITER CENTER')]), item('div', 'workspace-label', '创作空间'), item('nav', 'writer-nav', [link('工作台', true), link('我的作品'), link('审核进度'), link('数据中心'), link('收益与结算')]), item('div', 'sidebar-bottom', [link('创作学院'), link('账号设置')])]),
          item('div', 'writer-content', [
            item('header', 'writer-topbar', [item('div', '', [item('p', 'top-kicker', 'WRITER CENTER'), item('h1', '', '作者工作台')]), item('div', 'top-actions', [h('a', { href: '#messages' }, '消息 2'), h('span', { class: 'author-avatar' }, '林')])]),
            item('main', 'writer-main', [
              item('section', 'writer-welcome', [item('div', '', [item('p', 'top-kicker', '今日创作'), item('h2', '', '把想象写成下一章。'), item('p', 'welcome-copy', '作品、草稿与审核进度，都从这里开始。')]), h('a', { class: 'writer-primary', href: '#new-book' }, '创建作品')]),
              item('section', 'writer-stats', [item('article', 'stat-block', [item('span', '', '待处理事项'), item('strong', '', '0'), item('small', '', '当前没有待办')]), item('article', 'stat-block', [item('span', '', '本月新增字数'), item('strong', '', '--'), item('small', '', '接入数据后显示')]), item('article', 'stat-block', [item('span', '', '可结算收益'), item('strong', '', '--'), item('small', '', '以结算单为准')])]),
              item('section', 'writer-grid', [item('article', 'writer-panel', [item('div', 'panel-heading', [item('div', '', [item('p', 'top-kicker', '作品空间'), item('h2', '', '我的作品')]), h('a', { href: '#books' }, '查看全部')]), item('div', 'panel-empty', [item('div', 'empty-line', '＋'), item('h3', '', '还没有作品'), item('p', '', '先创建作品，再开始编辑章节。'), h('a', { href: '#new-book' }, '创建第一本作品 →')])]), item('article', 'writer-panel', [item('div', 'panel-heading', [item('div', '', [item('p', 'top-kicker', '审核工作流'), item('h2', '', '最近审核')]), h('a', { href: '#reviews' }, '查看全部')]), item('div', 'panel-empty compact', [item('div', 'empty-line', '✓'), item('h3', '', '暂无审核记录'), item('p', '', '提交章节后，审核状态会出现在这里。')])])]),
              item('section', 'writer-tip', [item('span', 'tip-index', '01'), item('div', '', [item('h3', '', '写作提醒'), item('p', '', '发布章节会创建固定版本并进入对应审核流程。')]), h('a', { href: '#academy' }, '查看创作指南 →')]),
            ]),
          ]),
        ])
  },
})

createApp(App).mount('#app')
