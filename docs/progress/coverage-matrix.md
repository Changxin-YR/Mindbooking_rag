# V1.2 Coverage Matrix

| Wave | Workstream | Status | Evidence |
| --- | --- | --- | --- |
| 0 | Monorepo, FastAPI, Nuxt/Vite, Compose, CI | PASS | workspace builds, Compose config, foundation self-check |
| 1 | IAM, real-name account limit, author/profile, staff/RBAC, content versions | PASS | `tests/modules/test_identity_author_staff.py`, `test_content_review_reading.py`, migrations `0002-0003` |
| 2 | Review, fixed-version publish, reader access, progress, shelf | PASS | `tests/modules/test_content_review_reading.py`, API smoke tests |
| 3 | Wallet, lots, expiry-first/FIFO, payment callback, purchase, membership | PASS | `tests/golden/test_wallet_commerce.py`, migration `0005` |
| 4 | Refund formula/snapshot/source lock, reports, notification, support, risk, approval | PASS | `tests/golden/test_refund.py`, `tests/modules/test_governance.py`, migrations `0006-0007` |
| 5 | Contract, revenue ledger, settlement, withdrawal, chargeback/recovery | PASS | `tests/golden/test_author_finance.py`, migration `0008` |
| 6 | Ranking/recommendation separation, editorial slots, export, retention policy/jobs | PARTIAL | `tests/golden/test_operation_legal.py`, `test_governance_v12.py`; campaigns/rewards and basic author metrics exist, advanced search/experiments/jobs remain |
| 7 | Copyright dossier/rights/conflict/complaint/counter notice, legal case/hold | PASS | `tests/golden/test_operation_legal.py`, migration `0009` |
| 7 | Privacy requests, agreements, parameter/change center, advanced audit/file governance | PARTIAL | `test_governance_v12.py`; privacy/agreement/parameter/reconciliation/emergency/outbox facts and migration `0011` exist, full persistence/audit/file service remains |
| Reader experience | Catalog filters, rating eligibility, follows, growth, corrections, minor policy | PARTIAL | API, `0010_reader_experience`, public detail/read/shelf/wallet/support/settings pages; full community/profile/preferences remain |
| Writer center | Calendar, tasks, growth, campaigns, academy, funnel, appeals | PARTIAL | `test_author_center_v12.py`, migration `0012`, Writer workspace routes; editor, signing, full finance and public author page remain |
| Admin center | Rule library, review queue, quality, User360 masking, support/CSAT | PARTIAL | `test_admin_center_v12.py`, migration `0013`, Admin workspace routes; full dashboard/read models, governance moderation and file/audit views remain |
| Risk center | Login signals, observe/freeze, watchlist with audited release | PARTIAL | `test_admin_center_v12.py`, migration `0014`; SMS, device graph, volume detection, emergency playbooks remain |
| UI | Reader | PARTIAL | home/catalog plus detail/read/library/wallet/support/settings routes and API loading states |
| UI | Writer | PARTIAL | live works/reviews/calendar workspace and states; full editor/analytics/signing/finance flows remain |
| UI | Admin | PARTIAL | live review/rules/User360/support/finance/risk/parameter workspaces; full operational pages remain |

`PARTIAL` records the exact remaining scope; it is not a claim of full V1.2 acceptance.
