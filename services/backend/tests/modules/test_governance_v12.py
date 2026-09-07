import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1] / "src"))

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from novel_platform.main import create_app
from novel_platform.modules.governance.api import build_governance_router
from novel_platform.modules.governance.application import GovernanceService
from novel_platform.modules.governance.domain import (
    AgreementAcceptance,
    ParameterStatus,
    ReconciliationDifference,
    ReconciliationStatus,
)
from novel_platform.modules.platform.application import PlatformApplication
from novel_platform.modules.platform.domain import StaffStatus
from novel_platform.modules.platform.repository import InMemoryPlatformRepository


def _staff_headers(client: TestClient) -> dict[str, str]:
    response = client.post(
        "/admin/api/v1/auth/staff/sessions",
        json={"employee_code": "ops-test", "password": "StaffPassword#123"},
    )
    assert response.status_code == 200
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def test_privacy_and_agreement_facts_are_idempotent_by_version() -> None:
    service = GovernanceService()

    request = service.open_privacy_request("acct-1", "EXPORT")
    assert request.status == "OPEN"
    assert service.open_privacy_request("acct-1", "EXPORT").id == request.id

    accepted = service.accept_agreement("acct-1", "terms", "2026-01")
    assert accepted == AgreementAcceptance("acct-1", "terms", "2026-01")
    assert service.accept_agreement("acct-1", "terms", "2026-01") == accepted
    with pytest.raises(ValueError, match="AGREEMENT_VERSION_REQUIRED"):
        service.accept_agreement("acct-1", "terms", "")


def test_parameter_requires_distinct_maker_checker_before_activation() -> None:
    service = GovernanceService()
    draft = service.draft_parameter("vip.price", "199", "maker-1")
    assert draft.status is ParameterStatus.DRAFT

    service.approve_parameter(draft.id, "checker-1")
    active = service.activate_parameter(draft.id, "2026-09-04T00:00:00+00:00")
    assert active.status is ParameterStatus.ACTIVE
    with pytest.raises(ValueError, match="PARAMETER_MAKER_CHECKER_SEPARATION"):
        service.approve_parameter(service.draft_parameter("gift.coin", "10", "same").id, "same")
    pending = service.draft_parameter("gift.coin", "10", "maker-2")
    with pytest.raises(ValueError, match="PARAMETER_CHECKER_REQUIRED"):
        service.activate_parameter(pending.id, "2026-09-04T00:00:00+00:00")


def test_reconciliation_preserves_channel_success_when_credit_fails() -> None:
    service = GovernanceService()
    pending = service.record_payment_credit_failure("pay-1", "acct-1", 1000)
    assert pending.status == "CREDIT_PENDING"
    assert service.record_payment_credit_failure("pay-1", "acct-1", 1000).id == pending.id

    batch = service.open_reconciliation("2026-09-04")
    item = service.add_reconciliation_item(
        batch.id, "pay-1", ReconciliationDifference.MISSING_LEDGER, 1000
    )
    assert item.difference is ReconciliationDifference.MISSING_LEDGER
    assert service.reconciliation_batch(batch.id).status is ReconciliationStatus.OPEN


def test_reconciliation_batch_can_be_repaired_and_closed_idempotently() -> None:
    service = GovernanceService()
    batch = service.open_reconciliation("2026-09-05")
    repaired = service.mark_reconciliation_repaired(batch.id, "finance-1")
    assert repaired.status is ReconciliationStatus.REPAIRED
    closed = service.close_reconciliation(batch.id, "finance-2")
    assert closed.status is ReconciliationStatus.CLOSED
    assert service.close_reconciliation(batch.id, "finance-3").status is ReconciliationStatus.CLOSED
    assert [item.id for item in service.list_reconciliation_batches()] == [batch.id]


def test_credit_pending_repair_retries_once_and_is_idempotent() -> None:
    service = GovernanceService()
    pending = service.record_payment_credit_failure("pay-repair", "acct-1", 1000)
    calls: list[str] = []
    service.repair_payment_credit = lambda payment_id: calls.append(payment_id) or "REPAIRED"

    repaired = service.retry_payment_credit(pending.payment_id, "staff-1")
    assert repaired.status == "RESOLVED"
    assert repaired.attempts == 1
    assert repaired.repair_actor_id == "staff-1"
    assert calls == ["pay-repair"]

    again = service.retry_payment_credit(pending.payment_id, "staff-2")
    assert again.id == repaired.id
    assert again.status == "RESOLVED"
    assert again.attempts == 1
    assert calls == ["pay-repair"]


def test_credit_pending_repair_failure_is_repair_required_and_listable() -> None:
    service = GovernanceService()
    pending = service.record_payment_credit_failure("pay-fail", "acct-1", 1000)

    def fail(_: str) -> None:
        raise RuntimeError("wallet unavailable")

    service.repair_payment_credit = fail
    failed = service.retry_payment_credit(pending.payment_id, "staff-1")
    assert failed.status == "REPAIR_REQUIRED"
    assert failed.attempts == 1
    assert failed.last_error == "wallet unavailable"
    assert [item.payment_id for item in service.list_payment_credit_pending()] == ["pay-fail"]


def test_credit_pending_auto_repair_attempts_only_new_pending_records() -> None:
    service = GovernanceService()
    service.record_payment_credit_failure("pay-auto", "acct-1", 1000)
    service.repair_payment_credit = lambda _: True

    repaired = service.auto_repair_payment_credits()
    assert [item.payment_id for item in repaired] == ["pay-auto"]
    assert service.list_payment_credit_pending() == ()


def test_credit_pending_staff_api_lists_and_retries_with_explicit_actor() -> None:
    service = GovernanceService()
    service.record_payment_credit_failure("pay-api", "acct-1", 1000)
    service.repair_payment_credit = lambda _: True
    app = FastAPI()
    app.include_router(build_governance_router(service))
    client = TestClient(app)

    listed = client.get("/admin/api/v1/reconciliation/credit-pending")
    assert listed.status_code == 200
    assert listed.json()[0]["payment_id"] == "pay-api"
    retried = client.post(
        "/admin/api/v1/reconciliation/credit-pending/pay-api/retry",
        params={"operator_id": "staff-api"},
    )
    assert retried.status_code == 200
    assert retried.json()["status"] == "RESOLVED"


def test_reconciliation_batch_api_exposes_repair_and_close_workflow() -> None:
    service = GovernanceService()
    app = FastAPI()
    app.include_router(build_governance_router(service))
    client = TestClient(app)

    created = client.post(
        "/admin/api/v1/reconciliation/batches", json={"business_date": "2026-09-05"}
    )
    assert created.status_code == 201
    batch_id = created.json()["id"]
    listed = client.get("/admin/api/v1/reconciliation/batches")
    assert listed.status_code == 200
    assert listed.json()[0]["status"] == "OPEN"
    repaired = client.post(
        f"/admin/api/v1/reconciliation/batches/{batch_id}/repair",
        params={"operator_id": "finance-1"},
    )
    assert repaired.status_code == 200
    closed = client.post(
        f"/admin/api/v1/reconciliation/batches/{batch_id}/close",
        params={"operator_id": "finance-2"},
    )
    assert closed.status_code == 200
    assert closed.json()["status"] == "CLOSED"


def test_emergency_and_outbox_are_explicit_and_recoverable() -> None:
    service = GovernanceService()
    emergency = service.pause_features("payment-provider", {"RECHARGE", "REFUND"}, "ops-1")
    assert service.is_feature_paused("RECHARGE")
    service.resolve_emergency(emergency.id, "ops-2")
    assert not service.is_feature_paused("RECHARGE")

    event = service.enqueue_outbox("BOOK_TAKEN_DOWN", "book-1", {"visibility": "OFFLINE"})
    assert event.attempts == 0
    assert service.outbox_event(event.id).payload["visibility"] == "OFFLINE"


def test_governance_api_exposes_explicit_workflows(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("STAFF_BOOTSTRAP_EMPLOYEE_CODE", "ops-test")
    monkeypatch.setenv("STAFF_BOOTSTRAP_PASSWORD", "StaffPassword#123")
    client = TestClient(create_app())
    account = client.post(
        "/api/v1/iam/accounts",
        json={"phone": "13800138025", "password": "Correct#123"},
    ).json()["account_id"]
    token = client.post(
        "/api/v1/iam/sessions",
        json={"phone": "13800138025", "password": "Correct#123"},
    ).json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    staff_headers = _staff_headers(client)
    checker = client.app.state.platform.create_staff("checker-1", "platform")
    client.app.state.staff_auth.set_password(checker.id, "CheckerPassword#123")
    client.app.state.platform.grant_permission(checker.id, "governance.write")
    client.app.state.platform.grant_data_scope(checker.id, "ALL", "*")
    privacy = client.post(
        "/api/v1/privacy/requests",
        json={"account_id": account, "kind": "EXPORT"},
        headers=headers,
    )
    assert privacy.status_code == 201
    draft = client.post(
        "/admin/api/v1/parameters",
        json={"key": "vip.price", "value": "199", "maker_id": "maker-1"},
        headers=staff_headers,
    )
    assert draft.status_code == 201
    parameter_id = draft.json()["id"]
    checker_login = client.post(
        "/admin/api/v1/auth/staff/sessions",
        json={"employee_code": "checker-1", "password": "CheckerPassword#123"},
    )
    assert checker_login.status_code == 200
    approved = client.post(
        f"/admin/api/v1/parameters/{parameter_id}/approve",
        params={"checker_id": "checker-1"},
        headers={"Authorization": f"Bearer {checker_login.json()['access_token']}"},
    )
    assert approved.status_code == 200
    assert (
        client.post(
            f"/admin/api/v1/parameters/{parameter_id}/activate",
            json={"effective_at": "2026-09-04T00:00:00+00:00"},
            headers=staff_headers,
        ).json()["status"]
        == "ACTIVE"
    )


def test_staff_offboarding_disables_access_but_keeps_the_staff_record() -> None:
    application = PlatformApplication(InMemoryPlatformRepository())
    staff = application.create_staff("EMP-1", "support")

    updated = application.change_staff_status(staff.id, StaffStatus.OFFBOARDED)
    assert updated.status is StaffStatus.OFFBOARDED
    with pytest.raises(ValueError, match="STAFF_STATUS_TRANSITION_INVALID"):
        application.change_staff_status(staff.id, StaffStatus.ACTIVE)


def test_invoice_lifecycle_is_not_a_wallet_adjustment() -> None:
    service = GovernanceService()
    invoice = service.request_invoice("acct-1", 1990, "墨页科技", "91310000TEST")
    assert invoice.status == "APPLIED"
    issued = service.issue_invoice(invoice.id, "file-invoice-1")
    assert issued.status == "ISSUED"
    reversed_invoice = service.reverse_invoice(invoice.id, "red-invoice-1")
    assert reversed_invoice.status == "REVERSED"


def test_operation_campaign_and_reward_endpoints_are_idempotent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("STAFF_BOOTSTRAP_EMPLOYEE_CODE", "ops-test")
    monkeypatch.setenv("STAFF_BOOTSTRAP_PASSWORD", "StaffPassword#123")
    client = TestClient(create_app())
    client.post(
        "/api/v1/iam/accounts",
        json={"phone": "13800138026", "password": "Correct#123"},
    )
    client.post(
        "/api/v1/iam/sessions",
        json={"phone": "13800138026", "password": "Correct#123"},
    )
    staff_headers = _staff_headers(client)
    campaign = client.post(
        "/admin/api/v1/operation/campaigns",
        json={"title": "秋日征文", "start_date": "2026-09-01", "end_date": "2026-10-01"},
        headers=staff_headers,
    )
    assert campaign.status_code == 201
    reward = client.post(
        "/admin/api/v1/operation/rewards",
        json={"subject_id": "author-1", "reward_type": "POINT", "amount": 10},
        headers={**staff_headers, "Idempotency-Key": "reward-request-1"},
    )
    assert reward.status_code == 201
    assert (
        client.post(
            "/admin/api/v1/operation/rewards",
            json={"subject_id": "author-1", "reward_type": "POINT", "amount": 10},
            headers={**staff_headers, "Idempotency-Key": "reward-request-1"},
        ).json()["id"]
        == reward.json()["id"]
    )
