import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1] / "src"))

from novel_platform.modules.admin_center.application import AdminCenterService
from novel_platform.modules.risk.application import RiskService


def test_review_rule_and_quality_metrics_are_structured() -> None:
    service = AdminCenterService()
    rule = service.add_review_rule("AD", "HIGH", "HOLD", True, ("COMMENT",), "2026-01")
    assert rule.code == "AD"
    quality = service.record_reviewer_quality("staff-1", 9400, 300, 200, 500, 42, 100)
    assert quality.accuracy_bps == 9400
    assert quality.avg_handle_seconds == 42


def test_user_360_masks_sensitive_fields_by_default() -> None:
    service = AdminCenterService()
    view = service.user360("acct-1", "13812345678", "张三", 1990, 2, 3)
    assert view.phone == "138****5678"
    assert view.real_name == "已实名"
    assert view.asset_cents is None
    sensitive = service.user360("acct-1", "13812345678", "张三", 1990, 2, 3, sensitive=True)
    assert sensitive.asset_cents == 1990


def test_support_csat_and_author_alerts_are_read_model_facts() -> None:
    service = AdminCenterService()
    alert = service.create_author_alert("author-1", "UPDATE_DROP", "连续三天断更", "MEDIUM")
    assert alert.status == "OPEN"
    service.record_csat("ticket-1", 4)
    assert service.support_dashboard()["csat_count"] == 1


def test_login_risk_is_observe_first_and_watchlist_release_keeps_history() -> None:
    service = RiskService()
    signal = service.record_login(
        "acct-1", "device-1", "Chrome", "Windows", "198.51.100.1", "CN", "ua"
    )
    assert signal.status == "OBSERVE"
    entry = service.add_watchlist("IP", "198.51.100.1", "suspicious login", "case-1")
    assert service.is_watchlisted("IP", "198.51.100.1")
    service.release_watchlist(entry.id, "manual review", "evidence-1", "case-1")
    assert not service.is_watchlisted("IP", "198.51.100.1")
    assert service.watchlist(entry.id).release_reason == "manual review"
