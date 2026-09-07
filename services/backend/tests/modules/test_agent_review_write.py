from fastapi.testclient import TestClient

from novel_platform.main import create_app
from novel_platform.modules.content.domain import CommercialPolicy


def _mcp_call(
    client: TestClient,
    headers: dict[str, str],
    *,
    name: str,
    arguments: dict[str, str],
) -> dict[str, object]:
    return client.post(
        "/admin/api/v1/agent/mcp",
        headers=headers,
        json={
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {"name": name, "arguments": arguments},
        },
    ).json()


def _pending_submission(client: TestClient, staff_id: str) -> str:
    app = client.app
    content = app.state.content_service
    review = app.state.review_service
    book = content.create_book("agent-review-author", "Agent review book")
    volume = content.create_volume(book.id, "Volume", 1)
    chapter = content.create_chapter(volume.id, "Chapter", CommercialPolicy.FREE)
    version = content.create_chapter_version(chapter.id, content.save_draft(chapter.id, "body").id)
    submission = review.submit_first_listing(book.id, [version.id])
    review.assign_submission(submission.id, staff_id)
    return submission.id


def _staff_headers(client: TestClient, employee_code: str, staff_id: str) -> dict[str, str]:
    app = client.app
    app.state.staff_auth.set_password(staff_id, "ReviewAgent#123")
    for permission in ("agent.execute", "review.read", "review.decide"):
        app.state.platform.grant_permission(staff_id, permission)
    app.state.platform.grant_data_scope(staff_id, "ASSIGNED", staff_id)
    login = client.post(
        "/admin/api/v1/auth/staff/sessions",
        json={"employee_code": employee_code, "password": "ReviewAgent#123"},
    )
    assert login.status_code == 200
    return {"Authorization": f"Bearer {login.json()['access_token']}"}


def test_agent_review_decision_executes_for_assigned_staff(monkeypatch) -> None:
    monkeypatch.setenv("PERSISTENCE_MODE", "memory")
    client = TestClient(create_app())
    staff = client.app.state.platform.create_staff("agent-reviewer", "review")
    headers = _staff_headers(client, "agent-reviewer", staff.id)
    submission_id = _pending_submission(client, staff.id)

    result = _mcp_call(
        client,
        headers,
        name="review.decide",
        arguments={"submission_id": submission_id, "decision": "APPROVE"},
    )

    assert result["result"]
    assert client.app.state.review_service.get_submission(submission_id).status.value == "APPROVED"


def test_agent_review_decision_rejects_unassigned_submission(monkeypatch) -> None:
    monkeypatch.setenv("PERSISTENCE_MODE", "memory")
    client = TestClient(create_app())
    assigned = client.app.state.platform.create_staff("assigned-reviewer", "review")
    denied = client.app.state.platform.create_staff("denied-reviewer", "review")
    headers = _staff_headers(client, "denied-reviewer", denied.id)
    submission_id = _pending_submission(client, assigned.id)

    result = _mcp_call(
        client,
        headers,
        name="review.decide",
        arguments={"submission_id": submission_id, "decision": "REJECT"},
    )

    assert result["error"]["code"] == -32003
    assert client.app.state.review_service.get_submission(submission_id).status.value == "PENDING"
