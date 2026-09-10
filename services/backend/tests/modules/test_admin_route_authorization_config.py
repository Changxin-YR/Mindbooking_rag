from collections.abc import Callable

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from novel_platform.core.auth import SessionClaims, SessionSigner
from novel_platform.core.middleware import _admin_permission
from novel_platform.modules.approval.api import build_approval_router
from novel_platform.modules.approval.application import ApprovalService
from novel_platform.modules.copyright.api import build_copyright_router
from novel_platform.modules.copyright.application import CopyrightService
from novel_platform.modules.governance.api import build_governance_router
from novel_platform.modules.governance.application import GovernanceService
from novel_platform.modules.legal.api import build_legal_router
from novel_platform.modules.legal.application import LegalService
from novel_platform.modules.operation.api import build_operation_router
from novel_platform.modules.operation.application import OperationService
from novel_platform.modules.platform.application import PlatformApplication
from novel_platform.modules.platform.http import build_platform_router
from novel_platform.modules.platform.repository import InMemoryPlatformRepository
from novel_platform.modules.risk.api import build_risk_router
from novel_platform.modules.risk.application import RiskService


@pytest.fixture
def staff_client() -> tuple[TestClient, str]:
    app = FastAPI()
    signer = SessionSigner("authorization-test-secret")
    app.state.session_signer = signer
    app.state.staff_auth = _StaffVerifier(signer)
    token = signer.issue_staff("staff-1")
    return TestClient(app), token


class _StaffVerifier:
    def __init__(self, signer: SessionSigner) -> None:
        self.signer = signer

    def verify(self, token: str) -> SessionClaims | None:
        return self.signer.verify(token)


@pytest.mark.parametrize(
    ("mount", "prefix", "path", "payload"),
    [
        (
            lambda: build_risk_router(RiskService(), auth_required=True),
            "",
            "/admin/api/v1/risk/signals",
            {"account_id": "acct-1", "signal_type": "ABUSE", "order_id": "order-1"},
        ),
        (
            lambda: build_operation_router(OperationService(), auth_required=True),
            "",
            "/admin/api/v1/operation/campaigns",
            {"title": "campaign", "start_date": "2026-01-01", "end_date": "2026-02-01"},
        ),
        (
            lambda: build_copyright_router(CopyrightService(), auth_required=True),
            "",
            "/admin/api/v1/copyright/dossiers",
            {"book_id": "book-1"},
        ),
        (
            lambda: build_legal_router(LegalService(), auth_required=True),
            "",
            "/admin/api/v1/legal/cases",
            {"subject": "book-1"},
        ),
        (
            lambda: build_governance_router(GovernanceService(), auth_required=True),
            "",
            "/admin/api/v1/parameters",
            {"key": "k", "value": "v", "maker_id": "maker-1"},
        ),
        (
            lambda: build_approval_router(ApprovalService(), auth_required=True),
            "",
            "/admin/api/v1/approvals",
            {"action": "PAYOUT", "requester_id": "maker-1", "critical": False},
        ),
        (
            lambda: build_platform_router(
                PlatformApplication(InMemoryPlatformRepository()), auth_required=True
            ),
            "/admin/api/v1",
            "/admin/api/v1/platform/staff",
            {"employee_code": "employee-1", "department": "operations"},
        ),
    ],
)
def test_admin_write_requires_explicit_authorization_callback(
    staff_client: tuple[TestClient, str],
    mount: Callable[[], object],
    prefix: str,
    path: str,
    payload: dict[str, object],
) -> None:
    client, token = staff_client
    client.app.include_router(mount(), prefix=prefix)

    response = client.post(
        path,
        json=payload,
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 500
    assert response.json()["detail"]["code"] == "AUTHORIZATION_CONFIGURATION_ERROR"


def test_admin_write_authenticates_before_reporting_missing_configuration(
    staff_client: tuple[TestClient, str],
) -> None:
    client, _ = staff_client
    client.app.include_router(build_operation_router(OperationService(), auth_required=True))

    response = client.post(
        "/admin/api/v1/operation/campaigns",
        json={"title": "campaign", "start_date": "2026-01-01", "end_date": "2026-02-01"},
    )

    assert response.status_code == 401
    assert response.json()["detail"]["code"] == "AUTHENTICATION_REQUIRED"


def test_admin_write_returns_forbidden_when_authorization_callback_denies(
    staff_client: tuple[TestClient, str],
) -> None:
    client, token = staff_client

    def deny(_: SessionClaims, permission: str) -> None:
        raise HTTPException(
            status_code=403,
            detail={"code": "PERMISSION_DENIED", "message": f"denied: {permission}"},
        )

    client.app.include_router(
        build_operation_router(OperationService(), auth_required=True, authorize_staff=deny)
    )
    response = client.post(
        "/admin/api/v1/operation/campaigns",
        json={"title": "campaign", "start_date": "2026-01-01", "end_date": "2026-02-01"},
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 403
    assert response.json()["detail"]["code"] == "PERMISSION_DENIED"


def test_reconciliation_collections_use_read_permission_for_get() -> None:
    assert (
        _admin_permission("/admin/api/v1/reconciliation/credit-pending", "GET") == "governance.read"
    )
    assert _admin_permission("/admin/api/v1/reconciliation/batches", "GET") == "governance.read"
