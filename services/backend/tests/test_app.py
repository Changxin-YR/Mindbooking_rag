import pytest
from fastapi.testclient import TestClient

from novel_platform.main import create_app
from novel_platform.modules.admin_center.application import AdminCenterService
from novel_platform.modules.approval.application import ApprovalService
from novel_platform.modules.author_center.application import AuthorCenterService
from novel_platform.modules.author_finance.application import AuthorFinanceService
from novel_platform.modules.commerce.application import CommerceService
from novel_platform.modules.commerce.refund import RefundService
from novel_platform.modules.community.application import CommunityService
from novel_platform.modules.content.application import ContentService
from novel_platform.modules.copyright.application import CopyrightService
from novel_platform.modules.governance.application import GovernanceService
from novel_platform.modules.governance.worker import OutboxWorker
from novel_platform.modules.legal.application import LegalService
from novel_platform.modules.library.application import LibraryService
from novel_platform.modules.notification.application import NotificationService
from novel_platform.modules.operation.application import OperationService
from novel_platform.modules.reader_experience.application import ReaderExperienceService
from novel_platform.modules.reading.application import ReadingService
from novel_platform.modules.review.application import ReviewService
from novel_platform.modules.risk.application import RiskService
from novel_platform.modules.support.application import SupportService
from novel_platform.modules.wallet.application import WalletService


def _staff_headers(client: TestClient) -> dict[str, str]:
    response = client.post(
        "/admin/api/v1/auth/staff/sessions",
        json={"employee_code": "ops-test", "password": "StaffPassword#123"},
    )
    assert response.status_code == 200
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def test_live_health_returns_request_context_and_public_api_routes() -> None:
    client = TestClient(create_app())

    response = client.get("/api/v1/health/live")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
    assert response.headers["x-request-id"]
    assert response.headers["x-trace-id"]


def test_create_app_registers_runtime_outbox_worker() -> None:
    app = create_app()

    assert isinstance(app.state.outbox_worker, OutboxWorker)
    assert app.state.outbox_worker.worker_id


def test_runtime_outbox_worker_handles_core_commercial_events() -> None:
    app = create_app()

    assert {
        "ContractCreated",
        "ContractActivated",
        "RechargeOrderCreated",
        "RechargeCredited",
        "EntitlementCreated",
    } <= set(app.state.outbox_worker.handlers)


def test_unknown_route_returns_snake_case_error_dto() -> None:
    response = TestClient(create_app()).get("/writer/api/v1/missing")

    assert response.status_code == 401


def test_create_app_mounts_reader_writer_and_admin_domain_routes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("STAFF_BOOTSTRAP_EMPLOYEE_CODE", "ops-test")
    monkeypatch.setenv("STAFF_BOOTSTRAP_PASSWORD", "StaffPassword#123")
    client = TestClient(create_app())
    account = client.post(
        "/api/v1/iam/accounts",
        json={"phone": "13800138021", "password": "Correct#123"},
    ).json()["account_id"]
    token = client.post(
        "/api/v1/iam/sessions",
        json={"phone": "13800138021", "password": "Correct#123"},
    ).json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    assert (
        client.post(
            f"/api/v1/iam/accounts/{account}/real-name",
            json={"name": "测试用户", "identity_document": "11010119900101001X"},
            headers=headers,
        ).status_code
        == 201
    )
    author_id = client.post(
        "/writer/api/v1/author/profiles",
        json={"account_id": account, "pen_name": "测试作者"},
        headers=headers,
    ).json()["id"]

    assert (
        client.get("/api/v1/wallet", params={"account_id": account}, headers=headers).status_code
        == 200
    )
    assert client.get("/api/v1/books/unknown").status_code == 404
    assert (
        client.post(
            "/writer/api/v1/books",
            json={"author_id": author_id, "title": "测试书"},
            headers=headers,
        ).status_code
        == 201
    )
    assert client.get("/admin/api/v1/reviews", headers=_staff_headers(client)).status_code == 200
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


def test_sandbox_provider_checkout_and_signed_event_use_recharge_callback_path(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("PAYMENT_CALLBACK_SECRET", "sandbox-callback-secret")
    client = TestClient(create_app())
    account = client.post(
        "/api/v1/iam/accounts",
        json={"phone": "13800138023", "password": "Correct#123"},
    ).json()["account_id"]
    token = client.post(
        "/api/v1/iam/sessions",
        json={"phone": "13800138023", "password": "Correct#123"},
    ).json()["access_token"]
    headers = {"Authorization": f"Bearer {token}", "Idempotency-Key": "sandbox-recharge-1"}
    assert (
        client.post(
            f"/api/v1/iam/accounts/{account}/real-name",
            json={"name": "支付测试", "identity_document": "11010119900101002X"},
            headers={"Authorization": f"Bearer {token}"},
        ).status_code
        == 201
    )
    recharge = client.post(
        "/api/v1/recharge",
        json={"account_id": account, "product_code": "RECHARGE_100", "channel": "SANDBOX"},
        headers=headers,
    )
    assert recharge.status_code == 200
    assert recharge.json()["checkout_url"]
    provider = client.app.state.commerce_service.payment_provider
    event = provider.generate_callback_event(recharge.json()["payment_no"])
    callback = client.post(
        "/api/v1/recharge/provider-callback",
        json={
            "provider": event.provider,
            "event_type": event.event_type,
            "event_id": event.event_id,
            "reference_id": event.reference_id,
            "provider_transaction_id": event.provider_transaction_id,
            "status": event.status.value,
            "amount_cents": event.amount_cents,
            "currency": event.currency,
            "occurred_at": event.occurred_at.isoformat(),
            "available_at": event.available_at.isoformat(),
            "signature": event.signature,
        },
    )
    assert callback.status_code == 200
    assert callback.json()["status"] == "PAID"


def test_sql_mode_wires_durable_domain_adapters(monkeypatch: pytest.MonkeyPatch) -> None:
    import novel_platform.main as main_module

    class MarkerContent(ContentService):
        pass

    class MarkerWallet(WalletService):
        pass

    class MarkerCommerce(CommerceService):
        def __init__(self, wallet, is_real_named=None) -> None:
            super().__init__(wallet, is_real_named)

    class MarkerReading(ReadingService):
        pass

    class MarkerLibrary(LibraryService):
        pass

    class MarkerReview(ReviewService):
        pass

    class MarkerCommunity(CommunityService):
        pass

    class MarkerNotification(NotificationService):
        pass

    class MarkerSupport(SupportService):
        pass

    class MarkerApproval(ApprovalService):
        pass

    class MarkerAuthorFinance(AuthorFinanceService):
        pass

    class MarkerRisk(RiskService):
        pass

    class MarkerOperation(OperationService):
        pass

    class MarkerAuthorCenter(AuthorCenterService):
        pass

    class MarkerReaderExperience(ReaderExperienceService):
        pass

    class MarkerAdminCenter(AdminCenterService):
        pass

    class MarkerCopyright(CopyrightService):
        pass

    class MarkerLegal(LegalService):
        pass

    class MarkerGovernance(GovernanceService):
        pass

    class MarkerAgentAuditSink:
        def append(self, audit) -> None:
            pass

        def reload(self):
            return ()

    class MarkerRefund(RefundService):
        def __init__(self) -> None:
            pass

    monkeypatch.setenv("PERSISTENCE_MODE", "sql")
    monkeypatch.setenv("SESSION_SECRET", "test-session-secret")
    monkeypatch.setattr(main_module, "get_engine", lambda _: object())
    monkeypatch.setattr(main_module, "SqlAuthorRepository", lambda engine: object())
    monkeypatch.setattr(main_module, "SqlContentService", lambda engine: MarkerContent())
    monkeypatch.setattr(main_module, "SqlReadingService", lambda engine: MarkerReading())
    monkeypatch.setattr(main_module, "SqlLibraryService", lambda engine: MarkerLibrary())
    monkeypatch.setattr(
        main_module,
        "SqlReviewService",
        lambda engine, content: MarkerReview(content),
    )
    monkeypatch.setattr(main_module, "SqlCommunityService", lambda engine: MarkerCommunity())
    monkeypatch.setattr(main_module, "SqlNotificationService", lambda engine: MarkerNotification())
    monkeypatch.setattr(main_module, "SqlSupportService", lambda engine: MarkerSupport())
    monkeypatch.setattr(main_module, "SqlApprovalService", lambda engine: MarkerApproval())
    monkeypatch.setattr(
        main_module, "SqlAuthorFinanceService", lambda engine: MarkerAuthorFinance()
    )
    monkeypatch.setattr(main_module, "SqlRiskService", lambda engine: MarkerRisk())
    monkeypatch.setattr(main_module, "SqlOperationService", lambda engine: MarkerOperation())
    monkeypatch.setattr(
        main_module,
        "SqlAuthorCenterService",
        lambda engine, operation: MarkerAuthorCenter(operation),
    )
    monkeypatch.setattr(
        main_module, "SqlReaderExperienceService", lambda engine: MarkerReaderExperience()
    )
    monkeypatch.setattr(main_module, "SqlAdminCenterService", lambda engine: MarkerAdminCenter())
    monkeypatch.setattr(main_module, "SqlCopyrightService", lambda engine: MarkerCopyright())
    monkeypatch.setattr(main_module, "SqlLegalService", lambda engine: MarkerLegal())
    monkeypatch.setattr(main_module, "SqlGovernanceService", lambda engine: MarkerGovernance())
    monkeypatch.setattr(main_module, "SqlAgentAuditSink", lambda engine: MarkerAgentAuditSink())
    monkeypatch.setattr(main_module, "SqlRefundService", lambda *args, **kwargs: MarkerRefund())
    monkeypatch.setattr(main_module, "SqlWalletService", lambda engine: MarkerWallet())
    monkeypatch.setattr(
        main_module,
        "SqlCommerceService",
        lambda engine, wallet, is_real_named: MarkerCommerce(wallet, is_real_named),
    )

    app = create_app()

    assert isinstance(app.state.content_service, MarkerContent)
    assert isinstance(app.state.reading_service, MarkerReading)
    assert isinstance(app.state.library_service, MarkerLibrary)
    assert isinstance(app.state.review_service, MarkerReview)
    assert isinstance(app.state.community_service, MarkerCommunity)
    assert isinstance(app.state.notification_service, MarkerNotification)
    assert isinstance(app.state.support_service, MarkerSupport)
    assert isinstance(app.state.approval_service, MarkerApproval)
    assert isinstance(app.state.author_finance_service, MarkerAuthorFinance)
    assert isinstance(app.state.risk_service, MarkerRisk)
    assert isinstance(app.state.operation_service, MarkerOperation)
    assert isinstance(app.state.author_center_service, MarkerAuthorCenter)
    assert isinstance(app.state.reader_experience_service, MarkerReaderExperience)
    assert isinstance(app.state.admin_center_service, MarkerAdminCenter)
    assert isinstance(app.state.copyright_service, MarkerCopyright)
    assert isinstance(app.state.legal_service, MarkerLegal)
    assert isinstance(app.state.governance_service, MarkerGovernance)
    assert isinstance(app.state.agent_audit_sink, MarkerAgentAuditSink)
    assert isinstance(app.state.refund_service, MarkerRefund)
    assert isinstance(app.state.wallet_service, MarkerWallet)
    assert isinstance(app.state.commerce_service, MarkerCommerce)


def test_create_app_wires_named_sandbox_channels(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PERSISTENCE_MODE", "memory")
    monkeypatch.setenv("PAYMENT_PROVIDER", "SANDBOX_ALIPAY")
    monkeypatch.setenv("PAYOUT_PROVIDER", "SANDBOX_BANK")
    app = create_app()

    assert app.state.commerce_service.payment_provider.provider_name == "SANDBOX_ALIPAY"
    assert app.state.author_finance_service.payout_provider.provider_name == "SANDBOX_BANK"


def test_create_app_mounts_governance_finance_operation_and_legal_routes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("STAFF_BOOTSTRAP_EMPLOYEE_CODE", "ops-test")
    monkeypatch.setenv("STAFF_BOOTSTRAP_PASSWORD", "StaffPassword#123")
    client = TestClient(create_app())
    account = client.post(
        "/api/v1/iam/accounts",
        json={"phone": "13800138022", "password": "Correct#123"},
    ).json()["account_id"]
    token = client.post(
        "/api/v1/iam/sessions",
        json={"phone": "13800138022", "password": "Correct#123"},
    ).json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    staff_headers = _staff_headers(client)

    report = client.post(
        "/api/v1/community/report-cases",
        json={
            "content_type": "BOOK",
            "content_id": "book-1",
            "reporter_id": account,
            "reason": "spam",
        },
        headers=headers,
    )
    assert report.status_code == 201
    notification = client.post(
        "/api/v1/notifications",
        json={
            "account_id": account,
            "category": "SECURITY",
            "priority": "P0",
            "channels": ["IN_APP"],
        },
        headers=headers,
    )
    assert notification.status_code == 201
    assert notification.json()["channels"] == ["IN_APP", "SMS"]

    approval = client.post(
        "/admin/api/v1/approvals",
        json={"action": "PAYOUT", "requester_id": "maker", "critical": False},
        headers=staff_headers,
    )
    assert approval.status_code == 201
    decision = client.post(
        f"/admin/api/v1/approvals/{approval.json()['id']}/decision",
        json={"approver_id": "checker", "decision": "REJECT"},
        headers=staff_headers,
    )
    assert decision.status_code == 200
    assert decision.json()["status"] == "REJECTED"

    profile = client.post(
        "/writer/api/v1/author/profiles",
        json={"account_id": account, "pen_name": "后台财务作者"},
        headers=headers,
    )
    assert profile.status_code == 201
    book = client.post(
        "/writer/api/v1/books",
        json={
            "author_id": profile.json()["id"],
            "title": "后台财务作品",
            "synopsis": "用于路由挂载测试",
        },
        headers=headers,
    )
    assert book.status_code == 201
    book_id = book.json()["id"]
    contract = client.post(
        "/writer/api/v1/finance/contracts",
        json={"author_id": profile.json()["id"], "book_id": book_id},
        headers=headers,
    )
    assert contract.status_code == 201
    assert contract.json()["policy_version"] == "SANDBOX_CN_2026_V1"
    assert "SANDBOX_CN_2026_V1" in contract.json()["document_text"]
    fetched_contract = client.get(
        f"/writer/api/v1/finance/contracts/{contract.json()['id']}", headers=headers
    )
    assert fetched_contract.status_code == 200
    assert fetched_contract.json()["document_hash"] == contract.json()["document_hash"]
    contract_inbox = client.get(
        "/admin/api/v1/finance/contracts",
        params={"author_id": profile.json()["id"], "status": "DRAFT"},
        headers=staff_headers,
    )
    assert contract_inbox.status_code == 200
    assert [item["id"] for item in contract_inbox.json()] == [contract.json()["id"]]
    assert (
        client.post(
            "/admin/api/v1/operation/rankings",
            json={
                "book_ids": ["b1", "b2"],
                "kind": "ALGORITHM",
                "scores": [1, 2],
                "snapshot_id": "s1",
            },
            headers=staff_headers,
        ).status_code
        == 201
    )
    dossier = client.post(
        "/admin/api/v1/copyright/dossiers", json={"book_id": "book-1"}, headers=staff_headers
    )
    assert dossier.status_code == 201
    legal = client.post(
        "/admin/api/v1/legal/cases", json={"subject": "book-1"}, headers=staff_headers
    )
    assert legal.status_code == 201
