from datetime import UTC, datetime, timedelta

import pytest

from novel_platform.core.settings import Settings
from novel_platform.main import create_app
from novel_platform.modules.integrations.provider import SandboxProviderRegistry


def test_sms_otp_is_deterministic_deduplicated_and_expires() -> None:
    now = datetime(2026, 9, 5, 12, tzinfo=UTC)
    provider = SandboxProviderRegistry(clock=lambda: now).sms

    first = provider.send_otp("13800138000")
    duplicate = provider.send_otp("13800138000")
    assert first == duplicate
    assert provider.verify_otp("13800138000", first.code).verified

    with pytest.raises(ValueError, match="OTP_ALREADY_USED"):
        provider.verify_otp("13800138000", first.code)

    expiring = provider.send_otp("13800138001", ttl_seconds=30)
    provider.clock = lambda: now + timedelta(seconds=31)
    expired = provider.verify_otp("13800138001", expiring.code)
    assert not expired.verified
    assert expired.reason == "OTP_EXPIRED"


def test_oauth_codes_are_provider_specific_and_one_time() -> None:
    registry = SandboxProviderRegistry()
    code = registry.oauth_wechat.issue_code("wechat-user-1")
    identity = registry.oauth_wechat.exchange_code(code.code)
    assert identity.provider == "SANDBOX_OAUTH_WECHAT"
    assert identity.subject == "wechat-user-1"

    with pytest.raises(ValueError, match="OAUTH_CODE_ALREADY_USED"):
        registry.oauth_wechat.exchange_code(code.code)

    qq_code = registry.oauth_qq.issue_code("qq-user-1")
    assert registry.oauth_qq.exchange_code(qq_code.code).provider == "SANDBOX_OAUTH_QQ"


def test_realname_moderation_storage_and_notification_are_deterministic() -> None:
    registry = SandboxProviderRegistry()

    realname = registry.realname.verify("测试用户", "11010119900101001X")
    assert realname.verified
    assert (
        realname.subject_id == registry.realname.verify("测试用户", "11010119900101001X").subject_id
    )

    moderation = registry.moderation.moderate("这是正常的章节内容", content_id="chapter-1")
    assert moderation.decision == "PASS"
    assert registry.moderation.moderate("这是正常的章节内容", content_id="chapter-1") == moderation
    assert registry.moderation.moderate("包含违法内容", content_id="chapter-2").decision == "BLOCK"

    stored = registry.storage.put_object("covers/book-1.png", b"image-bytes")
    assert stored.key == "covers/book-1.png"
    assert registry.storage.get_object(stored.key).data == b"image-bytes"

    first = registry.notification.deliver(
        "notification-1", account_id="account-1", channel="IN_APP", payload={"title": "hi"}
    )
    duplicate = registry.notification.deliver(
        "notification-1", account_id="account-1", channel="IN_APP", payload={"title": "hi"}
    )
    assert duplicate == first
    assert registry.notification.delivery_count == 1


def test_registry_rejects_non_sandbox_provider_names() -> None:
    with pytest.raises(ValueError, match="NON_SANDBOX_PROVIDER_NOT_ALLOWED"):
        SandboxProviderRegistry(sms_provider="TWILIO")


def test_production_settings_reject_explicit_sandbox_integration(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("PERSISTENCE_MODE", "sql")
    monkeypatch.setenv("PAYMENT_PROVIDER", "ALIPAY")
    monkeypatch.setenv("PAYOUT_PROVIDER", "BANK")
    monkeypatch.setenv("SMS_PROVIDER", "SANDBOX_SMS")
    monkeypatch.setenv("SESSION_SECRET", "a" * 48)
    monkeypatch.setenv("REAL_NAME_ENCRYPTION_KEY", "b" * 48)
    monkeypatch.setenv("PAYMENT_CALLBACK_SECRET", "c" * 48)

    with pytest.raises(ValueError, match="PRODUCTION_PROVIDER_NOT_ALLOWED"):
        Settings.from_env().validate_runtime()


def test_settings_and_app_expose_named_sandbox_integration_registry(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("SMS_PROVIDER", "SANDBOX_SMS")
    monkeypatch.setenv("OAUTH_WECHAT_PROVIDER", "SANDBOX_OAUTH_WECHAT")
    settings = Settings.from_env()
    assert settings.sms_provider == "SANDBOX_SMS"
    assert settings.oauth_wechat_provider == "SANDBOX_OAUTH_WECHAT"

    app = create_app()
    assert app.state.integration_registry is app.state.sandbox_provider_registry
    assert app.state.integration_health["status"] == "ok"
    assert app.state.integration_health["SANDBOX_SMS"]["status"] == "ok"
