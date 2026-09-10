import sys
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).parents[1] / "src"))

from novel_platform.core.auth import SessionSigner
from novel_platform.modules.admin_center.api import build_admin_center_router
from novel_platform.modules.admin_center.application import AdminCenterService
from novel_platform.modules.author_center.api import build_author_center_router
from novel_platform.modules.author_center.application import AuthorCenterService
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


def test_admin_center_router_requires_staff_when_auth_is_enabled() -> None:
    app = FastAPI()
    app.include_router(build_admin_center_router(AdminCenterService(), auth_required=True))
    response = TestClient(app).get("/admin/api/v1/review-rules")
    assert response.status_code == 401


def test_admin_center_router_rejects_staff_bearer_without_authorizer() -> None:
    app = FastAPI()
    signer = SessionSigner("standalone-secret", ttl_seconds=3600)
    app.state.session_signer = signer
    app.include_router(build_admin_center_router(AdminCenterService(), auth_required=True))
    response = TestClient(app).get(
        "/admin/api/v1/review-rules",
        headers={"Authorization": f"Bearer {signer.issue_staff('staff-1')}"},
    )
    assert response.status_code == 500
    assert response.json()["detail"]["code"] == "AUTHORIZATION_CONFIGURATION_ERROR"


def test_admin_center_router_accepts_staff_bearer_with_authorizer() -> None:
    app = FastAPI()
    signer = SessionSigner("standalone-secret", ttl_seconds=3600)
    app.state.session_signer = signer
    calls: list[tuple[str, str]] = []

    def authorize(claims, permission: str) -> None:
        calls.append((claims.account_id, permission))

    app.include_router(
        build_admin_center_router(
            AdminCenterService(), auth_required=True, authorize_staff=authorize
        )
    )
    response = TestClient(app).get(
        "/admin/api/v1/review-rules",
        headers={"Authorization": f"Bearer {signer.issue_staff('staff-1')}"},
    )
    assert response.status_code == 200
    assert calls == [("staff-1", "review.read")]


def test_author_center_router_rejects_staff_bearer_without_authorizer() -> None:
    app = FastAPI()
    signer = SessionSigner("standalone-secret", ttl_seconds=3600)
    app.state.session_signer = signer
    _, admin_router = build_author_center_router(AuthorCenterService(), auth_required=True)
    app.include_router(admin_router)
    response = TestClient(app).post(
        "/admin/api/v1/author-tasks",
        json={"code": "FIRST", "title": "首章", "target": 1},
        headers={"Authorization": f"Bearer {signer.issue_staff('staff-1')}"},
    )
    assert response.status_code == 500
    assert response.json()["detail"]["code"] == "AUTHORIZATION_CONFIGURATION_ERROR"
