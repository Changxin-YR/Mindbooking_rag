from fastapi.testclient import TestClient

from novel_platform.main import create_app


def test_refund_requires_a_bearer_session_before_source_lookup() -> None:
    response = TestClient(create_app()).post(
        "/api/v1/refunds",
        json={"payment_no": "PAY-1", "recharge_no": "RECH-1", "refund_reference": "REF-1"},
    )

    assert response.status_code == 401
