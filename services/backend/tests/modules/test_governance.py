import importlib
import sys
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).parents[1] / "src"))


def _load(module_name: str):
    try:
        return importlib.import_module(module_name)
    except ModuleNotFoundError as exc:
        pytest.fail(f"governance module is missing: {module_name}: {exc}")


def test_reports_for_same_content_share_case_and_hide_reporter() -> None:
    module = _load("novel_platform.modules.community.application")
    service = module.CommunityService()

    first = service.submit_report("CHAPTER_COMMENT", "comment-1", "reporter-a", "AD")
    second = service.submit_report("CHAPTER_COMMENT", "comment-1", "reporter-b", "AD")

    assert first.id == second.id
    assert len(first.submissions) == 2
    assert first.submissions[0].reporter_id == "reporter-a"

    api = _load("novel_platform.modules.community.api")
    app = FastAPI()
    app.include_router(api.build_community_router(service))
    response = TestClient(app).get(f"/api/v1/community/report-cases/{first.id}")

    assert response.status_code == 200
    assert "reporter_id" not in response.json()
    assert all("reporter_id" not in item for item in response.json()["submissions"])


def test_p0_security_forces_in_app_and_sms_and_marketing_cannot_be_disabled() -> None:
    module = _load("novel_platform.modules.notification.application")
    service = module.NotificationService()

    notification = service.send(
        "account-1",
        module.NotificationCategory.SECURITY,
        module.NotificationPriority.P0,
        {"WEB_PUSH"},
    )

    assert notification.channels == frozenset({"IN_APP", "SMS"})
    with pytest.raises(ValueError, match="marketing notifications cannot be disabled"):
        service.set_marketing_enabled("account-1", False)


def test_resolved_ticket_reopens_on_user_reply_and_support_cannot_change_assets() -> None:
    module = _load("novel_platform.modules.support.application")
    service = module.SupportService()
    ticket = service.open_ticket("account-1", "REFUND", module.SupportPriority.P2)

    service.resolve(ticket.id)
    assert service.get_ticket(ticket.id).status is module.SupportStatus.RESOLVED
    service.reply(ticket.id, "用户补充了订单信息", author="USER")
    assert service.get_ticket(ticket.id).status is module.SupportStatus.IN_PROGRESS

    with pytest.raises(PermissionError, match="support cannot modify assets"):
        service.modify_asset("account-1", "gift_coin", 100)


def test_risk_observe_and_freeze_preserve_order_fact() -> None:
    module = _load("novel_platform.modules.risk.application")
    service = module.RiskService()
    order = service.record_order("purchase-1", "account-1", 1000)

    signal = service.observe("account-1", "SELF_DEALING", order.id)
    assert signal.status is module.RiskSignalStatus.OBSERVE
    service.freeze(signal.id)

    assert service.get_signal(signal.id).status is module.RiskSignalStatus.FROZEN
    assert service.get_order(order.id) == order


def test_requester_cannot_approve_critical_action() -> None:
    module = _load("novel_platform.modules.approval.application")
    service = module.ApprovalService()
    request = service.request("REFUND_OVERRIDE", "maker-1", critical=True)

    with pytest.raises(module.MakerCheckerError, match="requester cannot approve"):
        service.approve(request.id, "maker-1")

    approved = service.approve(request.id, "checker-1")
    assert approved.status is module.ApprovalStatus.APPROVED


def test_governance_api_uses_explicit_dtos_and_http_semantics() -> None:
    module = _load("novel_platform.modules.approval.application")
    api = _load("novel_platform.modules.approval.api")
    service = module.ApprovalService()
    app = FastAPI()
    app.include_router(api.build_approval_router(service))
    client = TestClient(app)

    created = client.post(
        "/admin/api/v1/approvals",
        json={"action": "REFUND_OVERRIDE", "requester_id": "maker-1", "critical": True},
    )
    assert created.status_code == 201
    approval_id = created.json()["id"]

    conflict = client.post(
        f"/admin/api/v1/approvals/{approval_id}/decision",
        json={"approver_id": "maker-1", "decision": "APPROVE"},
    )
    assert conflict.status_code == 409

    extra = client.post(
        "/admin/api/v1/approvals",
        json={"action": "X", "requester_id": "m", "critical": False, "unexpected": True},
    )
    assert extra.status_code == 422


def test_support_ticket_accepts_and_stores_user_description() -> None:
    support = _load("novel_platform.modules.support.application")
    service = support.SupportService()
    ticket = service.open_ticket("account-1", "阅读", support.SupportPriority.P2, "章节显示异常")

    assert ticket.messages[0].author == "USER"
    assert ticket.messages[0].body == "章节显示异常"
