from functools import lru_cache

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import SQLAlchemyError

from novel_platform.core.settings import Settings


@lru_cache
def get_engine(database_url: str) -> Engine:
    return create_engine(database_url, pool_pre_ping=True)


def database_is_ready(settings: Settings) -> bool:
    try:
        with get_engine(settings.database_url).connect() as connection:
            connection.execute(text("SELECT 1"))
        return True
    except ModuleNotFoundError, SQLAlchemyError:
        return False
