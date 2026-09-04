import os
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Settings:
    database_url: str
    app_name: str = "Novel Platform API"
    app_version: str = "0.1.0"

    @classmethod
    def from_env(cls) -> Settings:
        return cls(
            database_url=os.getenv(
                "DATABASE_URL",
                "mysql+pymysql://root:password@127.0.0.1:3306/novel_platform",
            )
        )
