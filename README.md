# MindBooking_rag
基于国内诸多主流小说平台，结合deepseek_harnesss智能体设计的一个现代化智能阅读与写作平台

## Local development

```powershell
pnpm install
./scripts/dev.ps1
```

Backend quality checks run from `services/backend`:

```powershell
pytest -q
ruff format --check src tests
ruff check src tests
mypy src
alembic upgrade head
```

The API exposes `/api/v1`, `/writer/api/v1`, and `/admin/api/v1`. Compose starts
MySQL, Redis, RabbitMQ, OpenSearch, ClickHouse, MinIO, and the local proxy.
Production payment, SMS, identity, tax, and bank adapters remain external
credential boundaries; the local commerce adapter is intentionally fake.
