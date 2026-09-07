# V1.2 Parallel Development Status

| Wave | Workstream | Status | Branch/worktree | Commit | Tests | Blocker | Integration |
|---|---|---|---|---|---|---|---|
| 0 | Root workspace | PASS | `codex/v1.2-foundation` / `.worktrees/foundation` | `58594e7` | pnpm tests/typecheck/build | none | integrated |
| 0 | Backend core | PASS | `codex/v1.2-foundation` | `58594e7` | pytest, Ruff, Mypy | live DB credentials unavailable | integrated |
| 0 | Frontend shells | PASS | `codex/v1.2-foundation` | `58594e7` | Vitest, typecheck, build | none | integrated |
| 0 | Infrastructure/CI | PASS | `codex/v1.2-foundation` | working tree | Compose config, self-check, Docker healthchecks, apps image build and browser smoke | production registry/secret rollout remains | integrated |
| 1-4 | Consumer and governance domains | PARTIAL | `codex/v1.2-full-audit` | working tree | 274 backend tests, API smoke, MySQL migration/smoke | risk/operation/admin/reader governance runtime and advanced workflows remain | integrated |
| 5 | Author finance | PARTIAL | `codex/v1.2-full-audit` | working tree | finance Golden/SQL policy tests, generated virtual contract document/hash/signature, named-channel SQL commercial E2E, migrations through `0036` | production payment/bank/tax credentials and formal policy versions | integrated |
| 6-8 | Operation, governance, author/admin/risk centers | PARTIAL | `codex/v1.2-full-audit` | working tree | 316 backend tests, least-privilege role E2E, advanced workflow E2E, workspace test/typecheck/build, migrations `0011-0036` | durable domain repositories, production-grade capacity/DR and some advanced policies remain | integrated |

## 2026-09-04 continuation

- Authentication: password registration/login, signed Bearer sessions, canonical Base64 verification, account-bound Reader/Writer mutations, and global Writer/Admin session gate are integrated.
- Frontend sessions: Writer and Admin no longer use fixed demo identities; both read configurable local sessions and send Bearer headers.
- Reader session: Reader no longer uses fixed demo account IDs; settings supports phone/password registration/login and private actions send the signed Bearer session.
- Commerce boundary: recharge requires active real-name verification; refund requires an authenticated source owner; review submission is bound to the author account.
- Wallet persistence: SQLAlchemy Wallet adapter and migration `0016_wallet_lot_sources` are integrated behind explicit `PERSISTENCE_MODE=sql`; SQLite transaction regression covers lot locking and source recovery.
- Commerce persistence: SQLAlchemy Payment/Recharge adapter is wired in SQL mode; deterministic idempotency, provider callback deduplication/conflict checks, source ownership lookup and shared-connection wallet rollback are covered by tests and a real MySQL recharge smoke.
- Author/content persistence: SQL author profile and SQL content services are wired in SQL mode; author/profile, book/volume/chapter, draft and fixed-version records survive service/container restart.
- Staff security: durable staff credentials/sessions/devices/MFA/roles migrations through `0017_staff_auth_rbac`, staff-only Admin session gate, permission and offboarding regression tests.
- Search and Agent boundaries: structured SearchPort with filtering/sorting/fallback, and Agent Gateway Tool/Resource registration with read-only business callbacks, high-risk write rejection and audit hook.
- Regression evidence (historical baseline): backend `274 passed`; workspace test/typecheck/build passed; Alembic offline SQL and real MySQL upgrade reached `0030_finance_constraints`; MySQL-backed FastAPI health/private-route/registration/login/real-name/author/content/recharge/refund/membership/gift, membership sandbox SUCCESS/FAILED/delayed/duplicate, notification history, and Staff-only payout sandbox SUCCESS/FAILED/PROCESSING/REJECTED/TIMEOUT/duplicate smoke passed; backend restart preserved MySQL facts; OpenSearch and Compose browser/editor smoke passed.
- Deliberate remaining `PARTIAL`: Risk, Operation, Admin Center, Reader Experience, Copyright, Legal and Governance are SQL-wired but their complete policies, cross-domain transactions, audit and workflows remain incomplete; complete membership/contract/finance policy, chapter purchase, third-party payment and browser E2E remain incomplete; Admin has not completed resource-level DataScope and MFA verification; OpenSearch projection is request-refresh based until an outbox/MQ consumer is added. Reader notification history is now queryable with account/category/limit controls; unread state and delivery channels remain partial.

## 2026-09-05 continuation

- Fixed membership admin plan/gift creation `500` caused by the shared dispatcher argument `name` colliding with payload field `name`; API regression coverage added.
- Membership SQL checkout, signed callback, ticket grant, recharge funding and gift debit/idempotency are runtime-verified. Added SQL AuthorCenter task-progress idempotency migration `0028` and verified Writer settlement list/editor flows. Commercially complete membership policy, contract/finance policy and external payment integration remain `PARTIAL`.

## 2026-09-05 interrupted-task continuation

- Added and executed `scripts/qa_sql_commercial_e2e.py` against the running MySQL Compose stack. The author -> contract -> fixed-version review -> VIP chapter -> reader recharge -> chapter purchase -> revenue -> settlement -> withdrawal -> Risk/Finance approval -> sandbox payout path passed, including duplicate payment and payout callbacks.
- Added TOTP MFA recovery codes/audit and high-risk Staff enforcement; added backend Review DataScope assignment filtering for `SELF/ASSIGNED/ALL/GLOBAL`; migration head is `0027_mfa_review_scope`.
- Added durable Outbox delivery deduplication and registered the core commercial event types. The current E2E produced 12 `PROCESSED` events, 0 current-run failures and no duplicate `(event_id, consumer)` deliveries.
- Fixed Sandbox Provider default callback event IDs so separate provider instances cannot reuse a process-local `event-1` identifier for different references.
- Earlier interrupted-task snapshot: backend `211 passed`, Ruff/Ruff format/Mypy, workspace Vitest/typecheck/build, and the three Compose browser smokes passed at that point. Full role-by-role browser E2E, cross-instance concurrency, and real payment/payout credentials remained unverified.

## 2026-09-05 final verification

- Backend 按测试文件分批 `274 passed`; Ruff, Mypy, Alembic offline SQL, workspace tests/typecheck/build all pass.
- Fresh Compose smoke, Writer editor smoke, Staff-authenticated V1.2 browser smoke, SQL commercial E2E, and membership sandbox SQL smoke pass.
- Runtime migration head was `0028_author_center_idempotency` at this historical checkpoint; the current head is `0030_finance_constraints` (see sandbox finance policy section).
- AuthorCenter/AdminCenter Staff permission gates and Commerce/Payout terminal callback state transitions are covered by the final regression suite.
- Real Alipay/WeChat production credentials, real bank payout, full role-by-role browser E2E, cross-instance MySQL contention, and incomplete policy/workflow/audit coverage remain `PARTIAL`.

## 2026-09-05 completeness workstreams

- Agent audit: staff-only explicit paginated API `GET /admin/api/v1/agent/audits`, SQL/in-memory filtering, and sensitive argument step-up permission are covered by `test_agent_audit_api.py` and `test_agent_sql_query.py`.
- Search projection: `BOOK_INDEX` and `BOOK_TAKEN_DOWN` are routed through an idempotent projection handler and covered by `test_search_projection_outbox.py`; the runtime registers the handler while retaining delivery deduplication.
- Reader TTS: basic deterministic sentence segments are returned only after the shared ContentAccessService decision; `test_reading_tts.py` covers FREE, PURCHASED, MEMBER_FREE, denial, ownership and option validation.
- Production safety: `APP_ENV=production` now requires SQL persistence, non-development secrets, non-sandbox provider names, and fails closed until real provider adapters are wired. Sandbox remains development/test-only.

## 2026-09-05 resumed sandbox finance verification

- Provider selection now supports `SANDBOX_ALIPAY`, `SANDBOX_WECHAT`, and `SANDBOX_BANK`; `SANDBOX`/`SANDBOX_PAYOUT` remain compatibility aliases. Compose defaults exercise the named Alipay and bank adapters.
- Migrations `0029_sandbox_finance_policy`, `0030_finance_constraints`, and `0031_finance_maker_checker` persist `SANDBOX_CN_2026_V1` contract snapshots, integer tax/net settlement fields, amount integrity checks, and Risk/Finance reviewer identities. The policy is explicitly staging-only and does not claim production tax or legal compliance.
- Verification: backend full suite `283 passed`; fresh rebuilt Compose services and all five smoke scripts pass, including the SQL commercial E2E with separate Maker/Checker Staff accounts.

## 2026-09-05 virtual contract continuation

- Contract creation now renders and persists a deterministic virtual agreement (`SANDBOX_CN_2026_V1`) with SHA-256; Writer GET API and account-settings view expose the document for sandbox acceptance.
- Migration head is `0035_virtual_contract_document`; fresh backend suite is `302 passed`, and SQL commercial/concurrency plus Compose browser smokes pass.

## 2026-09-05 沙盒第三方与高级域继续开发

- Sandbox integrations workstream: SMS/OAuth/实名/审核/对象存储/通知 registry and production fail-closed settings are integrated; focused and full backend tests pass.
- Role E2E workstream: `qa_role_e2e.py` passes all 11 role identities, permission boundaries, three web shells and Agent success path on rebuilt Compose.
- Advanced workflow workstream: `qa_advanced_workflows.py` passes Review, Operation, Risk, Copyright, Legal, Governance and Agent workflows, including Maker/Checker and reward idempotency.
- MySQL load workstream: `qa_mysql_load.py --concurrency 4` and `qa_mysql_concurrency.py --concurrency 8` pass. SQL chapter purchase now has bounded deadlock/lock-timeout retry after real 1213 contention evidence.
- These are local/Staging acceptance signals. Production provider credentials, formal legal/tax policies, cross-instance capacity, disaster recovery and remaining advanced policies stay `PARTIAL`.

## 2026-09-05 resumed completeness

- Compose MySQL is at Alembic head `0036_contract_author_signature`; contract signing is persisted and required before activation.
- Role E2E covers all 11 documented identities. Advanced workflow E2E uses separate Reviewer, Operator, Risk, Legal, Finance, Governance Maker/Checker and Agent sessions and verifies expected cross-domain `403` responses.
- MySQL load evidence: 16-way `112/112` and 32-way `224/224` successful requests, including login/catalog/Wallet reads, callbacks and purchases, with no negative wallets or duplicate wallet idempotency keys. Thresholds are configurable via `LOAD_MAX_P95_MS` and `LOAD_MIN_THROUGHPUT_RPS`; these remain local staging measurements, not a production capacity or disaster-recovery guarantee.

## 2026-09-05 fresh verification

- Fresh backend regression is `316 passed`; Ruff check/format, Mypy, workspace tests, typecheck and builds pass.
- Role E2E and advanced workflow E2E both returned `status=PASS`; the latter uses least-privilege staff sessions and verifies Maker/Checker, idempotency and cross-domain `403` boundaries.
- Serial MySQL evidence is 8-way callback PASS, 16-way load 112/112 at 35.41 RPS, and 32-way load 224/224 at 37.08 RPS, with p95 1.9401s and 2.4265s respectively and zero financial invariant violations.
- Reconciliation GET route permission mapping now matches the `governance.read` handler contract. Production provider credentials, formal policies, multi-instance capacity/DR and broader advanced-domain completeness remain `PARTIAL`.

## 2026-09-05 latest runtime pressure evidence

- After the Backend rebuild, 16-way load passed 112/112 at 33.27 RPS and 32-way load passed 224/224 at 35.65 RPS; p95 was 2.1957s and 2.4809s, with zero negative wallets and zero duplicate wallet idempotency keys. These are local/Staging measurements only.

## 2026-09-05 final verification snapshot

- Final backend regression after lock-order and permission fixes: `319 passed`; Ruff check/format and Mypy pass. Historical counts in earlier sections are retained as audit history.
- Final thresholded load gate passed: 16-way 112/112 at 32.41 RPS and 32-way 224/224 at 36.35 RPS; p95 2.2376s/2.4017s, zero negative wallets and zero duplicate wallet idempotency keys.

Status is updated only after a fresh command verifies the stated test result.
