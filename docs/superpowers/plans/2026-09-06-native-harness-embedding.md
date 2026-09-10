# Native DeepSeek Harness Embedding Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Embed the untouched DeepSeek Harness `dsh web` workbench inside the Admin Console with per-Staff session isolation.

**Architecture:** The backend launches one loopback `dsh web` process per Staff actor/session and returns its authenticated launch URL. The Admin UI renders the returned URL in an iframe; Harness MCP calls continue to the existing permission-checked backend gateway.

**Tech Stack:** FastAPI, Python subprocess/threading, existing StaffAuth/RBAC/MCP gateway, Vue-compatible Admin Vite shell, Docker Compose, native DeepSeek Harness checkout.

---

### Task 1: Native Harness process manager

**Files:**
- Modify: `services/backend/src/novel_platform/modules/agent/runtime.py`
- Test: `services/backend/tests/modules/test_agent_harness_integration.py`

- [ ] Add a small process manager that launches `dsh web --no-open --host 127.0.0.1 --port 0`, captures the printed authenticated URL, assigns an isolated `DSH_HOME`, and stops the process on session close.
- [ ] Inject the Staff access token and MCP endpoint through a generated per-session patch/config without changing Harness source.
- [ ] Keep actor/session/token checks and expose `web_url(actor_id, session_id, access_token)` plus `close`/`close_all`.
- [ ] Add tests for URL parsing, actor mismatch, token rotation, and graceful process shutdown using a fake launcher.

### Task 2: Admin backend URL endpoint and lifecycle

**Files:**
- Modify: `services/backend/src/novel_platform/modules/agent/api.py`
- Modify: `services/backend/src/novel_platform/main.py`
- Test: `services/backend/tests/modules/test_agent_harness_integration.py`

- [ ] Add `GET /admin/api/v1/agent/harness-url` behind `agent.execute` and return an explicit DTO containing only the current session's URL and session id.
- [ ] Ensure token changes and logout cannot reuse the prior process; map startup failures to a friendly 503 response.
- [ ] Keep existing `/chat`, `/mcp`, and `/tools/execute` behavior intact for API clients.

### Task 3: Admin native workbench iframe

**Files:**
- Modify: `apps/admin-web/src/main.ts`
- Modify: `apps/admin-web/src/route.css`
- Test: `apps/admin-web/tests/agent.test.ts`

- [ ] Replace the custom chat panel for `AI 运营助手` with an iframe loading the backend-provided native Harness URL.
- [ ] Add loading, unavailable, reload, and logout cleanup states; do not render this view in reader or writer apps.
- [ ] Preserve the existing Admin navigation and design tokens; do not copy Harness components.

### Task 4: Runtime/deployment configuration

**Files:**
- Modify: `services/backend/src/novel_platform/core/settings.py`
- Modify: `infra/docker-compose.yml`
- Modify: `infra/docker/backend.Dockerfile`
- Modify: `.env.example`

- [ ] Add environment-configurable Harness checkout/CLI path, home root, startup timeout, and optional model settings.
- [ ] Make the backend container able to invoke the local Harness CLI/runtime and keep the process loopback-only.
- [ ] Document required external conditions without committing credentials.

### Task 5: Verification

**Files:**
- Modify: `services/backend/tests/modules/test_agent_harness_integration.py`
- Add: `scripts/qa_native_harness_embed.py`

- [ ] Run backend unit/integration tests, Admin typecheck/Vitest/build, and a Playwright smoke that logs in, opens the iframe, and verifies the native Harness document is reachable.
- [ ] Run permission, DataScope, Prompt Injection, and cross-session checks against MCP.
- [ ] Report any missing native build/runtime/model credential as an external blocker only.
