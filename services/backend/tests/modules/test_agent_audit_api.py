from datetime import UTC, datetime

from fastapi import FastAPI, HTTPException, status
from fastapi.testclient import TestClient

from novel_platform.core.auth import SessionClaims, SessionSigner
from novel_platform.modules.agent.api import (
    AgentAudit,
    ToolResource,
    build_agent_admin_router,
    build_agent_gateway_router,
)
from novel_platform.modules.agent.application import AgentGateway, InMemoryAgentAuditLog


def _audit(
    event_id: str,
    *,
    actor_id: str = "staff-1",
    tool_name: str = "content.get_book",
    outcome: str = "SUCCESS",
) -> AgentAudit:
    return AgentAudit(
        id=event_id,
        agent_id="agent-1",
        actor_id=actor_id,
        tool_name=tool_name,
        permission="content.read",
        outcome=outcome,
        occurred_at=datetime(2026, 1, 1, tzinfo=UTC),
        arguments={"book_id": "book-secret"},
        result_summary="tool_result_returned",
    )


def _app(
    sink: InMemoryAgentAuditLog,
    *,
    authorize_staff=None,
) -> tuple[TestClient, SessionSigner]:
    app = FastAPI()
    signer = SessionSigner("agent-audit-test-secret", ttl_seconds=3600)
    app.state.session_signer = signer
    app.include_router(
        build_agent_admin_router(
            sink,
            auth_required=True,
            authorize_staff=authorize_staff,
        )
    )
    return TestClient(app), signer


def test_agent_audit_admin_list_requires_staff_session() -> None:
    client, _ = _app(InMemoryAgentAuditLog(), authorize_staff=lambda *_: None)

    response = client.get("/admin/api/v1/agent/audits")

    assert response.status_code == status.HTTP_401_UNAUTHORIZED


def test_agent_audit_admin_list_requires_agent_audit_permission() -> None:
    def deny(_: SessionClaims, permission: str) -> None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"code": "PERMISSION_DENIED", "permission": permission},
        )

    client, signer = _app(InMemoryAgentAuditLog(), authorize_staff=deny)

    response = client.get(
        "/admin/api/v1/agent/audits",
        headers={"Authorization": f"Bearer {signer.issue_staff('staff-1')}"},
    )

    assert response.status_code == status.HTTP_403_FORBIDDEN
    assert response.json()["detail"]["permission"] == "agent.audit.read"


def test_agent_audit_admin_list_filters_paginates_and_hides_arguments() -> None:
    sink = InMemoryAgentAuditLog()
    sink.append(_audit("evt-1", actor_id="staff-1", tool_name="content.get_book"))
    sink.append(_audit("evt-2", actor_id="staff-2", tool_name="wallet.read"))
    sink.append(_audit("evt-3", actor_id="staff-1", tool_name="wallet.read", outcome="FAILED"))

    client, signer = _app(sink, authorize_staff=lambda *_: None)
    response = client.get(
        "/admin/api/v1/agent/audits?actor=staff-1&tool=wallet.read&outcome=FAILED&page=1&page_size=10",
        headers={"Authorization": f"Bearer {signer.issue_staff('staff-1')}"},
    )

    assert response.status_code == status.HTTP_200_OK
    body = response.json()
    assert body["total"] == 1
    assert body["page"] == 1
    assert body["page_size"] == 10
    assert [item["id"] for item in body["items"]] == ["evt-3"]
    assert body["items"][0]["arguments"] is None


def test_agent_audit_admin_list_can_return_arguments_with_sensitive_permission() -> None:
    sink = InMemoryAgentAuditLog()
    sink.append(_audit("evt-1"))
    requested: list[str] = []

    def authorize(_: SessionClaims, permission: str) -> None:
        requested.append(permission)

    client, signer = _app(sink, authorize_staff=authorize)
    response = client.get(
        "/admin/api/v1/agent/audits?include_arguments=true",
        headers={"Authorization": f"Bearer {signer.issue_staff('staff-1')}"},
    )

    assert response.status_code == status.HTTP_200_OK
    assert requested == ["agent.audit.read", "agent.audit.sensitive"]
    assert response.json()["items"][0]["arguments"] == {"book_id": "book-secret"}


def test_agent_gateway_lists_resources_and_executes_with_bound_staff_actor() -> None:
    class Permissions:
        def has_permission(self, actor_id: str, permission: str) -> bool:
            return actor_id == "staff-1" and permission == "content.read"

    gateway = AgentGateway(Permissions(), audit_sink=InMemoryAgentAuditLog())
    gateway.register(
        ToolResource(
            name="content.get_book",
            description="Read a public book",
            permission="content.read",
        ),
        lambda args: {"book_id": args["book_id"]},
    )
    app = FastAPI()
    signer = SessionSigner("agent-gateway-test-secret", ttl_seconds=3600)
    app.state.session_signer = signer
    app.include_router(
        build_agent_gateway_router(
            gateway,
            auth_required=True,
            authorize_staff=lambda *_: None,
        )
    )
    client = TestClient(app)
    headers = {"Authorization": f"Bearer {signer.issue_staff('staff-1')}"}

    resources = client.get("/admin/api/v1/agent/resources", headers=headers)
    assert resources.status_code == status.HTTP_200_OK
    assert resources.json()["items"][0]["name"] == "content.get_book"

    executed = client.post(
        "/admin/api/v1/agent/tools/execute",
        headers=headers,
        json={
            "agent_id": "agent-1",
            "actor_id": "staff-1",
            "tool_name": "content.get_book",
            "arguments": {"book_id": "book-1"},
        },
    )
    assert executed.status_code == status.HTTP_200_OK
    assert executed.json()["data"] == {"book_id": "book-1"}


def test_agent_gateway_rejects_spoofed_actor_and_denied_permission() -> None:
    class Permissions:
        def has_permission(self, actor_id: str, permission: str) -> bool:
            return False

    gateway = AgentGateway(Permissions(), audit_sink=InMemoryAgentAuditLog())
    gateway.register(
        ToolResource(name="content.get_book", description="Read", permission="content.read"),
        lambda _: {"ok": True},
    )
    app = FastAPI()
    signer = SessionSigner("agent-gateway-deny-test-secret", ttl_seconds=3600)
    app.state.session_signer = signer
    app.include_router(
        build_agent_gateway_router(
            gateway,
            auth_required=True,
            authorize_staff=lambda *_: None,
        )
    )
    client = TestClient(app)
    headers = {"Authorization": f"Bearer {signer.issue_staff('staff-1')}"}
    spoofed = client.post(
        "/admin/api/v1/agent/tools/execute",
        headers=headers,
        json={
            "agent_id": "agent-1",
            "actor_id": "staff-2",
            "tool_name": "content.get_book",
        },
    )
    assert spoofed.status_code == status.HTTP_403_FORBIDDEN
    assert spoofed.json()["detail"]["code"] == "AGENT_ACTOR_MISMATCH"

    denied = client.post(
        "/admin/api/v1/agent/tools/execute",
        headers=headers,
        json={
            "agent_id": "agent-1",
            "actor_id": "staff-1",
            "tool_name": "content.get_book",
        },
    )
    assert denied.status_code == status.HTTP_403_FORBIDDEN
