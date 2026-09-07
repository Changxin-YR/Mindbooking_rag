# Reader Web interaction audit

| 控件 | 页面 | 原问题 | 修复 | 对应 API | 结果 |
| --- | --- | --- | --- | --- | --- |
| 顶部搜索 | 全部 Reader 页面 | 表单回到首页，曾存在跨项目跳转风险 | Reader `/search` 路由、统一 API base、客户端兼容拦截 | `GET /api/v1/search` | 已验证 URL 不含 ADP |
| 开始阅读 | 首页 | 与探索按钮执行同一动作 | 登录用户恢复书架进度，无历史进入发现页 | Bookshelf + Progress + Book detail | 已实现 |
| 探索更多好书 | 首页 | 滚动到“今天读什么” | 进入 `/library?mode=discover` | `GET /api/v1/books` | 已实现 |
| 换一批 | 首页 | 眼睛图标无响应 | URL recommendation page 改变并重新排序当前 API 结果 | `GET /api/v1/books` | 已实现 |
| 分类/频道/状态/商业筛选 | 首页、书库、搜索 | 只改变 UI，不重新查询 | 条件写入 URL 并重新请求 | `GET /api/v1/books` / `GET /api/v1/search` | 已实现 |
| 加入书架 | 作品详情 | Toast 后按钮不变 | 读取真实状态，POST/DELETE 后切换按钮 | Bookshelf API | 已实现 |
| 关注作者 | 作品详情 | Toast 后按钮不变 | 读取真实状态，POST/DELETE 后切换按钮 | Follow API | 已实现 |
| 目录/上下章/自动阅读 | 阅读器 | 阅读器仅有占位按钮 | 目录、章节导航、滚动/分页、自动滚动 | Chapter API + Progress API | 已实现 |
| 阅读设置 | 阅读器 | 跳到账户设置 | Drawer 即时写入 localStorage，登录用户同步 reading_preferences | `GET/PUT /api/v1/accounts/{account_id}/reading-preferences` | 已实现 |
| 书签/TTS/全屏 | 阅读器 | 无真实动作 | 浏览器能力 + TTS 权限检查 | TTS API | 已实现 |
| 榜单完整榜单/说明 | 首页、排行榜 | 静态 UI 无响应 | `/rankings/:kind` 与说明弹窗 | Ranking API | 已实现 |
| 钱包充值 | 钱包 | 内部 code 泄漏、实名无入口 | 中文产品名、REAL_NAME_REQUIRED 弹窗 | Recharge + RealName API | 已实现 |
| 客服分类/提交 | 客服 | 选择不回显、仅 Toast | code 绑定、编号回显、刷新读取列表 | Support Ticket API | 已实现 |
| 账号资料 | 账户设置 | 只展示随机内部 ID，昵称/登录名无法修改 | 展示稳定 account_no，并通过受权限保护的 profile API 更新昵称/登录名 | `GET/PATCH /api/v1/iam/accounts/{account_id}/profile` | 已实现 |
