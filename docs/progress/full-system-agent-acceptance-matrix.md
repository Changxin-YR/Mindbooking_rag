# Full System Agent Acceptance Matrix

更新时间：2026-09-07

本矩阵按当前 Admin UI、OpenAPI、Application Service 和注册 Tool 实际读取生成。MANUAL_ONLY 表示该操作保留人工入口并受原有审批边界保护；没有对应 Tool 的操作不计为 Agent 已覆盖。

| ID | 端/域 | 页面或入口 | 人工动作 | API / Method | Application Service | DB / 事实 | Permission | DataScope | Risk | Agent Tool | Test / 状态 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| R-01 | Reader | 目录、搜索 | 查询公开作品 | /api/v1/books GET、/api/v1/search GET | Content/Search | books、metadata、search projection、Outbox | public | public | READ | N/A（Reader 不暴露后台 Agent） | Reader Vitest、build PASS |
| R-02 | Reader | 阅读器 | 读取章节、TTS | /api/v1/books/{book}/chapters/{chapter}/tts GET | ContentAccess/Reading | chapters、versions、entitlements | account/session | account | READ | N/A | test_reading_tts.py PASS |
| R-03 | Reader | 书架 | 加入/移除书架 | /api/v1/library/** | LibraryService | bookshelf、entitlement | account | account | LOW | N/A | library module tests PASS |
| R-04 | Reader | 钱包/购买 | 充值、购买章节 | /api/v1/wallet/**、/api/v1/chapters/** | Commerce/Wallet | wallet lots/ledger、orders、entitlements、revenue | account | account | CRITICAL | N/A | SQL commerce evidence available; sandbox provider |
| W-01 | Writer | 作品/章节编辑器 | 保存草稿、发布送审 | /writer/api/v1/** | Author/Content/Review | draft snapshots、versions、review submissions、Outbox | author/content.write | author | HIGH | N/A | Writer tests/build PASS |
| W-02 | Writer | 合同/财务 | 签署合同、提现申请 | /writer/api/v1/finance/** | AuthorFinance | contracts、revenue ledger、settlement、payout | author.finance | author | CRITICAL | N/A | Maker/Checker remains human boundary |
| A-01 | Admin | 内容审核 | 查询审核队列 | /admin/api/v1/reviews GET | ReviewService | review_submissions、review_tasks | review.read | ALL/GLOBAL/ASSIGNED | READ | review.list_pending | Agent API + advanced workflow |
| A-02 | Admin | 内容审核 | 审核通过/拒绝/退回 | /admin/api/v1/reviews/{id}/decisions POST | ReviewService.decide | review_decisions、submission、published versions、Outbox | review.decide | submission scope | HIGH | review.decide + PendingAction | natural-language/confirmation tests |
| A-03 | Admin | 作者与作品 | 查询作品清单/详情 | /admin/api/v1/books GET、ContentService | ContentService | books、metadata | content.read | BOOK/CUSTOM/ASSIGNED/ALL | READ | content.list_books、content.get_book | scope and actor tests |
| A-04 | Admin | 总览/客服 | 查看客服运营指标 | /admin/api/v1/support/dashboard GET | AdminCenter/Support | tickets、CSAT、alerts | support.read | assigned scope | READ | support.dashboard | registry/API regression |
| A-05 | Admin | 用户 360 | 脱敏查看用户 | /admin/api/v1/user-360 POST | AdminCenter | account projection、PII audit | admin.access/sensitive | account/assigned | HIGH | MANUAL_ONLY | UI/API existing; no Agent Tool registered |
| A-06 | Admin | 财务查询 | 登记/重试对账待处理 | /admin/api/v1/reconciliation/** | Governance/Commerce | credit_pending、wallet ledger、Outbox | governance.read/write | batch/account | CRITICAL | MANUAL_ONLY | SQL finance tests; approval boundary |
| A-07 | Admin | 风险与审批 | 观察/冻结风险信号 | /admin/api/v1/risk/** | RiskService/ApprovalService | risk signals、watchlist、approvals、Audit | risk.read/write | account/order/assigned | CRITICAL | MANUAL_ONLY | role workflow tests |
| A-08 | Admin | 参数中心 | 创建参数草案、Checker 生效 | /admin/api/v1/parameters/** | GovernanceService | parameter versions、approvals、Outbox | governance.write | parameter | CRITICAL | MANUAL_ONLY | Maker/Checker tests |
| A-09 | Admin | 会员配置 | 配置会员与章节商业策略 | /admin/api/v1/membership/**、/chapters/** | Membership/Commerce | plans、commercial policies、orders | governance.write/commerce.write | configured resource | HIGH | MANUAL_ONLY | sandbox membership tests |
| A-10 | Admin | 文件与审计 | 入队 Outbox、查询审计 | /admin/api/v1/outbox/**、/agent/audits | Governance/AgentAudit | outbox、agent_audit_events | governance.write/agent.audit.read | event/actor | HIGH | MANUAL_ONLY for Outbox; audit is API-only | SQL audit tests |
| AG-01 | Admin Agent | 会话列表/消息 | 创建会话、发送自然语言 | /admin/api/v1/agent/sessions POST/GET、/agent/messages POST | Agent runtime + Fake/DeepSeek adapter | agent session context (runtime), AgentAudit | agent.execute | authenticated Staff scopes | READ/WRITE | Orchestrator | test_agent_natural_language.py、browser smoke |
| AG-02 | Admin Agent | Tool registry | 查看当前可用工具 | /admin/api/v1/agent/resources GET、MCP tools/list | AgentGateway | registry metadata | agent.execute + tool permission | authenticated Staff scopes | READ | registry | API tests |
| AG-03 | Admin Agent | 直接 Tool | 查询作品 | /admin/api/v1/agent/tools/execute POST、MCP tools/call | AgentGateway → ContentService | books/metadata | content.read | resource resolver | READ | content.get_book、content.list_books | cross-scope/actor regression |
| AG-04 | Admin Agent | 审核助手 | 查询并提交审核决定 | /agent/messages、/agent/actions/{id}/confirm | AgentGateway → ReviewService | review decision、published version、Outbox、Audit | review.read/decide | submission resolver | HIGH | review.list_pending、review.decide | pending/verification tests |
| AG-05 | Admin Agent | 支持助手 | 查看授权范围客服指标 | /agent/tools/execute POST | AgentGateway → AdminCenter | support facts | support.read | staff scope | READ | support.dashboard | permission registry test |
| AG-06 | Admin Agent | 高风险确认 | 确认/取消动作 | /agent/actions/{id}/confirm POST、/cancel POST | PendingActionStore → AgentGateway | agent_pending_actions、AgentAudit | agent.execute + original permission | actor/session/resource scope | HIGH | shared confirmation protocol | SQL store + replay tests |
| SEC-01 | Cross-cutting | Staff 登录 | 签发/撤销 Staff session | /admin/api/v1/auth/staff/sessions POST/DELETE | StaffAuth/SessionSigner | staff credentials/sessions/MFA audit | staff auth | staff identity | CRITICAL | Agent inherits session | auth/RBAC tests |
| SEC-02 | Cross-cutting | Audit | 查询 Agent 执行记录 | /admin/api/v1/agent/audits GET | SqlAgentAuditSink | append-only agent_audit_events | agent.audit.read, sensitive split | actor/tool filters | HIGH | N/A | audit API/SQL tests |

## 当前覆盖边界

- Agent 的身份、权限和 DataScope 始终来自验证后的 Staff Bearer session；请求中的 actor_id 只用于一致性校验。
- Tool permission 与 Staff permission 交集生效；资源通过当前 Staff DataScope resolver 后才可执行。
- 高风险写操作不直接执行；PendingAction 绑定 actor、session、tool、arguments hash、TTL 和一次性状态，确认时再次检查权限/scope。
- review.decide 走 ReviewService，执行后重新读取 submission 验证状态；Agent 不直接操作数据库。
- SQL 部署的 PendingAction 使用 agent_pending_actions；内存模式只用于确定性测试和本地开发。
