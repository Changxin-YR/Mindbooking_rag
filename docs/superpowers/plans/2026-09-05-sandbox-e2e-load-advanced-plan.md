# Sandbox E2E, Load, and Advanced Workflows Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Verify and extend the V1.2 platform so all external integrations use deterministic sandbox adapters, every documented role has an executable E2E path, and advanced operational domains have repeatable workflow and load evidence.

**Architecture:** Reuse the existing Application/Domain/SQL services and explicit DTO APIs. Add only deterministic sandbox adapters and QA harnesses where a third-party boundary is currently implicit. Role tests authenticate through the real Staff/Reader/Writer endpoints; load tests target the running MySQL Compose stack and fail closed on non-MySQL persistence.

**Tech Stack:** FastAPI, SQLAlchemy/MySQL, Alembic, Playwright, Python standard library concurrency, Vitest, Docker Compose.

---

### Task 1: Sandbox external provider registry

**Files:**
- Create: `services/backend/src/novel_platform/modules/integrations/provider.py`
- Modify: `services/backend/src/novel_platform/core/settings.py`
- Modify: `services/backend/src/novel_platform/main.py`
- Test: `services/backend/tests/modules/test_sandbox_integrations.py`

- [ ] Write tests for deterministic SMS OTP, WeChat/QQ OAuth identity, real-name verification, moderation, object-storage, and notification delivery results.
- [ ] Implement in-memory deterministic adapters with explicit provider names and no network calls.
- [ ] Wire provider selection through settings and expose provider health metadata without exposing secrets.
- [ ] Verify invalid provider configuration fails closed and sandbox mode remains staging-only.

### Task 2: Full role E2E

**Files:**
- Create: `scripts/qa_role_e2e.py`
- Modify: `docs/progress/coverage-matrix.md`
- Modify: `docs/progress/sandbox-release-readiness.md`

- [ ] Seed and authenticate Guest, Reader, Verified Reader, Author, Signed Author, Reviewer, Operator, Finance, Risk, Admin, and Super Admin identities.
- [ ] Exercise the least-privilege API path for each role, including an intentional forbidden cross-domain write.
- [ ] Run the same checks through browser pages for Reader, Writer, and Admin and emit JSON evidence.

### Task 3: Production-shaped MySQL load gate

**Files:**
- Create: `scripts/qa_mysql_load.py`
- Modify: `scripts/qa_mysql_concurrency.py`
- Modify: `docs/progress/coverage-matrix.md`
- Modify: `docs/progress/sandbox-release-readiness.md`

- [ ] Add a bounded concurrent workload for login, catalog, wallet read, idempotent purchase, payment callback, and payout review.
- [ ] Report p50/p95 latency, throughput, error count, duplicate-ledger count, and negative-wallet count.
- [ ] Fail when persistence is not MySQL or financial invariants are violated; keep thresholds configurable by environment.

### Task 4: Advanced-domain workflow E2E

**Files:**
- Create: `scripts/qa_advanced_workflows.py`
- Test: `services/backend/tests/modules/test_advanced_workflows.py`
- Modify: `docs/progress/coverage-matrix.md`

- [ ] Exercise review queue and quality metrics, operation ranking/editorial/recommendation/campaign/reward, risk observe/freeze/watchlist release, copyright rights/complaint/counter-notice, legal hold/release, governance privacy/agreement/parameter/reconciliation/invoice, and Agent audit filtering.
- [ ] Verify Maker/Checker and DataScope permissions plus idempotency/retry behavior for every write path.
- [ ] Record every workflow result as explicit PASS/PARTIAL evidence rather than upgrading unsupported production claims.

### Task 5: Full verification

**Files:**
- Modify: `docs/progress/v1.2-development-acceptance-report.md`
- Modify: `docs/progress/requirements-compliance-report.md`

- [ ] Run backend, frontend, lint, typecheck, build, offline migration, all smoke scripts, role E2E, advanced workflow E2E, and MySQL load/concurrency gates.
- [ ] Update Coverage Matrix with fresh counts and preserve `PARTIAL` for real credentials, formal legal/tax decisions, and production capacity evidence.
