import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from novel_platform.core.auth import SessionSigner
from novel_platform.core.http_auth import require_account_access
from novel_platform.main import create_app
from novel_platform.modules.iam.application import IdentityApplication
from novel_platform.modules.iam.repository import InMemoryIdentityRepository


def test_password_login_returns_signed_session_without_exposing_password() -> None:
    identity = IdentityApplication(InMemoryIdentityRepository())
    registration = identity.register_phone_account("13800138000", password="Correct#123")

    session = identity.authenticate_phone("13800138000", "Correct#123")

    assert session.account_id == registration.account_id
    assert session.token.count(".") == 1
    assert "Correct#123" not in session.token


def test_session_signer_rejects_tampered_and_expired_tokens() -> None:
    signer = SessionSigner("test-secret", ttl_seconds=1)
    token = signer.issue("acct-1")
    assert signer.verify(token).account_id == "acct-1"
    assert signer.verify(token[:-1] + ("A" if token[-1] != "A" else "B")) is None

    expired = SessionSigner("test-secret", ttl_seconds=0).issue("acct-1")
    assert signer.verify(expired) is None


def test_http_password_login_rejects_wrong_password() -> None:
    client = TestClient(create_app())
    response = client.post(
        "/api/v1/iam/accounts",
        json={"phone": "13800138001", "password": "Correct#123"},
    )
    assert response.status_code == 201

    failed = client.post(
        "/api/v1/iam/sessions",
        json={"phone": "13800138001", "password": "wrong"},
    )
    assert failed.status_code == 401
    assert failed.json()["error"]["code"] == "INVALID_CREDENTIALS"


def test_session_can_be_revoked_and_cannot_be_reused() -> None:
    client = TestClient(create_app())
    created = client.post(
        "/api/v1/iam/accounts", json={"phone": "13800138043", "password": "Correct#123"}
    )
    token = client.post(
        "/api/v1/iam/sessions", json={"phone": "13800138043", "password": "Correct#123"}
    ).json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    assert created.status_code == 201
    assert client.delete("/api/v1/iam/sessions/current", headers=headers).status_code == 204
    assert (
        client.get(
            "/api/v1/wallet", params={"account_id": created.json()["account_id"]}, headers=headers
        ).status_code
        == 401
    )


def test_writer_can_resolve_own_author_profile_from_session() -> None:
    client = TestClient(create_app())
    created = client.post(
        "/api/v1/iam/accounts", json={"phone": "13800138099", "password": "Correct#123"}
    )
    account_id = created.json()["account_id"]
    token = client.post(
        "/api/v1/iam/sessions", json={"phone": "13800138099", "password": "Correct#123"}
    ).json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    profile = client.post(
        "/writer/api/v1/author/profiles",
        json={"account_id": account_id, "pen_name": "资料解析"},
        headers=headers,
    )
    assert profile.status_code == 201

    response = client.get("/writer/api/v1/author/profile", headers=headers)

    assert response.status_code == 200
    assert response.json()["id"] == profile.json()["id"]
    assert response.json()["account_id"] == account_id


def test_staff_subject_cannot_pass_account_access_guard() -> None:
    claims = SessionSigner("test-secret").verify(
        SessionSigner("test-secret").issue_staff("staff-1")
    )
    assert claims is not None

    with pytest.raises(HTTPException) as error:
        require_account_access(claims, "staff-1", required=True)

    assert error.value.status_code == 403
    assert error.value.detail["code"] == "ACCOUNT_ACCESS_DENIED"
