import { createApp, defineComponent, h, onMounted, ref } from 'vue'
import { parseShellState, type ShellState } from './shell-state'
import './styles.css'
import './route.css'

type WritingStat = { business_date: string; words: number; goal: number }
type Book = { id: string; title: string; lifecycle: string; visibility: string }
type Review = { id: string; book_id: string; status: string; fixed_version_ids: string[] }

const apiBase = 'http://localhost:8000'
const authorId = 'author-demo'

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${apiBase}${path}`, {
    ...init,
    headers: { Accept: 'application/json', ...(init?.body ? { 'Content-Type': 'application/json' } : {}) },
  })
  if (!response.ok) throw new Error(`HTTP ${response.status}`)
  return response.json() as Promise<T>
}

const item = (tag: string, className: string, children: Parameters<typeof h>[2] = []) => h(tag, { class: className }, children)
const link = (label: string, active = false) => h('a', { class: ['side-link', active && 'active'], href: `?view=${encodeURIComponent(label)}` }, label)

function stateView(state: ShellState) {
  const content = { loading: ['state-spinner', '正在加载工作台', '作品、审核和收益信息即将出现。'], empty: ['state-mark', '还没有作品', '创建第一本作品，开始你的连载。'], error: ['state-mark', '工作台暂时不可用', '请稍后重试，草稿内容不会受影响。'], unauthorized: ['state-mark', '需要作者权限', '请登录作者账号后继续使用 Writer Center。'], ready: ['', '', ''] }[state]
  return item('main', 'writer-state', [item('div', 'state-box', [item('div', content[0], content[0] === 'state-spinner' ? '' : '!'), item('h1', '', content[1]), item('p', '', content[2]), h('a', { class: 'state-action', href: '?state=ready' }, state === 'error' ? '重新加载' : '回到工作台')])])
}

const Workspace = defineComponent({
  setup() {
    const state = ref(parseShellState(new URLSearchParams(window.location.search).get('state')))
    const view = ref(new URLSearchParams(window.location.search).get('view') || '工作台')
    const stats = ref<WritingStat[]>([])
    const books = ref<Book[]>([])
    const reviews = ref<Review[]>([])
    const title = ref('')
    const message = ref('')

    async function load() {
      try {
        if (view.value === '数据中心') stats.value = await request<WritingStat[]>(`/writer/api/v1/authors/${authorId}/calendar`)
        if (view.value === '审核进度') reviews.value = await request<Review[]>('/admin/api/v1/reviews')
      } catch { message.value = '数据暂时不可用，稍后可重新加载。' }
    }
    async function createBook(event: Event) {
      event.preventDefault()
      if (!title.value.trim()) return
      try {
        const book = await request<Book>('/writer/api/v1/books', { method: 'POST', body: JSON.stringify({ author_id: authorId, title: title.value }) })
        books.value.unshift(book)
        title.value = ''
        message.value = '作品已创建，可以继续添加卷和章节。'
      } catch { message.value = '作品创建失败，请稍后重试。' }
    }

    onMounted(load)

    function workspace() {
      if (view.value === '我的作品') return item('section', 'workspace-card', [item('div', 'panel-heading', [item('div', '', [item('p', 'top-kicker', 'WORKS'), item('h2', '', '作品空间')])]), h('form', { class: 'inline-form', onSubmit: createBook }, [h('input', { value: title.value, placeholder: '输入作品名', 'aria-label': '作品名', onInput: (event: Event) => { title.value = (event.target as HTMLInputElement).value } }), h('button', { class: 'writer-primary', type: 'submit' }, '创建作品')]), books.value.length ? item('ul', 'workspace-list', books.value.map((book) => h('li', { key: book.id }, [h('strong', {}, book.title), h('span', {}, `${book.lifecycle} · ${book.visibility}`)]))) : item('div', 'panel-empty', [item('div', 'empty-line', '+'), item('h3', '', '还没有作品'), item('p', '', '从这里创建第一本作品。')])])
      if (view.value === '审核进度') return item('section', 'workspace-card', [item('p', 'top-kicker', 'REVIEW QUEUE'), item('h2', '', '固定版本审核'), reviews.value.length ? item('ul', 'workspace-list', reviews.value.map((review) => h('li', { key: review.id }, [h('strong', {}, review.book_id), h('span', {}, `${review.status} · ${review.fixed_version_ids.length} 个版本`)]))) : item('div', 'panel-empty', [item('div', 'empty-line', '✓'), item('h3', '', '暂无审核记录'), item('p', '', '提交固定版本后，进度会显示在这里。')])])
      if (view.value === '数据中心') return item('section', 'workspace-card', [item('p', 'top-kicker', 'METRIC CENTER'), item('h2', '', '创作日历'), stats.value.length ? item('div', 'stat-table', stats.value.map((stat) => item('div', 'stat-row', [h('span', {}, stat.business_date), h('strong', {}, `${stat.words.toLocaleString()} 字`), h('small', {}, `目标 ${stat.goal.toLocaleString()}`)]))) : item('div', 'panel-empty', [item('div', 'empty-line', '—'), item('h3', '', '暂无日统计'), item('p', '', '保存草稿后，写作事实会进入日历。')])])
      if (view.value === '收益与结算') return item('section', 'workspace-card', [item('p', 'top-kicker', 'AUTHOR FINANCE'), item('h2', '', '收益与结算'), item('div', 'finance-rows', ['收入明细', '已锁定结算单', '可提现余额'].map((label) => item('div', 'finance-row', [h('span', {}, label), h('strong', {}, '--'), h('small', {}, '以 AuthorFinance 事实为准')]))) , h('a', { class: 'writer-primary', href: '#finance' }, '查看财务流程')])
      if (view.value === '创作学院') return item('section', 'workspace-card', [item('p', 'top-kicker', 'LEARNING'), item('h2', '', '创作学院'), item('div', 'academy-grid', ['开篇', '人物', '剧情', '平台规则', '签约', '版权'].map((label) => item('a', 'academy-item', [h('strong', {}, label), h('span', {}, '查看课程 →')]))), item('p', 'workspace-note', '课程内容由运营 CMS 管理，正文不会执行任意脚本。')])
      if (view.value === '账号设置') return item('section', 'workspace-card', [item('p', 'top-kicker', 'ACCOUNT'), item('h2', '', '账号设置'), item('div', 'setting-line', [h('span', {}, '作者身份'), h('strong', {}, 'author-demo')]), item('div', 'setting-line', [h('span', {}, '笔名'), h('strong', {}, '等待签约审核流程')]), item('p', 'workspace-note', '笔名修改会保留历史记录，签约后需经过独立审核。')])
      return item('section', 'workspace-card', [item('p', 'top-kicker', 'NEXT CHAPTER'), item('h2', '', '今天也写一点。'), item('p', 'workspace-note', '作品、草稿、固定版本审核和结算单都从明确的 Domain 命令产生。'), item('div', 'quick-actions', [h('a', { class: 'writer-primary', href: '?view=我的作品' }, '管理作品'), h('a', { class: 'secondary-action', href: '?view=数据中心' }, '查看创作数据')])])
    }

    return () => state.value !== 'ready' ? stateView(state.value) : item('div', 'writer-shell', [item('aside', 'writer-sidebar', [item('div', 'writer-logo', ['墨页', item('small', '', 'WRITER CENTER')]), item('div', 'workspace-label', '创作空间'), item('nav', 'writer-nav', ['工作台', '我的作品', '审核进度', '数据中心', '收益与结算'].map((label) => link(label, label === view.value))), item('div', 'sidebar-bottom', [link('创作学院', view.value === '创作学院'), link('账号设置', view.value === '账号设置')])]), item('div', 'writer-content', [item('header', 'writer-topbar', [item('div', '', [item('p', 'top-kicker', 'WRITER CENTER'), item('h1', '', view.value)]), item('div', 'top-actions', [h('a', { href: '#messages' }, '消息 2'), h('span', { class: 'author-avatar' }, '林')])]), item('main', 'writer-main', [item('section', 'writer-welcome', [item('div', '', [item('p', 'top-kicker', 'AUTHOR WORKSPACE'), item('h2', '', view.value === '工作台' ? '今天也写一点。' : view.value), item('p', 'welcome-copy', message.value || '业务状态和操作结果会在这里反馈。')]), h('a', { class: 'writer-primary', href: '?view=我的作品' }, '进入作品')]), item('section', 'writer-stats', [item('article', 'stat-block', [h('span', {}, '作品'), h('strong', {}, String(books.value.length)), h('small', {}, '当前作者范围')]), item('article', 'stat-block', [h('span', {}, '今日字数'), h('strong', {}, stats.value.length ? String(stats.value.at(-1)?.words ?? '--') : '--'), h('small', {}, '由写作事实汇总')]), item('article', 'stat-block', [h('span', {}, '结算状态'), h('strong', {}, '待查'), h('small', {}, '由财务域提供')])]), workspace(), item('section', 'writer-tip', [h('span', { class: 'tip-index' }, '01'), item('div', '', [h('h3', {}, '发布提醒'), h('p', {}, '发布章节会创建固定版本并进入审核工作流。')]), h('a', { href: '?view=审核进度' }, '查看审核 →')])])])])
  },
})

createApp(Workspace).mount('#app')
