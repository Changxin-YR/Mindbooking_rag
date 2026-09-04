import os
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Settings:
    database_url: str
    app_name: str = "Novel Platform API"
    app_version: str = "0.1.0"
    cors_origins: tuple[str, ...] = ()

    @classmethod
    def from_env(cls) -> Settings:
        origins = tuple(
            origin.strip() for origin in os.getenv("CORS_ORIGINS", "").split(",") if origin.strip()
        )
        return cls(
            database_url=os.getenv(
                "DATABASE_URL",
                "mysql+pymysql://root:password@127.0.0.1:3306/novel_platform",
            ),
            cors_origins=origins,
        )
