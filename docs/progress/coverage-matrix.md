# V1.2 Coverage Matrix

| Wave | Workstream | Status | Evidence |
| --- | --- | --- | --- |
| 0 | Monorepo, FastAPI, Nuxt/Vite, Compose, CI | PASS | workspace builds, Compose config, foundation self-check |
| 1 | IAM, real-name account limit, author/profile, staff/RBAC, content versions | PASS | `tests/modules/test_identity_author_staff.py`, `test_content_review_reading.py`, migrations `0002-0003` |
| 2 | Review, fixed-version publish, reader access, progress, shelf | PASS | `tests/modules/test_content_review_reading.py`, API smoke tests |
| 3 | Wallet, lots, expiry-first/FIFO, payment callback, purchase, membership | PASS | `tests/golden/test_wallet_commerce.py`, migration `0005` |
| 4 | Refund formula/snapshot/source lock, reports, notification, support, risk, approval | PASS | `tests/golden/test_refund.py`, `tests/modules/test_governance.py`, migrations `0006-0007` |
| 5 | Contract, revenue ledger, settlement, withdrawal, chargeback/recovery | PASS | `tests/golden/test_author_finance.py`, migration `0008` |
| 6 | Ranking/recommendation separation, editorial slots, export, retention policy/jobs | PARTIAL | `tests/golden/test_operation_legal.py`, migration `0009`; advanced search, campaigns, rewards, metrics remain |
| 7 | Copyright dossier/rights/conflict/complaint/counter notice, legal case/hold | PASS | `tests/golden/test_operation_legal.py`, migration `0009` |
| 7 | Privacy requests, agreements, parameter/change center, advanced audit/file governance | PARTIAL | retention/export primitives exist; dedicated workflows remain |
| Reader experience | Catalog filters, rating eligibility, follows, growth, corrections, minor policy | PARTIAL | API, `0010_reader_experience`, and Reader catalog states are wired; profile/privacy, preferences, and full moderation workflows remain |
| UI | Reader | PARTIAL | home/library/ranking/finished/free routes and live catalog loading; reader detail/community/wallet/support screens remain |
| UI | Writer | PARTIAL | dashboard, author workspaces, shell states; editor/analytics/signing/finance screens remain |
| UI | Admin | PARTIAL | review/risk/finance/governance workspaces and shell states; advanced centers remain |

`PARTIAL` records the exact remaining scope; it is not a claim of full V1.2 acceptance.
