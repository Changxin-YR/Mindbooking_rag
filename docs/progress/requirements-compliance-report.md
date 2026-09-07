# 当前实现与最终需求文档符合性报告

审计基线：

- 唯一事实来源：`C:\Users\27363\Documents\Codex\2026-09-04\bnag\outputs\平台项目最终需求与技术设计规格说明书.md`
- 仓库入口：`docs/business/V1.2-FINAL-MASTER-DEVELOPMENT-SPEC-V2.md`
- 冻结正文：`docs/business/V1.2-FINAL-MASTER-DEVELOPMENT-SPEC-V2.parts/part-01.md` 至 `part-10.md`
- 审计基线提交：`e1d165d`；本报告包含其后的未提交 continuation 工作树证据。

## 判定口径

`A` 完全符合；`B` 基本符合但有缺陷；`C` 部分实现；`D` 未实现；`E` 与冻结规则冲突；`F` 超出需求范围或需关闭。风险等级使用 `P0` 至 `P3`，其中 `P0` 为资金、数据损坏、权限或安全风险。

## 需求符合性

| ID | 模块 | 文档要求 | 当前实现 | 符合状态 | 问题 | 风险等级 | 修复方案 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| REQ-001/BR-001 | 三端平台 | Reader、Writer、Admin 共享统一业务能力 | 三个前端和 FastAPI 模块均存在，页面与域服务仍不完整 | C | 不能作为商业级平台交付 | P1 | 以垂直闭环补全页面/API/持久化/权限/测试 |
| BR-002/BR-003 | 游客与登录分级 | 公共阅读可游客访问，资产、云端数据、互动要求登录 | 多个路由通过 `account_id` 查询参数或请求体识别用户，没有认证依赖 | E | 存在 IDOR 和未登录访问个人资产的风险 | P0 | 增加统一身份上下文、后端主体校验和 401/403 测试 |
| BR-004/BR-005/FLOW-001~005 | IAM | 手机号密码/验证码、微信/QQ 绑定同一 User；邮箱不做 | 只有手机号 identity 和账号创建；无密码、验证码、OAuth、Session/Refresh/Revoke | C | 首次注册/登录闭环缺失 | P1 | 增加凭据、会话、撤销、Fake Adapter，并保留手机号多账号路由 |
| BR-007~009/FLOW-006 | 实名 | 充值前实名；敏感信息仅合规后台可用 | 实名三槽位有内存逻辑和迁移，充值/提现未统一强制实名，敏感访问审计缺失 | C | 强制节点和脱敏边界不完整 | P0 | 在应用服务强制检查实名与权限，增加敏感访问日志 |
| BR-010~013 | 作者实名关系 | 一账号一笔名、一身份证最多三账号，关联账号独立复核 | 唯一约束和三账号内存测试存在，运行时未接持久化 | C | 重启丢失，无法作为事实源 | P1 | 使用事务 Repository 与唯一/锁定约束，并补 MySQL 并发测试 |
| BR-014/015 | 搜索 | 多字段联想、纠错、过滤、排序；DB 是事实源，Search 是投影 | 仅有基础内容查询，没有 OpenSearch Projection/高级搜索 | D | 书名/作者/角色/标签搜索闭环未完成 | P1 | 增加 Search Port、索引投影和可降级查询 API |
| BR-016~022/REQ-006 | Agent | Gateway→权限→Tool/Resource→Business Service；高风险确认并审计 | 当前没有完整 Agent Gateway、Tool/Resource DTO 和 AgentAudit | D | 架构预留尚未落地 | P1 | 只实现结构化只读工具与审计，禁止 DB 直连 |
| BR-023~024 | 阅读/TTS | 滚动/分页/同步进度和基础 TTS，遵守 ContentAccessService | 阅读器与进度 API 有部分实现；TTS、访问权限/游客本地进度合并缺失 | C | 内容消费主链不完整 | P1 | 统一 Access Service，补本地/云端冲突与 TTS 权限测试 |
| BR-025~027/FLOW-010 | VIP/订阅 | 签约后平台配置 VIP，服务端按有效字数定价，权益不重复 | 内存 Commerce 可注册 policy 和单章购买，但无签约/平台授权/价格版本/完整订阅 | E | 任意调用者可影响商业 policy，缺少订单事务 | P0 | 将 policy 写入版本化域服务，增加权限、订单、幂等、价格快照 |
| BR-028~030 | 双账本/充值 | RechargeCoin 与 GiftCoin 分离，1 RMB=100 RechargeCoin，回调幂等，渠道可配置 | 内存 Wallet 分离余额/lot/entry；迁移有表；运行时不落库，商品与价格写死在 `CommerceService.PRODUCTS` | E | 资金真相依赖进程内存且充值前实名未强制 | P0 | MySQL 事务 Wallet/Payment/Recharge Repository；配置中心提供产品快照 |
| BR-031~035 | 会员/票/礼物/成长 | 会员与等级分离，票券分离，礼物收益和粉丝值可追溯 | 仅有会员访问领域类型；完整 API、批次、礼物、票、成长未形成闭环 | C | 需求范围大量缺失 | P1 | 按域补最小可用事实表、服务、权限和幂等测试 |
| BR-036~039 | UGC/作者内容治理 | 作者不能删正常差评；版本不可覆盖；机器/人工审核分层；AI 不得自动发布 | 社区/审核基础服务和版本模型存在，权限与持久化不完整；AI 发布边界未实现 | C | 规则没有覆盖所有真实 API | P1 | 统一 UGC Governance、作者权限拒绝测试、固定版本审核 |
| BR-040/FLOW-015 | 收益/结算/提现 | 三层收益、合同分成配置化、实名主体一致、二次验证/风控/审核 | 有内存 AuthorFinance 骨架，含不可自批检查；最低提现和分成写死，提现缺真实实名/风险/审批 | E | 财务规则近似实现且不可审计 | P0 | 版本化政策、append-only finance ledger、Maker/Checker、失败补偿 |
| BR-041/BR-042/BR-043 | 删除/私信/多人创作 | 签约作品不可删；不开放用户私信；不预留多人共同创作 | 未发现用户私信功能；编辑工作消息存在方向；签约删除与联合作者边界未全覆盖 | B | 需继续核对每个 UI/API 入口 | P1 | 保留工作消息，封禁用户私信/联合作者模型入口，补删除策略测试 |
| BR-044~045/SEC-001~004 | 隐私/未成年人 | 阅读历史默认私密；实名脱敏；未成年人限制由策略版本控制 | 有部分 privacy/minor API 和迁移，未统一接入推荐、消费、互动和高额礼物限制 | C | 保护钩子未覆盖业务动作 | P1 | 统一 policy check，补默认私密和策略版本测试 |
| ENTITY-010~017 | 内容/知识库 | Book/Volume/Chapter/Version/Draft/Knowledge 等结构化且版本不可覆盖 | 内容、草稿、版本、首发审核基础已存在；知识库/角色/关系缺失 | C | Writer 编辑完整能力缺失 | P1 | 先补 Draft/Version/restore API，再接知识库只读结构 |
| ENTITY-021~024 | 阅读/书架/书单 | 进度 last/furthest、书架分组、书单与权限独立 | 进度 revision、书架基础 API 和页面存在；书单/隐私/批量二次确认缺失 | C | Reader 主链只完成子集 | P1 | 统一 Library Service，补书单和冲突/批量操作测试 |
| ENTITY-031~037 | 支付/钱包/退款 | Payment/Recharge/Flow/Refund/批次/流水可追溯 | 迁移和退款计算服务存在；Refund HTTP 默认源查询直接抛错，业务数据未接真实 Repository | E | 生产调用无法完成退款，财务记录不闭环 | P0 | 连接 source lot/consumption/recovery Repository，保持快照不可变 |
| ENTITY-043~046 | 作者财务/合同 | 收益、结算、提现、合同版本和附件可审计 | 内存域对象和迁移部分存在；合同签署/附件/结算策略不完整 | C | 只有骨架，不能宣称可结算 | P0 | 持久化 append-only ledger、合同状态机和提现审批 |
| ENTITY-051~054 | Risk/Audit/Notification | 风险事实不删除；Agent/高敏操作可审计；通知分级 | Risk、Notification、Governance API 存在；登录/SMS/设备图谱、完整 Audit/Event 消费缺失 | C | 风险/审计无法支撑全平台 | P1 | Event/Outbox 消费、Risk Case、Audit immutable log |
| ARCH-001~005 | 架构边界 | 三端共用业务服务，DB 事实源，运营变量配置化 | 模块化 monolith 目录符合；内存服务、写死商品、未接投影消费 | C | 目录形态符合，运行时架构未达标 | P0 | 先接 MySQL Repository，再接 Outbox/Projection/Policy |
| NFR-001~002 | 非功能 | 高风险可审计，关键运营参数不能硬编码 | 部分审计/参数中心已存在；关键商品和提现最低额仍有常量 | E | 关键规则可被代码常量绕过 | P0 | 所有业务参数使用 versioned policy + effective_at + approval |

## 风险汇总

| 优先级 | 数量 | 代表问题 |
| --- | ---: | --- |
| P0 | 7 | 认证/IDOR、内存资金真相、充值前实名、VIP policy 越权、退款不可执行、提现不完整、配置硬编码 |
| P1 | 12 | IAM 完整流程、搜索、Agent 预留、阅读/TTS、会员社区、作者编辑/合同、事件投影、未成年人钩子 |
| P2 | 3 | 三端页面缺项、状态/错误/冲突交互不完整、OpenAPI 类型覆盖不足 |
| P3 | 2 | 视觉密度和可访问性专项、部署文档与运行态体验 |

## 当前修复顺序

1. 统一认证主体与后端授权，先关闭通过 `account_id` 越权访问个人数据的入口。
2. 将核心写路径从 `InMemory*` 切换为 SQLAlchemy Repository，并保留内存实现仅供单元测试。
3. 完成 Payment/Recharge/Wallet/Entitlement/Refund 的事务、幂等和 MySQL 集成验证。
4. 补 Search/Outbox/Agent 结构化边界和 Reader/Writer/Admin 缺失闭环。
5. 按 `part-10.md` Coverage Matrix 逐项更新状态；未验证项目保持 `PARTIAL`。

本报告不把已有单元测试、迁移文件或可打开页面等同于生产闭环；后续每项状态只有在对应 API、数据库、权限、测试和构建证据齐备后才提升。

## 本轮补充审计与修复（2026-09-04）

| 分类 | 已处理 | 验证 |
| --- | --- | --- |
| SECURITY/P0 | 增加签名 Session、规范 Base64 校验、Writer/Admin Bearer 入口、账户主体绑定，关闭钱包、书架、阅读进度、实名、作者资料、Reader 账户动作、通知、客服、社区举报、隐私请求和 Writer 内容写入的匿名/跨账号入口 | `test_auth_protected_routes.py`，后端全量 `92 passed` |
| UX/SECURITY | Writer/Admin 去除固定 `demo` 身份，改为可配置本地会话和 Bearer 请求头 | 两端 Vitest、typecheck、build 通过 |
| DATA/TECH | 重新生成 `migration.sql`，认证凭据/会话 migration 头部为 `0015_auth_credentials` | `alembic upgrade head --sql` 通过 |

## 继续开发补充（2026-09-04）

| 分类 | 已处理 | 验证 |
| --- | --- | --- |
| SECURITY/P0 | 身份证指纹改为 HMAC-SHA256；实名姓名与证件字段使用环境密钥 Fernet 加密；退款接口要求 Bearer，并按支付/充值源反查账号后校验主体 | IAM 指纹/密文回归、退款未登录回归 |
| BUSINESS/P0 | Commerce 充值入口接入实名认证事实，未实名返回 `REAL_NAME_REQUIRED` | 充值实名门禁测试 |
| P1 | Writer 首发固定版本提交、Admin 审核决定真实调用 Review API；Writer 提交校验作品所属作者 | Writer/Admin 构建、跨作者审核拒绝测试 |
| DATA/P0 | 新增 SQLAlchemy Wallet adapter，事务覆盖 lot 锁定、赠币优先消费、流水、LotAllocation、退款批次回收；新增 `0016_wallet_lot_sources` | SQLite 事务测试、Ruff、Mypy、Alembic offline SQL |
| READER/P1 | Reader 注册/登录/退出、Bearer 会话、书架/钱包/客服/阅读进度/未成年人保护/互动主体接入；首页榜单改为真实只读 API | Reader Vitest、typecheck、Nuxt build |

SQL Wallet 通过 `PERSISTENCE_MODE=sql` 显式启用并依赖已执行 migration；当前主应用的 IAM、Author、Content、Commerce、Reading、Library、Review、Community、Notification、Support、Approval、Author Finance、Wallet、Risk、Operation、Admin Center、Reader Experience、Copyright、Legal 和 Governance 均已接入 SQL 适配器，但不能据此宣称完整 MySQL 生产闭环，因为部分策略、跨域事务、审计和工作流仍未完成。

本轮没有提升以下状态：Admin 仍缺完整的资源级 DataScope/MFA 最终验证；Risk、Operation、Admin Center、Reader Experience、Copyright、Legal、Governance 虽已接入 SQL 适配器，但其完整策略、跨域事务、审计和工作流仍不完整；章节购买、完整会员/合同/收益/结算/提现策略和 append-only 财务对账仍不完整。这些差异仍按 P0/P1 保持 `PARTIAL`，不能作为 V1.2 商业上线完成依据。Notification 已补齐账户隔离的历史查询，但未读状态及 Push/SMS 投递仍未完成。

## 本轮最终复核（2026-09-04）

新增证据：后端全量 `137 passed`；Ruff format/check、Mypy、Foundation validation 和 Alembic offline SQL 全部通过，迁移链到 `0017_staff_auth_rbac`；Admin、Writer、Reader 和 api-client 的测试、类型检查、构建通过。

已补入符合性范围：Staff 凭据/会话/设备/MFA factor/角色迁移与 Staff-only Admin gate；SearchPort 的过滤、排序、纠错和降级；Agent Gateway 的 Tool/Resource 业务服务边界、高风险写拒绝和审计 hook；SQL Wallet lot 来源追踪/恢复；SQL Commerce 订单、幂等、支付事件冲突和失败回滚测试。

状态保持 `PARTIAL` 的关键原因：完整会员/合同/收益/结算/提现策略、OpenSearch/MQ/Outbox、Agent 持久化审计、细粒度 DataScope/MFA 验证和真实第三方支付尚未完成。各主要领域均已有 SQL 适配器并在 SQL 模式接入，但部分策略、跨域事务、审计和完整工作流仍未达到生产闭环。Docker 基础设施现已实测可用，详见 [v1.2-development-acceptance-report.md](v1.2-development-acceptance-report.md)。

## 本轮运行态补充复核（2026-09-04）

- SQL IAM repository 已接入 `PERSISTENCE_MODE=sql`，真实 MySQL 注册、登录、实名关联和重复实名冲突 smoke 通过。
- 修复 MySQL 8.4 `GET_LOCK` 名称超过 64 字符导致实名接口 500 的数据一致性缺陷；锁名现按指纹稳定映射且满足 MySQL 限制。
- SearchPort 已接入 OpenSearch REST projection，索引创建、删除/刷新、过滤排序和不可用时降级均已验证；空库不再被误标为 degraded。
- `apps` profile 已替换为真实 Backend、Reader、Writer、Admin 镜像，统一 Nginx API 路由已修正，容器构建、healthcheck、CORS 和 Playwright smoke 通过。
- 新鲜回归证据：后端 `137 passed`；前端 test/typecheck/build 通过；Ruff format/check、Mypy、Alembic offline、Compose config/Foundation validation 通过；真实 MySQL 重启保持作者、内容、订单和钱包事实；真实充值/回调/退款 API smoke 通过，退款重复 reference 幂等且恢复后余额归零。

上述补充不改变最终结论：Review/Finance 等全域 SQL 持久化、完整退款/财务/会员/合同闭环、Outbox/MQ 投影、细粒度 DataScope/MFA 和生产支付凭据仍为 `PARTIAL`。

## 2026-09-05 继续开发与运行态复核

| 分类 | 已处理 | 验证 |
| --- | --- | --- |
| BUSINESS/P1 | 会员计划价格快照、会员订单创建、实名门禁、签名支付回调、会员激活和按计划发放推荐票/月票 | MySQL 运行态 API smoke；重复订单和重复支付事件幂等 |
| BUSINESS/P1 | 礼物定义后台入口、礼物订单 SQL 持久化、充值币扣款和重复礼物请求幂等 | MySQL 运行态充值回调/礼物扣款 smoke；余额 `10000` → `9950` |
| DATA/P1 | 新增 `0025_membership_orders`，重新生成 `services/backend/migration.sql` | 容器内 `alembic current` 为 `0025_membership_orders`，OpenAPI 路由已发布 |
| BUG/P1 | 修复会员 Router 通用调用器参数 `name` 与计划/礼物请求字段同名导致后台创建接口 `500` | 新增 `test_membership_admin_payload_name_is_forwarded_without_invoke_collision`，专项测试通过 |
| QA | 重建 Backend/Reader/Writer/Admin 镜像，补跑全量质量门禁和三端浏览器 smoke | 后端 `188 passed`；Ruff/Mypy/Vitest/typecheck/build/Compose smoke 全部通过 |

本次复核后的结论仍为 `PARTIAL`。尚未完成且不能以本轮 smoke 替代的范围：真实微信/支付宝生产支付、章节购买完整商业政策、合同签署与附件、完整收益/分成/结算/提现/税务出款、全域 SQL 持久化、Outbox/MQ 消费与事件投影、细粒度 DataScope/MFA、全角色浏览器 E2E 和跨实例并发验证。

## 2026-09-05 中断续作阶段复核（历史快照）

| 分类 | 本次结果 | 证据 |
| --- | --- | --- |
| BUSINESS/P0 | 章节商业化和财务沙盒闭环真实跑通：作者作品/章节、固定版本审核、VIP策略、Reader实名充值、支付回调、章节购买、权益、Wallet/Ledger、收益、结算、提现、风控/财务审批、Payout | `scripts/qa_sql_commercial_e2e.py`；真实 Compose MySQL API E2E PASS |
| PAYMENT/PAYOUT | 统一 Provider 适配层支持命名沙盒 Alipay/WeChat/Bank 适配器；成功、失败/取消/超时/处理中/拒绝、延迟和重复回调由 Provider API 支持 | `modules/payment/provider.py`、`test_payment_provider.py`、命名渠道商业 E2E PASS；真实支付机构未接入 |
| DATA/P0 | 新增 `0027_mfa_review_scope`：MFA审计/恢复码、Review assignment、Outbox delivery 去重；SQL head 已执行（后续已升级到 `0028`） | 容器 `alembic current`、MySQL表结构和 Outbox 查询 |
| SECURITY/P0 | Staff MFA/TOTP、Secret加密、恢复码一次性消费、高风险部门强制门禁；Review DataScope 在后端查询/授权生效 | `test_sql_staff_auth.py`、`test_staff_auth_rbac.py`、`test_staff_datascope.py`、Admin review scope API test |
| OUTBOX/P1 | 核心商业事件注册到可靠 Worker；本轮 12 类事件均 `PROCESSED`，失败数为 `0`，delivery 无重复复合键 | MySQL `outbox_events`、`outbox_event_deliveries` 查询 |
| QA | 后端全量 `211 passed`（历史快照）；Ruff/Ruff format/Mypy、workspace Vitest/typecheck/build、三组 Compose 浏览器烟测全部 PASS | 本轮命令输出及 `docs/progress/2026-09-05-acceptance-run.log` |

本次仍未把以下范围写成通过：Risk/Operation/Admin Center/Reader Experience/Copyright/Legal/Governance 的全域 SQL 运行时、完整会员和版本化财务政策、完整 Outbox 投影消费者、全角色浏览器 E2E、真实支付宝/微信及银行出款、跨实例 MySQL 并发与生产凭据。旧表格中的早期 `C/E/D` 记录保留作为审计历史，以上 continuation 记录是当前状态的优先证据。

## 2026-09-05 最终复核

| 分类 | 本次结果 | 证据 |
| --- | --- | --- |
| QA | 后端全量新鲜 `302 passed`；Ruff/Ruff format/Mypy、workspace Vitest/typecheck/build 全部通过；通知历史、沙盒出款 HTTP API、SQL 商业 E2E 和 MySQL 并发通过 | 本轮命令输出 |
| SECURITY | AuthorCenter/AdminCenter handler 权限和跨作者 funnel 归属校验补齐；Provider 回调状态机禁止终态回退并兼容 naive 时间 | 权限/状态机回归测试 |
| DATA | 历史快照中的 SQL migration head 为 `0035_virtual_contract_document`；当前 Compose head 为 `0036_contract_author_signature`，合同虚拟正文/哈希、签名、政策快照、Outbox delivery 去重和财务约束均已迁移 | 容器 Alembic/MySQL 查询 |
| RUNTIME | Compose、Reader、Writer、Admin 浏览器 smoke、SQL commercial E2E、会员沙盒 SUCCESS/FAILED/延迟/重复回调全部通过 | QA scripts 与 MySQL 运行态验收 |

真实支付宝/微信生产凭据、真实银行或支付机构出款、全角色浏览器 E2E、跨实例生产压测和未完成的非 SQL 域仍保持 `PARTIAL`；当前已通过本地 MySQL 并发回归，不能替代生产容量证据。

## 2026-09-05 沙盒合同与税务政策补充

已新增 migration `0029_sandbox_finance_policy`。创建合同时自动生成并快照虚拟政策 `SANDBOX_CN_2026_V1`（作者分成 7000 BPS、税款 1000 BPS、100000 分免征阈值）；收益和结算使用 BIGINT cents 计算税额与税后净额。该政策只用于本地/Staging 运行验收，不代表正式税法、合同或生产出款合规结论。

## 2026-09-05 沙盒与高级域继续开发

合规证据已新增：

- 七类非财务第三方统一由确定性 Sandbox Provider 提供，生产环境拒绝 `SANDBOX_*` 配置。
- 全角色脚本覆盖 Guest、Reader、Verified Reader、Author、Signed Author、Reviewer、Operator、Finance、Risk、Admin、Super Admin，包含权限拒绝、真实三端页面和 Agent 审计调用。
- 高级域脚本覆盖 Review、Operation、Risk、Copyright、Legal、Governance、Agent；参数审批验证 Maker/Checker 分离，奖励验证重复幂等。
- MySQL 有界压测覆盖健康检查、搜索/榜单、登录、Wallet、支付回调和章节购买，并输出吞吐、p50/p95/最大延迟、重复幂等键和负余额指标。

这些证据只证明本地/Staging 沙盒功能齐全和可回归，不改变真实第三方生产协议、正式税务/法律政策、生产容量/灾备以及 Coverage Matrix 中其他 `PARTIAL` 项的结论。

## 2026-09-05 恢复开发补充

- 合同签署事实已落库并成为激活前置条件，Alembic head 为 `0036_contract_author_signature`；虚拟合同/税务策略仍是 `SANDBOX_CN_2026_V1`，不具备正式法律或税务效力。
- 全角色 E2E 与高级域 E2E 已使用最小权限 Staff token 通过，覆盖预期跨域 `403`、Maker/Checker、幂等和 Agent 审计。
- MySQL 16/32 路压测和 8 路并发回调通过，钱包负数及重复 Wallet 幂等键均为 `0`。本地测量不能替代生产多实例、容量、备份恢复、灾备和监控验证。
- 修正发票与 Agent 的全局路由权限映射，避免默认 `admin.access` 绕过领域权限边界。

## 2026-09-05 latest verification after concurrency fix

- Fresh backend full regression is `319 passed`; Ruff check/format, Mypy, workspace Vitest, typecheck and production builds pass.
- Role API/web-shell E2E and advanced-domain workflow E2E pass on Compose; MySQL concurrency/load gates pass at 8, 16 and 32 workers with no negative wallets or duplicate Wallet idempotency keys.
- The chapter purchase lock-order fix is covered by a SQL commerce regression and verified by the 32-worker live MySQL run. Production provider credentials, formal tax/legal policy, multi-instance capacity/DR and the broader `PARTIAL` rows remain unchanged.

## 2026-09-05 final verification snapshot

- Final Backend regression: `319 passed`; Ruff check/format and Mypy pass. Workspace Vitest, typecheck and production builds pass.
- Fresh Compose role E2E and advanced workflow E2E both returned `status=PASS`; SQL commercial E2E and all browser/Compose smoke scripts pass.
- Thresholded MySQL load gates pass at 16 and 32 concurrency: 112/112 at 32.41 RPS and 224/224 at 36.35 RPS, p95 2.2376s/2.4017s, zero negative wallets and zero duplicate wallet idempotency keys.
- These are deterministic sandbox and local MySQL/Staging evidence. Real provider credentials, formal legal/tax approval, multi-instance production capacity, DR/monitoring and the broader `PARTIAL` matrix are intentionally not upgraded.
