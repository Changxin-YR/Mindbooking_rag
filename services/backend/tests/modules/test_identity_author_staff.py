import importlib.util
from concurrent.futures import ThreadPoolExecutor
from hashlib import sha256

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from novel_platform.modules.author.application import (
    AuthorApplication,
    DuplicateAuthorProfileError,
    DuplicatePenNameError,
)
from novel_platform.modules.author.http import build_author_router
from novel_platform.modules.author.repository import InMemoryAuthorRepository
from novel_platform.modules.iam.application import (
    IdentityApplication,
    RealNameSlotLimitError,
)
from novel_platform.modules.iam.domain import identity_document_fingerprint
from novel_platform.modules.iam.http import build_iam_router
from novel_platform.modules.iam.repository import InMemoryIdentityRepository
from novel_platform.modules.platform.application import AccessDeniedError, PlatformApplication
from novel_platform.modules.platform.http import build_platform_router
from novel_platform.modules.platform.repository import InMemoryPlatformRepository


def test_identity_module_is_present() -> None:
    assert importlib.util.find_spec("novel_platform.modules.iam") is not None


def test_identity_document_fingerprint_uses_hmac_not_plain_sha256() -> None:
    document = "11010119900101001X"
    assert (
        identity_document_fingerprint(document, "test-secret")
        != sha256(document.encode("ascii")).hexdigest()
    )


def test_phone_identity_can_route_between_multiple_accounts() -> None:
    application = IdentityApplication(InMemoryIdentityRepository())

    first = application.register_phone_account("13800138000")
    second = application.register_phone_account("13800138000")

    assert first.identity_id == second.identity_id
    assert [account.id for account in application.accounts_for_phone("13800138000")] == [
        first.account_id,
        second.account_id,
    ]
    assert application.default_account_for_phone("13800138000").id == first.account_id

    application.route_phone_to_account("13800138000", second.account_id)

    assert application.default_account_for_phone("13800138000").id == second.account_id


def test_real_name_slot_limit_is_atomic_under_concurrent_requests() -> None:
    repository = InMemoryIdentityRepository()
    application = IdentityApplication(repository)
    accounts = [application.register_phone_account(f"138001380{index:02d}") for index in range(4)]

    def verify(account_id: str) -> str:
        try:
            application.verify_real_name(account_id, "张三", "11010119900101001X")
            return "ok"
        except RealNameSlotLimitError:
            return "limit"

    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(verify, [account.account_id for account in accounts]))

    assert results.count("ok") == 3
    assert results.count("limit") == 1
    fingerprint = identity_document_fingerprint("11010119900101001X")
    assert repository.count_active_real_name_links(fingerprint) == 3


def test_author_profile_and_pen_name_history_are_unique() -> None:
    repository = InMemoryAuthorRepository()
    application = AuthorApplication(repository)

    profile = application.create_profile("account-1", "  星河  ")
    application.change_pen_name(profile.id, "夜航")

    with pytest.raises(DuplicateAuthorProfileError):
        application.create_profile("account-1", "另一个名字")
    with pytest.raises(DuplicatePenNameError):
        application.create_profile("account-2", "星河")
    with pytest.raises(DuplicatePenNameError):
        application.create_profile("account-2", "夜航")

    assert repository.pen_name_history(profile.id) == ["星河", "夜航"]


def test_staff_account_is_separate_and_access_requires_permission_and_scope() -> None:
    repository = InMemoryPlatformRepository()
    application = PlatformApplication(repository)
    staff = application.create_staff("employee-1", "editorial")
    application.grant_permission(staff.id, "author.read")
    application.grant_data_scope(staff.id, "department", "editorial")

    assert staff.platform_account_id is None
    assert application.can_access(staff.id, "author.read", "department", "editorial")

    with pytest.raises(AccessDeniedError):
        application.require_access(staff.id, "author.write", "department", "editorial")
    with pytest.raises(AccessDeniedError):
        application.require_access(staff.id, "author.read", "department", "finance")


def test_identity_author_and_staff_routes_use_explicit_dtos_and_http_semantics() -> None:
    identity = IdentityApplication(InMemoryIdentityRepository())
    author = AuthorApplication(InMemoryAuthorRepository())
    platform = PlatformApplication(InMemoryPlatformRepository())
    app = FastAPI()
    app.include_router(build_iam_router(identity), prefix="/api/v1")
    app.include_router(build_author_router(author), prefix="/writer/api/v1")
    app.include_router(build_platform_router(platform), prefix="/admin/api/v1")
    client = TestClient(app)

    created = client.post("/api/v1/iam/accounts", json={"phone": "13800138000"})
    assert created.status_code == 201
    assert set(created.json()) == {"account_id", "identity_id", "phone"}

    profile = client.post(
        "/writer/api/v1/author/profiles",
        json={"account_id": created.json()["account_id"], "pen_name": "星河"},
    )
    assert profile.status_code == 201
    assert set(profile.json()) == {"id", "account_id", "pen_name", "normalized_pen_name"}

    staff = client.post(
        "/admin/api/v1/platform/staff",
        json={"employee_code": "employee-1", "department": "editorial"},
    )
    assert staff.status_code == 201
    assert set(staff.json()) == {"id", "employee_code", "department", "status"}

    denied = client.post(
        "/admin/api/v1/platform/access/check",
        json={
            "staff_id": staff.json()["id"],
            "permission": "author.read",
            "scope_type": "department",
            "scope_value": "editorial",
        },
    )
    assert denied.status_code == 403
