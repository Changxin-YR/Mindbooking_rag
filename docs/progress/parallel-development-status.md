# V1.2 Parallel Development Status

| Wave | Workstream | Status | Branch/worktree | Commit | Tests | Blocker | Integration |
|---|---|---|---|---|---|---|---|
| 0 | Root workspace | PASS | `codex/v1.2-foundation` / `.worktrees/foundation` | `58594e7` | pnpm tests/typecheck/build | none | integrated |
| 0 | Backend core | PASS | `codex/v1.2-foundation` | `58594e7` | pytest, Ruff, Mypy | live DB credentials unavailable | integrated |
| 0 | Frontend shells | PASS | `codex/v1.2-foundation` | `58594e7` | Vitest, typecheck, build | none | integrated |
| 0 | Infrastructure/CI | PASS | `codex/v1.2-foundation` | working tree | Compose config, self-check, Docker healthchecks, apps image build and browser smoke | production registry/secret rollout remains | integrated |
| 1-4 | Consumer and governance domains | PARTIAL | `codex/v1.2-foundation` | working tree | 137 backend tests, API smoke, MySQL migration/smoke | risk/operation/admin/reader governance runtime and advanced workflows remain | integrated |
| 5 | Author finance | PARTIAL | `codex/v1.2-foundation` | working tree | finance Golden tests, migration 0008 | durable finance ledger, approval/RBAC and production payment/bank/tax credentials | integrated |
| 6-8 | Operation, governance, author/admin/risk centers | PARTIAL | `main` | working tree | 115 backend tests, workspace test/typecheck/build, migrations `0011-0017` | durable domain repositories, advanced workflows and app runtime remain | integrated |

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
- Regression evidence (latest): backend `188 passed`; workspace test/typecheck/build passed; Ruff check and Mypy passed; Alembic offline SQL and real MySQL upgrade reached `0025_membership_orders`; MySQL-backed FastAPI health/private-route/registration/login/real-name/author/content/recharge/refund/membership/gift smoke passed; backend restart preserved MySQL facts; OpenSearch and Compose browser smoke passed.
- Deliberate remaining `PARTIAL`: Risk, Operation, Admin Center, Reader Experience, Copyright, Legal and Governance application services still contain in-memory runtime state; complete membership/contract/finance policy, chapter purchase, third-party payment and browser E2E remain incomplete; Admin has not completed resource-level DataScope and MFA verification; OpenSearch projection is request-refresh based until an outbox/MQ consumer is added.

## 2026-09-05 continuation

- Fixed membership admin plan/gift creation `500` caused by the shared dispatcher argument `name` colliding with payload field `name`; API regression coverage added.
- Membership SQL checkout, signed callback, ticket grant, recharge funding and gift debit/idempotency are now runtime-verified. Commercially complete membership, contract/finance policy and external payment integration remain `PARTIAL`.

## 2026-09-05 interrupted-task continuation

- Added and executed `scripts/qa_sql_commercial_e2e.py` against the running MySQL Compose stack. The author -> contract -> fixed-version review -> VIP chapter -> reader recharge -> chapter purchase -> revenue -> settlement -> withdrawal -> Risk/Finance approval -> sandbox payout path passed, including duplicate payment and payout callbacks.
- Added TOTP MFA recovery codes/audit and high-risk Staff enforcement; added backend Review DataScope assignment filtering for `SELF/ASSIGNED/ALL/GLOBAL`; migration head is `0027_mfa_review_scope`.
- Added durable Outbox delivery deduplication and registered the core commercial event types. The current E2E produced 12 `PROCESSED` events, 0 current-run failures and no duplicate `(event_id, consumer)` deliveries.
- Fixed Sandbox Provider default callback event IDs so separate provider instances cannot reuse a process-local `event-1` identifier for different references.
- Latest verification: backend `211 passed`, Ruff/Ruff format/Mypy, workspace Vitest/typecheck/build, and `qa_compose_smoke.py`, `qa_v12_smoke.py`, `qa_writer_editor_smoke.py` all pass. Full role-by-role browser E2E, cross-instance concurrency, and real payment/payout credentials remain unverified.

Status is updated only after a fresh command verifies the stated test result.
