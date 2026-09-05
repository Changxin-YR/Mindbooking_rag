import { createApp, defineComponent, h, onMounted, ref } from 'vue'
import { parseShellState, type ShellState } from './shell-state'
import { buildRequestHeaders, clearSession, loadSession, resolveApiBaseUrl, saveSession, type WriterSession } from './session'
import './styles.css'
import './route.css'

type WritingStat = { business_date: string; words: number; goal: number }
type Book = { id: string; title: string; lifecycle: string; visibility: string }
type Review = { id: string; book_id: string; status: string; fixed_version_ids: string[] }
type AuthorProfile = { id: string; account_id: string; pen_name: string }
type Volume = { id: string; book_id: string; number: number; title: string }
type Chapter = { id: string; volume_id: string; number: number; title: string; commercial_policy: string }
type DraftSnapshot = { id: string; chapter_id: string; revision: number; content: string; save_mode: string }
type ChapterVersion = { id: string; chapter_id: string; version: number; content: string; word_count: number }

const apiBase = resolveApiBaseUrl(
  (import.meta as ImportMeta & { env?: { VITE_API_BASE_URL?: string } }).env?.VITE_API_BASE_URL || '',
  'http://localhost:8000',
)

async function request<T>(session: WriterSession, path: string, init?: RequestInit): Promise<T> {
  const headers = buildRequestHeaders(session.token, init?.headers)
  if (init?.body) headers.set('Content-Type', 'application/json')
  const response = await fetch(`${apiBase}${path}`, { ...init, headers })
  if (!response.ok) throw new Error(`HTTP ${response.status}`)
  return response.json() as Promise<T>
}

const item = (tag: string, className: string, children: Parameters<typeof h>[2] = []) => h(tag, { class: className }, children)
const link = (label: string, active = false) => h('a', { class: ['side-link', active && 'active'], href: `?view=${encodeURIComponent(label)}` }, label)

function stateView(state: ShellState) {
  const content = {
    loading: ['state-spinner', '正在加载工作台', '作品、审核和收益信息即将出现。'],
    empty: ['state-mark', '还没有作品', '创建第一本作品，开始你的连载。'],
    error: ['state-mark', '工作台暂时不可用', '请稍后重试，草稿内容不会受影响。'],
    unauthorized: ['state-mark', '需要作者权限', '请登录作者账号后继续使用 Writer Center。'],
    ready: ['', '', ''],
  }[state]
  return item('main', 'writer-state', [item('div', 'state-box', [item('div', content[0], content[0] === 'state-spinner' ? '' : '!'), item('h1', '', content[1]), item('p', '', content[2]), h('a', { class: 'state-action', href: '?state=ready' }, state === 'error' ? '重新加载' : '回到工作台')])])
}

function sessionView(token: string, accountId: string, error: string, onSubmit: (event: Event) => void, onToken: (event: Event) => void, onAccountId: (event: Event) => void) {
  return item('main', 'writer-state', [h('form', { class: 'state-box session-box', onSubmit }, [
    item('div', 'state-mark', '墨'),
    item('h1', '', '进入 Writer Center'),
    item('p', '', '请输入登录接口返回的会话信息。'),
    h('label', {}, ['Access token', h('input', { value: token, type: 'password', autocomplete: 'off', required: true, onInput: onToken })]),
    h('label', {}, ['Account ID', h('input', { value: accountId, autocomplete: 'username', required: true, onInput: onAccountId })]),
    error && item('p', 'session-error', error),
    h('button', { class: 'state-action', type: 'submit' }, '保存并进入'),
  ])])
}

const Workspace = defineComponent({
  setup() {
    const state = ref(parseShellState(new URLSearchParams(window.location.search).get('state')))
    const session = ref<WriterSession | null>(loadSession())
    const authorId = ref('')
    const view = ref(new URLSearchParams(window.location.search).get('view') || '工作台')
    const stats = ref<WritingStat[]>([])
    const books = ref<Book[]>([])
    const reviews = ref<Review[]>([])
    const title = ref('')
    const reviewBookId = ref('')
    const reviewVersions = ref('')
    const editorBookId = ref(localStorage.getItem('writer-last-book-id') || '')
    const volumeTitle = ref('')
    const volumeNumber = ref('1')
    const volumeId = ref('')
    const chapterTitle = ref('')
    const chapterNumber = ref('1')
    const chapterPolicy = ref('FREE')
    const chapterId = ref('')
    const draftId = ref('')
    const draftRevision = ref(0)
    const editorContent = ref('')
    const editorMessage = ref('')
    const message = ref('')
    const sessionToken = ref(session.value?.token || '')
    const sessionAccountId = ref(session.value?.accountId || '')
    const sessionError = ref('')

    function updateSession(event: Event) {
      event.preventDefault()
      try {
        session.value = saveSession({ token: sessionToken.value, accountId: sessionAccountId.value })
        sessionError.value = ''
        void load()
      } catch {
        sessionError.value = '请输入有效的 Access token 和 Account ID。'
      }
    }

    function signOut(event: Event) {
      event.preventDefault()
      clearSession()
      session.value = null
      sessionToken.value = ''
      sessionAccountId.value = ''
    }

    async function load() {
      if (!session.value) return
      try {
        const profile = await request<AuthorProfile>(session.value, '/writer/api/v1/author/profile')
        authorId.value = profile.id
        if (view.value === '数据中心') stats.value = await request<WritingStat[]>(session.value, `/writer/api/v1/authors/${authorId.value}/calendar`)
        if (view.value === '审核进度') reviews.value = await request<Review[]>(session.value, '/admin/api/v1/reviews')
      } catch (error) {
        if (error instanceof Error && error.message === 'HTTP 401') session.value = null
        message.value = '数据暂时不可用，请重新登录或稍后重试。'
      }
    }

    async function createBook(event: Event) {
      event.preventDefault()
      if (!title.value.trim() || !session.value || !authorId.value) {
        message.value = '未找到当前账号的作者资料，请先完成作者申请。'
        return
      }
      try {
        const book = await request<Book>(session.value, '/writer/api/v1/books', { method: 'POST', body: JSON.stringify({ author_id: authorId.value, title: title.value }) })
        books.value.unshift(book)
        localStorage.setItem('writer-last-book-id', book.id)
        editorBookId.value = book.id
        title.value = ''
        message.value = '作品已创建，可以继续添加卷和章节。'
      } catch (error) {
        if (error instanceof Error && error.message === 'HTTP 401') session.value = null
        message.value = '作品创建失败，请稍后重试。'
      }
    }

    async function createVolume(event: Event) {
      event.preventDefault()
      if (!session.value || !editorBookId.value.trim() || !volumeTitle.value.trim()) {
        editorMessage.value = '请先填写作品 ID 和卷标题。'
        return
      }
      try {
        const volume = await request<Volume>(session.value, `/writer/api/v1/books/${encodeURIComponent(editorBookId.value.trim())}/volumes`, { method: 'POST', body: JSON.stringify({ title: volumeTitle.value.trim(), number: Number(volumeNumber.value) }) })
        volumeId.value = volume.id
        editorMessage.value = '卷已创建，可以继续创建章节。'
      } catch {
        editorMessage.value = '卷创建失败，请确认作品属于当前作者且序号未重复。'
      }
    }

    async function createChapter(event: Event) {
      event.preventDefault()
      if (!session.value || !volumeId.value.trim() || !chapterTitle.value.trim()) {
        editorMessage.value = '请先填写卷 ID 和章节标题。'
        return
      }
      try {
        const chapter = await request<Chapter>(session.value, `/writer/api/v1/volumes/${encodeURIComponent(volumeId.value.trim())}/chapters`, { method: 'POST', body: JSON.stringify({ title: chapterTitle.value.trim(), number: Number(chapterNumber.value), commercial_policy: chapterPolicy.value }) })
        chapterId.value = chapter.id
        editorMessage.value = '章节已创建，可以开始写作。'
      } catch {
        editorMessage.value = '章节创建失败，请确认卷属于当前作者且序号未重复。'
      }
    }

    async function saveDraft(event: Event) {
      event.preventDefault()
      if (!session.value || !chapterId.value.trim()) {
        editorMessage.value = '请先创建章节。'
        return
      }
      try {
        const draft = await request<DraftSnapshot>(session.value, `/writer/api/v1/chapters/${encodeURIComponent(chapterId.value.trim())}/drafts`, { method: 'POST', body: JSON.stringify({ content: editorContent.value, save_mode: 'MANUAL', ...(draftRevision.value ? { expected_revision: draftRevision.value } : {}) }) })
        draftId.value = draft.id
        draftRevision.value = draft.revision
        editorMessage.value = '草稿已保存。'
      } catch {
        editorMessage.value = '草稿保存失败，可能是版本已更新，请重新加载后再试。'
      }
    }

    async function createVersion(event: Event) {
      event.preventDefault()
      if (!session.value || !chapterId.value.trim() || !draftId.value.trim()) {
        editorMessage.value = '请先保存草稿。'
        return
      }
      try {
        const version = await request<ChapterVersion>(session.value, `/writer/api/v1/chapters/${encodeURIComponent(chapterId.value.trim())}/versions`, { method: 'POST', body: JSON.stringify({ snapshot_id: draftId.value }) })
        editorMessage.value = `固定版本已生成 v${version.version}，可提交首发审核。`
      } catch {
        editorMessage.value = '固定版本生成失败，请先保存有效草稿。'
      }
    }

    async function submitFirstListing(event: Event) {
      event.preventDefault()
      if (!session.value || !reviewBookId.value.trim()) return
      const fixedVersionIds = reviewVersions.value.split(',').map((value) => value.trim()).filter(Boolean)
      if (!fixedVersionIds.length) {
        message.value = '请填写至少一个固定版本 ID。'
        return
      }
      try {
        const review = await request<Review>(session.value, `/writer/api/v1/books/${encodeURIComponent(reviewBookId.value.trim())}/first-listing-submissions`, { method: 'POST', body: JSON.stringify({ fixed_version_ids: fixedVersionIds }) })
        reviews.value.unshift(review)
        reviewVersions.value = ''
        message.value = '首发审核已提交，等待人工审核。'
      } catch {
        message.value = '首发审核提交失败，请确认作品和固定版本属于当前作者。'
      }
    }

    onMounted(load)

    function workspace() {
      if (view.value === '我的作品') return item('section', 'workspace-card', [item('div', 'panel-heading', [item('div', '', [item('p', 'top-kicker', 'WORKS'), item('h2', '', '作品空间')])]), h('form', { class: 'inline-form', onSubmit: createBook }, [h('input', { value: title.value, placeholder: '输入作品名', 'aria-label': '作品名', onInput: (event: Event) => { title.value = (event.target as HTMLInputElement).value } }), h('button', { class: 'writer-primary', type: 'submit' }, '创建作品')]), books.value.length ? item('ul', 'workspace-list', books.value.map((book) => h('li', { key: book.id }, [h('strong', {}, book.title), h('span', {}, `${book.lifecycle} · ${book.visibility}`)]))) : item('div', 'panel-empty', [item('div', 'empty-line', '+'), item('h3', '', '还没有作品'), item('p', '', '从这里创建第一本作品。')])])
      if (view.value === '章节编辑') return item('section', 'workspace-card editor-card', [item('div', 'panel-heading', [item('div', '', [item('p', 'top-kicker', 'CHAPTER EDITOR'), item('h2', '', '章节编辑')]), item('p', 'workspace-note', '作品、卷、章节、草稿和固定版本按顺序保存。')]), item('div', 'editor-grid', [h('form', { class: 'editor-step', onSubmit: createVolume }, [h('h3', {}, '1. 创建卷'), h('label', {}, ['作品 ID', h('input', { value: editorBookId.value, required: true, 'aria-label': '作品 ID', onInput: (event: Event) => { editorBookId.value = (event.target as HTMLInputElement).value } })]), h('label', {}, ['卷标题', h('input', { value: volumeTitle.value, required: true, 'aria-label': '卷标题', onInput: (event: Event) => { volumeTitle.value = (event.target as HTMLInputElement).value } })]), h('label', {}, ['卷序号', h('input', { value: volumeNumber.value, type: 'number', min: 1, required: true, 'aria-label': '卷序号', onInput: (event: Event) => { volumeNumber.value = (event.target as HTMLInputElement).value } })]), h('button', { class: 'writer-primary', type: 'submit' }, '创建卷'), volumeId.value && h('output', {}, `卷 ID：${volumeId.value}`)]), h('form', { class: 'editor-step', onSubmit: createChapter }, [h('h3', {}, '2. 创建章节'), h('label', {}, ['卷 ID', h('input', { value: volumeId.value, required: true, 'aria-label': '卷 ID', onInput: (event: Event) => { volumeId.value = (event.target as HTMLInputElement).value } })]), h('label', {}, ['章节标题', h('input', { value: chapterTitle.value, required: true, 'aria-label': '章节标题', onInput: (event: Event) => { chapterTitle.value = (event.target as HTMLInputElement).value } })]), h('label', {}, ['章节序号', h('input', { value: chapterNumber.value, type: 'number', min: 1, required: true, 'aria-label': '章节序号', onInput: (event: Event) => { chapterNumber.value = (event.target as HTMLInputElement).value } })]), h('label', {}, ['商业策略', h('select', { value: chapterPolicy.value, 'aria-label': '商业策略', onChange: (event: Event) => { chapterPolicy.value = (event.target as HTMLSelectElement).value } }, [h('option', { value: 'FREE' }, '免费'), h('option', { value: 'VIP' }, 'VIP')])]), h('button', { class: 'writer-primary', type: 'submit' }, '创建章节'), chapterId.value && h('output', {}, `章节 ID：${chapterId.value}`)]), h('form', { class: 'editor-step editor-writing', onSubmit: saveDraft }, [h('h3', {}, '3. 写作与版本'), h('label', {}, ['章节正文', h('textarea', { value: editorContent.value, required: true, 'aria-label': '章节正文', rows: 12, onInput: (event: Event) => { editorContent.value = (event.target as HTMLTextAreaElement).value } })]), item('div', 'editor-actions', [h('button', { class: 'writer-primary', type: 'submit' }, '保存草稿'), h('button', { class: 'secondary-action', type: 'button', onClick: createVersion }, '生成固定版本')]), draftId.value && h('output', {}, `草稿 ID：${draftId.value} · 修订 ${draftRevision.value}`)]), editorMessage.value && item('p', 'action-message', editorMessage.value)]),])
      if (view.value === '审核进度') return item('section', 'workspace-card', [item('p', 'top-kicker', 'REVIEW QUEUE'), item('h2', '', '固定版本审核'), h('form', { class: 'inline-form', onSubmit: submitFirstListing }, [h('input', { value: reviewBookId.value, placeholder: '作品 ID', 'aria-label': '作品 ID', required: true, onInput: (event: Event) => { reviewBookId.value = (event.target as HTMLInputElement).value } }), h('input', { value: reviewVersions.value, placeholder: '固定版本 ID，逗号分隔', 'aria-label': '固定版本 ID', required: true, onInput: (event: Event) => { reviewVersions.value = (event.target as HTMLInputElement).value } }), h('button', { class: 'writer-primary', type: 'submit' }, '提交首发审核')]), reviews.value.length ? item('ul', 'workspace-list', reviews.value.map((review) => h('li', { key: review.id }, [h('strong', {}, review.book_id), h('span', {}, `${review.status} · ${review.fixed_version_ids.length} 个版本`)]))) : item('div', 'panel-empty', [item('div', 'empty-line', '✓'), item('h3', '', '暂无审核记录'), item('p', '', '提交固定版本后，进度会显示在这里。')])])
      if (view.value === '数据中心') return item('section', 'workspace-card', [item('p', 'top-kicker', 'METRIC CENTER'), item('h2', '', '创作日历'), stats.value.length ? item('div', 'stat-table', stats.value.map((stat) => item('div', 'stat-row', [h('span', {}, stat.business_date), h('strong', {}, `${stat.words.toLocaleString()} 字`), h('small', {}, `目标 ${stat.goal.toLocaleString()}`)]))) : item('div', 'panel-empty', [item('div', 'empty-line', '—'), item('h3', '', '暂无日统计'), item('p', '', '保存草稿后，写作事实会进入日历。')])])
      if (view.value === '收益与结算') return item('section', 'workspace-card', [item('p', 'top-kicker', 'AUTHOR FINANCE'), item('h2', '', '收益与结算'), item('div', 'finance-rows', ['收入明细', '已锁定结算单', '可提现余额'].map((label) => item('div', 'finance-row', [h('span', {}, label), h('strong', {}, '--'), h('small', {}, '以 AuthorFinance 事实为准')]))) , h('a', { class: 'writer-primary', href: '#finance' }, '查看财务流程')])
      if (view.value === '创作学院') return item('section', 'workspace-card', [item('p', 'top-kicker', 'LEARNING'), item('h2', '', '创作学院'), item('div', 'academy-grid', ['开篇', '人物', '剧情', '平台规则', '签约', '版权'].map((label) => item('a', 'academy-item', [h('strong', {}, label), h('span', {}, '查看课程 →')]))), item('p', 'workspace-note', '课程内容由运营 CMS 管理，正文不会执行任意脚本。')])
      if (view.value === '账号设置') return item('section', 'workspace-card', [item('p', 'top-kicker', 'ACCOUNT'), item('h2', '', '账号设置'), item('div', 'setting-line', [h('span', {}, '当前账号'), h('strong', {}, session.value?.accountId || '未登录')]), item('div', 'setting-line', [h('span', {}, '作者资料'), h('strong', {}, '由作者服务返回')]), item('p', 'workspace-note', '笔名修改会保留历史记录，签约后需经过独立审核。')])
      return item('section', 'workspace-card', [item('p', 'top-kicker', 'NEXT CHAPTER'), item('h2', '', '今天也写一点。'), item('p', 'workspace-note', '作品、草稿、固定版本审核和结算单都从明确的 Domain 命令产生。'), item('div', 'quick-actions', [h('a', { class: 'writer-primary', href: '?view=我的作品' }, '管理作品'), h('a', { class: 'secondary-action', href: '?view=数据中心' }, '查看创作数据')])])
    }

    return () => !session.value
      ? sessionView(sessionToken.value, sessionAccountId.value, sessionError.value, updateSession, (event) => { sessionToken.value = (event.target as HTMLInputElement).value }, (event) => { sessionAccountId.value = (event.target as HTMLInputElement).value })
      : state.value !== 'ready' ? stateView(state.value) : item('div', 'writer-shell', [item('aside', 'writer-sidebar', [item('div', 'writer-logo', ['墨页', item('small', '', 'WRITER CENTER')]), item('div', 'workspace-label', '创作空间'), item('nav', 'writer-nav', ['工作台', '我的作品', '章节编辑', '审核进度', '数据中心', '收益与结算'].map((label) => link(label, label === view.value))), item('div', 'sidebar-bottom', [link('创作学院', view.value === '创作学院'), link('账号设置', view.value === '账号设置'), h('a', { class: 'side-link', href: '#sign-out', onClick: signOut }, '退出登录')])]), item('div', 'writer-content', [item('header', 'writer-topbar', [item('div', '', [item('p', 'top-kicker', 'WRITER CENTER'), item('h1', '', view.value)]), item('div', 'top-actions', [h('span', {}, session.value.accountId)])]), item('main', 'writer-main', [item('section', 'writer-welcome', [item('div', '', [item('p', 'top-kicker', 'AUTHOR WORKSPACE'), item('h2', '', view.value === '工作台' ? '今天也写一点。' : view.value), item('p', 'welcome-copy', message.value || '业务状态和操作结果会在这里反馈。')]), h('a', { class: 'writer-primary', href: '?view=我的作品' }, '进入作品')]), item('section', 'writer-stats', [item('article', 'stat-block', [h('span', {}, '作品'), h('strong', {}, String(books.value.length)), h('small', {}, '当前作者范围')]), item('article', 'stat-block', [h('span', {}, '今日字数'), h('strong', {}, stats.value.length ? String(stats.value.at(-1)?.words ?? '--') : '--'), h('small', {}, '由写作事实汇总')]), item('article', 'stat-block', [h('span', {}, '结算状态'), h('strong', {}, '待查'), h('small', {}, '由财务域提供')])]), workspace(), item('section', 'writer-tip', [h('span', { class: 'tip-index' }, '01'), item('div', '', [h('h3', {}, '发布提醒'), h('p', {}, '发布章节会创建固定版本并进入审核工作流。')]), h('a', { href: '?view=审核进度' }, '查看审核 →')])])])])
  },
})

createApp(Workspace).mount('#app')
