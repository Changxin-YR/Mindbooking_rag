"""Run the durable author-to-payout sandbox flow against a running API."""

import argparse
import os
import sys
from datetime import UTC, datetime
from pathlib import Path
from time import time

# Keep the smoke command runnable from a clean checkout without an external
# PYTHONPATH export.
_backend_src = Path(__file__).resolve().parents[1] / "services" / "backend" / "src"
if str(_backend_src) not in sys.path:
    sys.path.insert(0, str(_backend_src))

from novel_platform.modules.payment import build_payment_provider
from playwright.sync_api import APIRequestContext, sync_playwright


def _json(response, expected: int | tuple[int, ...]):
    expected_statuses = (expected,) if isinstance(expected, int) else expected
    assert response.status in expected_statuses, response.text()
    return response.json()


def _token(api: APIRequestContext, phone: str, password: str) -> str:
    return _json(
        api.post("/api/v1/iam/sessions", data={"phone": phone, "password": password}),
        200,
    )["access_token"]


def _staff_token(api: APIRequestContext, employee_code: str, password: str) -> str:
    return _json(
        api.post(
            "/admin/api/v1/auth/staff/sessions",
            data={"employee_code": employee_code, "password": password},
        ),
        200,
    )["access_token"]


def _provision_finance_checker(
    api: APIRequestContext, bootstrap_headers: dict[str, str], suffix: str
) -> dict[str, str]:
    """Create and authorize a distinct finance checker through platform APIs."""
    employee_code = f"qa-finance-{suffix}"
    password = "QaFinance#123456"
    staff = _json(
        api.post(
            "/admin/api/v1/platform/staff",
            headers=bootstrap_headers,
            data={"employee_code": employee_code, "department": "platform"},
        ),
        201,
    )
    _json(
        api.post(
            f"/admin/api/v1/platform/staff/{staff['id']}/status",
            headers=bootstrap_headers,
            data={"status": "ACTIVE"},
        ),
        200,
    )
    permission_response = api.post(
        f"/admin/api/v1/platform/staff/{staff['id']}/permissions",
        headers=bootstrap_headers,
        data={"permission": "finance.write"},
    )
    assert permission_response.status == 204, permission_response.text()
    scope_response = api.post(
        f"/admin/api/v1/platform/staff/{staff['id']}/data-scopes",
        headers=bootstrap_headers,
        data={"scope_type": "ALL", "scope_value": "*"},
    )
    assert scope_response.status == 204, scope_response.text()
    credential_response = api.post(
        f"/admin/api/v1/auth/staff/credentials/{staff['id']}",
        headers=bootstrap_headers,
        data={"password": password},
    )
    assert credential_response.status == 204, credential_response.text()
    return {"Authorization": f"Bearer {_staff_token(api, employee_code, password)}"}


def _real_name(
    api: APIRequestContext, account_id: str, token: str, document: str
) -> None:
    _json(
        api.post(
            f"/api/v1/iam/accounts/{account_id}/real-name",
            headers={"Authorization": f"Bearer {token}"},
            data={"name": "SQL验收实名", "identity_document": document},
        ),
        201,
    )


def _event_payload(event) -> dict[str, object]:
    return {
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
    }


def run(
    api: APIRequestContext, payment_secret: str, staff_code: str, staff_password: str
) -> None:
    suffix = str(int(time() * 1000))[-8:]
    password = "Correct#123"
    author_phone = f"139{suffix}"
    reader_phone = f"138{suffix}"
    author_account = _json(
        api.post(
            "/api/v1/iam/accounts", data={"phone": author_phone, "password": password}
        ),
        201,
    )["account_id"]
    author_token = _token(api, author_phone, password)
    _real_name(api, author_account, author_token, f"11010119900101{suffix[-3:]}1")
    author = _json(
        api.post(
            "/writer/api/v1/author/profiles",
            headers={"Authorization": f"Bearer {author_token}"},
            data={"account_id": author_account, "pen_name": f"SQL作者{suffix}"},
        ),
        201,
    )
    author_id = author["id"]
    book = _json(
        api.post(
            "/writer/api/v1/books",
            headers={"Authorization": f"Bearer {author_token}"},
            data={
                "author_id": author_id,
                "title": f"SQL商业闭环{suffix}",
                "synopsis": "验收",
            },
        ),
        201,
    )
    book_id = book["id"]
    volume = _json(
        api.post(
            f"/writer/api/v1/books/{book_id}/volumes",
            headers={"Authorization": f"Bearer {author_token}"},
            data={"number": 1, "title": "第一卷"},
        ),
        201,
    )
    chapter = _json(
        api.post(
            f"/writer/api/v1/volumes/{volume['id']}/chapters",
            headers={"Authorization": f"Bearer {author_token}"},
            data={"number": 1, "title": "VIP序章", "commercial_policy": "FREE"},
        ),
        201,
    )
    chapter_id = chapter["id"]
    draft = _json(
        api.post(
            f"/writer/api/v1/chapters/{chapter_id}/drafts",
            headers={"Authorization": f"Bearer {author_token}"},
            data={"content": "SQL商业闭环正文"},
        ),
        201,
    )
    version = _json(
        api.post(
            f"/writer/api/v1/chapters/{chapter_id}/versions",
            headers={"Authorization": f"Bearer {author_token}"},
            data={"snapshot_id": draft["id"]},
        ),
        201,
    )
    contract = _json(
        api.post(
            "/writer/api/v1/finance/contracts",
            headers={"Authorization": f"Bearer {author_token}"},
            data={"author_id": author_id, "book_id": book_id, "share_bps": 7000},
        ),
        201,
    )
    staff = _staff_token(api, staff_code, staff_password)
    staff_headers = {"Authorization": f"Bearer {staff}"}
    finance_headers = _provision_finance_checker(api, staff_headers, suffix)
    _json(
        api.post(
            f"/admin/api/v1/finance/contracts/{contract['id']}/approve",
            headers=staff_headers,
            data={"actor_id": "ignored"},
        ),
        200,
    )
    _json(
        api.post(
            f"/writer/api/v1/finance/contracts/{contract['id']}/sign",
            headers={"Authorization": f"Bearer {author_token}"},
        ),
        200,
    )
    _json(
        api.post(
            f"/admin/api/v1/finance/contracts/{contract['id']}/activate",
            headers=staff_headers,
            data={"actor_id": "ignored"},
        ),
        200,
    )
    submission = _json(
        api.post(
            f"/writer/api/v1/books/{book_id}/first-listing-submissions",
            headers={"Authorization": f"Bearer {author_token}"},
            data={"fixed_version_ids": [version["id"]]},
        ),
        201,
    )
    _json(
        api.post(
            f"/admin/api/v1/reviews/{submission['id']}/decisions",
            headers=staff_headers,
            data={"reviewer_id": "ignored", "decision": "APPROVE"},
        ),
        201,
    )
    _json(
        api.post(
            f"/admin/api/v1/chapters/{chapter_id}/commercial-policy",
            headers=staff_headers,
            data={"price_coin": 1500},
        ),
        200,
    )

    reader_account = _json(
        api.post(
            "/api/v1/iam/accounts", data={"phone": reader_phone, "password": password}
        ),
        201,
    )["account_id"]
    reader_token = _token(api, reader_phone, password)
    _real_name(api, reader_account, reader_token, f"11010119900101{suffix[-3:]}2")
    reader_headers = {"Authorization": f"Bearer {reader_token}"}
    payment_provider_name = (
        os.getenv("PAYMENT_PROVIDER", "SANDBOX_ALIPAY").strip().upper()
    )
    payment_provider = build_payment_provider(payment_provider_name, payment_secret)
    recharge = _json(
        api.post(
            "/api/v1/recharge",
            headers={**reader_headers, "Idempotency-Key": f"e2e-recharge-{suffix}"},
            data={
                "account_id": reader_account,
                "product_code": "RECHARGE_100",
                "channel": payment_provider_name,
            },
        ),
        200,
    )
    payment_provider.create_checkout(recharge["payment_no"], recharge["paid_cents"])
    payment_event = payment_provider.generate_callback_event(recharge["payment_no"])
    _json(
        api.post(
            "/api/v1/recharge/provider-callback", data=_event_payload(payment_event)
        ),
        200,
    )
    _json(
        api.post(
            "/api/v1/recharge/provider-callback", data=_event_payload(payment_event)
        ),
        200,
    )
    balance_before = _json(
        api.get(
            "/api/v1/wallet",
            params={"account_id": reader_account},
            headers=reader_headers,
        ),
        200,
    )["total_coin"]
    assert balance_before == 10_000
    purchase = _json(
        api.post(
            "/api/v1/purchases",
            headers=reader_headers,
            data={"account_id": reader_account, "chapter_id": chapter_id},
        ),
        200,
    )
    duplicate = _json(
        api.post(
            "/api/v1/purchases",
            headers=reader_headers,
            data={"account_id": reader_account, "chapter_id": chapter_id},
        ),
        200,
    )
    assert duplicate["purchase_no"] == purchase["purchase_no"]
    balance_after = _json(
        api.get(
            "/api/v1/wallet",
            params={"account_id": reader_account},
            headers=reader_headers,
        ),
        200,
    )["total_coin"]
    assert balance_after == 8_500

    revenue = _json(
        api.post(
            "/admin/api/v1/finance/revenue",
            headers=staff_headers,
            data={
                "author_id": author_id,
                "source": "CHAPTER_PURCHASE",
                "source_ref": purchase["purchase_no"],
                "gross_cents": 1500,
                "share_bps": 7000,
            },
        ),
        (200, 201),
    )
    _json(
        api.post(
            f"/admin/api/v1/finance/revenue/{revenue['id']}/confirm",
            headers=staff_headers,
        ),
        200,
    )
    settlement = _json(
        api.post(
            "/admin/api/v1/finance/settlements",
            headers=staff_headers,
            data={
                "author_id": author_id,
                "period": datetime.now(UTC).strftime("%Y-%m"),
            },
        ),
        201,
    )
    withdrawal = _json(
        api.post(
            f"/writer/api/v1/finance/settlements/{settlement['id']}/withdraw",
            headers={"Authorization": f"Bearer {author_token}"},
            data={
                "author_id": author_id,
                "amount_cents": 1050,
                "payout_method": f"bank:test-{suffix}",
                "holder_matches_real_name": True,
            },
        ),
        200,
    )
    _json(
        api.post(
            f"/admin/api/v1/finance/withdrawals/{withdrawal['id']}/risk-approve",
            headers=staff_headers,
            data={"actor_id": "ignored"},
        ),
        200,
    )
    payout = _json(
        api.post(
            f"/admin/api/v1/finance/withdrawals/{withdrawal['id']}/finance-approve",
            headers=finance_headers,
            data={"actor_id": "ignored"},
        ),
        200,
    )
    payout_simulation = _json(
        api.post(
            "/api/v1/payouts/sandbox/simulate",
            headers=staff_headers,
            data={
                "payout_no": payout["payout_no"],
                "status": "SUCCESS",
                "duplicate": True,
            },
        ),
        200,
    )
    assert payout_simulation["status"] == "SUCCESS"
    assert payout_simulation["processed"] is True
    assert payment_event.provider == payment_provider_name
    print(
        f"sql commercial e2e: ok account={reader_account} chapter={chapter_id} "
        f"purchase={purchase['purchase_no']} payout={payout['payout_no']}"
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--api", default=os.getenv("API_BASE_URL", "http://127.0.0.1:8000")
    )
    parser.add_argument(
        "--payment-secret",
        default=os.getenv(
            "PAYMENT_CALLBACK_SECRET", "development-only-payment-callback-secret"
        ),
    )
    parser.add_argument(
        "--staff-code", default=os.getenv("STAFF_BOOTSTRAP_EMPLOYEE_CODE", "qa-admin")
    )
    parser.add_argument(
        "--staff-password",
        default=os.getenv("STAFF_BOOTSTRAP_PASSWORD", "QaAdmin#123456"),
    )
    args = parser.parse_args()
    with sync_playwright() as playwright:
        api = playwright.request.new_context(base_url=args.api.rstrip("/"))
        try:
            run(api, args.payment_secret, args.staff_code, args.staff_password)
        finally:
            api.dispose()


if __name__ == "__main__":
    main()
