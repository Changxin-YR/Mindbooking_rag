# Sandbox/Staging Release Readiness

日期：2026-09-05

## 结论

当前版本可以部署到本地或 Staging 进行功能验收，不能宣称为真实支付宝/微信/银行生产上线。

## 已通过

- Compose 默认以 `APP_ENV=staging` 启动，全部服务健康，Reader/Writer/Admin 真实前后端可访问。
- `SANDBOX_ALIPAY`、`SANDBOX_WECHAT`、`SANDBOX_BANK` 通过统一 Provider 端口运行；旧沙盒名称兼容。
- `SANDBOX_SMS`、`SANDBOX_OAUTH_WECHAT`、`SANDBOX_OAUTH_QQ`、`SANDBOX_REALNAME`、`SANDBOX_MODERATION`、`SANDBOX_STORAGE`、`SANDBOX_NOTIFICATION` 通过 `SandboxProviderRegistry` 提供确定性内存适配；OTP/OAuth 一次性与过期、实名/审核结果、对象 key、通知幂等均有专项测试。
- 支付/出款签名、SUCCESS/FAILED/PROCESSING/REJECTED/TIMEOUT、延迟、重复回调、幂等和终态防回退已验证。
- `0029_sandbox_finance_policy` + `0030_finance_constraints` + `0031_finance_maker_checker` + `0032-0036` 已在 MySQL 执行；虚拟合同政策快照、自动生成合同正文/哈希、作者签名、税前/税额/税后整数结算以及 Risk/Finance 审批人留痕已验证。
- 作者、合同、审核、章节购买、Wallet/Ledger、收益、结算、提现、Risk/Finance 审批和沙盒出款商业闭环已通过 SQL E2E。
- Reader 通知中心已支持 SQL 持久化未读计数、账户隔离和幂等标记已读；前端页面已接入真实 API。
- 后端全量 `319 passed`；Ruff check/format、Mypy、前端 Vitest、`pnpm typecheck`、`pnpm -r build` 和六组浏览器/SQL smoke 通过。
- `qa_role_e2e.py`、`qa_advanced_workflows.py`、`qa_mysql_load.py` 和 `qa_mysql_concurrency.py` 已在重建后的 Compose/MySQL 上通过；高级域使用最小权限角色 token，压测脚本输出吞吐、p50/p95/最大延迟、重复幂等键和负余额指标。
- 同一账户并发章节购买的 MySQL 1213/1205 事务失败现在进行最多 3 次完整事务重试，并由负余额、唯一幂等键和唯一 entitlement 约束兜底。
- 最近一次 `qa_mysql_load.py --concurrency 16` 的 112 个请求全部成功，吞吐 `34.19 rps`，p50 `0.1246s`，p95 `2.1244s`，最大 `2.1940s`；`--concurrency 32` 的 224 个请求全部成功，吞吐 `37.05 rps`，p50 `0.2804s`，p95 `2.4264s`，最大 `3.9696s`；工作负载包含登录、目录、Wallet 读取、支付回调和购买，并支持 `LOAD_MAX_P95_MS`/`LOAD_MIN_THROUGHPUT_RPS` 门禁，仅作为当前本地环境基线。

## 最新增量

- 创建合同会按 `SANDBOX_CN_2026_V1` 生成确定性虚拟合同正文和 SHA-256，写入 `contract_versions.document_text/document_hash`；Writer 可通过 `GET /writer/api/v1/finance/contracts/{contract_id}` 查看并在签约页展示。
- Alembic 当前 head 为 `0036_contract_author_signature`；旧合同签名字段兼容为空，新合同在激活前必须完成作者签署。

## 最新并发修复证据

- 章节购买首次并发时先锁定账户 Wallet 行，再锁定权益记录，避免 MySQL 空权益间隙锁与 Wallet 锁交叉形成死锁；SQL Wallet/Commerce 单元回归覆盖锁顺序。
- 修复后 16/32 路 MySQL 负载均为全量成功，资金不变量和 Wallet 幂等键均为零违规。该数据是本地 Staging 基线，不代表生产容量、跨实例故障转移或灾备能力。

## 生产前仍需替换

- 接入并审计真实支付宝/微信支付、银行或支付机构出款凭据与回调协议。
- 接入并审计真实 SMS、微信/QQ OAuth、实名核验、内容审核、对象存储和通知投递凭据/协议；生产配置会拒绝所有 `SANDBOX_*` provider，当前沙盒不联网且不接收真实凭据。
- 由法务/税务确认正式合同、分成、扣缴、发票和结算政策，并替换 `SANDBOX_CN_2026_V1`；当前文档只用于本地/Staging 演示。
- 完成全角色浏览器 E2E、跨实例 MySQL 并发/锁竞争、监控告警、备份恢复和生产镜像发布。
- Coverage Matrix 中标记 `PARTIAL` 的高级域仍不能以本沙盒验收替代。

## 2026-09-05 fresh verification

- `qa_role_e2e.py`: `status=PASS`，覆盖 11 个角色、真实 Reader/Writer/Admin 页面、预期越权拒绝和 Super Admin Agent 成功路径。
- `qa_advanced_workflows.py`: `status=PASS`，覆盖 Review、Operation、Risk、Copyright、Legal、Governance、Agent，使用最小权限 Staff token 并验证跨域 `403`、Maker/Checker 和奖励幂等。
- `qa_mysql_concurrency.py --concurrency 8`: `status=PASS`。
- `qa_mysql_load.py --concurrency 16`: 112/112 成功，35.41 RPS，p50 `0.1351s`，p95 `1.9401s`，最大 `2.0307s`；`--concurrency 32`: 224/224 成功，37.08 RPS，p50 `0.2457s`，p95 `2.4265s`，最大 `3.8850s`；两轮负余额和重复 Wallet 幂等键均为 `0`。
- 对账 GET 集合路由已改为使用 `governance.read`，与 handler 授权契约一致。

## 最新运行态压测证据

- Backend 重建后，`qa_mysql_load.py --concurrency 16` 通过 112/112（33.27 RPS，p50 `0.1289s`，p95 `2.1957s`，最大 `2.2477s`）；`--concurrency 32` 通过 224/224（35.65 RPS，p50 `0.2714s`，p95 `2.4809s`，最大 `4.2433s`）。两轮负余额和重复 Wallet 幂等键均为 `0`。
- 该结果覆盖真实 MySQL、并发登录/目录/Wallet 读取、支付回调和章节购买；仍是本地/Staging 基线，不等同生产容量、跨实例锁竞争或灾备证明。

## 最终验证快照

- 最终 Backend 代码（含 Wallet-first 锁顺序、1205/1213 重试和对账 GET 权限修复）全量回归为 `319 passed`；Ruff check/format、Mypy 通过。
- 最终阈值压测门（p95 <= 5000ms、吞吐下限 20/30 RPS）通过：16 路 112/112，32.41 RPS，p50 `0.1551s`，p95 `2.2376s`，最大 `2.3254s`；32 路 224/224，36.35 RPS，p50 `0.2646s`，p95 `2.4017s`，最大 `4.1414s`；负余额和重复 Wallet 幂等键均为 `0`。
