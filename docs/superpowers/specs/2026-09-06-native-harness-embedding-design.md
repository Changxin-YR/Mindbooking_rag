# 原生 DeepSeek Harness 工作台嵌入设计

## 目标

在运营后台内嵌本地 DeepSeek Harness 的原生 `dsh web` 工作台，保留其原有会话、历史、工具调用、运行状态、设置和确认交互。Harness 源码与前端组件不复制、不重写；平台只提供启动、认证桥接和业务工具适配。

## 架构

Admin Web 登录后调用后台 `harness-url` 接口。后台依据当前 Staff 会话创建或复用该账号专属的原生 `dsh web` 子进程和独立 `DSH_HOME`，读取 Harness 打印的带 token URL 返回给浏览器。Admin 页面将 URL 放入受限 iframe。Harness 的 MCP 配置指向现有 `/admin/api/v1/agent/mcp`，请求携带当前 Staff access token 和 Harness session 标识；MCP 每次调用仍执行 StaffAuth、RBAC、DataScope 和业务 Service 校验。

## 安全边界

- 每个 `actor_id + Staff session_id` 使用独立 Harness home、端口和浏览器会话。
- Harness URL token 只从已认证 Admin API 返回，不写入源码或持久日志。
- iframe 只在 Admin Console 渲染；Reader/Writer 不增加入口或接口。
- Agent 不能直连数据库，写操作继续受业务规则、确认和审计约束。
- Staff 登出或 token 变化后，旧 Harness 会话不可复用。

## 运行与降级

Harness 使用仓库提供的 `dsh web --no-open --host 127.0.0.1 --port <free-port>`。若本机缺少构建产物、Node 运行时或模型凭据，Admin 显示友好错误，不影响原有后台操作。后台保留当前 MCP/SDK 路径作为 API 兼容能力，但 UI 入口只展示原生工作台。

## 验收

登录运营后台后可打开原生 Harness 页面并创建多轮会话；刷新后会话仍由 Harness 管理；两个 Staff 账号的 URL、cookie、DSH_HOME 和工具权限互相隔离；MCP 调用的权限拒绝、DataScope、Prompt Injection 和审计测试保持通过。
