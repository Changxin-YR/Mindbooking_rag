from fastapi.testclient import TestClient

from novel_platform.main import create_app


def _account(client: TestClient, phone: str) -> tuple[str, dict[str, str]]:
    response = client.post("/api/v1/iam/accounts", json={"phone": phone, "password": "Correct#123"})
    account_id = response.json()["account_id"]
    token = client.post(
        "/api/v1/iam/sessions", json={"phone": phone, "password": "Correct#123"}
    ).json()["access_token"]
    return account_id, {"Authorization": f"Bearer {token}"}


def test_first_listing_submission_is_bound_to_the_author_account() -> None:
    client = TestClient(create_app())
    account_a, headers_a = _account(client, "13800138040")
    _, headers_b = _account(client, "13800138041")
    author = client.post(
        "/writer/api/v1/author/profiles",
        json={"account_id": account_a, "pen_name": "审核作者"},
        headers=headers_a,
    ).json()["id"]
    book = client.post(
        "/writer/api/v1/books",
        json={"author_id": author, "title": "首发作品"},
        headers=headers_a,
    ).json()["id"]

    response = client.post(
        f"/writer/api/v1/books/{book}/first-listing-submissions",
        json={"fixed_version_ids": ["CV-missing"]},
        headers=headers_b,
    )

    assert response.status_code == 403
