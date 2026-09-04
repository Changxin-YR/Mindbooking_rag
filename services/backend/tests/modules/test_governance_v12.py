import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1] / "src"))

import pytest
from fastapi.testclient import TestClient

from novel_platform.main import create_app
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


def test_emergency_and_outbox_are_explicit_and_recoverable() -> None:
    service = GovernanceService()
    emergency = service.pause_features("payment-provider", {"RECHARGE", "REFUND"}, "ops-1")
    assert service.is_feature_paused("RECHARGE")
    service.resolve_emergency(emergency.id, "ops-2")
    assert not service.is_feature_paused("RECHARGE")

    event = service.enqueue_outbox("BOOK_TAKEN_DOWN", "book-1", {"visibility": "OFFLINE"})
    assert event.attempts == 0
    assert service.outbox_event(event.id).payload["visibility"] == "OFFLINE"


def test_governance_api_exposes_explicit_workflows() -> None:
    client = TestClient(create_app())
    privacy = client.post(
        "/api/v1/privacy/requests", json={"account_id": "acct-1", "kind": "EXPORT"}
    )
    assert privacy.status_code == 201
    draft = client.post(
        "/admin/api/v1/parameters",
        json={"key": "vip.price", "value": "199", "maker_id": "maker-1"},
    )
    assert draft.status_code == 201
    parameter_id = draft.json()["id"]
    approved = client.post(
        f"/admin/api/v1/parameters/{parameter_id}/approve", params={"checker_id": "checker-1"}
    )
    assert approved.status_code == 200
    assert (
        client.post(
            f"/admin/api/v1/parameters/{parameter_id}/activate",
            json={"effective_at": "2026-09-04T00:00:00+00:00"},
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


def test_operation_campaign_and_reward_endpoints_are_idempotent() -> None:
    client = TestClient(create_app())
    campaign = client.post(
        "/admin/api/v1/operation/campaigns",
        json={"title": "秋日征文", "start_date": "2026-09-01", "end_date": "2026-10-01"},
    )
    assert campaign.status_code == 201
    reward = client.post(
        "/admin/api/v1/operation/rewards",
        json={"subject_id": "author-1", "reward_type": "POINT", "amount": 10},
        headers={"Idempotency-Key": "reward-request-1"},
    )
    assert reward.status_code == 201
    assert (
        client.post(
            "/admin/api/v1/operation/rewards",
            json={"subject_id": "author-1", "reward_type": "POINT", "amount": 10},
            headers={"Idempotency-Key": "reward-request-1"},
        ).json()["id"]
        == reward.json()["id"]
    )
