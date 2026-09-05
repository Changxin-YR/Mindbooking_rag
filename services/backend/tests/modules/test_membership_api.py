from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient

from novel_platform.main import create_app
from novel_platform.modules.membership.api import build_membership_router


def test_membership_status_requires_account_session_and_returns_state() -> None:
    client = TestClient(create_app())
    registered = client.post(
        "/api/v1/iam/accounts",
        json={"phone": "13800138999", "password": "Correct#123"},
    ).json()
    account_id = registered["account_id"]
    token = client.post(
        "/api/v1/iam/sessions",
        json={"phone": "13800138999", "password": "Correct#123"},
    ).json()["access_token"]

    assert (
        client.get("/api/v1/membership/status", params={"account_id": account_id}).status_code
        == 401
    )
    response = client.get(
        "/api/v1/membership/status",
        params={"account_id": account_id},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    assert response.json() == {"account_id": account_id, "active": False}


def test_membership_admin_payload_name_is_forwarded_without_invoke_collision(monkeypatch) -> None:
    class MembershipRecorder:
        def __init__(self) -> None:
            self.plan: dict[str, object] = {}
            self.gift: dict[str, object] = {}

        def create_plan(self, **payload: object) -> SimpleNamespace:
            self.plan = payload
            return SimpleNamespace(status="ACTIVE", **payload)

        def register_gift(self, **payload: object) -> SimpleNamespace:
            self.gift = payload
            return SimpleNamespace(status="ACTIVE", **payload)

    service = MembershipRecorder()
    app = FastAPI()
    app.include_router(build_membership_router(service))
    monkeypatch.setattr(
        "novel_platform.modules.membership.api.require_staff_session",
        lambda request: None,
    )
    client = TestClient(app)

    plan = client.post(
        "/admin/api/v1/membership/plans",
        json={
            "plan_code": "TEST_MONTHLY",
            "name": "测试会员",
            "duration_days": 30,
            "daily_recommend_tickets": 2,
            "monthly_chapter_tickets": 5,
            "price_cents": 999,
        },
    )
    assert plan.status_code == 201, plan.text
    assert plan.json()["name"] == "测试会员"
    assert service.plan["name"] == "测试会员"

    gift = client.post(
        "/admin/api/v1/gifts",
        json={
            "gift_code": "TEST_LAMP",
            "name": "测试明灯",
            "price_coin": 50,
            "fan_value": 8,
        },
    )
    assert gift.status_code == 201, gift.text
    assert gift.json()["name"] == "测试明灯"
    assert service.gift["name"] == "测试明灯"
