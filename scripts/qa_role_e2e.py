"""Exercise every documented role against the running API and web shells."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import struct
from dataclasses import dataclass
from time import time
from typing import Any
from uuid import uuid4

from playwright.sync_api import sync_playwright

API_URL = os.environ.get("API_BASE_URL", "http://127.0.0.1:8000").rstrip("/")
WEB_URL = os.environ.get("WEB_BASE_URL", "http://127.0.0.1:8080").rstrip("/")
STAFF_PASSWORD = os.environ.get("STAFF_BOOTSTRAP_PASSWORD", "QaAdmin#123456")
STAFF_CODE = os.environ.get("STAFF_BOOTSTRAP_EMPLOYEE_CODE", "qa-admin")


@dataclass(frozen=True)
class StaffIdentity:
    code: str
    department: str
    permissions: tuple[str, ...]


def _assert(response: Any, *codes: int) -> dict[str, Any]:
    if response.status not in codes:
        raise AssertionError(
            f"unexpected response status {response.status}: {response.text()}"
        )
    if response.status == 204:
        return {}
    return response.json()


def _totp_code(secret: str, counter: int | None = None) -> str:
    raw = base64.b32decode(secret + "=" * ((8 - len(secret) % 8) % 8), casefold=True)
    moving = int(time()) // 30 if counter is None else counter
    digest = hmac.new(raw, struct.pack(">Q", moving), hashlib.sha1).digest()
    offset = digest[-1] & 0x0F
    value = (
        struct.unpack(">I", digest[offset : offset + 4])[0] & 0x7FFFFFFF
    ) % 1_000_000
    return str(value).zfill(6)


def _staff_login(
    api: Any, identity: StaffIdentity, bootstrap: dict[str, str]
) -> tuple[str, str]:
    response = api.post(
        "/admin/api/v1/platform/staff",
        headers=bootstrap,
        data={"employee_code": identity.code, "department": identity.department},
    )
    body = _assert(response, 201)
    staff_id = body["id"]
    _assert(
        api.post(
            f"/admin/api/v1/auth/staff/credentials/{staff_id}",
            headers=bootstrap,
            data={"password": STAFF_PASSWORD},
        ),
        204,
    )
    for permission in identity.permissions:
        _assert(
            api.post(
                f"/admin/api/v1/platform/staff/{staff_id}/permissions",
                headers=bootstrap,
                data={"permission": permission},
            ),
            204,
        )
    _assert(
        api.post(
            f"/admin/api/v1/platform/staff/{staff_id}/data-scopes",
            headers=bootstrap,
            data={"scope_type": "ALL", "scope_value": "*"},
        ),
        204,
    )
    otp = None
    if identity.department.lower().replace("-", "_") in {
        "finance",
        "risk",
        "admin",
        "security",
        "super_admin",
    }:
        factor = _assert(
            api.post(
                f"/admin/api/v1/auth/staff/mfa/totp/{staff_id}", headers=bootstrap
            ),
            200,
        )
        otp = _totp_code(factor["secret"])
    login = _assert(
        api.post(
            "/admin/api/v1/auth/staff/sessions",
            data={
                "employee_code": identity.code,
                "password": STAFF_PASSWORD,
                **({"otp": otp} if otp else {}),
            },
        ),
        200,
    )
    return f"Bearer {login['access_token']}", login["staff_id"]


def main() -> None:
    suffix = uuid4().hex[:12]
    identity_suffix = f"{int(suffix, 16) % 10_000_000:07d}"
    identities = (
        StaffIdentity(
            f"qa-reviewer-{suffix}", "reviewer", ("review.read", "review.decide")
        ),
        StaffIdentity(
            f"qa-operator-{suffix}", "operation", ("operation.read", "operation.write")
        ),
        StaffIdentity(
            f"qa-finance-{suffix}",
            "finance",
            ("finance.read", "finance.write", "approval.write"),
        ),
        StaffIdentity(f"qa-risk-{suffix}", "risk", ("risk.read", "risk.write")),
        StaffIdentity(
            f"qa-admin-role-{suffix}", "admin", ("admin.access", "review.read")
        ),
        StaffIdentity(
            f"qa-super-admin-{suffix}",
            "super_admin",
            (
                "platform.manage",
                "admin.access",
                "agent.execute",
                "agent.audit.read",
                "content.read",
            ),
        ),
    )
    with sync_playwright() as playwright:
        api = playwright.request.new_context(base_url=API_URL)
        browser = playwright.chromium.launch(headless=True)
        try:
            _assert(api.get("/health/ready"), 200)
            bootstrap_login = _assert(
                api.post(
                    "/admin/api/v1/auth/staff/sessions",
                    data={"employee_code": STAFF_CODE, "password": STAFF_PASSWORD},
                ),
                200,
            )
            bootstrap = {"Authorization": f"Bearer {bootstrap_login['access_token']}"}

            phone = f"139{int(time() * 1000) % 100_000_000:08d}"
            account = _assert(
                api.post(
                    "/api/v1/iam/accounts",
                    data={"phone": phone, "password": "Correct#123"},
                ),
                201,
            )
            account_id = account["account_id"]
            reader_login = _assert(
                api.post(
                    "/api/v1/iam/sessions",
                    data={"phone": phone, "password": "Correct#123"},
                ),
                200,
            )
            reader = {"Authorization": f"Bearer {reader_login['access_token']}"}
            _assert(api.get("/api/v1/search?q=", headers=reader), 200)
            _assert(
                api.get(
                    "/api/v1/wallet", params={"account_id": account_id}, headers=reader
                ),
                200,
            )
            _assert(
                api.post("/admin/api/v1/reviews", headers=reader), 401, 403, 404, 405
            )
            _assert(
                api.post(
                    f"/api/v1/iam/accounts/{account_id}/real-name",
                    headers=reader,
                    data={
                        "name": "验收读者",
                        "identity_document": f"1101011990{identity_suffix}1",
                    },
                ),
                201,
            )

            profile = _assert(
                api.post(
                    "/writer/api/v1/author/profiles",
                    headers=reader,
                    data={
                        "account_id": account_id,
                        "pen_name": f"角色验收{phone[-4:]}",
                    },
                ),
                201,
            )
            author_id = profile["id"]
            book = _assert(
                api.post(
                    "/writer/api/v1/books",
                    headers=reader,
                    data={
                        "author_id": author_id,
                        "title": "角色验收作品",
                        "synopsis": "角色链路",
                    },
                ),
                201,
            )
            contract = _assert(
                api.post(
                    "/writer/api/v1/finance/contracts",
                    headers=reader,
                    data={"author_id": author_id, "book_id": book["id"]},
                ),
                201,
            )

            role_tokens: dict[str, str] = {}
            role_staff_ids: dict[str, str] = {}
            for identity in identities:
                token, staff_id = _staff_login(api, identity, bootstrap)
                role_tokens[identity.department] = token
                role_staff_ids[identity.department] = staff_id
            reviewer = {"Authorization": role_tokens["reviewer"]}
            operator = {"Authorization": role_tokens["operation"]}
            finance = {"Authorization": role_tokens["finance"]}
            risk = {"Authorization": role_tokens["risk"]}
            admin = {"Authorization": role_tokens["admin"]}
            super_admin = {"Authorization": role_tokens["super_admin"]}

            contract_id = contract["id"]
            _assert(
                api.post(
                    f"/admin/api/v1/finance/contracts/{contract_id}/approve",
                    headers=bootstrap,
                    data={"actor_id": "role-maker-checker"},
                ),
                200,
            )
            signed_contract = _assert(
                api.post(
                    f"/writer/api/v1/finance/contracts/{contract_id}/sign",
                    headers=reader,
                ),
                200,
            )
            if not signed_contract.get("signature_hash"):
                raise AssertionError("author contract signature was not persisted")
            active_contract = _assert(
                api.post(
                    f"/admin/api/v1/finance/contracts/{contract_id}/activate",
                    headers=bootstrap,
                    data={"actor_id": "role-activator"},
                ),
                200,
            )
            if active_contract.get("status") != "ACTIVE":
                raise AssertionError("signed author contract did not activate")
            _assert(
                api.get(
                    f"/writer/api/v1/finance/contracts/{contract_id}", headers=reader
                ),
                200,
            )

            _assert(
                api.post(
                    "/admin/api/v1/platform/access/check",
                    headers=bootstrap,
                    data={
                        "staff_id": role_staff_ids["super_admin"],
                        "permission": "agent.execute",
                        "scope_type": "ALL",
                        "scope_value": "*",
                    },
                ),
                204,
            )

            _assert(api.get("/admin/api/v1/reviews", headers=reviewer), 200)
            _assert(api.get("/admin/api/v1/review-rules", headers=operator), 403)
            _assert(
                api.post(
                    "/admin/api/v1/operation/rankings",
                    headers=operator,
                    data={
                        "book_ids": [book["id"]],
                        "kind": "ALGORITHM",
                        "scores": [1],
                        "snapshot_id": "role",
                    },
                ),
                201,
            )
            _assert(
                api.post(
                    "/admin/api/v1/operation/rankings",
                    headers=reviewer,
                    data={
                        "book_ids": [book["id"]],
                        "kind": "ALGORITHM",
                        "scores": [1],
                        "snapshot_id": "role-denied",
                    },
                ),
                403,
            )
            _assert(
                api.post(
                    "/admin/api/v1/finance/revenue",
                    headers=finance,
                    data={
                        "author_id": author_id,
                        "source": "ROLE_E2E",
                        "source_ref": f"role-{suffix}",
                        "gross_cents": 1,
                        "share_bps": 7000,
                    },
                ),
                201,
            )
            _assert(
                api.post(
                    "/admin/api/v1/risk/login-signals",
                    headers=risk,
                    data={
                        "account_id": account_id,
                        "device_id": "role-device",
                        "browser": "Chromium",
                        "operating_system": "Windows",
                        "ip": "198.51.100.40",
                        "region": "CN",
                        "user_agent": "role-e2e",
                    },
                ),
                201,
            )
            _assert(api.get("/admin/api/v1/review-rules", headers=admin), 200)
            _assert(
                api.get("/admin/api/v1/agent/resources", headers=super_admin),
                200,
            )
            catalog = _assert(api.get("/api/v1/books"), 200)
            public_book_id = catalog["items"][0]["id"]
            agent_result = _assert(
                api.post(
                    "/admin/api/v1/agent/tools/execute",
                    headers=super_admin,
                    data={
                        "agent_id": "role-agent",
                        "actor_id": role_staff_ids["super_admin"],
                        "tool_name": "content.get_book",
                        "arguments": {"book_id": public_book_id},
                    },
                ),
                200,
            )
            if agent_result.get("tool_name") != "content.get_book":
                raise AssertionError(
                    "agent tool result did not identify the requested tool"
                )

            for path, storage_key, marker in (
                ("/", "reader-web-session", "墨页"),
                ("/writer/", "writer-web-session", "墨页"),
                ("/admin/", "admin_access_token", "墨页"),
            ):
                page = browser.new_page()
                if storage_key in {"reader-web-session", "writer-web-session"}:
                    value = json.dumps(
                        {"token": reader_login["access_token"], "accountId": account_id}
                    )
                    page.add_init_script(
                        f"localStorage.setItem({json.dumps(storage_key)}, {json.dumps(value)});"
                    )
                else:
                    page.add_init_script(
                        f"localStorage.setItem({json.dumps(storage_key)}, {json.dumps(role_tokens['admin'].split('Bearer ', 1)[1])});"
                    )
                page.goto(f"{WEB_URL}{path}", wait_until="networkidle")
                if marker not in page.locator("body").inner_text():
                    raise AssertionError(f"{path} missing marker {marker!r}")
                page.close()
            print(
                json.dumps(
                    {
                        "status": "PASS",
                        "roles": [
                            "Guest",
                            "Reader",
                            "VerifiedReader",
                            "Author",
                            "SignedAuthor",
                            "Reviewer",
                            "Operator",
                            "Finance",
                            "Risk",
                            "Admin",
                            "SuperAdmin",
                        ],
                    },
                    ensure_ascii=False,
                )
            )
        finally:
            api.dispose()
            browser.close()


if __name__ == "__main__":
    main()
