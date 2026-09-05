from datetime import UTC, datetime, timedelta

from fastapi import FastAPI
from fastapi.testclient import TestClient

from novel_platform.core.auth import SessionSigner
from novel_platform.modules.content.application import ContentService
from novel_platform.modules.content.domain import CommercialPolicy
from novel_platform.modules.membership.domain import AccessMode, ChapterPolicy, MembershipService
from novel_platform.modules.reading.api import build_reading_router
from novel_platform.modules.reading.application import ReadingService


def _published_chapter(content: ContentService, policy: CommercialPolicy = CommercialPolicy.FREE):
    book = content.create_book("author-1", "TTS book")
    volume = content.create_volume(book.id, "Volume 1", 1)
    chapter = content.create_chapter(volume.id, "Chapter 1", policy)
    version = content.create_chapter_version(
        chapter.id, content.save_draft(chapter.id, "第一句。第二句！").id
    )
    content.publish_fixed_versions(book.id, [version.id])
    return book, chapter


def _client(content: ContentService, commerce: object | None = None) -> tuple[TestClient, str]:
    app = FastAPI()
    app.include_router(build_reading_router(ReadingService()))
    app.state.content_service = content
    app.state.commerce_service = commerce
    app.state.membership_service = MembershipService()
    signer = SessionSigner("test-secret")
    app.state.session_signer = signer
    return TestClient(app), signer.issue("account-1")


def test_tts_returns_deterministic_segments_after_free_access_check() -> None:
    content = ContentService()
    book, chapter = _published_chapter(content)
    client, _ = _client(content)

    response = client.get(f"/api/v1/books/{book.id}/chapters/{chapter.id}/tts")

    assert response.status_code == 200
    assert response.json() == {
        "book_id": book.id,
        "chapter_id": chapter.id,
        "access": "FREE",
        "voice": "female-1",
        "speed": 1.0,
        "provider": "deterministic",
        "segments": [
            {"index": 0, "text": "第一句。", "start_ms": 0, "end_ms": 500},
            {"index": 1, "text": "第二句！", "start_ms": 500, "end_ms": 1000},
        ],
    }


def test_tts_reuses_purchase_access_and_rejects_vip_without_entitlement() -> None:
    content = ContentService()
    book, chapter = _published_chapter(content, CommercialPolicy.VIP)

    class Commerce:
        purchased = False

        def has_entitlement(self, account_id: str, chapter_id: str) -> bool:
            assert account_id == "account-1"
            assert chapter_id == chapter.id
            return self.purchased

    commerce = Commerce()
    client, token = _client(content, commerce)
    headers = {"Authorization": f"Bearer {token}"}

    denied = client.get(f"/api/v1/books/{book.id}/chapters/{chapter.id}/tts", headers=headers)
    assert denied.status_code == 403
    assert denied.json()["detail"]["code"] == "VIP_REQUIRED"

    commerce.purchased = True
    allowed = client.get(f"/api/v1/books/{book.id}/chapters/{chapter.id}/tts", headers=headers)
    assert allowed.status_code == 200
    assert allowed.json()["access"] == "PURCHASED"


def test_tts_supports_member_free_and_validates_playback_options() -> None:
    content = ContentService()
    book, chapter = _published_chapter(content, CommercialPolicy.VIP)

    class Commerce:
        def has_entitlement(self, account_id: str, chapter_id: str) -> bool:
            return False

    client, token = _client(content, Commerce())
    client.app.state.membership_service.activate("account-1", datetime.now(UTC) + timedelta(days=1))
    client.app.state.membership_service.add_library_book(book.id)

    response = client.get(
        f"/api/v1/books/{book.id}/chapters/{chapter.id}/tts",
        params={"voice": "male-1", "speed": 1.5},
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    assert response.json()["access"] == "MEMBER_FREE"
    assert response.json()["voice"] == "male-1"
    assert response.json()["speed"] == 1.5

    invalid = client.get(
        f"/api/v1/books/{book.id}/chapters/{chapter.id}/tts",
        params={"speed": 1.1},
    )
    assert invalid.status_code == 422


def test_tts_supports_limited_free_without_changing_vip_chapter_fact() -> None:
    content = ContentService()
    book, chapter = _published_chapter(content, CommercialPolicy.VIP)

    class Commerce:
        def has_entitlement(self, account_id: str, chapter_id: str) -> bool:
            return False

    client, token = _client(content, Commerce())
    client.app.state.chapter_policy_resolver = lambda chapter_id: ChapterPolicy(
        1, AccessMode.LIMITED_FREE
    )

    response = client.get(
        f"/api/v1/books/{book.id}/chapters/{chapter.id}/tts",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    assert response.json()["access"] == "LIMITED_FREE"
    assert chapter.commercial_policy is CommercialPolicy.VIP


def test_tts_account_query_must_match_authenticated_account() -> None:
    content = ContentService()
    book, chapter = _published_chapter(content)
    client, token = _client(content)

    response = client.get(
        f"/api/v1/books/{book.id}/chapters/{chapter.id}/tts",
        params={"account_id": "account-2"},
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 403
    assert response.json()["detail"]["code"] == "ACCOUNT_ACCESS_DENIED"
