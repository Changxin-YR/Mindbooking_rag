from fastapi.testclient import TestClient

from novel_platform.main import create_app


def _register(client: TestClient, phone: str) -> str:
    response = client.post(
        "/api/v1/iam/accounts",
        json={"phone": phone, "password": "Correct#123"},
    )
    assert response.status_code == 201
    return response.json()["account_id"]


def _login(client: TestClient, phone: str) -> str:
    response = client.post(
        "/api/v1/iam/sessions",
        json={"phone": phone, "password": "Correct#123"},
    )
    assert response.status_code == 200
    return response.json()["access_token"]


def test_wallet_requires_bearer_session_and_rejects_other_account() -> None:
    client = TestClient(create_app())
    account_a = _register(client, "13800138010")
    account_b = _register(client, "13800138011")
    token = _login(client, "13800138010")

    assert client.get("/api/v1/wallet", params={"account_id": account_a}).status_code == 401

    own = client.get(
        "/api/v1/wallet",
        params={"account_id": account_a},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert own.status_code == 200
    assert own.json()["account_id"] == account_a

    other = client.get(
        "/api/v1/wallet",
        params={"account_id": account_b},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert other.status_code == 403
    assert other.json()["error"]["code"] == "ACCOUNT_ACCESS_DENIED"


def test_reading_progress_is_bound_to_authenticated_account() -> None:
    client = TestClient(create_app())
    account = _register(client, "13800138012")
    token = _login(client, "13800138012")
    headers = {"Authorization": f"Bearer {token}"}

    missing = client.get("/api/v1/books/book-1/progress", params={"account_id": account})
    assert missing.status_code == 401

    response = client.get(
        "/api/v1/books/book-1/progress", params={"account_id": account}, headers=headers
    )
    assert response.status_code == 200
    assert response.json()["account_id"] == account


def test_sensitive_identity_mutations_require_own_session() -> None:
    client = TestClient(create_app())
    account_a = _register(client, "13800138013")
    account_b = _register(client, "13800138014")
    token = _login(client, "13800138013")
    payload = {"name": "张三", "identity_document": "11010119900101001X"}

    missing = client.post(f"/api/v1/iam/accounts/{account_a}/real-name", json=payload)
    assert missing.status_code == 401

    other = client.post(
        f"/api/v1/iam/accounts/{account_b}/real-name",
        json=payload,
        headers={"Authorization": f"Bearer {token}"},
    )
    assert other.status_code == 403
    assert other.json()["error"]["code"] == "ACCOUNT_ACCESS_DENIED"


def test_author_profile_creation_is_bound_to_session_account() -> None:
    client = TestClient(create_app())
    account_a = _register(client, "13800138015")
    account_b = _register(client, "13800138016")
    token = _login(client, "13800138015")
    headers = {"Authorization": f"Bearer {token}"}

    missing = client.post(
        "/writer/api/v1/author/profiles",
        json={"account_id": account_a, "pen_name": "星河"},
    )
    assert missing.status_code == 401

    other = client.post(
        "/writer/api/v1/author/profiles",
        json={"account_id": account_b, "pen_name": "长夜"},
        headers=headers,
    )
    assert other.status_code == 403

    own = client.post(
        "/writer/api/v1/author/profiles",
        json={"account_id": account_a, "pen_name": "星河"},
        headers=headers,
    )
    assert own.status_code == 201


def test_reader_account_actions_require_the_authenticated_account() -> None:
    client = TestClient(create_app())
    account_a = _register(client, "13800138017")
    account_b = _register(client, "13800138018")
    token = _login(client, "13800138017")
    headers = {"Authorization": f"Bearer {token}"}

    missing = client.post(
        "/api/v1/social/follows",
        json={"account_id": account_a, "target_type": "AUTHOR", "target_id": "author-1"},
    )
    assert missing.status_code == 401

    other = client.post(
        "/api/v1/social/follows",
        json={"account_id": account_b, "target_type": "AUTHOR", "target_id": "author-1"},
        headers=headers,
    )
    assert other.status_code == 403

    growth = client.get(f"/api/v1/accounts/{account_b}/growth", headers=headers)
    assert growth.status_code == 403


def test_support_and_notification_actions_require_the_authenticated_account() -> None:
    client = TestClient(create_app())
    account = _register(client, "13800138019")
    token = _login(client, "13800138019")
    headers = {"Authorization": f"Bearer {token}"}
    ticket_payload = {
        "account_id": account,
        "category": "ACCOUNT",
        "priority": "P2",
        "description": "无法修改资料",
    }

    assert client.post("/api/v1/support/tickets", json=ticket_payload).status_code == 401
    assert (
        client.post(
            "/api/v1/support/tickets",
            json=ticket_payload,
            headers=headers,
        ).status_code
        == 201
    )
    notification = {
        "account_id": account,
        "category": "SECURITY",
        "priority": "P0",
        "channels": ["IN_APP"],
    }
    assert client.post("/api/v1/notifications", json=notification).status_code == 401


def test_writer_content_is_bound_to_the_authenticated_author_account() -> None:
    client = TestClient(create_app())
    account_a = _register(client, "13800138023")
    _register(client, "13800138024")
    token_a = _login(client, "13800138023")
    token_b = _login(client, "13800138024")
    headers_a = {"Authorization": f"Bearer {token_a}"}
    headers_b = {"Authorization": f"Bearer {token_b}"}

    profile = client.post(
        "/writer/api/v1/author/profiles",
        json={"account_id": account_a, "pen_name": "远山"},
        headers=headers_a,
    )
    assert profile.status_code == 201
    author_id = profile.json()["id"]

    missing = client.post(
        "/writer/api/v1/books",
        json={"author_id": author_id, "title": "无 token 的书"},
    )
    assert missing.status_code == 401

    other = client.post(
        "/writer/api/v1/books",
        json={"author_id": author_id, "title": "越权的书"},
        headers=headers_b,
    )
    assert other.status_code == 403

    own = client.post(
        "/writer/api/v1/books",
        json={"author_id": author_id, "title": "远山的书"},
        headers=headers_a,
    )
    assert own.status_code == 201


def test_writer_and_admin_api_surfaces_require_a_bearer_session() -> None:
    client = TestClient(create_app())

    assert client.get("/writer/api/v1/authors/author-1/calendar").status_code == 401
    assert client.get("/admin/api/v1/reviews").status_code == 401


def test_cors_preflight_reaches_cors_middleware_before_private_auth(
    monkeypatch,
) -> None:
    monkeypatch.setenv("CORS_ORIGINS", "http://127.0.0.1:8080")
    response = TestClient(create_app()).options(
        "/writer/api/v1/author/profile",
        headers={
            "Origin": "http://127.0.0.1:8080",
            "Access-Control-Request-Method": "GET",
            "Access-Control-Request-Headers": "authorization",
        },
    )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "http://127.0.0.1:8080"


def test_governance_and_community_account_actions_require_a_bearer_session() -> None:
    client = TestClient(create_app())
    account = _register(client, "13800138030")
    token = _login(client, "13800138030")
    headers = {"Authorization": f"Bearer {token}"}

    privacy = {"account_id": account, "kind": "EXPORT"}
    assert client.post("/api/v1/privacy/requests", json=privacy).status_code == 401
    assert client.post("/api/v1/privacy/requests", json=privacy, headers=headers).status_code == 201

    report = {
        "content_type": "BOOK",
        "content_id": "book-1",
        "reporter_id": account,
        "reason": "spam",
    }
    assert client.post("/api/v1/community/report-cases", json=report).status_code == 401


def test_staff_session_cannot_access_writer_api(monkeypatch) -> None:
    monkeypatch.setenv("STAFF_BOOTSTRAP_EMPLOYEE_CODE", "ops-writer-bound")
    monkeypatch.setenv("STAFF_BOOTSTRAP_PASSWORD", "StaffPassword#123")
    client = TestClient(create_app())
    response = client.post(
        "/admin/api/v1/auth/staff/sessions",
        json={"employee_code": "ops-writer-bound", "password": "StaffPassword#123"},
    )
    assert response.status_code == 200
    writer = client.get(
        "/writer/api/v1/authors/author-1/calendar",
        headers={"Authorization": f"Bearer {response.json()['access_token']}"},
    )
    assert writer.status_code == 401


def test_writer_finance_is_bound_to_author_account(monkeypatch) -> None:
    monkeypatch.setenv("STAFF_BOOTSTRAP_EMPLOYEE_CODE", "ops-finance-bound")
    monkeypatch.setenv("STAFF_BOOTSTRAP_PASSWORD", "StaffPassword#123")
    client = TestClient(create_app())
    account_a = _register(client, "13800138031")
    _register(client, "13800138032")
    token_a = _login(client, "13800138031")
    token_b = _login(client, "13800138032")
    profile = client.post(
        "/writer/api/v1/author/profiles",
        json={"account_id": account_a, "pen_name": "财务归属"},
        headers={"Authorization": f"Bearer {token_a}"},
    )
    assert profile.status_code == 201

    response = client.post(
        "/writer/api/v1/finance/contracts",
        json={"author_id": profile.json()["id"], "book_id": "book-1"},
        headers={"Authorization": f"Bearer {token_b}"},
    )
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "ACCOUNT_ACCESS_DENIED"


def test_writer_withdrawal_uses_server_real_name_state(monkeypatch) -> None:
    monkeypatch.setenv("STAFF_BOOTSTRAP_EMPLOYEE_CODE", "ops-withdrawal")
    monkeypatch.setenv("STAFF_BOOTSTRAP_PASSWORD", "StaffPassword#123")
    client = TestClient(create_app())
    account = _register(client, "13800138033")
    token = _login(client, "13800138033")
    headers = {"Authorization": f"Bearer {token}"}
    profile = client.post(
        "/writer/api/v1/author/profiles",
        json={"account_id": account, "pen_name": "实名提现"},
        headers=headers,
    )
    assert profile.status_code == 201
    author_id = profile.json()["id"]
    service = client.app.state.author_finance_service
    revenue = service.record_revenue(author_id, "CHAPTER", "smoke-revenue", 10_000, 7000)
    service.confirm_revenue(revenue.id)
    settlement = service.settle(author_id, "2026-09")

    response = client.post(
        f"/writer/api/v1/finance/settlements/{settlement.id}/withdraw",
        json={
            "author_id": author_id,
            "amount_cents": 7000,
            "payout_method": "BANK",
            "holder_matches_real_name": True,
        },
        headers=headers,
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "HTTP_ERROR"
    assert response.json()["error"]["message"] == "PAYOUT_HOLDER_MISMATCH"


def test_admin_approval_uses_staff_session_identity(monkeypatch) -> None:
    monkeypatch.setenv("STAFF_BOOTSTRAP_EMPLOYEE_CODE", "ops-approval-bound")
    monkeypatch.setenv("STAFF_BOOTSTRAP_PASSWORD", "StaffPassword#123")
    client = TestClient(create_app())
    login = client.post(
        "/admin/api/v1/auth/staff/sessions",
        json={"employee_code": "ops-approval-bound", "password": "StaffPassword#123"},
    )
    assert login.status_code == 200
    headers = {"Authorization": f"Bearer {login.json()['access_token']}"}

    approval = client.post(
        "/admin/api/v1/approvals",
        json={"action": "PAYOUT", "requester_id": "forged-maker", "critical": True},
        headers=headers,
    )
    assert approval.status_code == 201
    assert approval.json()["requester_id"] != "forged-maker"

    decision = client.post(
        f"/admin/api/v1/approvals/{approval.json()['id']}/decision",
        json={"approver_id": "forged-checker", "decision": "APPROVE"},
        headers=headers,
    )
    assert decision.status_code == 409
    assert "requester cannot approve" in decision.json()["error"]["message"]


def test_support_mutations_require_staff_or_ticket_owner(monkeypatch) -> None:
    monkeypatch.setenv("STAFF_BOOTSTRAP_EMPLOYEE_CODE", "ops-support-boundary")
    monkeypatch.setenv("STAFF_BOOTSTRAP_PASSWORD", "StaffPassword#123")
    client = TestClient(create_app())
    account_a = _register(client, "13800138045")
    _register(client, "13800138046")
    token_a = _login(client, "13800138045")
    token_b = _login(client, "13800138046")
    ticket = client.post(
        "/api/v1/support/tickets",
        json={
            "account_id": account_a,
            "category": "ACCOUNT",
            "priority": "P2",
            "description": "需要人工处理",
        },
        headers={"Authorization": f"Bearer {token_a}"},
    ).json()

    ticket_id = ticket["id"]
    assert client.post(f"/api/v1/support/tickets/{ticket_id}/resolve").status_code == 401
    assert (
        client.post(
            f"/api/v1/support/tickets/{ticket_id}/replies",
            json={"body": "越权", "author": "STAFF"},
            headers={"Authorization": f"Bearer {token_b}"},
        ).status_code
        == 403
    )

    staff_token = client.post(
        "/admin/api/v1/auth/staff/sessions",
        json={"employee_code": "ops-support-boundary", "password": "StaffPassword#123"},
    ).json()["access_token"]
    assert (
        client.post(
            f"/api/v1/support/tickets/{ticket_id}/resolve",
            headers={"Authorization": f"Bearer {staff_token}"},
        ).status_code
        == 200
    )
    assert (
        client.post(
            f"/api/v1/support/tickets/{ticket_id}/replies",
            json={"body": "已处理", "author": "USER"},
            headers={"Authorization": f"Bearer {staff_token}"},
        ).status_code
        == 200
    )


def test_report_case_is_visible_only_to_its_reporter() -> None:
    client = TestClient(create_app())
    account_a = _register(client, "13800138047")
    _register(client, "13800138048")
    token_a = _login(client, "13800138047")
    token_b = _login(client, "13800138048")
    report = client.post(
        "/api/v1/community/report-cases",
        json={
            "content_type": "BOOK",
            "content_id": "book-private",
            "reporter_id": account_a,
            "reason": "违规内容",
        },
        headers={"Authorization": f"Bearer {token_a}"},
    )
    case_id = report.json()["id"]

    assert client.get(f"/api/v1/community/report-cases/{case_id}").status_code == 401
    assert (
        client.get(
            f"/api/v1/community/report-cases/{case_id}",
            headers={"Authorization": f"Bearer {token_b}"},
        ).status_code
        == 403
    )
    assert (
        client.get(
            f"/api/v1/community/report-cases/{case_id}",
            headers={"Authorization": f"Bearer {token_a}"},
        ).status_code
        == 200
    )


def test_author_center_routes_bind_author_id_to_session_account() -> None:
    client = TestClient(create_app())
    _register(client, "13800138049")
    account_b = _register(client, "13800138050")
    token_a = _login(client, "13800138049")
    token_b = _login(client, "13800138050")
    author = client.post(
        "/writer/api/v1/author/profiles",
        json={"account_id": account_b, "pen_name": "中心边界"},
        headers={"Authorization": f"Bearer {token_b}"},
    ).json()

    response = client.post(
        f"/writer/api/v1/authors/{author['id']}/writing-stats",
        json={"business_date": "2026-09-05", "words": 1000, "goal": 2000},
        headers={"Authorization": f"Bearer {token_a}"},
    )
    assert response.status_code == 403
    assert (
        client.post(
            f"/writer/api/v1/authors/{author['id']}/writing-stats",
            json={"business_date": "2026-09-05", "words": 1000, "goal": 2000},
            headers={"Authorization": f"Bearer {token_b}"},
        ).status_code
        == 201
    )


def test_phone_account_listing_requires_a_linked_authenticated_identity() -> None:
    client = TestClient(create_app())
    _register(client, "13800138051")
    _register(client, "13800138052")
    token_b = _login(client, "13800138052")

    assert client.get("/api/v1/iam/identities/phone/13800138051/accounts").status_code == 401
    assert (
        client.get(
            "/api/v1/iam/identities/phone/13800138051/accounts",
            headers={"Authorization": f"Bearer {token_b}"},
        ).status_code
        == 403
    )
