from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from novel_platform.modules.author_finance.api import build_payout_callback_router
from novel_platform.modules.payment import SandboxPayoutProvider


def test_staff_can_simulate_sandbox_payout_callback(monkeypatch: pytest.MonkeyPatch) -> None:
    provider = SandboxPayoutProvider("test-secret", provider_name="SANDBOX_PAYOUT")

    class PayoutRecorder:
        payout_provider = provider
        payout_provider_secret = "test-secret"

        def __init__(self) -> None:
            self.events: list[object] = []

        def payout_details(self, payout_no: str) -> tuple[int, str, str]:
            assert payout_no == "PO-1"
            return 1050, "CNY", "BANK:test"

        def handle_payout_provider_event(self, event, **kwargs) -> SimpleNamespace:
            self.events.append(event)
            return SimpleNamespace(
                id="PAYOUT-1",
                withdrawal_id="WD-1",
                payout_no=event.reference_id,
                provider=event.provider,
                amount_cents=event.amount_cents,
                currency=event.currency,
                destination="BANK:test",
                status=event.status,
                provider_event_id=event.event_id,
            )

    service = PayoutRecorder()
    app = FastAPI()
    app.include_router(build_payout_callback_router(service, auth_required=True))
    from novel_platform.modules.author_finance import api as module

    monkeypatch.setattr(
        module,
        "require_staff_authorization",
        lambda request, authorize_staff, permission: SimpleNamespace(
            subject_type="STAFF", account_id="staff-1"
        ),
    )
    client = TestClient(app)

    response = client.post(
        "/api/v1/payouts/sandbox/simulate",
        json={"payout_no": "PO-1", "status": "REJECTED", "duplicate": True},
    )

    assert response.status_code == 200, response.text
    assert response.json()["status"] == "REJECTED"
    assert response.json()["processed"] is True
    assert len(service.events) == 2


def test_sandbox_payout_simulation_requires_staff_session() -> None:
    provider = SandboxPayoutProvider("test-secret", provider_name="SANDBOX_PAYOUT")

    class PayoutRecorder:
        payout_provider = provider
        payout_provider_secret = "test-secret"

        def payout_details(self, payout_no: str) -> tuple[int, str, str]:
            return 1050, "CNY", "BANK:test"

        def handle_payout_provider_event(self, event, **kwargs):
            return SimpleNamespace(
                id="PAYOUT-1",
                withdrawal_id="WD-1",
                payout_no=event.reference_id,
                provider=event.provider,
                amount_cents=event.amount_cents,
                currency=event.currency,
                destination="BANK:test",
                status=event.status,
                provider_event_id=event.event_id,
            )

    app = FastAPI()
    app.include_router(build_payout_callback_router(PayoutRecorder(), auth_required=True))
    assert (
        TestClient(app)
        .post("/api/v1/payouts/sandbox/simulate", json={"payout_no": "PO-1"})
        .status_code
        == 401
    )


def test_sandbox_payout_simulation_maps_provider_state_errors() -> None:
    provider = SandboxPayoutProvider("test-secret", provider_name="SANDBOX_PAYOUT")

    class PayoutRecorder:
        payout_provider = provider
        payout_provider_secret = "test-secret"

        def payout_details(self, payout_no: str) -> tuple[int, str, str]:
            return 1050, "CNY", "BANK:test"

        def handle_payout_provider_event(self, event, **kwargs):
            raise ValueError("PAYOUT_STATE_CONFLICT")

    app = FastAPI()
    app.include_router(build_payout_callback_router(PayoutRecorder()))
    response = TestClient(app).post(
        "/api/v1/payouts/sandbox/simulate",
        json={"payout_no": "PO-1", "status": "SUCCESS"},
    )
    assert response.status_code == 422
    assert response.json()["detail"] == "PAYOUT_STATE_CONFLICT"
