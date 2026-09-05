# V1.2 Coverage Matrix

| Wave | Workstream | Status | Evidence |
| --- | --- | --- | --- |
| 0 | Monorepo, FastAPI, Nuxt/Vite, Compose, CI | PASS | workspace builds, Compose config, foundation self-check |
| 1 | IAM, real-name account limit, author/profile, staff/RBAC, content versions | PARTIAL | account/password/session, SQL IAM and SQL Author repositories, SQL Content versions, real-name locking, Staff MFA/TOTP recovery codes/audit and bearer/RBAC gates tested; migrations `0002-0003`, `0015`, `0017`, `0027`; OAuth remains outside the verified scope |
| 2 | Review, fixed-version publish, reader access, progress, shelf | PARTIAL | SQL Content/Review/Reading/Library services are wired; fixed-version publish, review decisions, progress and shelf persistence have SQLite and MySQL smoke evidence; full access policy and browser E2E remain |
| 3 | Wallet, lots, expiry-first/FIFO, payment callback, purchase, membership | PARTIAL | SQL Wallet lot/ledger/source recovery, durable chapter purchase/entitlement/revenue transaction, Sandbox PaymentProvider callbacks, membership order/callback/ticket grant and gift debit are wired; migrations `0016`, `0025`; full membership policy remains |
| 4 | Refund formula/snapshot/source lock, reports, notification, support, risk, approval | PARTIAL | SQL Refund/Community/Notification/Support/Approval services are wired; migrations `0006-0007`; Risk and full operational governance persistence remain |
| 5 | Contract, revenue ledger, settlement, withdrawal, chargeback/recovery | PARTIAL | SQL Author Finance contract/revenue/settlement/withdrawal/payout adapters are wired; risk and finance approvals plus SandboxPayoutProvider success/idempotency are verified; production policy versions, bank/tax integration and complete approval workflow remain |
| 6 | Ranking/recommendation separation, editorial slots, export, retention policy/jobs | PARTIAL | `tests/golden/test_operation_legal.py`, `test_governance_v12.py`; campaigns/rewards and basic author metrics exist, advanced search/experiments/jobs remain |
| 7 | Copyright dossier/rights/conflict/complaint/counter notice, legal case/hold | PASS | `tests/golden/test_operation_legal.py`, migration `0009` |
| 7 | Privacy requests, agreements, parameter/change center, advanced audit/file governance | PARTIAL | `test_governance_v12.py`; privacy/agreement/parameter/reconciliation/emergency/outbox facts and migration `0011` exist, full persistence/audit/file service remains |
| Search | Multi-field query, filter, sort, typo correction, fallback | PARTIAL | `tests/modules/test_search_v12.py`, OpenSearch REST projection/index wiring, empty-result and unavailable fallback checks; event-driven projection lifecycle and Chinese analyzer tuning remain |
| Agent | Gateway, Tool/Resource, Business Service boundary, audit | PARTIAL | `tests/modules/test_agent_v12.py`; read-only callbacks and high-risk write rejection are present, durable audit and full Business API remain |
| Reader experience | Catalog filters, rating eligibility, follows, growth, corrections, minor policy | PARTIAL | API, `0010_reader_experience`, public detail/read/shelf/wallet/support/settings pages; full community/profile/preferences remain |
| Writer center | Calendar, tasks, growth, campaigns, academy, funnel, appeals | PARTIAL | `test_author_center_v12.py`, migration `0012`, Writer workspace routes; editor, signing, full finance and public author page remain |
| Admin center | Rule library, review queue, quality, User360 masking, support/CSAT | PARTIAL | `test_admin_center_v12.py`, staff session/RBAC/DataScope/MFA tests, migrations `0013`, `0017`, `0027`, Admin workspace routes; scoped review assignment is verified, while full operational pages, governance moderation and file/audit views remain |
| Risk center | Login signals, observe/freeze, watchlist with audited release | PARTIAL | `test_admin_center_v12.py`, migration `0014`; SMS, device graph, volume detection, emergency playbooks remain |
| UI | Reader | PARTIAL | home/catalog plus detail/read/library/wallet/support/settings routes and API loading states |
| UI | Writer | PARTIAL | live works/reviews/calendar workspace and states; Compose apps image and browser smoke pass; full editor/analytics/signing/finance flows remain |
| UI | Admin | PARTIAL | live review/rules/User360/support/finance/risk/parameter workspaces; Staff login and Compose browser smoke pass; full operational pages remain |

`PARTIAL` records the exact remaining scope; it is not a claim of full V1.2 acceptance.

## 2026-09-05 continuation evidence

- Backend full regression: `211 passed`; Ruff, Ruff format, Mypy, workspace Vitest, typecheck and production builds pass.
- Real SQL commercial E2E: author -> contract approval/activation -> fixed-version review -> VIP policy -> reader real-name/recharge -> signed Sandbox payment callback and duplicate callback -> chapter purchase/entitlement -> wallet/ledger -> revenue confirmation -> settlement -> withdrawal -> risk/finance approval -> Sandbox payout success and duplicate callback: PASS.
- Runtime Outbox: the current E2E's 12 core events are `PROCESSED`; current-run failed events `0`; `outbox_event_deliveries` has no duplicate `(event_id, consumer)` keys.
- Migration head: `0027_mfa_review_scope`; verified tables include `staff_mfa_audits`, `review_tasks.assigned_staff_id`, and `outbox_event_deliveries`.
- Compose API/browser smoke: `qa_compose_smoke.py`, `qa_v12_smoke.py`, and `qa_writer_editor_smoke.py` all PASS.
- Remaining evidence gaps: full role-by-role browser E2E, cross-instance MySQL concurrency, and real third-party payment/payout credentials are not claimed as PASS.
- Docker apps profile was rebuilt and all services are healthy. OpenAPI includes `/api/v1/membership/orders`, `/api/v1/membership/payments/callback` and `/api/v1/gifts`.
- Runtime SQL smoke passed: Staff-configured membership plan, real-name gate, idempotent order creation, invalid/valid signed callback, membership activation, configured ticket grant, recharge callback, gift debit and duplicate gift request.
- Fixed a membership HTTP dispatcher collision where the dispatcher parameter `name` conflicted with plan/gift payload field `name`; added API regression coverage.
