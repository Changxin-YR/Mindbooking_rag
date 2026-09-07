from fastapi.testclient import TestClient

from novel_platform.main import create_app
from novel_platform.modules.iam.application import IdentityApplication
from novel_platform.modules.iam.repository import InMemoryIdentityRepository


def _account(client: TestClient, phone: str) -> tuple[str, str]:
    created = client.post(
        "/api/v1/iam/accounts", json={"phone": phone, "password": "Correct#123"}
    )
    assert created.status_code == 201, created.text
    token = client.post(
        "/api/v1/iam/sessions", json={"phone": phone, "password": "Correct#123"}
    ).json()["access_token"]
    return created.json()["account_id"], token


def test_account_no_is_stable_and_profile_changes_persist() -> None:
    identity = IdentityApplication(InMemoryIdentityRepository())
    registration = identity.register_phone_account("13800138070", password="Correct#123")

    first = identity.profile_for_account(registration.account_id)
    updated = identity.update_profile(
        registration.account_id, nickname="长新", login_name="changxin"
    )
    rebuilt = identity.profile_for_account(registration.account_id)

    assert first.account_no == updated.account_no == rebuilt.account_no
    assert rebuilt.nickname == "长新"
    assert rebuilt.login_name == "changxin"


def test_account_profile_http_is_account_scoped_and_login_name_unique() -> None:
    client = TestClient(create_app())
    account, token = _account(client, "13800138071")
    other, other_token = _account(client, "13800138072")
    headers = {"Authorization": f"Bearer {token}"}

    profile = client.get(f"/api/v1/iam/accounts/{account}/profile", headers=headers)
    assert profile.status_code == 200
    assert profile.json()["account_no"].startswith("MB")
    assert profile.json()["phone"] == "13800138071"
    assert client.get(f"/api/v1/iam/accounts/{account}/profile").status_code == 401

    updated = client.patch(
        f"/api/v1/iam/accounts/{account}/profile",
        json={"nickname": "长新", "login_name": "changxin"},
        headers=headers,
    )
    assert updated.status_code == 200
    assert updated.json()["nickname"] == "长新"
    assert updated.json()["login_name"] == "changxin"

    conflict = client.patch(
        f"/api/v1/iam/accounts/{other}/profile",
        json={"login_name": "changxin"},
        headers={"Authorization": f"Bearer {other_token}"},
    )
    assert conflict.status_code == 409
    assert conflict.json()["error"]["code"] == "LOGIN_NAME_TAKEN"

    denied = client.patch(
        f"/api/v1/iam/accounts/{other}/profile",
        json={"nickname": "越权"},
        headers=headers,
    )
    assert denied.status_code == 403


def test_login_name_validation_rejects_reserved_and_malformed_values() -> None:
    identity = IdentityApplication(InMemoryIdentityRepository())
    account = identity.register_phone_account("13800138073")

    for value in ("ab", "1invalid", "admin"):
        try:
            identity.update_profile(account.account_id, login_name=value)
        except ValueError:
            pass
        else:
            raise AssertionError(value)
