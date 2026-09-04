from fastapi.testclient import TestClient

from novel_platform.main import create_app


def test_live_health_returns_request_context_and_public_api_routes() -> None:
    client = TestClient(create_app())

    response = client.get("/api/v1/health/live")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
    assert response.headers["x-request-id"]
    assert response.headers["x-trace-id"]


def test_unknown_route_returns_snake_case_error_dto() -> None:
    response = TestClient(create_app()).get("/writer/api/v1/missing")

    assert response.status_code == 404
    assert set(response.json()) == {"error"}
    assert response.json()["error"]["code"] == "RESOURCE_NOT_FOUND"
    assert set(response.json()["error"]) == {
        "code",
        "message",
        "request_id",
        "trace_id",
    }


def test_create_app_mounts_reader_writer_and_admin_domain_routes() -> None:
    client = TestClient(create_app())

    assert client.get("/api/v1/wallet", params={"account_id": "acct-1"}).status_code == 200
    assert client.get("/api/v1/books/unknown").status_code == 404
    assert (
        client.post(
            "/writer/api/v1/books", json={"author_id": "author-1", "title": "测试书"}
        ).status_code
        == 201
    )
    assert client.get("/admin/api/v1/reviews").status_code == 200
    assert (
        client.post(
            "/api/v1/refunds",
            json={
                "payment_no": "PAY-missing",
                "recharge_no": "RECH-missing",
                "refund_reference": "REF-1",
            },
        ).status_code
        != 404
    )


def test_create_app_mounts_governance_finance_operation_and_legal_routes() -> None:
    client = TestClient(create_app())

    report = client.post(
        "/api/v1/community/report-cases",
        json={
            "content_type": "BOOK",
            "content_id": "book-1",
            "reporter_id": "u-1",
            "reason": "spam",
        },
    )
    assert report.status_code == 201
    notification = client.post(
        "/api/v1/notifications",
        json={
            "account_id": "u-1",
            "category": "SECURITY",
            "priority": "P0",
            "channels": ["IN_APP"],
        },
    )
    assert notification.status_code == 201
    assert notification.json()["channels"] == ["IN_APP", "SMS"]

    approval = client.post(
        "/admin/api/v1/approvals",
        json={"action": "PAYOUT", "requester_id": "maker", "critical": True},
    )
    assert approval.status_code == 201
    decision = client.post(
        f"/admin/api/v1/approvals/{approval.json()['id']}/decision",
        json={"approver_id": "checker", "decision": "REJECT"},
    )
    assert decision.status_code == 200
    assert decision.json()["status"] == "REJECTED"

    contract = client.post(
        "/writer/api/v1/finance/contracts", json={"author_id": "a-1", "book_id": "book-1"}
    )
    assert contract.status_code == 201
    assert (
        client.post(
            "/admin/api/v1/operation/rankings",
            json={
                "book_ids": ["b1", "b2"],
                "kind": "ALGORITHM",
                "scores": [1, 2],
                "snapshot_id": "s1",
            },
        ).status_code
        == 201
    )
    dossier = client.post("/admin/api/v1/copyright/dossiers", json={"book_id": "book-1"})
    assert dossier.status_code == 201
    legal = client.post("/admin/api/v1/legal/cases", json={"subject": "book-1"})
    assert legal.status_code == 201
