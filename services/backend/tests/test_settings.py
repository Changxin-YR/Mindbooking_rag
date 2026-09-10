import pytest

from novel_platform.core.settings import Settings


def test_production_settings_reject_sandbox_provider_and_default_secrets(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("PERSISTENCE_MODE", "sql")
    monkeypatch.setenv("PAYMENT_PROVIDER", "SANDBOX")
    monkeypatch.setenv("PAYOUT_PROVIDER", "SANDBOX_PAYOUT")
    settings = Settings.from_env()

    with pytest.raises(ValueError, match="PRODUCTION_PROVIDER_NOT_ALLOWED"):
        settings.validate_runtime()


def test_production_settings_accept_configured_external_provider(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("PERSISTENCE_MODE", "sql")
    monkeypatch.setenv("PAYMENT_PROVIDER", "ALIPAY")
    monkeypatch.setenv("PAYOUT_PROVIDER", "BANK")
    monkeypatch.setenv("SESSION_SECRET", "a" * 48)
    monkeypatch.setenv("REAL_NAME_ENCRYPTION_KEY", "b" * 48)
    monkeypatch.setenv("PAYMENT_CALLBACK_SECRET", "c" * 48)
    settings = Settings.from_env()

    settings.validate_runtime()


def test_production_settings_rejects_named_sandbox_channels(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("PERSISTENCE_MODE", "sql")
    monkeypatch.setenv("PAYMENT_PROVIDER", "SANDBOX_ALIPAY")
    monkeypatch.setenv("PAYOUT_PROVIDER", "SANDBOX_BANK")
    monkeypatch.setenv("SESSION_SECRET", "a" * 48)
    monkeypatch.setenv("REAL_NAME_ENCRYPTION_KEY", "b" * 48)
    monkeypatch.setenv("PAYMENT_CALLBACK_SECRET", "c" * 48)

    with pytest.raises(ValueError, match="PRODUCTION_PROVIDER_NOT_ALLOWED"):
        Settings.from_env().validate_runtime()
