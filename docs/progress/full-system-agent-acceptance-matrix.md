# Full System Agent Acceptance Matrix

更新时间：2026-09-07

本矩阵按当前 Admin UI、OpenAPI、Application Service 和注册 Tool 实际读取生成。Agent 分类为 `AGENT_CAPABLE`、`HUMAN_CONFIRM_REQUIRED`、`HUMAN_ONLY`；后两类必须有业务或法律原因，不能仅以“风险高”规避 Agent 能力。

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
| A-05 | Admin | 用户 360 | 脱敏查看用户 | /admin/api/v1/user-360 POST | AdminCenter | account projection、PII audit | admin.access；敏感字段另需 admin.user360.sensitive | account/assigned | READ | user360.lookup（默认脱敏；敏感字段仍受权限） | AGENT_CAPABLE | PII masking + scope regression |
| A-06 | Admin | 财务查询 | 查看/登记/重试对账待处理 | /admin/api/v1/reconciliation/** | Governance/Commerce | credit_pending、wallet ledger、Outbox | finance.read/write | batch/account；当前全局查询要求 ALL/GLOBAL | READ / HUMAN_CONFIRM_REQUIRED | governance.reconciliation.pending/list；修复写入需原 Finance API 的确认/审批边界 | AGENT_CAPABLE（查询）；HUMAN_CONFIRM_REQUIRED（修复） | SQL finance/concurrency + Agent registry |
| A-07 | Admin | 风险与审批 | 观察/冻结风险信号 | /admin/api/v1/risk/** | RiskService/ApprovalService | risk signals、watchlist、approvals、Audit | risk.read/write | account/order/assigned | READ / CRITICAL | risk.get_signal；risk.freeze + PendingAction | AGENT_CAPABLE（查询）；HUMAN_CONFIRM_REQUIRED（冻结） | scoped risk + confirmation regression |
| A-08 | Admin | 参数中心 | 创建参数草案、Checker 生效 | /admin/api/v1/parameters/** | GovernanceService | parameter versions、approvals、Outbox | governance.write | parameter/global | HIGH / CRITICAL | governance.parameter.draft；governance.parameter.approve + PendingAction | AGENT_CAPABLE（Maker/Checker 分离；服务端强制 maker_actor != checker_actor） | Maker/Checker actor inequality tests |
| A-09 | Admin | 会员配置 | 查询会员状态、创建会员方案、配置章节商业策略 | /admin/api/v1/membership/**、/chapters/** | Membership/Commerce/Content | plans、commercial policies、orders | governance.read/write、commerce.write | account/book scope；全局方案要求 ALL/GLOBAL | READ / HUMAN_CONFIRM_REQUIRED | membership.status；membership.plan.create；membership.chapter_policy.update + PendingAction | AGENT_CAPABLE（查询）；HUMAN_CONFIRM_REQUIRED（配置写入） | registry/scope tests；sandbox membership tests |
| A-10 | Admin | 文件与审计 | 入队 Outbox、查询审计 | /admin/api/v1/outbox/**、/agent/audits | Governance/AgentAudit | outbox、agent_audit_events | governance.write/agent.audit.read | event/actor | READ / HIGH | approval.get；Agent audits 由 agent.audit.read 查询；Outbox 投递保留人工运维入口 | AGENT_CAPABLE（审计查询）；HUMAN_ONLY（Outbox 运维投递，需独立运维控制） | SQL audit tests |
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
- `HUMAN_CONFIRM_REQUIRED` 表示 Agent 可识别并生成影响摘要/PendingAction，由同一 Staff 会话确认；Maker/Checker 仍要求不同 authenticated actor。`HUMAN_ONLY` 仅用于独立第二审批人、法律签署或明确运维边界，并记录具体原因。
