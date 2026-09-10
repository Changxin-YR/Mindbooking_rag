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


def test_sandbox_payment_simulation_uses_provider_callback_chain_and_ownership() -> None:
    client = TestClient(create_app())
    account = _register(client, "13800138009")
    token = _login(client, "13800138009")
    headers = {"Authorization": f"Bearer {token}"}
    assert (
        client.post(
            f"/api/v1/iam/accounts/{account}/real-name",
            json={"name": "张三", "identity_document": "11010119900101001X"},
            headers=headers,
        ).status_code
        == 201
    )
    recharge = client.post(
        "/api/v1/recharge",
        json={"account_id": account, "product_code": "RECHARGE_100", "channel": "SANDBOX"},
        headers={**headers, "Idempotency-Key": "sandbox-payment-1"},
    )
    assert recharge.status_code == 200
    payment_no = recharge.json()["payment_no"]
    simulated = client.post(
        "/api/v1/recharge/sandbox/simulate",
        json={
            "account_id": account,
            "payment_no": payment_no,
            "status": "SUCCESS",
            "duplicate": True,
        },
        headers=headers,
    )
    assert simulated.status_code == 200
    assert simulated.json()["processed"] is True
    wallet = client.get("/api/v1/wallet", params={"account_id": account}, headers=headers)
    assert wallet.json()["recharge_coin"] == recharge.json()["recharge_coin"]

    other = _register(client, "13800138008")
    other_token = _login(client, "13800138008")
    forbidden = client.post(
        "/api/v1/recharge/sandbox/simulate",
        json={"account_id": other, "payment_no": payment_no, "status": "FAILED"},
        headers={"Authorization": f"Bearer {other_token}"},
    )
    assert forbidden.status_code == 403


def test_writer_can_list_own_settlements_for_withdrawal_context() -> None:
    client = TestClient(create_app())
    account = _register(client, "13800138007")
    token = _login(client, "13800138007")
    headers = {"Authorization": f"Bearer {token}"}
    profile = client.post(
        "/writer/api/v1/author/profiles",
        json={"account_id": account, "pen_name": "结算作者"},
        headers=headers,
    )
    assert profile.status_code == 201
    author_id = profile.json()["id"]
    service = client.app.state.author_finance_service
    created = service.settle(author_id, "2026-09")

    response = client.get(
        "/writer/api/v1/finance/settlements",
        params={"author_id": author_id},
        headers=headers,
    )
    assert response.status_code == 200
    assert response.json() == [
        {
            "id": created.id,
            "author_id": author_id,
            "period": "2026-09",
            "amount_cents": 0,
            "status": "WITHDRAWABLE",
            "withdrawn_cents": 0,
            "gross_cents": 0,
            "tax_cents": 0,
        }
    ]


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


def test_notification_history_is_account_scoped_and_filterable() -> None:
    client = TestClient(create_app())
    account_a = _register(client, "13800138020")
    account_b = _register(client, "13800138021")
    token_a = _login(client, "13800138020")
    headers_a = {"Authorization": f"Bearer {token_a}"}
    payload = {
        "account_id": account_a,
        "category": "SYSTEM",
        "priority": "NORMAL",
        "channels": ["IN_APP"],
    }
    assert client.post("/api/v1/notifications", json=payload, headers=headers_a).status_code == 201
    assert (
        client.post(
            "/api/v1/notifications",
            json={**payload, "category": "SECURITY", "priority": "P0"},
            headers=headers_a,
        ).status_code
        == 201
    )

    own = client.get(
        "/api/v1/notifications",
        params={"account_id": account_a, "category": "SECURITY"},
        headers=headers_a,
    )
    assert own.status_code == 200
    assert len(own.json()) == 1
    assert own.json()[0]["category"] == "SECURITY"
    assert (
        client.get(
            "/api/v1/notifications", params={"account_id": account_b}, headers=headers_a
        ).status_code
        == 403
    )
    assert (
        client.get(
            "/api/v1/notifications", params={"account_id": account_a, "limit": 0}, headers=headers_a
        ).status_code
        == 422
    )

    created = client.post("/api/v1/notifications", json=payload, headers=headers_a).json()
    assert (
        client.get(
            "/api/v1/notifications/unread-count",
            params={"account_id": account_a},
            headers=headers_a,
        ).json()["unread_count"]
        == 3
    )
    marked = client.post(
        f"/api/v1/notifications/{created['id']}/read",
        json={"account_id": account_a},
        headers=headers_a,
    )
    assert marked.status_code == 200
    assert marked.json()["is_read"] is True
    assert (
        client.post(
            f"/api/v1/notifications/{created['id']}/read",
            json={"account_id": account_b},
            headers=headers_a,
        ).status_code
        == 403
    )


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


def test_writer_finance_contract_is_bound_to_book_author(monkeypatch) -> None:
    monkeypatch.setenv("STAFF_BOOTSTRAP_EMPLOYEE_CODE", "ops-finance-book-bound")
    monkeypatch.setenv("STAFF_BOOTSTRAP_PASSWORD", "StaffPassword#123")
    client = TestClient(create_app())
    account_a = _register(client, "13800138034")
    account_b = _register(client, "13800138035")
    token_a = _login(client, "13800138034")
    token_b = _login(client, "13800138035")
    profile_a = client.post(
        "/writer/api/v1/author/profiles",
        json={"account_id": account_a, "pen_name": "合同作者A"},
        headers={"Authorization": f"Bearer {token_a}"},
    )
    profile_b = client.post(
        "/writer/api/v1/author/profiles",
        json={"account_id": account_b, "pen_name": "合同作者B"},
        headers={"Authorization": f"Bearer {token_b}"},
    )
    assert profile_a.status_code == 201
    assert profile_b.status_code == 201
    other_book = client.app.state.content_service.create_book(profile_b.json()["id"], "他人作品")

    response = client.post(
        "/writer/api/v1/finance/contracts",
        json={"author_id": profile_a.json()["id"], "book_id": other_book.id},
        headers={"Authorization": f"Bearer {token_a}"},
    )

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "AUTHOR_BOOK_ACCESS_DENIED"


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


def test_admin_finance_mutations_require_domain_permissions(monkeypatch) -> None:
    monkeypatch.setenv("STAFF_BOOTSTRAP_EMPLOYEE_CODE", "ops-finance-permission-boundary")
    monkeypatch.setenv("STAFF_BOOTSTRAP_PASSWORD", "StaffPassword#123")
    client = TestClient(create_app())
    platform = client.app.state.platform
    staff = platform.create_staff("limited-finance", "editorial")
    client.app.state.staff_auth.set_password(staff.id, "StaffPassword#123")
    platform.grant_permission(staff.id, "admin.access")
    platform.grant_data_scope(staff.id, "ALL", "*")
    login = client.post(
        "/admin/api/v1/auth/staff/sessions",
        json={"employee_code": "limited-finance", "password": "StaffPassword#123"},
    )
    assert login.status_code == 200
    headers = {"Authorization": f"Bearer {login.json()['access_token']}"}

    denied = (
        (
            "/admin/api/v1/finance/contracts/missing/approve",
            {"actor_id": "forged-actor"},
        ),
        (
            "/admin/api/v1/finance/contracts/missing/activate",
            {"actor_id": "forged-actor"},
        ),
        (
            "/admin/api/v1/finance/revenue",
            {
                "author_id": "author-1",
                "source": "TEST",
                "source_ref": "permission-boundary",
                "gross_cents": 100,
            },
        ),
        (
            "/admin/api/v1/finance/revenue/missing/confirm",
            None,
        ),
        (
            "/admin/api/v1/finance/settlements",
            {"author_id": "author-1", "period": "2026-09"},
        ),
        (
            "/admin/api/v1/finance/chargebacks",
            {"source_ref": "missing", "amount_cents": 100},
        ),
        (
            "/api/v1/payouts/sandbox/simulate",
            {"payout_no": "missing"},
        ),
    )
    for path, payload in denied:
        response = client.post(path, json=payload, headers=headers)
        assert response.status_code == 403, (path, response.text)
        assert response.json()["error"]["code"] == "PERMISSION_DENIED"


def test_admin_contract_actions_require_approval_permission(monkeypatch) -> None:
    monkeypatch.setenv("STAFF_BOOTSTRAP_EMPLOYEE_CODE", "ops-contract-approval-boundary")
    monkeypatch.setenv("STAFF_BOOTSTRAP_PASSWORD", "StaffPassword#123")
    client = TestClient(create_app())
    platform = client.app.state.platform
    staff = platform.create_staff("finance-without-approval", "editorial")
    client.app.state.staff_auth.set_password(staff.id, "StaffPassword#123")
    platform.grant_permission(staff.id, "finance.write")
    platform.grant_data_scope(staff.id, "ALL", "*")
    login = client.post(
        "/admin/api/v1/auth/staff/sessions",
        json={
            "employee_code": "finance-without-approval",
            "password": "StaffPassword#123",
        },
    )
    assert login.status_code == 200
    headers = {"Authorization": f"Bearer {login.json()['access_token']}"}

    for path in (
        "/admin/api/v1/finance/contracts/missing/approve",
        "/admin/api/v1/finance/contracts/missing/activate",
    ):
        response = client.post(path, json={"actor_id": "forged-actor"}, headers=headers)
        assert response.status_code == 403, (path, response.text)
        assert response.json()["error"]["code"] == "PERMISSION_DENIED"


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


def test_author_center_funnel_binds_book_to_session_account() -> None:
    client = TestClient(create_app())
    _register(client, "13800138053")
    account_b = _register(client, "13800138054")
    token_a = _login(client, "13800138053")
    token_b = _login(client, "13800138054")
    author = client.post(
        "/writer/api/v1/author/profiles",
        json={"account_id": account_b, "pen_name": "漏斗边界"},
        headers={"Authorization": f"Bearer {token_b}"},
    ).json()
    book = client.post(
        "/writer/api/v1/books",
        json={"author_id": author["id"], "title": "漏斗作品"},
        headers={"Authorization": f"Bearer {token_b}"},
    ).json()

    response = client.post(
        f"/writer/api/v1/books/{book['id']}/chapters/chapter-1/funnel",
        json={
            "entrants": 100,
            "completion_bps": 7000,
            "next_chapter_bps": 4000,
            "subscription_bps": 1000,
        },
        headers={"Authorization": f"Bearer {token_a}"},
    )
    assert response.status_code == 403


def test_author_center_funnel_rejects_chapter_from_another_book() -> None:
    client = TestClient(create_app())
    account = _register(client, "13800138055")
    token = _login(client, "13800138055")
    headers = {"Authorization": f"Bearer {token}"}
    profile = client.post(
        "/writer/api/v1/author/profiles",
        json={"account_id": account, "pen_name": "章节归属"},
        headers=headers,
    ).json()
    first_book = client.post(
        "/writer/api/v1/books",
        json={"author_id": profile["id"], "title": "第一本"},
        headers=headers,
    ).json()
    second_book = client.post(
        "/writer/api/v1/books",
        json={"author_id": profile["id"], "title": "第二本"},
        headers=headers,
    ).json()
    volume = client.post(
        f"/writer/api/v1/books/{second_book['id']}/volumes",
        json={"title": "第二卷", "number": 1},
        headers=headers,
    ).json()
    chapter = client.post(
        f"/writer/api/v1/volumes/{volume['id']}/chapters",
        json={"title": "第二本第一章", "number": 1},
        headers=headers,
    ).json()

    response = client.post(
        f"/writer/api/v1/books/{first_book['id']}/chapters/{chapter['id']}/funnel",
        json={
            "entrants": 100,
            "completion_bps": 7000,
            "next_chapter_bps": 4000,
            "subscription_bps": 1000,
        },
        headers=headers,
    )
    assert response.status_code == 404


def test_author_center_task_progress_rejects_mismatched_path_author() -> None:
    client = TestClient(create_app())
    account = _register(client, "13800138056")
    token = _login(client, "13800138056")
    headers = {"Authorization": f"Bearer {token}"}
    profile = client.post(
        "/writer/api/v1/author/profiles",
        json={"account_id": account, "pen_name": "任务归属"},
        headers=headers,
    ).json()
    # The service is used here to create a valid task without widening the writer API surface.
    task = client.app.state.author_center_service.create_task("TASK-BOUNDARY", "任务", 1)
    response = client.post(
        f"/writer/api/v1/authors/another-author/tasks/{task.id}/progress",
        json={"author_id": profile["id"], "progress": 1, "idempotency_key": "path-mismatch"},
        headers=headers,
    )
    assert response.status_code == 403


def test_author_center_admin_writes_require_staff_session() -> None:
    client = TestClient(create_app())
    response = client.post(
        "/admin/api/v1/author-tasks/",
        json={"code": "TASK", "title": "任务", "target": 1},
    )
    assert response.status_code == 401


def test_author_center_admin_writes_require_operation_permission(monkeypatch) -> None:
    monkeypatch.setenv("STAFF_BOOTSTRAP_EMPLOYEE_CODE", "ops-author-center-permission")
    monkeypatch.setenv("STAFF_BOOTSTRAP_PASSWORD", "StaffPassword#123")
    client = TestClient(create_app())
    platform = client.app.state.platform
    staff = platform.create_staff("limited-author-center", "editorial")
    client.app.state.staff_auth.set_password(staff.id, "StaffPassword#123")
    platform.grant_permission(staff.id, "admin.access")
    platform.grant_data_scope(staff.id, "ALL", "*")
    login = client.post(
        "/admin/api/v1/auth/staff/sessions",
        json={"employee_code": "limited-author-center", "password": "StaffPassword#123"},
    )
    assert login.status_code == 200
    response = client.post(
        "/admin/api/v1/author-tasks",
        json={"code": "TASK", "title": "任务", "target": 1},
        headers={"Authorization": f"Bearer {login.json()['access_token']}"},
    )
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "PERMISSION_DENIED"


def test_author_center_admin_writes_accept_operation_role_without_admin_access(monkeypatch) -> None:
    monkeypatch.setenv("STAFF_BOOTSTRAP_EMPLOYEE_CODE", "ops-author-center-role")
    monkeypatch.setenv("STAFF_BOOTSTRAP_PASSWORD", "StaffPassword#123")
    client = TestClient(create_app())
    platform = client.app.state.platform
    staff = platform.create_staff("operation-author-center", "editorial")
    client.app.state.staff_auth.set_password(staff.id, "StaffPassword#123")
    platform.grant_permission(staff.id, "operation.write")
    platform.grant_data_scope(staff.id, "ALL", "*")
    login = client.post(
        "/admin/api/v1/auth/staff/sessions",
        json={"employee_code": "operation-author-center", "password": "StaffPassword#123"},
    )
    assert login.status_code == 200
    response = client.post(
        "/admin/api/v1/author-tasks/",
        json={"code": "TASK", "title": "任务", "target": 1},
        headers={"Authorization": f"Bearer {login.json()['access_token']}"},
    )
    assert response.status_code == 201


def test_admin_center_rule_writes_require_review_permission(monkeypatch) -> None:
    monkeypatch.setenv("STAFF_BOOTSTRAP_EMPLOYEE_CODE", "ops-admin-center-permission")
    monkeypatch.setenv("STAFF_BOOTSTRAP_PASSWORD", "StaffPassword#123")
    client = TestClient(create_app())
    platform = client.app.state.platform
    staff = platform.create_staff("limited-admin-center", "editorial")
    client.app.state.staff_auth.set_password(staff.id, "StaffPassword#123")
    platform.grant_permission(staff.id, "admin.access")
    platform.grant_data_scope(staff.id, "ALL", "*")
    login = client.post(
        "/admin/api/v1/auth/staff/sessions",
        json={"employee_code": "limited-admin-center", "password": "StaffPassword#123"},
    )
    assert login.status_code == 200
    response = client.post(
        "/admin/api/v1/review-rules",
        json={
            "code": "SPAM",
            "severity": "MEDIUM",
            "recommended_action": "HOLD",
            "auto_block_policy": False,
            "subject_types": ["COMMENT"],
            "version": "2026-09",
        },
        headers={"Authorization": f"Bearer {login.json()['access_token']}"},
    )
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "PERMISSION_DENIED"


def test_admin_center_rule_writes_accept_governance_role_without_admin_access(monkeypatch) -> None:
    monkeypatch.setenv("STAFF_BOOTSTRAP_EMPLOYEE_CODE", "ops-admin-center-role")
    monkeypatch.setenv("STAFF_BOOTSTRAP_PASSWORD", "StaffPassword#123")
    client = TestClient(create_app())
    platform = client.app.state.platform
    staff = platform.create_staff("governance-admin-center", "editorial")
    client.app.state.staff_auth.set_password(staff.id, "StaffPassword#123")
    platform.grant_permission(staff.id, "governance.write")
    platform.grant_data_scope(staff.id, "ALL", "*")
    login = client.post(
        "/admin/api/v1/auth/staff/sessions",
        json={"employee_code": "governance-admin-center", "password": "StaffPassword#123"},
    )
    assert login.status_code == 200
    response = client.post(
        "/admin/api/v1/review-rules",
        json={
            "code": "SPAM",
            "severity": "MEDIUM",
            "recommended_action": "HOLD",
            "auto_block_policy": False,
            "subject_types": ["COMMENT"],
            "version": "2026-09",
        },
        headers={"Authorization": f"Bearer {login.json()['access_token']}"},
    )
    assert response.status_code == 201


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


def test_invoice_mutations_use_finance_permission(monkeypatch) -> None:
    monkeypatch.setenv("STAFF_BOOTSTRAP_EMPLOYEE_CODE", "ops-invoice-permission")
    monkeypatch.setenv("STAFF_BOOTSTRAP_PASSWORD", "StaffPassword#123")
    client = TestClient(create_app())
    platform = client.app.state.platform

    finance_staff = platform.create_staff("invoice-finance-only", "editorial")
    client.app.state.staff_auth.set_password(finance_staff.id, "StaffPassword#123")
    platform.grant_permission(finance_staff.id, "finance.write")
    platform.grant_data_scope(finance_staff.id, "ALL", "*")

    governance_staff = platform.create_staff("invoice-governance-only", "editorial")
    client.app.state.staff_auth.set_password(governance_staff.id, "StaffPassword#123")
    platform.grant_permission(governance_staff.id, "governance.write")
    platform.grant_data_scope(governance_staff.id, "ALL", "*")

    def login(employee_code: str) -> dict[str, str]:
        response = client.post(
            "/admin/api/v1/auth/staff/sessions",
            json={"employee_code": employee_code, "password": "StaffPassword#123"},
        )
        assert response.status_code == 200
        return {"Authorization": f"Bearer {response.json()['access_token']}"}

    finance_headers = login("invoice-finance-only")
    governance_headers = login("invoice-governance-only")
    for action in ("issue", "reverse"):
        path = f"/admin/api/v1/invoices/missing/{action}"
        payload = {"document_id": f"invoice-{action}"}
        assert client.post(path, json=payload, headers=finance_headers).status_code == 404
        denied = client.post(path, json=payload, headers=governance_headers)
        assert denied.status_code == 403
        assert denied.json()["error"]["code"] == "PERMISSION_DENIED"
