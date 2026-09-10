# MindBook domain deployment

正式入口为 `https://23331.cloud/books/`，这是 23331.cloud 下只代理 MindBook 的独立路径。兼容入口不会再落到其他项目。

## DNS 与证书

现有 `23331.cloud` 证书覆盖根域，因而无需新增子域即可上线。若以后启用 `books.23331.cloud`，需增加 `A 1.14.148.15` 记录并签发包含该主机名的新证书。

## 部署

```bash
git pull --ff-only origin main
cp .env .env.backup.$(date +%Y%m%d%H%M%S)
docker compose --env-file .env -f infra/docker-compose.yml --profile apps config --quiet
docker compose --env-file .env -f infra/docker-compose.yml --profile apps up -d --build --force-recreate
docker compose --env-file .env -f infra/docker-compose.yml exec backend alembic upgrade head
```

生产 `.env` 至少设置 `COMPOSE_PROJECT_NAME=novel-platform-books`、`BOOKS_PUBLIC_HOST=23331.cloud`、`BOOKS_API_BASE_URL=https://23331.cloud/books`，并让 `MYSQL_PORT`、`API_PORT`、`NGINX_HTTP_PORT` 使用 `127.0.0.1:端口` 形式。不要把 `.env` 提交 Git。

外层 Nginx 使用独立配置文件，仅将 `/books/` 及其 API、Writer、Admin 子路径代理到 `127.0.0.1:18080`；根路径和其他项目路径返回明确的重定向或 404。项目网关同时拒绝未列入白名单的 Host。

## 验收与回滚

```bash
python scripts/qa_domain_isolation.py --base-url https://23331.cloud/books --skip-compose
docker network inspect novel-platform-books_default
docker network inspect infra_default
docker volume ls --format '{{.Name}}' | grep -E 'novel-platform-books|infra'
```

确认登录页、`/api/v1/health/ready`、Reader、Writer、Admin 和 Staff 登录均通过后再切换 release。失败时恢复外层 Nginx 备份、切回旧 `current` release，并保留数据库卷，不删除历史业务事实。
