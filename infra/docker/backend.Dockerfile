FROM python:3.14-slim

WORKDIR /app

COPY services/backend/pyproject.toml services/backend/pyproject.toml
RUN pip install --no-cache-dir \
    "alembic>=1.18,<2" \
    "cryptography>=44,<49" \
    "fastapi>=0.115,<1" \
    "pydantic>=2.10,<3" \
    "pymysql>=1.1,<2" \
    "sqlalchemy>=2,<3" \
    "uvicorn[standard]>=0.34,<1"

COPY services/backend/alembic.ini services/backend/alembic.ini
COPY services/backend/alembic services/backend/alembic
COPY services/backend/src services/backend/src

ENV PYTHONPATH=/app/services/backend/src
EXPOSE 80
CMD ["sh", "-c", "alembic -c services/backend/alembic.ini upgrade head && uvicorn novel_platform.main:app --host 0.0.0.0 --port 80"]
