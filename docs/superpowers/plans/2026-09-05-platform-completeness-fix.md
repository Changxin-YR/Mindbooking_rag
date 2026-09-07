# V1.2 Platform Completeness Fix Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close the confirmed payment, payout, deployment, permission, and web-client gaps and verify the three web clients against the V1.2 frozen specification.

**Architecture:** Keep the existing Application/Domain boundaries and DTO contracts. Payment and payout callbacks will use explicit UTC normalization and monotonic state-transition rules; staff routes will enforce the existing staff session/permission ports; deployment will pass callback configuration through Compose. Frontend changes remain limited to API-client/session correctness and evidence-based missing workflows.

**Tech Stack:** Python/FastAPI, SQLAlchemy/MySQL, Alembic, TypeScript/Vite/Nuxt, Vitest/Pytest, Docker Compose, Playwright.

---

### Task 1: Payment and Payout Callback State Machines

**Files:**
- Modify: `services/backend/src/novel_platform/modules/commerce/sql_service.py`
- Modify: `services/backend/src/novel_platform/modules/author_finance/sql_service.py`
- Test: `services/backend/tests/modules/test_sql_commerce.py`
- Test: `services/backend/tests/modules/test_sql_payout.py`

- [x] Add regression tests for repeated provider transaction IDs, naive callback timestamps, and stale payout/payment events.
- [x] Run the focused tests and confirm the pre-fix failures.
- [x] Normalize callback datetimes through the existing UTC helper and apply explicit monotonic transition rules.
- [x] Record provider events idempotently without violating the channel transaction uniqueness constraint.
- [x] Run focused and module-level tests.

### Task 2: Staff Authorization and Payment Deployment Configuration

**Files:**
- Modify: `services/backend/src/novel_platform/modules/author_center/api.py`
- Modify: `services/backend/src/novel_platform/modules/admin_center/api.py`
- Modify: `infra/docker-compose.yml`
- Test: `services/backend/tests/modules/test_auth_protected_routes.py`

- [x] Add failing route tests for anonymous access and writer ownership checks.
- [x] Add staff session and permission guards using the existing platform auth helpers.
- [x] Inject `PAYMENT_CALLBACK_SECRET` and `PAYMENT_CALLBACK_MAX_SKEW_SECONDS` into the backend Compose service.
- [x] Run route and Compose/config tests.

### Task 3: Web Client Contract and Workflow Audit

**Files:**
- Modify only the specific client files identified by the audit under `apps/reader-web`, `apps/writer-web`, `apps/admin-web`, `packages/api-client`, and `packages/api-types`.
- Test: corresponding client test files.

- [x] Inventory every route/menu action and compare it to the frozen Reader, Writer, and Admin coverage matrix.
- [x] Add failing tests for concrete missing/broken client behavior, prioritizing session expiry, payment sandbox UX, and API error handling.
- [x] Implement the smallest fixes while preserving the frozen stack and explicit DTOs.
- [x] Run all client unit tests and production builds.

### Task 4: Full Verification and Coverage Matrix

**Files:**
- Modify: `docs/progress/coverage-matrix.md`
- Modify: `docs/progress/v1.2-development-acceptance-report.md`
- Test: repository CI/test commands and Playwright smoke scripts.

- [x] Run backend unit/integration tests, client tests/builds, and available Docker/Playwright smoke checks.
- [x] Reconcile each frozen matrix row with evidence, marking only verified items complete and retaining explicit partial/external-provider limitations.
- [x] Run a final diff/status review and report remaining blockers separately from fixed defects.

### Task 5: Completeness Continuation Workstreams

**Files:**
- Modify: `services/backend/src/novel_platform/modules/agent/api.py`, `application.py`, `sql_audit.py`
- Modify: `services/backend/src/novel_platform/modules/search/repository.py`, `governance/worker.py`, `main.py`
- Modify: `services/backend/src/novel_platform/modules/reading/api.py`, `application.py`, `domain.py`
- Modify: `services/backend/src/novel_platform/core/settings.py`, `core/middleware.py`
- Test: `services/backend/tests/modules/test_agent_audit_api.py`, `test_agent_sql_query.py`, `test_search_projection_outbox.py`, `test_reading_tts.py`, `tests/test_settings.py`

- [x] Add Staff-only paginated Agent audit DTO/API with sensitive-argument step-up permission.
- [x] Add idempotent Outbox search projection handler for public index/takedown events and register it in runtime worker.
- [x] Add access-gated deterministic TTS metadata endpoint using the shared chapter access decision.
- [x] Add production fail-closed settings validation and explicit provider-adapter startup guard.
- [x] Run backend full regression, Ruff, Mypy, workspace Vitest/typecheck/build and update Coverage Matrix/report.

### Task 6: Payment Credit Repair Lifecycle

**Files:**
- Modify: `services/backend/src/novel_platform/modules/governance/domain.py`
- Modify: `services/backend/src/novel_platform/modules/governance/application.py`
- Modify: `services/backend/src/novel_platform/modules/governance/sql_service.py`
- Modify: `services/backend/src/novel_platform/modules/governance/api.py`
- Modify: `services/backend/src/novel_platform/main.py`
- Test: `services/backend/tests/modules/test_governance_v12.py`
- Test: `services/backend/tests/modules/test_sql_governance_services.py`

- [x] Add staff-only list/get/retry/resolve operations for `CREDIT_PENDING` records with explicit `REPAIR_REQUIRED` failure state.
- [x] Make retries idempotent and preserve the original provider success fact and append-only ledger history.
- [x] Add API DTOs, permission checks, SQL persistence, migration if required, and regression tests.

### Task 7: Payout Provider Transaction Identity and Callback Freshness

**Files:**
- Modify: `services/backend/alembic/versions/0032_payout_provider_transaction.py`
- Modify: `services/backend/migration.sql`
- Modify: `services/backend/src/novel_platform/modules/author_finance/sql_service.py`
- Modify: `services/backend/src/novel_platform/modules/author_finance/application.py`
- Modify: `services/backend/src/novel_platform/modules/author_finance/api.py`
- Modify: `services/backend/src/novel_platform/modules/wallet/api.py`
- Modify: `services/backend/src/novel_platform/modules/membership/api.py`
- Test: payout/payment callback regression tests.

- [x] Persist `provider_transaction_id` for payout orders and reject reuse across different payouts.
- [x] Enforce callback event freshness using UTC `occurred_at` and configured skew without rejecting delayed-but-authorized sandbox events.
- [x] Add focused tests for stale/future events and cross-order transaction reuse.

### Task 8: Real MySQL Concurrency Evidence

**Files:**
- Create: `scripts/qa_mysql_concurrency.py`
- Modify: `docs/progress/sandbox-release-readiness.md`
- Modify: `docs/progress/coverage-matrix.md`

- [x] Exercise concurrent wallet spend, duplicate payment callback, duplicate purchase, settlement lock contention, and payout review race against the Compose MySQL service.
- [x] Fail closed when the target is not MySQL; emit machine-readable evidence for release reports.
- [x] Run the script against the current Compose stack and record results.

### Task 9: Virtual Contract Document

**Files:**
- Modify: `services/backend/src/novel_platform/modules/author_finance/domain.py`
- Modify: `services/backend/src/novel_platform/modules/author_finance/application.py`
- Modify: `services/backend/src/novel_platform/modules/author_finance/sql_service.py`
- Modify: `services/backend/src/novel_platform/modules/author_finance/api.py`
- Modify: `apps/writer-web/src/main.ts`, `apps/writer-web/src/route.css`
- Create: `services/backend/alembic/versions/0035_virtual_contract_document.py`
- Test: `services/backend/tests/golden/test_author_finance.py`, `services/backend/tests/modules/test_sql_author_finance.py`, `services/backend/tests/test_app.py`

- [x] Generate a deterministic `SANDBOX_CN_2026_V1` document and SHA-256 at contract creation.
- [x] Persist and rebuild document fields through SQL migration `0035_virtual_contract_document`.
- [x] Expose an ownership-checked Writer GET endpoint and render the document in the Writer signing view.
- [x] Verify backend, frontend, migration, Compose and SQL commercial smoke evidence.
