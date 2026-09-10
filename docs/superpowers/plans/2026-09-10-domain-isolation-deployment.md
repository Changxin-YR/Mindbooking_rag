# 23331.cloud Domain Isolation Deployment Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Expose MindBook through the dedicated `https://23331.cloud/books/` path, isolate its business/data plane from the two existing projects, and verify migration, page delivery, and real Staff login.

**Architecture:** Keep the existing Docker Compose modular monolith. Bind project services and databases to loopback only, retain a project-specific Compose network/volumes, and route only `/books/` from the host Nginx to the project gateway. Use the existing Staff API and MySQL-backed seed credentials for an end-to-end login check.

**Tech Stack:** Docker Compose, MySQL 8.4, FastAPI, Vue/Nuxt, Nginx, Alembic, PowerShell, SSH.

**Spec:** `docs/business/V1.2-FINAL-MASTER-DEVELOPMENT-SPEC-V2.md`

## Global Constraints

- `StaffAccount` 与 `PlatformAccount` 分离。
- 跨 Domain 通过 Application Port / Domain Event / API Contract。
- MySQL 8.4 是业务事实源；Migration 使用 Alembic。
- 三个 API Surface 保持 `/api/v1`、`/writer/api/v1`、`/admin/api/v1`。
- 不把 Secret 提交 Git；生产配置从现网 `.env` 继承。
- 关键写操作和登录必须通过真实 API 验证，不能用纯 Mock。

### Task 1: Repository ingress and isolation defaults

**Files:**
- Modify: `infra/docker-compose.yml`
- Modify: `.env.example`
- Modify: `infra/nginx/nginx.conf`
- Create: `scripts/qa_domain_isolation.py`
- Create: `docs/deployment/domain-isolation.md`

- [x] Add explicit `BOOKS_PUBLIC_HOST`, `BOOKS_API_BASE_URL`, and loopback-only service bindings while preserving the existing Compose project name and named volumes.
- [x] Add a repository-owned Nginx route for `/books/` and deny cross-project paths on that host.
- [x] Add a deterministic QA script that checks Host routing, service port exposure, Compose network separation, database identity, migration head, login page delivery, and real Staff login.
- [x] Document DNS, certificate, deployment, rollback, and verification commands without copying secrets.
- [x] Run Compose config validation and the focused QA checks where the configured server is available.

### Task 2: Cloud migration and verification

**Files:**
- Remote: `/etc/nginx/conf.d/adp-auth.conf`, `/etc/nginx/conf.d/adp-project-routes.inc`
- Remote: `/opt/novel-platform/releases/<release>/.env`

- [ ] Snapshot active Nginx config and current release pointer.
- [ ] Install the dedicated `/books/` route with `proxy_set_header Host 23331.cloud` and explicit `/api/v1`, `/writer/api/v1`, `/admin/api/v1`, `/writer/`, `/admin/`, and `/` routing.
- [ ] Verify `nginx -t`, reload, HTTPS response, login page, backend readiness, Alembic head, and real Staff login using the existing staging bootstrap account without printing its password.
- [ ] Prove isolation by checking the project network is distinct from `infra_default`, MySQL/OpenSearch bind only to loopback, and the dedicated host cannot reach the other projects' paths.
- [ ] Keep the prior release and Nginx backup for rollback; report any DNS/certificate blocker explicitly.

---
