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
