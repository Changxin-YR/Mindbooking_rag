from fastapi.testclient import TestClient

from novel_platform.main import create_app
from novel_platform.modules.reader_experience.application import ReaderExperienceService


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
    correction = client.post(
        "/api/v1/content-corrections",
        json={
            "account_id": "acct-1",
            "book_id": "book-1",
            "chapter_id": "chapter-1",
            "kind": "TYPO",
            "position": 18,
            "description": "错别字",
        },
    )
    assert correction.status_code == 201
    assert correction.json()["kind"] == "TYPO"

    minor = client.put(
        "/api/v1/accounts/acct-1/minor-protection",
        json={"is_minor": True, "policy_version": "minor-v1"},
    )
    assert minor.status_code == 200
    assert minor.json() == {
        "account_id": "acct-1",
        "is_minor": True,
        "policy_version": "minor-v1",
        "purchase_allowed": False,
    }


def test_reader_catalog_filters_public_books() -> None:
    client = TestClient(create_app())
    first = client.post(
        "/writer/api/v1/books",
        json={
            "author_id": "author-1",
            "title": "玄幻新书",
            "channel": "MALE",
            "category": "东方玄幻",
            "tags": ["系统"],
        },
    )
    second = client.post(
        "/writer/api/v1/books",
        json={"author_id": "author-2", "title": "女频新书", "channel": "FEMALE"},
    )
    assert first.status_code == 201
    assert second.status_code == 201

    volume = client.post(
        f"/writer/api/v1/books/{first.json()['id']}/volumes",
        json={"number": 1, "title": "第一卷"},
    )
    chapter = client.post(
        f"/writer/api/v1/volumes/{volume.json()['id']}/chapters",
        json={"number": 1, "title": "第一章", "commercial_policy": "FREE"},
    )
    draft = client.post(
        f"/writer/api/v1/chapters/{chapter.json()['id']}/drafts",
        json={"content": "正文"},
    )
    version = client.post(
        f"/writer/api/v1/chapters/{chapter.json()['id']}/versions",
        json={"snapshot_id": draft.json()["id"]},
    )
    submission = client.post(
        f"/writer/api/v1/books/{first.json()['id']}/first-listing-submissions",
        json={"fixed_version_ids": [version.json()["id"]]},
    )
    decision = client.post(
        f"/admin/api/v1/reviews/{submission.json()['id']}/decisions",
        json={"reviewer_id": "staff-1", "decision": "APPROVE"},
    )
    assert decision.status_code == 201

    response = client.get("/api/v1/books", params={"channel": "MALE"})
    assert response.status_code == 200
    assert response.json()["total"] == 1
    assert response.json()["items"][0]["title"] == "玄幻新书"
