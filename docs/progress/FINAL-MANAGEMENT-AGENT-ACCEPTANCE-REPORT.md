# Management and Agent Acceptance Report

更新时间：2026-09-08

## 结论

**A：通过。**

Portfolio Acceptance 的管理系统、Agent 安全边界、授权写入、真实 MySQL 等价链、CI 和受控 Live DeepSeek 验收均已通过。真实支付、银行、税务 Provider 认证属于本作品集项目范围外。

## 变更基线

- 远端基准：ec31dde34ce4f28b124041cefa9adfc09fc68345
- 工作分支：codex/v1.2-full-audit
- CI 修复提交：55e4090 fix(ci): restore reproducible quality gates
- Agent/管理系统实现提交：5203fd4（含前序 94d8dd9、67beaed）
- 环境：Windows、Python 3.x、Node 24、pnpm 11.22.0；时间：2026-09-08（Asia/Shanghai）
- Validated Live Acceptance SHA：c35c7b0e020e0d58f386ca17bb7afcf13864c7e9
- Live Acceptance Commit：`test(agent): certify live DeepSeek acceptance`
- PR：#1（<https://github.com/Changxin-YR/Mindbooking_rag/pull/1>）
- Final Acceptance CI：34230223413
- Docker Compose：MySQL、Backend、Admin、Reader、Writer、Harness、OpenSearch、Redis、RabbitMQ、ClickHouse、MinIO、Nginx 全部 healthy；Alembic head=`0042_agent_audit_pending_action`

## 已修复

| Bug ID | Severity | 模块 | 根因 | 修复 | 回归证据 | 状态 |
| --- | --- | --- | --- | --- | --- | --- |
| P0-A001 | P0 | Agent write | 写 Tool 被统一拒绝 | 受权限、DataScope、Risk、PendingAction 和业务回调约束的写执行 | test_agent_pending_actions.py、全量 pytest | FIXED |
| P0-A002 | P0 | Tool registry | 只有单一内容查询 Tool | 注册内容列表/详情、审核队列/决定、客服看板 Tool，并暴露显式 schema/policy | Agent registry/API tests | FIXED（覆盖范围见矩阵） |
| P0-A003 | P0 | Agent API | 会话、消息、确认路由缺失 | sessions/messages/actions confirm/cancel、MCP、Tool execute 路由 | OpenAPI route tests、browser smoke | FIXED |
| P0-A004 | P0 | Admin UI | 没有真实 Agent workspace | 增加会话列表、消息、Tool 摘要、PendingAction 风险卡、确认/取消和失败状态 | Admin Vitest/typecheck/build + Playwright smoke | FIXED |
| P0-A005 | P0 | Runtime | 没有确定性编排/Model Port | AgentModelPort、DeepSeek adapter、Fake adapter 和多轮本地编排 | natural-language tests | FIXED |
| P0-A006 | P0 | Equivalence | 没有 Agent 业务结果验证 | 写操作执行后重新查询并校验业务状态 | review result-validator tests | FIXED for registered Agent writes |
| P0-A007 | P1 | DataScope | Tool 只看 permission | 资源级 scope resolver；review/content 均按 Staff scope 查询 | cross-scope regression | FIXED |
| P1-CI001 | P1 | Backend CI | TestClient 缺 httpx | dev group 固定 httpx>=0.28,<1 并由 CI 安装 | pytest collection/full run | FIXED |
| P1-CI002 | P1 | Frontend CI | pnpm cache 在启用 pnpm 前执行 | 固定 Node/pnpm，先 action-setup 再 setup-node cache | workspace test/typecheck/build | FIXED |
| P1-S001 | P1 | Secrets | 生产可能使用默认值 | production runtime 对 persistence、provider、secret 长度/默认前缀 fail closed | settings tests | FIXED |
| P1-T001 | P1 | Prompt injection | 缺少自然语言注入覆盖 | fake orchestrator 拒绝权限声明、改 actor、直连 DB 等注入 | natural-language injection test | FIXED |
| P1-T002 | P1 | Tool injection | 业务文本可能被当作指令 | 扫描指令区并将《书名》作为 DATA；含注入样本文本的书名查询回归 | tool-injection regression | FIXED |
| P1-T003 | P1 | RBAC/DataScope | 缺资源级 Agent 矩阵 | Staff session + permission + scope resolver + actor mismatch 回归 | Agent HTTP regression | FIXED |
| P1-T007 | P1 | Confirmation | 只用客户端 boolean | 服务端 PendingAction、hash、actor/session 绑定、TTL、一次性状态和 SQL 存储 | pending action + SQL store tests | FIXED |

## 自动化证据

| Gate | 命令/场景 | 结果 |
| --- | --- | --- |
| Backend | python -m pytest -q | 362 passed, 0 failed, 0 skipped |
| Formatting | python -m ruff format --check src tests alembic | PASS |
| Lint | python -m ruff check src tests alembic | PASS |
| Types | python -m mypy src | PASS, 147 source files |
| Alembic | Compose MySQL `alembic upgrade head` | PASS, head `0042_agent_audit_pending_action` |
| Frontend tests | pnpm -r test | PASS |
| Frontend typecheck | pnpm -r typecheck | PASS |
| Frontend builds | pnpm -r build | Reader/Writer/Admin PASS |
| Agent targeted | Agent/session/security tests | PASS |
| Browser smoke | local FastAPI + Admin Vite + Playwright: login → Agent session → query | PASS |
| Compose QA | `qa_compose_smoke.py`, `qa_v12_smoke.py`, `qa_writer_editor_smoke.py`, `qa_sql_commercial_e2e.py`, `qa_mysql_concurrency.py`, `qa_mysql_load.py`, `qa_role_e2e.py`, `qa_harness_e2e.py`, `qa_advanced_workflows.py` | ALL PASS |
| Agent MySQL E2E | `scripts/qa_agent_mysql_e2e.py` | PASS：人工/Agent review 语义相等；PendingAction `EXECUTED`；SQL Agent Audit 已关联 |
| Live DeepSeek | `LIVE_LLM=1 python scripts/qa_agent_live_deepseek.py` | PASS：官方 provider/model、HTTP 200、真实生成、查询/多轮/PendingAction/确认/RBAC/DataScope/Injection/异常分类 |
| Frontend | `pnpm -r test`、`pnpm -r typecheck`、`pnpm -r build` | PASS |

## 第二轮 Exact-SHA CI

| Workflow | Run / Job | 结论 |
| --- | --- | --- |
| Foundation | [run 34154842708](https://github.com/Changxin-YR/Mindbooking_rag/actions/runs/34154842708) / Foundation configuration | PASS |
| Backend | [run 34154842708](https://github.com/Changxin-YR/Mindbooking_rag/actions/runs/34154842708) / Backend tests and quality | PASS (`362 passed`) |
| Frontend | [run 34154842708](https://github.com/Changxin-YR/Mindbooking_rag/actions/runs/34154842708) / Frontend tests and builds | PASS |

本轮后端测试共 362 个通过，无 skip；pytest 仅有第三方弃用警告。

## 最终 Live DeepSeek 验收 CI

| Workflow | Run / Job | 结论 |
| --- | --- | --- |
| Foundation | [run 34230223413](https://github.com/Changxin-YR/Mindbooking_rag/actions/runs/34230223413) / Foundation configuration | PASS |
| Backend | [run 34230223413](https://github.com/Changxin-YR/Mindbooking_rag/actions/runs/34230223413) / Backend tests and quality | PASS（362 passed） |
| Frontend | [run 34230223413](https://github.com/Changxin-YR/Mindbooking_rag/actions/runs/34230223413) / Frontend tests and builds | PASS |

## 关键安全与业务不变量

- actor 由验证后的 Staff session claims 决定；请求 actor 不一致直接 403。
- Tool permission 与 Staff permission 交集生效；资源通过当前 Staff DataScope resolver 后才可执行。
- 高风险写操作不直接执行；PendingAction 绑定 actor、session、tool、arguments hash、TTL、一次性状态，确认时再次检查权限/scope。
- review.decide 走 ReviewService，执行后重新读取 submission 验证状态；Agent 不直接操作数据库。
- SQL 部署的 PendingAction、Agent audit 和业务 Outbox 使用现有 Alembic 链；Agent audit 仍为 append-only。
- Prompt/Tool injection 不能改变 actor、permission、scope 或访问数据库。
- 生产 APP_ENV=production 对 SQL persistence、非 sandbox provider 和三类核心 secret fail closed。

## 外部验证项

| 项目 | 状态 | 证据/原因 |
| --- | --- | --- |
| LIVE_LLM | PASS | `provider=deepseek-official`、`model=deepseek-v4-flash`、HTTP 200、真实响应、延迟约 917 ms；Live 场景全部通过 |
| MySQL Agent E2E | PASS | `scripts/qa_agent_mysql_e2e.py` 通过人工/Agent 审核等价、PendingAction/Audit 持久化核对 |
| Compose/Browser full role E2E | PASS | Compose smoke、Harness browser E2E、Reader/Writer/Admin builds 全部通过 |
| Production Provider Certification | OUT OF SCOPE | Portfolio / resume project; no real-money production operation |
| Sandbox payment/payout | PASS | success、failure、timeout、duplicate callback、invalid signature、replay protection、idempotency 均已覆盖 |
| Session restart / second runtime | PASS | SQL session store 重建后恢复消息、实体上下文并保持 Staff 隔离 |
| Multi-instance logical context | PASS（logical SQL store） | 两个独立 `SqlAgentSessionStore` 实例共享 SQL session/message/context；并发版本冲突返回 `409 AGENT_SESSION_VERSION_CONFLICT`。未宣称生产容量/DR。 |

## Gate 判定

- Gate 1 管理系统：API/UI/真实 Compose MySQL/SQL PASS。
- Gate 2 Agent：Fake NLU、Tool、授权写、结果验证、审计 PASS。
- Gate 3 权限安全：RBAC、DataScope、actor 防伪、注入拒绝、确认重放保护 PASS。
- Gate 4 真实业务：人工、Agent、Hybrid、真实 MySQL Agent 等价链 PASS；Live DeepSeek PASS。

当前不存在已复现的 P0/P1 代码缺陷。`Platform Engineering=A`、`Agent Security=A`、`Agent Business Execution=A`、`LIVE DeepSeek=PASS`、`Sandbox Payment/Payout=PASS`；`Production Provider Certification=OUT OF SCOPE`。因此 Portfolio Acceptance 总等级为 **A：通过**。
