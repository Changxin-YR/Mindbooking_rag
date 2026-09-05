import pytest
from fastapi.testclient import TestClient

from novel_platform.main import create_app
from novel_platform.modules.reader_experience.application import ReaderExperienceService


def _session(client: TestClient, phone: str, pen_name: str) -> tuple[str, dict[str, str], str]:
    account = client.post(
        "/api/v1/iam/accounts", json={"phone": phone, "password": "Correct#123"}
    ).json()["account_id"]
    token = client.post(
        "/api/v1/iam/sessions", json={"phone": phone, "password": "Correct#123"}
    ).json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    author_id = client.post(
        "/writer/api/v1/author/profiles",
        json={"account_id": account, "pen_name": pen_name},
        headers=headers,
    ).json()["id"]
    return account, headers, author_id


def test_rating_requires_effective_reading_and_keeps_history() -> None:
    service = ReaderExperienceService(min_rating_words=1_000)

    try:
        service.rate("acct-1", "book-1", 5, 4, 5, 4, 100)
    except ValueError as exc:
        assert str(exc) == "RATING_NOT_ELIGIBLE"
    else:
        raise AssertionError("rating below the effective-reading threshold must fail")

    first = service.rate("acct-1", "book-1", 5, 4, 5, 4, 1_000)
    second = service.rate("acct-1", "book-1", 4, 4, 4, 4, 1_500)
    assert first.id == second.id
    assert service.rating_history("acct-1", "book-1") == (first, second)


def test_follow_is_idempotent_and_growth_is_separate_from_membership() -> None:
    service = ReaderExperienceService()

    assert service.follow("acct-1", "AUTHOR", "author-1") is True
    assert service.follow("acct-1", "AUTHOR", "author-1") is False
    assert service.follow("acct-1", "ACCOUNT", "acct-2") is True
    service.add_growth("acct-1", "READING", 120)
    profile = service.growth("acct-1")

    assert profile.points == 120
    assert profile.level == 2
    assert profile.membership_level == 0
    assert service.following("acct-1") == (("ACCOUNT", "acct-2"), ("AUTHOR", "author-1"))


def test_correction_and_minor_policy_are_explicit_api_boundaries() -> None:
    client = TestClient(create_app())
    account, headers, _ = _session(client, "13800138027", "纠错作者")
    correction = client.post(
        "/api/v1/content-corrections",
        json={
            "account_id": account,
            "book_id": "book-1",
            "chapter_id": "chapter-1",
            "kind": "TYPO",
            "position": 18,
            "description": "错别字",
        },
        headers=headers,
    )
    assert correction.status_code == 201
    assert correction.json()["kind"] == "TYPO"

    minor = client.put(
        f"/api/v1/accounts/{account}/minor-protection",
        json={"is_minor": True, "policy_version": "minor-v1"},
        headers=headers,
    )
    assert minor.status_code == 200
    assert minor.json() == {
        "account_id": account,
        "is_minor": True,
        "policy_version": "minor-v1",
        "purchase_allowed": False,
    }


def test_reader_catalog_filters_public_books(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("STAFF_BOOTSTRAP_EMPLOYEE_CODE", "ops-test")
    monkeypatch.setenv("STAFF_BOOTSTRAP_PASSWORD", "StaffPassword#123")
    client = TestClient(create_app())
    staff_token = client.post(
        "/admin/api/v1/auth/staff/sessions",
        json={"employee_code": "ops-test", "password": "StaffPassword#123"},
    ).json()["access_token"]
    staff_headers = {"Authorization": f"Bearer {staff_token}"}
    _, headers, author_id = _session(client, "13800138028", "分类作者")
    first = client.post(
        "/writer/api/v1/books",
        json={
            "author_id": author_id,
            "title": "玄幻新书",
            "channel": "MALE",
            "category": "东方玄幻",
            "tags": ["系统"],
        },
        headers=headers,
    )
    second = client.post(
        "/writer/api/v1/books",
        json={"author_id": author_id, "title": "女频新书", "channel": "FEMALE"},
        headers=headers,
    )
    assert first.status_code == 201
    assert second.status_code == 201

    volume = client.post(
        f"/writer/api/v1/books/{first.json()['id']}/volumes",
        json={"number": 1, "title": "第一卷"},
        headers=headers,
    )
    chapter = client.post(
        f"/writer/api/v1/volumes/{volume.json()['id']}/chapters",
        json={"number": 1, "title": "第一章", "commercial_policy": "FREE"},
        headers=headers,
    )
    draft = client.post(
        f"/writer/api/v1/chapters/{chapter.json()['id']}/drafts",
        json={"content": "正文"},
        headers=headers,
    )
    version = client.post(
        f"/writer/api/v1/chapters/{chapter.json()['id']}/versions",
        json={"snapshot_id": draft.json()["id"]},
        headers=headers,
    )
    submission = client.post(
        f"/writer/api/v1/books/{first.json()['id']}/first-listing-submissions",
        json={"fixed_version_ids": [version.json()["id"]]},
        headers=headers,
    )
    decision = client.post(
        f"/admin/api/v1/reviews/{submission.json()['id']}/decisions",
        json={"reviewer_id": "staff-1", "decision": "APPROVE"},
        headers=staff_headers,
    )
    assert decision.status_code == 201

    response = client.get("/api/v1/books", params={"channel": "MALE"})
    assert response.status_code == 200
    assert response.json()["total"] == 1
    assert response.json()["items"][0]["title"] == "玄幻新书"


def test_reader_book_detail_returns_only_public_metadata(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("STAFF_BOOTSTRAP_EMPLOYEE_CODE", "ops-test")
    monkeypatch.setenv("STAFF_BOOTSTRAP_PASSWORD", "StaffPassword#123")
    client = TestClient(create_app())
    staff_token = client.post(
        "/admin/api/v1/auth/staff/sessions",
        json={"employee_code": "ops-test", "password": "StaffPassword#123"},
    ).json()["access_token"]
    staff_headers = {"Authorization": f"Bearer {staff_token}"}
    _, headers, author_id = _session(client, "13800138029", "详情作者")
    book = client.post(
        "/writer/api/v1/books",
        json={"author_id": author_id, "title": "公开详情", "synopsis": "简介"},
        headers=headers,
    )
    assert book.status_code == 201
    book_id = book.json()["id"]
    assert client.get(f"/api/v1/books/{book_id}").status_code == 404

    volume = client.post(
        f"/writer/api/v1/books/{book_id}/volumes",
        json={"number": 1, "title": "第一卷"},
        headers=headers,
    )
    chapter = client.post(
        f"/writer/api/v1/volumes/{volume.json()['id']}/chapters",
        json={"number": 1, "title": "第一章", "commercial_policy": "FREE"},
        headers=headers,
    )
    draft = client.post(
        f"/writer/api/v1/chapters/{chapter.json()['id']}/drafts",
        json={"content": "正文"},
        headers=headers,
    )
    version = client.post(
        f"/writer/api/v1/chapters/{chapter.json()['id']}/versions",
        json={"snapshot_id": draft.json()["id"]},
        headers=headers,
    )
    submission = client.post(
        f"/writer/api/v1/books/{book_id}/first-listing-submissions",
        json={"fixed_version_ids": [version.json()["id"]]},
        headers=headers,
    )
    client.post(
        f"/admin/api/v1/reviews/{submission.json()['id']}/decisions",
        json={"reviewer_id": "staff-1", "decision": "APPROVE"},
        headers=staff_headers,
    )
    detail = client.get(f"/api/v1/books/{book_id}")
    assert detail.status_code == 200
    assert detail.json()["title"] == "公开详情"
    assert detail.json()["chapters"] == [
        {"id": chapter.json()["id"], "number": 1, "title": "第一章", "commercial_policy": "FREE"}
    ]
