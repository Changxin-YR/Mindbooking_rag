from fastapi.testclient import TestClient

from novel_platform.main import create_app


def test_recharge_requires_real_name_verification() -> None:
    client = TestClient(create_app())
    account = client.post(
        "/api/v1/iam/accounts", json={"phone": "13800138042", "password": "Correct#123"}
    ).json()["account_id"]
    token = client.post(
        "/api/v1/iam/sessions", json={"phone": "13800138042", "password": "Correct#123"}
    ).json()["access_token"]

    response = client.post(
        "/api/v1/recharge",
        json={"account_id": account, "product_code": "RECHARGE_100", "channel": "FAKE"},
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "REAL_NAME_REQUIRED"
