import pytest
from fastapi.testclient import TestClient

from novel_platform.core.middleware import _admin_scope
from novel_platform.main import create_app
from novel_platform.modules.content.domain import CommercialPolicy


@pytest.mark.parametrize(
    ("path", "expected"),
    [
        ("/admin/api/v1/reviews/review-1/decisions", ("ASSIGNED", "review-1")),
        ("/admin/api/v1/approvals/approval-1/decision", ("ASSIGNED", "approval-1")),
        ("/admin/api/v1/risk/signals/signal-1/freeze", ("ASSIGNED", "signal-1")),
        ("/admin/api/v1/finance/settlements/settlement-1/withdraw", ("ASSIGNED", "settlement-1")),
        ("/admin/api/v1/reviews", None),
    ],
)
def test_admin_resource_scope_is_server_derived(
    path: str, expected: tuple[str, str] | None
) -> None:
    assert _admin_scope(path) == expected


def test_admin_resource_route_passes_exact_assigned_scope_to_authorizer(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("STAFF_BOOTSTRAP_EMPLOYEE_CODE", "scope-admin")
    monkeypatch.setenv("STAFF_BOOTSTRAP_PASSWORD", "StaffPassword#123")
    client = TestClient(create_app())
    staff = client.app.state.platform.create_staff("scope-reviewer", "editorial")
    client.app.state.staff_auth.set_password(staff.id, "ReviewerPassword#123")
    client.app.state.platform.grant_permission(staff.id, "review.decide")
    client.app.state.platform.grant_data_scope(staff.id, "ASSIGNED", "review-1")
    login = client.post(
        "/admin/api/v1/auth/staff/sessions",
        json={"employee_code": "scope-reviewer", "password": "ReviewerPassword#123"},
    )

    response = client.post(
        "/admin/api/v1/reviews/review-1/decisions",
        headers={"Authorization": f"Bearer {login.json()['access_token']}"},
        json={"reviewer_id": "ignored", "decision": "APPROVE"},
    )

    assert response.status_code == 404


def test_review_collection_returns_only_submissions_in_staff_data_scope(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("STAFF_BOOTSTRAP_EMPLOYEE_CODE", "scope-admin-list")
    monkeypatch.setenv("STAFF_BOOTSTRAP_PASSWORD", "StaffPassword#123")
    client = TestClient(create_app())
    app = client.app
    reviewer_a = app.state.platform.create_staff("scope-a", "editorial")
    reviewer_b = app.state.platform.create_staff("scope-b", "editorial")
    for reviewer in (reviewer_a, reviewer_b):
        app.state.staff_auth.set_password(reviewer.id, "ReviewerPassword#123")
        app.state.platform.grant_permission(reviewer.id, "review.read")
        app.state.platform.grant_data_scope(reviewer.id, "ASSIGNED", reviewer.id)

    submissions = []
    for title, reviewer in (("Assigned A", reviewer_a), ("Assigned B", reviewer_b)):
        book = app.state.content_service.create_book("author-1", title)
        volume = app.state.content_service.create_volume(book.id, "Volume 1", 1)
        chapter = app.state.content_service.create_chapter(
            volume.id, "Chapter 1", CommercialPolicy.FREE
        )
        snapshot = app.state.content_service.save_draft(chapter.id, "content")
        version = app.state.content_service.create_chapter_version(chapter.id, snapshot.id)
        submission = app.state.review_service.submit_first_listing(book.id, [version.id])
        app.state.review_service.assign_submission(submission.id, reviewer.id)
        submissions.append(submission)

    login = client.post(
        "/admin/api/v1/auth/staff/sessions",
        json={"employee_code": "scope-a", "password": "ReviewerPassword#123"},
    )
    response = client.get(
        "/admin/api/v1/reviews",
        headers={"Authorization": f"Bearer {login.json()['access_token']}"},
    )

    assert response.status_code == 200
    assert [item["id"] for item in response.json()] == [submissions[0].id]
