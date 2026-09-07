import pytest
from fastapi import HTTPException

from novel_platform.core.auth import SessionClaims, SessionSigner
from novel_platform.core.middleware import _admin_permission
from novel_platform.modules.platform.application import PlatformApplication
from novel_platform.modules.platform.repository import InMemoryPlatformRepository
from novel_platform.modules.platform.staff_auth import StaffAuthService
from novel_platform.modules.review.application import ReviewService
from novel_platform.modules.review.domain import ReviewSubmission


def _authorized_staff(scope_type: str, scope_value: str) -> tuple[StaffAuthService, SessionClaims]:
    platform = PlatformApplication(InMemoryPlatformRepository())
    staff = platform.create_staff("staff-001", "editorial")
    platform.grant_permission(staff.id, "review.read")
    platform.grant_data_scope(staff.id, scope_type, scope_value)
    auth = StaffAuthService(platform, SessionSigner("test-secret"))
    claims = auth.signer.verify(auth.signer.issue_staff(staff.id))
    assert claims is not None
    return auth, claims


def test_authorize_uses_server_computed_assigned_scope_and_rejects_other_resource() -> None:
    auth, claims = _authorized_staff("ASSIGNED", "book-1")

    auth.authorize(claims, "review.read", "ASSIGNED", "book-1")

    with pytest.raises(HTTPException) as error:
        auth.authorize(claims, "review.read", "ASSIGNED", "book-2")
    assert error.value.status_code == 403


def test_authorize_uses_server_computed_custom_scope() -> None:
    auth, claims = _authorized_staff("CUSTOM", "department:editorial")

    auth.authorize(claims, "review.read", "CUSTOM", "department:editorial")

    with pytest.raises(HTTPException):
        auth.authorize(claims, "review.read", "CUSTOM", "department:finance")


def test_all_scope_authorizes_any_server_computed_scope() -> None:
    auth, claims = _authorized_staff("ALL", "*")

    auth.authorize(claims, "review.read", "ASSIGNED", "book-2")


def test_legacy_admin_authorize_call_remains_compatible_without_scope_bypass() -> None:
    auth, claims = _authorized_staff("ALL", "*")
    auth.authorize(claims, "review.read")

    scoped_auth, scoped_claims = _authorized_staff("ASSIGNED", "book-1")
    with pytest.raises(HTTPException):
        scoped_auth.authorize(scoped_claims, "review.read")


def test_authorize_rejects_account_claim_even_when_account_id_matches_staff() -> None:
    auth, staff_claims = _authorized_staff("ALL", "*")
    forged_actor = type(staff_claims)(
        account_id=staff_claims.account_id,
        expires_at=staff_claims.expires_at,
        subject_type="ACCOUNT",
        session_id=staff_claims.session_id,
    )

    with pytest.raises(HTTPException) as error:
        auth.authorize(forged_actor, "review.read", "ALL", "*")
    assert error.value.status_code == 403


def test_chapter_commercial_policy_uses_commerce_permission() -> None:
    assert _admin_permission("/admin/api/v1/chapters/ch-1/commercial-policy", "POST") == (
        "commerce.write"
    )


def test_finance_and_agent_routes_use_domain_permissions() -> None:
    assert _admin_permission("/admin/api/v1/invoices/inv-1/issue", "POST") == ("finance.write")
    assert _admin_permission("/admin/api/v1/agent/resources", "GET") == "agent.execute"
    assert _admin_permission("/admin/api/v1/agent/audits", "GET") == "agent.audit.read"
    assert _admin_permission("/admin/api/v1/finance/contracts/ctr-1/approve", "POST") == (
        "approval.write"
    )
    assert _admin_permission("/admin/api/v1/finance/contracts/ctr-1/activate", "POST") == (
        "approval.write"
    )


def test_review_collection_scope_filters_assigned_submissions_in_service() -> None:
    service = ReviewService.__new__(ReviewService)
    service._submissions = {
        "assigned": ReviewSubmission("assigned", "book-1", "FIRST_LISTING", ("v1",)),
        "other": ReviewSubmission("other", "book-2", "FIRST_LISTING", ("v2",)),
    }
    service._decisions = {}
    service._assignments = {"assigned": "staff-a", "other": "staff-b"}

    visible = service.list_submissions_for_scope("ASSIGNED", "staff-a")

    assert [item.id for item in visible] == ["assigned"]
