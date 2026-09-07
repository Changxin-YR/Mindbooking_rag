from datetime import UTC, datetime, timedelta

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from novel_platform.core.auth import SessionSigner
from novel_platform.modules.content.api import build_content_routers
from novel_platform.modules.content.application import ContentService
from novel_platform.modules.content.domain import BookLifecycle, BookVisibility, CommercialPolicy
from novel_platform.modules.library.api import build_library_router
from novel_platform.modules.library.application import EntitlementService, LibraryService
from novel_platform.modules.membership.domain import AccessMode, ChapterPolicy, MembershipService
from novel_platform.modules.reading.api import build_reading_router
from novel_platform.modules.reading.application import ContentAccessService, ReadingService
from novel_platform.modules.reading.domain import AccessResult, ProgressConflict
from novel_platform.modules.review.api import build_review_routers
from novel_platform.modules.review.application import ReviewService
from novel_platform.modules.review.domain import ReviewDecision


def test_book_has_independent_lifecycle_and_visibility() -> None:
    service = ContentService()
    book = service.create_book("author-1", "Book")

    assert book.lifecycle is BookLifecycle.DRAFT
    assert book.visibility is BookVisibility.PRIVATE

    service.set_book_visibility(book.id, BookVisibility.PUBLIC)
    service.set_book_lifecycle(book.id, BookLifecycle.SERIALIZING)

    assert service.get_book(book.id).visibility is BookVisibility.PUBLIC
    assert service.get_book(book.id).lifecycle is BookLifecycle.SERIALIZING


def test_draft_snapshot_and_published_chapter_version_are_immutable() -> None:
    service = ContentService()
    book = service.create_book("author-1", "Book")
    volume = service.create_volume(book.id, "Volume 1", 1)
    chapter = service.create_chapter(volume.id, "Chapter 1", CommercialPolicy.VIP)

    snapshot = service.save_draft(chapter.id, "draft v1")
    version = service.create_chapter_version(chapter.id, snapshot.id)
    service.publish_chapter_version(chapter.id, version.id)
    service.save_draft(chapter.id, "draft v2")

    assert service.get_chapter_version(version.id).content == "draft v1"
    with pytest.raises(ValueError, match="immutable"):
        service.update_published_version(version.id, "tampered")


def test_first_listing_submission_keeps_fixed_versions_until_human_approval() -> None:
    content = ContentService()
    book = content.create_book("author-1", "Book")
    volume = content.create_volume(book.id, "Volume 1", 1)
    chapter = content.create_chapter(volume.id, "Chapter 1", CommercialPolicy.FREE)
    snapshot = content.save_draft(chapter.id, "fixed content")
    version = content.create_chapter_version(chapter.id, snapshot.id)
    review = ReviewService(content)

    submission = review.submit_first_listing(book.id, [version.id])
    content.save_draft(chapter.id, "later draft")
    assert submission.fixed_version_ids == (version.id,)
    assert content.get_book(book.id).visibility is BookVisibility.PENDING_FIRST_REVIEW

    review.decide(submission.id, "reviewer-1", ReviewDecision.APPROVE)

    assert content.get_book(book.id).visibility is BookVisibility.PUBLIC
    assert content.get_chapter(chapter.id).published_version_id == version.id


def test_first_listing_requires_human_decision() -> None:
    content = ContentService()
    book = content.create_book("author-1", "Book")
    volume = content.create_volume(book.id, "Volume 1", 1)
    chapter = content.create_chapter(volume.id, "Chapter 1", CommercialPolicy.FREE)
    version = content.create_chapter_version(
        chapter.id, content.save_draft(chapter.id, "content").id
    )
    review = ReviewService(content)
    submission = review.submit_first_listing(book.id, [version.id])

    with pytest.raises(ValueError, match="human"):
        review.decide(submission.id, "machine-1", ReviewDecision.APPROVE, actor_type="machine")


def test_first_listing_requires_at_least_one_fixed_version() -> None:
    content = ContentService()
    book = content.create_book("author-1", "Book")

    with pytest.raises(ValueError, match="at least one"):
        ReviewService(content).submit_first_listing(book.id, [])


def test_first_listing_rejects_versions_from_another_book() -> None:
    content = ContentService()
    first_book = content.create_book("author-1", "Book 1")
    second_book = content.create_book("author-1", "Book 2")
    first_volume = content.create_volume(first_book.id, "Volume 1", 1)
    second_volume = content.create_volume(second_book.id, "Volume 1", 1)
    first_chapter = content.create_chapter(first_volume.id, "Chapter 1", CommercialPolicy.FREE)
    second_chapter = content.create_chapter(second_volume.id, "Chapter 1", CommercialPolicy.FREE)
    first_version = content.create_chapter_version(
        first_chapter.id, content.save_draft(first_chapter.id, "one").id
    )
    second_version = content.create_chapter_version(
        second_chapter.id, content.save_draft(second_chapter.id, "two").id
    )

    with pytest.raises(ValueError, match="does not belong"):
        ReviewService(content).submit_first_listing(
            first_book.id, [first_version.id, second_version.id]
        )


def test_content_access_obeys_availability_restriction_and_entitlement_order() -> None:
    access = ContentAccessService()
    kwargs = {
        "policy": CommercialPolicy.VIP,
        "purchased": True,
        "limited_free": True,
        "member_free": True,
    }

    assert (
        access.check(
            book_available=False, chapter_available=True, restricted=False, **kwargs
        ).result
        is AccessResult.UNAVAILABLE
    )
    assert (
        access.check(book_available=True, chapter_available=True, restricted=True, **kwargs).result
        is AccessResult.RESTRICTED
    )
    assert (
        access.check(
            book_available=True,
            chapter_available=True,
            restricted=False,
            policy=CommercialPolicy.FREE,
            purchased=False,
            limited_free=True,
            member_free=True,
        ).result
        is AccessResult.FREE
    )
    assert (
        access.check(book_available=True, chapter_available=True, restricted=False, **kwargs).result
        is AccessResult.PURCHASED
    )
    assert (
        access.check(
            book_available=True,
            chapter_available=True,
            restricted=False,
            policy=CommercialPolicy.VIP,
            purchased=False,
            limited_free=True,
            member_free=True,
        ).result
        is AccessResult.LIMITED_FREE
    )
    assert (
        access.check(
            book_available=True,
            chapter_available=True,
            restricted=False,
            policy=CommercialPolicy.VIP,
            purchased=False,
            limited_free=False,
            member_free=True,
        ).result
        is AccessResult.MEMBER_FREE
    )
    assert (
        access.check(
            book_available=True,
            chapter_available=True,
            restricted=False,
            policy=CommercialPolicy.VIP,
            purchased=False,
            limited_free=False,
            member_free=False,
        ).result
        is AccessResult.VIP_REQUIRED
    )


def test_reading_progress_preserves_furthest_and_rejects_revision_conflict() -> None:
    service = ReadingService()
    progress = service.update_progress(
        "account-1",
        "book-1",
        chapter_id="ch-100",
        chapter_number=100,
        position=10,
        expected_revision=0,
        session_id="phone",
    )
    progress = service.update_progress(
        "account-1",
        "book-1",
        chapter_id="ch-010",
        chapter_number=10,
        position=20,
        expected_revision=progress.revision,
        session_id="phone",
    )

    assert progress.last_chapter_id == "ch-010"
    assert progress.furthest_chapter_id == "ch-100"
    with pytest.raises(ProgressConflict):
        service.update_progress(
            "account-1",
            "book-1",
            chapter_id="ch-001",
            chapter_number=1,
            position=1,
            expected_revision=0,
            session_id="phone",
        )


def test_stale_reading_session_can_advance_furthest_but_not_resume_position() -> None:
    service = ReadingService()
    current = service.update_progress(
        "account-1",
        "book-1",
        chapter_id="ch-010",
        chapter_number=10,
        position=40,
        expected_revision=0,
        session_id="phone",
    )
    stale = service.update_progress(
        "account-1",
        "book-1",
        chapter_id="ch-020",
        chapter_number=20,
        position=5,
        expected_revision=current.revision,
        session_id="old-tab",
    )

    assert stale.last_chapter_id == "ch-010"
    assert stale.furthest_chapter_id == "ch-020"


def test_bookshelf_removal_does_not_remove_entitlement() -> None:
    entitlements = EntitlementService()
    library = LibraryService()
    entitlements.grant("account-1", "chapter-1")
    library.add("account-1", "book-1")

    library.remove("account-1", "book-1")

    assert library.list("account-1") == []
    assert entitlements.has("account-1", "chapter-1")


def test_explicit_reader_writer_admin_routes_use_dtos() -> None:
    content = ContentService()
    app = FastAPI()
    for router in build_content_routers(content):
        app.include_router(router)
    review = ReviewService(content)
    for router in build_review_routers(review):
        app.include_router(router)
    library = LibraryService()
    app.include_router(build_library_router(library), prefix="/api/v1")
    client = TestClient(app)

    response = client.post("/writer/api/v1/books", json={"author_id": "a-1", "title": "Book"})
    assert response.status_code == 201
    assert set(response.json()) == {"id", "title", "lifecycle", "visibility"}

    book_id = response.json()["id"]
    assert client.get(f"/api/v1/books/{book_id}").status_code == 404
    content.set_book_visibility(book_id, BookVisibility.PUBLIC)
    content.publish_metadata_version(book_id, content.get_book(book_id).metadata_version_ids[0])
    assert client.get(f"/api/v1/books/{book_id}").status_code == 404
    volume = content.create_volume(book_id, "正文", 1)
    chapter = content.create_chapter(volume.id, "第一章", CommercialPolicy.FREE, 1)
    snapshot = content.save_draft(chapter.id, "正文")
    version = content.create_chapter_version(chapter.id, snapshot.id)
    content.publish_chapter_version(chapter.id, version.id)
    reader_response = client.get(f"/api/v1/books/{book_id}")
    assert reader_response.status_code == 200
    assert "internal_risk_score" not in reader_response.json()

    admin_response = client.get("/admin/api/v1/reviews")
    assert admin_response.status_code == 200
    assert isinstance(admin_response.json(), list)


def test_reader_progress_route_exposes_explicit_dto_and_conflict() -> None:
    app = FastAPI()
    app.include_router(build_reading_router(ReadingService()))
    client = TestClient(app)

    response = client.put(
        "/api/v1/books/book-1/progress?account_id=account-1",
        json={
            "chapter_id": "chapter-1",
            "chapter_number": 1,
            "position": 3,
            "expected_revision": 0,
            "session_id": "phone",
        },
    )
    assert response.status_code == 200
    assert set(response.json()) == {
        "account_id",
        "book_id",
        "last_chapter_id",
        "last_chapter_number",
        "last_position",
        "furthest_chapter_id",
        "furthest_chapter_number",
        "furthest_position",
        "revision",
        "current_session_id",
    }

    conflict = client.put(
        "/api/v1/books/book-1/progress?account_id=account-1",
        json={
            "chapter_id": "chapter-2",
            "chapter_number": 2,
            "position": 1,
            "expected_revision": 0,
            "session_id": "phone",
        },
    )
    assert conflict.status_code == 409
    assert conflict.json()["detail"]["code"] == "REVISION_CONFLICT"


def test_content_rejects_duplicate_volume_and_chapter_numbers() -> None:
    service = ContentService()
    book = service.create_book("author-1", "Book")
    service.create_volume(book.id, "Volume 1", 1)

    with pytest.raises(ValueError, match="already exists"):
        service.create_volume(book.id, "Another Volume 1", 1)

    volume = service.create_volume(book.id, "Volume 2", 2)
    service.create_chapter(volume.id, "Chapter 1", CommercialPolicy.FREE, 1)
    with pytest.raises(ValueError, match="already exists"):
        service.create_chapter(volume.id, "Another Chapter 1", CommercialPolicy.FREE, 1)


def test_first_listing_rejects_two_versions_of_the_same_chapter() -> None:
    content = ContentService()
    book = content.create_book("author-1", "Book")
    volume = content.create_volume(book.id, "Volume 1", 1)
    chapter = content.create_chapter(volume.id, "Chapter 1", CommercialPolicy.FREE)
    first = content.create_chapter_version(chapter.id, content.save_draft(chapter.id, "v1").id)
    second = content.create_chapter_version(chapter.id, content.save_draft(chapter.id, "v2").id)

    with pytest.raises(ValueError, match="one version per chapter"):
        ReviewService(content).submit_first_listing(book.id, [first.id, second.id])


def test_public_book_chapter_update_stays_public_until_human_approval() -> None:
    content = ContentService()
    book = content.create_book("author-1", "Book")
    volume = content.create_volume(book.id, "Volume 1", 1)
    chapter = content.create_chapter(volume.id, "Chapter 1", CommercialPolicy.FREE)
    first = content.create_chapter_version(chapter.id, content.save_draft(chapter.id, "v1").id)
    content.publish_fixed_versions(book.id, [first.id])
    second = content.create_chapter_version(chapter.id, content.save_draft(chapter.id, "v2").id)
    review = ReviewService(content)

    submission = review.submit_chapter_update(book.id, [second.id])

    assert submission.submission_type == "CHAPTER_UPDATE"
    assert content.get_book(book.id).visibility is BookVisibility.PUBLIC
    assert content.get_chapter(chapter.id).published_version_id == first.id

    review.decide(submission.id, "reviewer-1", ReviewDecision.APPROVE)

    assert content.get_book(book.id).visibility is BookVisibility.PUBLIC
    assert content.get_chapter(chapter.id).published_version_id == second.id


def test_reader_can_read_only_public_free_chapter() -> None:
    content = ContentService()
    app = FastAPI()
    app.include_router(build_content_routers(content)[0])
    client = TestClient(app)

    book = content.create_book("author-1", "Book")
    volume = content.create_volume(book.id, "Volume 1", 1)
    free_chapter = content.create_chapter(volume.id, "Free", CommercialPolicy.FREE)
    vip_chapter = content.create_chapter(volume.id, "VIP", CommercialPolicy.VIP)
    free_version = content.create_chapter_version(
        free_chapter.id, content.save_draft(free_chapter.id, "free").id
    )
    vip_version = content.create_chapter_version(
        vip_chapter.id, content.save_draft(vip_chapter.id, "vip").id
    )
    content.publish_fixed_versions(book.id, [free_version.id, vip_version.id])

    free_response = client.get(f"/api/v1/books/{book.id}/chapters/{free_chapter.id}")
    assert free_response.status_code == 200
    assert free_response.json()["content"] == "free"

    vip_response = client.get(f"/api/v1/books/{book.id}/chapters/{vip_chapter.id}")
    assert vip_response.status_code == 403


def test_reader_lists_and_reads_multiple_published_chapters_in_order() -> None:
    content = ContentService()
    app = FastAPI()
    app.include_router(build_content_routers(content)[0])
    client = TestClient(app)

    book = content.create_book("author-1", "可连续阅读的书")
    volume = content.create_volume(book.id, "正文", 1)
    versions = []
    for number, text in ((1, "第一章的完整正文。"), (2, "第二章的完整正文。")):
        chapter = content.create_chapter(volume.id, f"第{number}章", CommercialPolicy.FREE, number)
        versions.append(
            content.create_chapter_version(chapter.id, content.save_draft(chapter.id, text).id)
        )
    content.publish_fixed_versions(book.id, [version.id for version in versions])

    detail = client.get(f"/api/v1/books/{book.id}")
    assert detail.status_code == 200
    assert [(item["number"], item["title"]) for item in detail.json()["chapters"]] == [
        (1, "第1章"),
        (2, "第2章"),
    ]
    first = client.get(f"/api/v1/books/{book.id}/chapters/{detail.json()['chapters'][0]['id']}")
    second = client.get(f"/api/v1/books/{book.id}/chapters/{detail.json()['chapters'][1]['id']}")
    assert first.json()["content"] == "第一章的完整正文。"
    assert second.json()["content"] == "第二章的完整正文。"


def test_reader_membership_access_returns_member_free_and_purchased() -> None:
    content = ContentService()
    book = content.create_book("author-1", "会员书")
    volume = content.create_volume(book.id, "第一卷", 1)
    chapter = content.create_chapter(volume.id, "VIP", CommercialPolicy.VIP)
    version = content.create_chapter_version(chapter.id, content.save_draft(chapter.id, "vip").id)
    content.publish_fixed_versions(book.id, [version.id])

    class Commerce:
        purchased = False

        def has_entitlement(self, account_id: str, chapter_id: str) -> bool:
            del account_id, chapter_id
            return self.purchased

    app = FastAPI()
    app.include_router(build_content_routers(content)[0])
    app.state.session_signer = SessionSigner("test-secret")
    app.state.commerce_service = commerce = Commerce()
    membership = MembershipService()
    app.state.membership_service = membership
    client = TestClient(app)
    headers = {"Authorization": f"Bearer {app.state.session_signer.issue('account-1')}"}

    non_member = client.get(f"/api/v1/books/{book.id}/chapters/{chapter.id}", headers=headers)
    assert non_member.status_code == 403
    assert non_member.json()["detail"]["code"] == "VIP_REQUIRED"

    membership.activate("account-1", datetime.now(UTC) + timedelta(days=1))
    membership.add_library_book(book.id)
    member = client.get(f"/api/v1/books/{book.id}/chapters/{chapter.id}", headers=headers)
    assert member.status_code == 200
    assert member.json()["access"] == "MEMBER_FREE"

    commerce.purchased = True
    purchased = client.get(f"/api/v1/books/{book.id}/chapters/{chapter.id}", headers=headers)
    assert purchased.status_code == 200
    assert purchased.json()["access"] == "PURCHASED"


def test_writer_list_books_includes_private_and_public_books_for_only_author() -> None:
    content = ContentService()
    private = content.create_book("author-1", "Private")
    public = content.create_book("author-1", "Public")
    content.set_book_visibility(public.id, BookVisibility.PUBLIC)
    content.publish_metadata_version(public.id, content.get_book(public.id).metadata_version_ids[0])
    content.create_book("author-2", "Other")

    app = FastAPI()
    app.include_router(build_content_routers(content)[1])
    client = TestClient(app)

    response = client.get("/writer/api/v1/books", params={"author_id": "author-1"})
    assert response.status_code == 200
    expected = [
        {
            "id": book.id,
            "title": title,
            "lifecycle": "DRAFT",
            "visibility": visibility,
        }
        for book, title, visibility in sorted(
            (
                (private, "Private", "PRIVATE"),
                (public, "Public", "PUBLIC"),
            ),
            key=lambda item: item[0].id,
        )
    ]
    assert response.json() == expected

    missing_author = client.get("/writer/api/v1/books", params={"author_id": " "})
    assert missing_author.status_code == 422


def test_admin_list_books_returns_author_scope_facts() -> None:
    content = ContentService()
    first = content.create_book("author-1", "Private")
    second = content.create_book("author-2", "Other")
    app = FastAPI()
    app.include_router(build_content_routers(content)[2])
    client = TestClient(app)

    response = client.get("/admin/api/v1/books")

    assert response.status_code == 200
    expected = [
        {
            "id": first.id,
            "title": "Private",
            "lifecycle": "DRAFT",
            "visibility": "PRIVATE",
            "author_id": "author-1",
        },
        {
            "id": second.id,
            "title": "Other",
            "lifecycle": "DRAFT",
            "visibility": "PRIVATE",
            "author_id": "author-2",
        },
    ]
    assert response.json() == sorted(expected, key=lambda item: item["id"])


def test_writer_cannot_create_vip_chapter_directly() -> None:
    content = ContentService()
    app = FastAPI()
    app.include_router(build_content_routers(content)[1])
    client = TestClient(app)
    book = content.create_book("author-1", "Book")
    volume = content.create_volume(book.id, "Volume 1", 1)

    response = client.post(
        f"/writer/api/v1/volumes/{volume.id}/chapters",
        json={"title": "VIP", "commercial_policy": "VIP"},
    )

    assert response.status_code == 403
    assert response.json()["detail"]["code"] == "PLATFORM_COMMERCIAL_POLICY_REQUIRED"


def test_staff_commercial_policy_route_uses_platform_configuration_port() -> None:
    content = ContentService()
    configured: list[tuple[str, ChapterPolicy]] = []
    app = FastAPI()
    app.include_router(
        build_content_routers(
            content,
            configure_commercial_policy=lambda chapter_id, policy: configured.append(
                (chapter_id, policy)
            ),
        )[2]
    )
    client = TestClient(app)
    book = content.create_book("author-1", "Book")
    volume = content.create_volume(book.id, "Volume 1", 1)
    chapter = content.create_chapter(volume.id, "Chapter 1", CommercialPolicy.FREE)

    response = client.post(
        f"/admin/api/v1/chapters/{chapter.id}/commercial-policy",
        json={"price_coin": 100},
    )

    assert response.status_code == 200
    assert configured == [(chapter.id, ChapterPolicy(100, AccessMode.VIP_REQUIRED))]
