import base64
import hashlib
import hmac
import struct
import time

import pytest
from fastapi.testclient import TestClient

from novel_platform.main import create_app
from novel_platform.modules.platform.staff_auth import StaffMFARequired


def _staff_app(monkeypatch: pytest.MonkeyPatch) -> tuple[TestClient, object]:
    monkeypatch.setenv("STAFF_BOOTSTRAP_EMPLOYEE_CODE", "ops-001")
    monkeypatch.setenv("STAFF_BOOTSTRAP_PASSWORD", "StaffPassword#123")
    app = create_app()
    return TestClient(app), app


def test_staff_login_is_separate_from_reader_session_and_is_revocable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, _ = _staff_app(monkeypatch)
    account = client.post(
        "/api/v1/iam/accounts", json={"phone": "13800138101", "password": "Correct#123"}
    ).json()["account_id"]
    reader_token = client.post(
        "/api/v1/iam/sessions",
        json={"phone": "13800138101", "password": "Correct#123"},
    ).json()["access_token"]

    assert client.get("/admin/api/v1/reviews").status_code == 401
    assert (
        client.get(
            "/admin/api/v1/reviews", headers={"Authorization": f"Bearer {reader_token}"}
        ).status_code
        == 401
    )

    login = client.post(
        "/admin/api/v1/auth/staff/sessions",
        json={"employee_code": "ops-001", "password": "StaffPassword#123"},
    )
    assert login.status_code == 200
    assert login.json()["staff_id"]
    staff_token = login.json()["access_token"]
    headers = {"Authorization": f"Bearer {staff_token}"}
    assert client.get("/admin/api/v1/reviews", headers=headers).status_code == 200

    assert (
        client.delete("/admin/api/v1/auth/staff/sessions/current", headers=headers).status_code
        == 204
    )
    assert client.get("/admin/api/v1/reviews", headers=headers).status_code == 401
    assert account


def test_staff_permission_is_enforced_at_admin_boundary(monkeypatch: pytest.MonkeyPatch) -> None:
    client, app = _staff_app(monkeypatch)
    limited = app.state.platform.create_staff("reviewer-001", "editorial")
    app.state.staff_auth.set_password(limited.id, "ReviewerPassword#123")
    app.state.platform.grant_permission(limited.id, "review.read")
    app.state.platform.grant_data_scope(limited.id, "ALL", "*")
    staff_token = client.post(
        "/admin/api/v1/auth/staff/sessions",
        json={"employee_code": "reviewer-001", "password": "ReviewerPassword#123"},
    ).json()["access_token"]
    headers = {"Authorization": f"Bearer {staff_token}"}
    assert client.get("/admin/api/v1/reviews", headers=headers).status_code == 200
    assert (
        client.post(
            "/admin/api/v1/approvals",
            json={"action": "PAYOUT", "requester_id": "maker", "critical": True},
            headers=headers,
        ).status_code
        == 403
    )


def test_offboarded_staff_session_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    client, _ = _staff_app(monkeypatch)
    session = client.post(
        "/admin/api/v1/auth/staff/sessions",
        json={"employee_code": "ops-001", "password": "StaffPassword#123"},
    ).json()
    token = session["access_token"]
    staff_id = session["staff_id"]
    headers = {"Authorization": f"Bearer {token}"}

    response = client.post(
        f"/admin/api/v1/platform/staff/{staff_id}/status",
        json={"status": "OFFBOARDED"},
        headers=headers,
    )
    assert response.status_code == 200
    assert client.get("/admin/api/v1/reviews", headers=headers).status_code == 401


def test_revoked_staff_session_is_rejected_from_non_admin_staff_route(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, app = _staff_app(monkeypatch)
    session = client.post(
        "/admin/api/v1/auth/staff/sessions",
        json={"employee_code": "ops-001", "password": "StaffPassword#123"},
    ).json()
    headers = {"Authorization": f"Bearer {session['access_token']}"}
    monkeypatch.setattr(app.state.staff_auth, "verify", lambda _token: None)

    response = client.post("/api/v1/support/tickets/TKT-missing/resolve", headers=headers)
    assert response.status_code == 401


def test_totp_factor_is_required_before_staff_session_is_issued() -> None:
    app = create_app()
    staff = app.state.platform.create_staff("mfa-001", "finance")
    app.state.staff_auth.set_password(staff.id, "MfaStaffPassword#123")
    secret = app.state.staff_auth.enroll_totp(staff.id)

    with pytest.raises(StaffMFARequired):
        app.state.staff_auth.authenticate("mfa-001", "MfaStaffPassword#123")

    counter = int(time.time()) // 30
    digest = hmac.new(
        base64.b32decode(secret + "=" * ((8 - len(secret) % 8) % 8)),
        struct.pack(">Q", counter),
        hashlib.sha1,
    ).digest()
    offset = digest[-1] & 0x0F
    code = str(
        (struct.unpack(">I", digest[offset : offset + 4])[0] & 0x7FFFFFFF) % 1_000_000
    ).zfill(6)

    session = app.state.staff_auth.authenticate("mfa-001", "MfaStaffPassword#123", otp=code)
    assert app.state.staff_auth.verify(session.token) is not None


def test_staff_can_enable_totp_and_login_route_enforces_it(monkeypatch: pytest.MonkeyPatch) -> None:
    client, app = _staff_app(monkeypatch)
    login = client.post(
        "/admin/api/v1/auth/staff/sessions",
        json={"employee_code": "ops-001", "password": "StaffPassword#123"},
    ).json()
    headers = {"Authorization": f"Bearer {login['access_token']}"}
    staff_id = login["staff_id"]

    enrolled = client.post(f"/admin/api/v1/auth/staff/mfa/totp/{staff_id}", headers=headers)
    assert enrolled.status_code == 200
    secret = enrolled.json()["secret"]
    required = client.post(
        "/admin/api/v1/auth/staff/sessions",
        json={"employee_code": "ops-001", "password": "StaffPassword#123"},
    )
    assert required.status_code == 401
    assert required.json()["error"]["code"] == "MFA_REQUIRED"
    code = _current_totp(secret)
    second_login = client.post(
        "/admin/api/v1/auth/staff/sessions",
        json={
            "employee_code": "ops-001",
            "password": "StaffPassword#123",
            "otp": code,
        },
    )
    assert second_login.status_code == 200
    assert app.state.staff_auth.verify(second_login.json()["access_token"]) is not None


def _current_totp(secret: str) -> str:
    counter = int(time.time()) // 30
    digest = hmac.new(
        base64.b32decode(secret + "=" * ((8 - len(secret) % 8) % 8)),
        struct.pack(">Q", counter),
        hashlib.sha1,
    ).digest()
    offset = digest[-1] & 0x0F
    return str(
        (struct.unpack(">I", digest[offset : offset + 4])[0] & 0x7FFFFFFF) % 1_000_000
    ).zfill(6)
