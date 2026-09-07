from fastapi import FastAPI
from fastapi.testclient import TestClient

from novel_platform.modules.content.application import ContentService
from novel_platform.modules.content.domain import BookVisibility
from novel_platform.modules.library.api import build_library_router
from novel_platform.modules.library.application import LibraryService
from novel_platform.modules.operation.api import build_reader_operation_router
from novel_platform.modules.operation.application import OperationService
from novel_platform.modules.operation.domain import RankingKind
from novel_platform.modules.reader_experience.api import build_reader_experience_router
from novel_platform.modules.reader_experience.application import ReaderExperienceService
from novel_platform.modules.reading.api import build_reading_router
from novel_platform.modules.reading.application import ReadingService


def test_bookshelf_rejects_unknown_book_and_returns_public_projection() -> None:
    content = ContentService()
    book = content.create_book("author-1", "测试小说一", synopsis="简介")
    content.set_book_visibility(book.id, BookVisibility.PUBLIC)
    content.publish_metadata_version(book.id, content.get_book(book.id).metadata_version_ids[0])

    app = FastAPI()
    app.include_router(build_library_router(LibraryService(), content=content), prefix="/api/v1")
    client = TestClient(app)

    unknown = client.post(
        "/api/v1/books/BK_missing/bookshelf",
        json={"account_id": "account-1"},
    )
    assert unknown.status_code == 404

    created = client.post(
        f"/api/v1/books/{book.id}/bookshelf",
        json={"account_id": "account-1"},
    )
    assert created.status_code == 201
    assert created.json()["book_id"] == book.id
    assert created.json()["title"] == "测试小说一"

    listed = client.get("/api/v1/bookshelf", params={"account_id": "account-1"})
    assert listed.status_code == 200
    assert listed.json()[0]["title"] == "测试小说一"


def test_follow_status_is_explicit_and_public_ranking_accepts_reader_alias() -> None:
    content = ContentService()
    app = FastAPI()
    app.include_router(
        build_reader_experience_router(content, ReaderExperienceService()),
        prefix="",
    )
    operation = OperationService()
    operation.publish_ranking(["book-1"], RankingKind.ALGORITHM, [100], "snap-1")
    app.include_router(build_reader_operation_router(operation))
    client = TestClient(app)

    before = client.get(
        "/api/v1/social/follows/status",
        params={"account_id": "account-1", "target_type": "AUTHOR", "target_id": "author-1"},
    )
    assert before.status_code == 200
    assert before.json()["following"] is False

    created = client.post(
        "/api/v1/social/follows",
        json={"account_id": "account-1", "target_type": "AUTHOR", "target_id": "author-1"},
    )
    assert created.status_code == 201
    assert created.json()["created"] is True

    after = client.get(
        "/api/v1/social/follows/status",
        params={"account_id": "account-1", "target_type": "AUTHOR", "target_id": "author-1"},
    )
    assert after.json()["following"] is True

    following = client.get("/api/v1/accounts/account-1/follows")
    assert following.json()["items"] == [{"target_type": "AUTHOR", "target_id": "author-1"}]

    ranking = client.get("/api/v1/rankings/hot")
    assert ranking.status_code == 200
    assert ranking.json()[0]["book_id"] == "book-1"

    operation.publish_ranking(["book-2"], RankingKind.ALGORITHM, [200], "snap-2")
    latest = client.get("/api/v1/rankings?kind=hot")
    assert [item["book_id"] for item in latest.json()] == ["book-2"]


def test_reading_session_route_persists_and_rejects_empty_session_id() -> None:
    app = FastAPI()
    app.include_router(build_reading_router(ReadingService()))
    client = TestClient(app)

    created = client.post(
        "/api/v1/books/book-1/progress/session?account_id=account-1",
        json={"session_id": "mobile-1"},
    )
    assert created.status_code == 200
    assert created.json()["current_session_id"] == "mobile-1"

    invalid = client.post(
        "/api/v1/books/book-1/progress/session?account_id=account-1",
        json={"session_id": "  "},
    )
    assert invalid.status_code == 422


def test_reading_preferences_round_trip_is_account_scoped() -> None:
    app = FastAPI()
    app.include_router(build_reading_router(ReadingService()))
    client = TestClient(app)

    before = client.get("/api/v1/accounts/account-1/reading-preferences")
    assert before.status_code == 200
    assert before.json()["background"] == "cream"

    updated = client.put(
        "/api/v1/accounts/account-1/reading-preferences",
        json={
            "mode": "paged",
            "font_family": "sans",
            "font_size": 22,
            "font_weight": 500,
            "line_height": 2.2,
            "paragraph_spacing": 1.5,
            "content_width": 820,
            "background": "eye",
            "auto_scroll_speed": 1.5,
            "auto_subscribe": True,
        },
    )
    assert updated.status_code == 200
    assert updated.json()["mode"] == "paged"
    assert client.get("/api/v1/accounts/account-1/reading-preferences").json()["font_size"] == 22
    assert (
        client.put(
            "/api/v1/accounts/account-1/reading-preferences",
            json={"font_size": 99},
        ).status_code
        == 422
    )
