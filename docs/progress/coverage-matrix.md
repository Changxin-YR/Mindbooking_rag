# V1.2 Coverage Matrix

| Wave | Workstream | Status | Evidence |
| --- | --- | --- | --- |
| 0 | Monorepo, FastAPI, Nuxt/Vite, Compose, CI | PASS | workspace builds, Compose config, foundation self-check |
| 1 | IAM, real-name account limit, author/profile, staff/RBAC, content versions | PARTIAL | account/password/session, SQL IAM and SQL Author repositories, SQL Content versions, real-name locking, Staff MFA/TOTP recovery codes/audit and bearer/RBAC gates tested; migrations `0002-0003`, `0015`, `0017`, `0027`; OAuth remains outside the verified scope |
| 2 | Review, fixed-version publish, reader access, progress, shelf | PARTIAL | SQL Content/Review/Reading/Library services are wired; fixed-version publish, review decisions, progress and shelf persistence have SQLite and MySQL smoke evidence; full access policy and browser E2E remain |
| 3 | Wallet, lots, expiry-first/FIFO, payment callback, purchase, membership | PARTIAL | SQL Wallet lot/ledger/source recovery, durable chapter purchase/entitlement/revenue transaction, Sandbox PaymentProvider callbacks, membership order/callback/ticket grant and gift debit are wired; SUCCESS/FAILED/duplicate/delayed membership callbacks were verified against MySQL; migrations `0016`, `0025`, `0028`; full membership policy remains |
| 4 | Refund formula/snapshot/source lock, reports, notification, support, risk, approval | PARTIAL | SQL Refund/Community/Notification/Support/Approval services are wired; migrations `0006-0007`; Risk and full operational governance persistence remain |
| 5 | Contract, revenue ledger, settlement, withdrawal, chargeback/recovery | PARTIAL | SQL Author Finance contract/revenue/settlement/withdrawal/payout adapters are wired; versioned virtual policy `SANDBOX_CN_2026_V1` snapshots contract share and tax withholding, generates/persists deterministic contract text/hash, requires an author signature before activation (`0035-0036`), and net settlement arithmetic is covered by memory/SQL tests; named Sandbox Alipay/WeChat/Bank adapters, Maker/Checker reviewer persistence and callback state machine are verified; real bank/tax integration and formal policy workflow remain |
| 6 | Ranking/recommendation separation, editorial slots, export, retention policy/jobs | PARTIAL | `tests/golden/test_operation_legal.py`, `test_governance_v12.py`; campaigns/rewards and basic author metrics exist, advanced search/experiments/jobs remain |
| 7 | Copyright dossier/rights/conflict/complaint/counter notice, legal case/hold | PASS | `tests/golden/test_operation_legal.py`, migration `0009` |
| 7 | Privacy requests, agreements, parameter/change center, advanced audit/file governance | PARTIAL | `test_governance_v12.py`; privacy/agreement/parameter/reconciliation/emergency/outbox facts and migration `0011` exist, full persistence/audit/file service remains |
| Search | Multi-field query, filter, sort, typo correction, fallback | PARTIAL | `tests/modules/test_search_v12.py`, OpenSearch REST projection/index wiring, empty-result and unavailable fallback checks, idempotent `BOOK_INDEX`/`BOOK_TAKEN_DOWN` Outbox projection handler (`test_search_projection_outbox.py`); durable OpenSearch consumer and Chinese analyzer tuning remain |
| Agent | Gateway, Tool/Resource, Business Service boundary, audit | PARTIAL | `tests/modules/test_agent_v12.py`, `test_agent_audit_api.py`, `test_agent_sql_query.py`; append-only SQL audit query API with sensitive-argument permission is live, full Business API and cross-instance audit retention remain |
| Reader experience | Catalog filters, rating eligibility, follows, growth, corrections, minor policy, basic TTS | PARTIAL | API, `0010_reader_experience`, public detail/read/shelf/wallet/support/settings/notifications pages, access-gated deterministic TTS (`test_reading_tts.py`), account-scoped notification history with SQL rebuild, unread count and idempotent read state (`0032_notification_read_state`); push/SMS delivery, full community/profile/preferences and production voice provider remain |
| Writer center | Calendar, tasks, growth, campaigns, academy, funnel, appeals | PARTIAL | `test_author_center_v12.py`, migration `0012`, SQL task idempotency `0028`, Writer workspace/editor/finance routes and Writer editor smoke; advanced campaigns/academy/funnel/appeals and public author page remain |
| Admin center | Rule library, review queue, quality, User360 masking, support/CSAT | PARTIAL | `test_admin_center_v12.py`, staff session/RBAC/DataScope/MFA tests, migrations `0013`, `0017`, `0027`, Admin workspace routes; scoped review assignment and reviewer-quality `review.decide` write gate are verified, while full operational pages, governance moderation and file/audit views remain |
| Risk center | Login signals, observe/freeze, watchlist with audited release | PARTIAL | `test_admin_center_v12.py`, migration `0014`; SMS, device graph, volume detection, emergency playbooks remain |
| UI | Reader | PARTIAL | home/catalog plus detail/read/library/wallet/support/settings routes, real purchase/interaction/wallet API wiring, API loading/error states and TTS contract; full role/browser matrix remains |
| UI | Writer | PARTIAL | live works/reviews/calendar/editor/signing/finance workspace and states; Compose image, editor smoke and settlement/withdrawal API flow pass; advanced analytics/public author page remain |
| UI | Admin | PARTIAL | live review/rules/User360/support/finance/risk/parameter/outbox workspaces; Staff login, MFA/DataScope APIs and Compose browser smoke pass; full operational query/approval views remain |

`PARTIAL` records the exact remaining scope; it is not a claim of full V1.2 acceptance.

## 2026-09-05 resumed completeness evidence

- Migration `0036_contract_author_signature` is applied to Compose MySQL. Contract activation now requires the owning author's signature; repeated same-author signing is idempotent and a different signer is rejected. The generated document, signer, signing time and SHA-256 signature hash survive SQL rebuild.
- `scripts/qa_role_e2e.py` PASS: Guest, Reader, Verified Reader, Author, Signed Author, Reviewer, Operator, Finance, Risk, Admin and Super Admin, including real Reader/Writer/Admin shells and expected forbidden writes.
- `scripts/qa_advanced_workflows.py` PASS with least-privilege Reviewer, Operator, Risk, Legal, Finance, Governance Maker/Checker and Agent sessions. Review, Operation, Risk, Copyright, Legal, Governance and Agent workflows pass; cross-domain writes return `403`; reward and Maker/Checker idempotency are verified.
- `qa_mysql_concurrency.py --concurrency 8` PASS. `qa_mysql_load.py --concurrency 16` PASS (112/112, p50 `0.1437s`, p95 `2.0691s`, max `2.1604s`, 34.42 RPS); `--concurrency 32` PASS (224/224, p50 `0.2308s`, p95 `2.4243s`, max `4.0331s`, 37.67 RPS). The workload includes concurrent login, catalog, Wallet reads, payment callbacks and purchases; negative wallets and duplicate wallet idempotency keys were both `0`.
- Fixed route-level permission mapping for invoice and Agent endpoints so Finance/Governance and Agent permissions are enforced consistently by middleware and handler guards. Production provider credentials, formal tax/legal policy, cross-instance capacity, disaster recovery and remaining advanced-domain completeness remain `PARTIAL`.

## 2026-09-05 fresh verification

- Backend full regression: `316 passed`; Ruff check/format, Mypy (144 source files), workspace Vitest, typecheck and production builds pass.
- `scripts/qa_role_e2e.py` returned `status=PASS` for all 11 documented identities and exercised the Reader, Writer and Admin web shells with real API sessions.
- `scripts/qa_advanced_workflows.py` returned `status=PASS` for Review, Operation, Risk, Copyright, Legal, Governance and Agent, including least-privilege `403` checks, Maker/Checker separation and reward idempotency.
- `qa_mysql_concurrency.py --concurrency 8` returned `status=PASS`; `qa_mysql_load.py --concurrency 16` returned 112/112 successful requests (35.41 RPS, p50 0.1351s, p95 1.9401s, max 2.0307s); `--concurrency 32` returned 224/224 (37.08 RPS, p50 0.2457s, p95 2.4265s, max 3.8850s). Both load runs reported zero negative wallets and zero duplicate wallet idempotency keys.
- Added the missing method-aware `governance.read` mapping for reconciliation GET collections. Production provider credentials, formal legal/tax policy, multi-instance capacity/DR and the broader `PARTIAL` rows remain unchanged.

## 2026-09-05 latest runtime evidence

- After rebuilding the Backend image with the wallet-lock ordering fix, `qa_mysql_load.py --concurrency 16` passed 112/112 (33.27 RPS, p50 0.1289s, p95 2.1957s, max 2.2477s) and `--concurrency 32` passed 224/224 (35.65 RPS, p50 0.2714s, p95 2.4809s, max 4.2433s). Both runs reported zero negative wallets and zero duplicate wallet idempotency keys.
- This latest runtime evidence supersedes the earlier local throughput samples in this document; it still does not establish production capacity, multi-instance contention or disaster recovery.

## 2026-09-05 final verification snapshot

- Backend full regression after the final lock-order and authorization changes: `319 passed`; Ruff check/format and Mypy pass.
- Final thresholded load gate (`p95 <= 5000ms`, minimum 20/30 RPS): 16-way 112/112 at 32.41 RPS (p50 0.1551s, p95 2.2376s, max 2.3254s); 32-way 224/224 at 36.35 RPS (p50 0.2646s, p95 2.4017s, max 4.1414s). Both had zero negative wallets and zero duplicate wallet idempotency keys.

## 2026-09-05 continuation evidence

- Backend full regression: fresh full run `302 passed`; Ruff, Ruff format, Mypy, workspace Vitest, typecheck and production builds pass.
- Real SQL commercial E2E: author -> contract approval/activation -> fixed-version review -> VIP policy -> reader real-name/recharge -> signed Sandbox payment callback and duplicate callback -> chapter purchase/entitlement -> wallet/ledger -> revenue confirmation -> settlement -> withdrawal -> risk/finance approval -> Sandbox payout success and duplicate callback: PASS.
- Runtime Outbox: the current E2E's core events are `PROCESSED`; current database totals are `174 PROCESSED / 8 PUBLISHED`, failed events `0`; `outbox_event_deliveries` has no duplicate `(event_id, consumer)` keys.
- Migration head: `0036_contract_author_signature`; verified tables include `staff_mfa_audits`, `review_tasks.assigned_staff_id`, `outbox_event_deliveries`, contract policy/tax snapshot plus generated document/hash/signature columns, revenue net/tax columns, finance amount checks, the `author_task_progress.idempotency_key` unique index, and notification read timestamps/indexes.
- Compose API/browser smoke: `qa_compose_smoke.py`, `qa_v12_smoke.py`, and `qa_writer_editor_smoke.py` all PASS.
- Remaining evidence gaps: full role-by-role browser E2E, cross-instance MySQL concurrency, and real third-party payment/payout credentials are not claimed as PASS.
- Docker apps profile was rebuilt and all services are healthy. OpenAPI includes `/api/v1/membership/orders`, `/api/v1/membership/payments/callback` and `/api/v1/gifts`.
- Runtime SQL smoke passed: Staff-configured membership plan, real-name gate, idempotent order creation, invalid/valid signed callback, membership activation, configured ticket grant, recharge callback, gift debit and duplicate gift request. A fresh membership sandbox smoke also verified SUCCESS/FAILED/delayed/duplicate provider simulation and ticket balances against MySQL.
- Staff-only `POST /api/v1/payouts/sandbox/simulate` is published in OpenAPI and exercised by the SQL commercial E2E; it routes sandbox payout status, delayed callbacks, duplicate callbacks, signature verification, idempotency and terminal-state handling through the same payout transaction path.
- Fixed a membership HTTP dispatcher collision where the dispatcher parameter `name` conflicted with plan/gift payload field `name`; added API regression coverage.
- Closed AuthorCenter/AdminCenter handler-level Staff permission gaps and cross-author funnel access; added regression coverage for `operation.write`, `governance.write`, and `review.read` gates.
- Fixed Commerce/Payout provider state machines so `PROCESSING` can only move to a terminal result, terminal callbacks cannot regress, transaction IDs are reused safely, and naive callback timestamps are normalized to UTC.
- Added selectable `SANDBOX_ALIPAY`, `SANDBOX_WECHAT`, and `SANDBOX_BANK` adapters with legacy aliases; Compose defaults now exercise named sandbox channels.
- Added migration `0029_sandbox_finance_policy` and the virtual contract/tax policy snapshot. SQL and memory settlement tests verify integer tax arithmetic and tax-after-threshold net payouts.

## 2026-09-05 resumed runtime verification

- Backend full regression: fresh full run `302 passed`; Ruff check and format, Mypy (143 source files), workspace Vitest, `pnpm typecheck`, and `pnpm -r build` all pass.
- Fresh Compose runtime: all services are healthy after rebuilding Backend/Reader/Writer/Admin images; API `/health/ready` and Nginx `/healthz` return `200`.
- Historical runtime snapshot: MySQL 8.4 Alembic head was `0035_virtual_contract_document` at the time of that verification; the current runtime head is `0036_contract_author_signature`.
- Fresh smoke evidence: `qa_smoke.py`, `qa_compose_smoke.py`, `qa_v12_smoke.py`, `qa_writer_editor_smoke.py`, and `qa_sql_commercial_e2e.py` all pass. The SQL commercial flow uses separate Risk and Finance Staff identities and verifies duplicate Sandbox payment and payout callbacks.
- Published OpenAPI contains the Staff-only payout simulator, membership sandbox simulator, account-scoped notification history, unread-count and mark-read endpoints.
- Staging target remains `PARTIAL`: production provider credentials/adapters, formal tax/legal policy, cross-instance contention, full role browser matrix, and advanced domain workflows are not represented by sandbox evidence.

## 2026-09-05 virtual contract continuation

- `AuthorFinanceService` and `SqlAuthorFinanceService` now generate a deterministic `SANDBOX_CN_2026_V1` contract document at creation time, persist `document_text` and `document_hash`, and expose it through the Writer contract GET API.
- Writer account settings renders the returned virtual contract and SHA-256; SQL rebuild and HTTP ownership checks are covered by `test_author_finance.py`, `test_sql_author_finance.py`, and `test_app.py`.
- Fresh verification after migration: backend `316 passed`; Compose MySQL head `0036_contract_author_signature`; SQL commercial E2E, MySQL concurrency, Compose and V1.2 browser smoke pass.

## 2026-09-05 sandbox/e2e/load continuation

- Non-financial third-party boundaries now use deterministic `SandboxProviderRegistry` adapters for SMS OTP, WeChat/QQ OAuth, real-name, moderation, object storage and notification delivery. Settings reject `SANDBOX_*` providers when `APP_ENV=production`; staging defaults remain explicit sandbox channels.
- `scripts/qa_role_e2e.py` passed against rebuilt Compose and exercised Guest, Reader, Verified Reader, Author, Signed Author, Reviewer, Operator, Finance, Risk, Admin and Super Admin boundaries, including expected 403s, real Reader/Writer/Admin shells and a successful Super Admin Agent tool call.
- `scripts/qa_advanced_workflows.py` passed Review quality, Operation ranking/editorial/recommendation/export/retention/campaign/reward idempotency, Risk login/watchlist release, Copyright dossier/rights/complaint/evidence/counter-notice, Legal hold lifecycle, Governance privacy/agreement/parameter Maker-Checker-Activate/reconciliation/invoice, and Agent audit persistence.
- `scripts/qa_mysql_load.py --concurrency 4` passed against MySQL with 12 read requests plus concurrent idempotent payment callbacks and chapter purchases; p50 `0.1593s`, p95 `0.4271s`, max `0.5859s`, negative wallet accounts `0`, duplicate wallet idempotency keys `0`. The result is local staging evidence, not a production capacity guarantee.
- SQL chapter purchase now retries bounded MySQL deadlock/lock-timeout victims (`1205`/`1213`) at the transaction boundary before returning an error; unique entitlement and append-only ledger constraints remain authoritative.
- Latest rerun after the retry/statistics fix: `qa_mysql_load.py --concurrency 4` returned 20/20 benchmark requests successful, throughput `35.03 rps`, p50 `0.0322s`, p95 `0.3557s`, max `0.3621s`, negative wallets `0`, duplicate idempotency keys `0`.

## 2026-09-05 latest verification after concurrency fix

- Backend full regression: `319 passed`; Ruff check/format and Mypy (144 source files) pass; workspace Vitest, `pnpm typecheck`, and `pnpm -r build` pass.
- `scripts/qa_role_e2e.py` returned `status=PASS` for 11 documented identities. It verifies real API permission boundaries and the Reader/Writer/Admin web shells; it is not claimed as 11 separate browser journeys.
- `scripts/qa_advanced_workflows.py` returned `status=PASS` for Review, Operation, Risk, Copyright, Legal, Governance, and Agent with least-privilege tokens, Maker/Checker separation, forbidden cross-domain writes, and reward idempotency.
- MySQL evidence: `qa_mysql_concurrency.py --concurrency 8` PASS; `qa_mysql_load.py --concurrency 16` PASS (112/112, 34.19 RPS, p50 `0.1246s`, p95 `2.1244s`, max `2.1940s`); `--concurrency 32` PASS (224/224, 37.05 RPS, p50 `0.2804s`, p95 `2.4264s`, max `3.9696s`). Both runs report zero negative wallets and zero duplicate wallet idempotency keys.
- SQL chapter purchase now acquires the account Wallet row before the entitlement re-check, preventing MySQL gap-lock cycles under concurrent first purchases; bounded 1205/1213 transaction retries remain as a final recovery path. Current Compose head is `0036_contract_author_signature`.
