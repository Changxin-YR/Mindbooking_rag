import os
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Settings:
    database_url: str
    app_env: str = "development"
    opensearch_url: str = ""
    app_name: str = "Novel Platform API"
    app_version: str = "0.1.0"
    cors_origins: tuple[str, ...] = ()
    session_secret: str = ""
    real_name_encryption_key: str = ""
    session_ttl_seconds: int = 86_400
    payment_callback_secret: str = ""
    payment_provider: str = "SANDBOX"
    payout_provider: str = "SANDBOX_PAYOUT"
    sms_provider: str = "SANDBOX_SMS"
    oauth_wechat_provider: str = "SANDBOX_OAUTH_WECHAT"
    oauth_qq_provider: str = "SANDBOX_OAUTH_QQ"
    realname_provider: str = "SANDBOX_REALNAME"
    moderation_provider: str = "SANDBOX_MODERATION"
    storage_provider: str = "SANDBOX_STORAGE"
    notification_provider: str = "SANDBOX_NOTIFICATION"
    payment_callback_max_skew_seconds: int = 300
    persistence_mode: str = "memory"
    staff_bootstrap_employee_code: str = ""
    staff_bootstrap_password: str = ""
    outbox_worker_id: str = "backend-outbox"
    outbox_poll_interval_seconds: float = 1.0
    agent_backend_url: str = "http://127.0.0.1:8000"
    agent_dsh_home: str = ".dsh-novel-platform"
    agent_harness_sdk_path: str = ""
    agent_harness_provider: str = "deepseek-official"
    agent_harness_model: str = "deepseek-v4-flash"
    agent_harness_api_key: str = ""
    agent_harness_base_url: str = ""
    agent_harness_profile: str = "sdk"
    agent_harness_timeout_seconds: float = 120.0
    agent_harness_runtime_mode: str = "sdk"
    agent_harness_web_command: str = ""
    agent_harness_dsh_bin: str = ""
    agent_harness_repo: str = ""
    agent_harness_web_start_timeout_seconds: float = 30.0
    agent_harness_web_bridge_url: str = ""
    agent_harness_web_bridge_secret: str = ""

    @property
    def real_name_provider(self) -> str:
        return self.realname_provider

    @property
    def object_storage_provider(self) -> str:
        return self.storage_provider

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
            app_env=os.getenv("APP_ENV", "development").strip().lower(),
            opensearch_url=os.getenv("OPENSEARCH_URL", "").strip().rstrip("/"),
            cors_origins=origins,
            session_secret=os.getenv("SESSION_SECRET", os.getenv("HMAC_SECRET", "")),
            real_name_encryption_key=os.getenv("REAL_NAME_ENCRYPTION_KEY", ""),
            session_ttl_seconds=int(os.getenv("SESSION_TTL_SECONDS", "86400")),
            payment_callback_secret=os.getenv(
                "PAYMENT_CALLBACK_SECRET", "development-only-payment-callback-secret"
            ),
            payment_provider=os.getenv("PAYMENT_PROVIDER", "SANDBOX").strip().upper(),
            payout_provider=os.getenv("PAYOUT_PROVIDER", "SANDBOX_PAYOUT").strip().upper(),
            sms_provider=os.getenv("SMS_PROVIDER", "SANDBOX_SMS").strip().upper(),
            oauth_wechat_provider=os.getenv("OAUTH_WECHAT_PROVIDER", "SANDBOX_OAUTH_WECHAT")
            .strip()
            .upper(),
            oauth_qq_provider=os.getenv("OAUTH_QQ_PROVIDER", "SANDBOX_OAUTH_QQ").strip().upper(),
            realname_provider=os.getenv(
                "REALNAME_PROVIDER", os.getenv("REAL_NAME_PROVIDER", "SANDBOX_REALNAME")
            )
            .strip()
            .upper(),
            moderation_provider=os.getenv("MODERATION_PROVIDER", "SANDBOX_MODERATION")
            .strip()
            .upper(),
            storage_provider=os.getenv(
                "STORAGE_PROVIDER",
                os.getenv("OBJECT_STORAGE_PROVIDER", "SANDBOX_STORAGE"),
            )
            .strip()
            .upper(),
            notification_provider=os.getenv("NOTIFICATION_PROVIDER", "SANDBOX_NOTIFICATION")
            .strip()
            .upper(),
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
            agent_backend_url=os.getenv("AGENT_BACKEND_URL", "http://127.0.0.1:8000")
            .strip()
            .rstrip("/"),
            agent_dsh_home=os.getenv("AGENT_DSH_HOME", ".dsh-novel-platform").strip(),
            agent_harness_sdk_path=os.getenv("DEEPSEEK_HARNESS_SDK_PATH", "").strip(),
            agent_harness_provider=os.getenv("DEEPSEEK_PROVIDER", "deepseek-official").strip(),
            agent_harness_model=os.getenv("DEEPSEEK_MODEL", "deepseek-v4-flash").strip(),
            agent_harness_api_key=os.getenv("DEEPSEEK_API_KEY", ""),
            agent_harness_base_url=os.getenv("DEEPSEEK_BASE_URL", "").strip(),
            agent_harness_profile=os.getenv("DEEPSEEK_HARNESS_PROFILE", "sdk").strip() or "sdk",
            agent_harness_timeout_seconds=max(
                1.0, float(os.getenv("DEEPSEEK_TIMEOUT_SECONDS", "120"))
            ),
            agent_harness_runtime_mode=os.getenv("DEEPSEEK_HARNESS_RUNTIME_MODE", "sdk")
            .strip()
            .lower(),
            agent_harness_web_command=os.getenv("DEEPSEEK_HARNESS_WEB_COMMAND", "").strip(),
            agent_harness_dsh_bin=os.getenv("DEEPSEEK_HARNESS_DSH_BIN", "").strip(),
            agent_harness_repo=os.getenv("DEEPSEEK_HARNESS_REPO", "").strip(),
            agent_harness_web_start_timeout_seconds=max(
                1.0, float(os.getenv("DEEPSEEK_HARNESS_WEB_START_TIMEOUT_SECONDS", "30"))
            ),
            agent_harness_web_bridge_url=os.getenv("DEEPSEEK_HARNESS_WEB_BRIDGE_URL", "")
            .strip()
            .rstrip("/"),
            agent_harness_web_bridge_secret=os.getenv("DEEPSEEK_HARNESS_WEB_BRIDGE_SECRET", ""),
        )

    def validate_runtime(self) -> None:
        """Fail closed for production when only development adapters/secrets are configured."""
        if self.app_env not in {"production", "prod"}:
            return
        if self.persistence_mode != "sql":
            raise ValueError("PRODUCTION_PERSISTENCE_REQUIRED")
        providers = (self.payment_provider, self.payout_provider)
        if any(provider.startswith("SANDBOX") for provider in providers):
            raise ValueError("PRODUCTION_PROVIDER_NOT_ALLOWED")
        integration_providers = (
            self.sms_provider,
            self.oauth_wechat_provider,
            self.oauth_qq_provider,
            self.realname_provider,
            self.moderation_provider,
            self.storage_provider,
            self.notification_provider,
        )
        integration_env_names = (
            "SMS_PROVIDER",
            "OAUTH_WECHAT_PROVIDER",
            "OAUTH_QQ_PROVIDER",
            "REALNAME_PROVIDER",
            "REAL_NAME_PROVIDER",
            "MODERATION_PROVIDER",
            "STORAGE_PROVIDER",
            "OBJECT_STORAGE_PROVIDER",
            "NOTIFICATION_PROVIDER",
        )
        if any(provider.startswith("SANDBOX") for provider in integration_providers) and any(
            os.getenv(name) is not None for name in integration_env_names
        ):
            raise ValueError("PRODUCTION_PROVIDER_NOT_ALLOWED")
        for value, code in (
            (self.session_secret, "SESSION_SECRET"),
            (self.real_name_encryption_key, "REAL_NAME_ENCRYPTION_KEY"),
            (self.payment_callback_secret, "PAYMENT_CALLBACK_SECRET"),
        ):
            if len(value) < 32 or value.startswith("development-only"):
                raise ValueError(f"PRODUCTION_SECRET_INVALID:{code}")

    def validate_integration_runtime(self) -> None:
        if self.app_env not in {"production", "prod"}:
            return
        providers = (
            self.sms_provider,
            self.oauth_wechat_provider,
            self.oauth_qq_provider,
            self.realname_provider,
            self.moderation_provider,
            self.storage_provider,
            self.notification_provider,
        )
        if any(provider.startswith("SANDBOX") for provider in providers):
            raise ValueError("PRODUCTION_PROVIDER_NOT_ALLOWED")
