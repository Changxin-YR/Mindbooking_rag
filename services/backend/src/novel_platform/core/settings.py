import os
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Settings:
    database_url: str
    opensearch_url: str = ""
    app_name: str = "Novel Platform API"
    app_version: str = "0.1.0"
    cors_origins: tuple[str, ...] = ()
    session_secret: str = ""
    real_name_encryption_key: str = ""
    session_ttl_seconds: int = 86_400
    payment_callback_secret: str = ""
    payment_callback_max_skew_seconds: int = 300
    persistence_mode: str = "memory"
    staff_bootstrap_employee_code: str = ""
    staff_bootstrap_password: str = ""
    outbox_worker_id: str = "backend-outbox"
    outbox_poll_interval_seconds: float = 1.0

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
            opensearch_url=os.getenv("OPENSEARCH_URL", "").strip().rstrip("/"),
            cors_origins=origins,
            session_secret=os.getenv("SESSION_SECRET", os.getenv("HMAC_SECRET", "")),
            real_name_encryption_key=os.getenv("REAL_NAME_ENCRYPTION_KEY", ""),
            session_ttl_seconds=int(os.getenv("SESSION_TTL_SECONDS", "86400")),
            payment_callback_secret=os.getenv(
                "PAYMENT_CALLBACK_SECRET", "development-only-payment-callback-secret"
            ),
            payment_callback_max_skew_seconds=int(
                os.getenv("PAYMENT_CALLBACK_MAX_SKEW_SECONDS", "300")
            ),
            persistence_mode=os.getenv("PERSISTENCE_MODE", "memory").strip().lower(),
            staff_bootstrap_employee_code=os.getenv("STAFF_BOOTSTRAP_EMPLOYEE_CODE", "").strip(),
            staff_bootstrap_password=os.getenv("STAFF_BOOTSTRAP_PASSWORD", ""),
            outbox_worker_id=os.getenv("OUTBOX_WORKER_ID", "backend-outbox").strip()
            or "backend-outbox",
            outbox_poll_interval_seconds=max(
                0.05, float(os.getenv("OUTBOX_POLL_INTERVAL_SECONDS", "1"))
            ),
        )
