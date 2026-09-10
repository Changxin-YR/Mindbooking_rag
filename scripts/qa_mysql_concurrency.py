"""Exercise the payment callback idempotency path against a live MySQL-backed API.

This script intentionally uses the public HTTP contract and several independent
HTTP connections. It is a release-evidence check, not a unit-test substitute.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from time import time
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

_backend_src = Path(__file__).resolve().parents[1] / "services" / "backend" / "src"
if str(_backend_src) not in sys.path:
    sys.path.insert(0, str(_backend_src))

from novel_platform.modules.payment import build_payment_provider


def _request(
    base_url: str,
    method: str,
    path: str,
    *,
    payload=None,
    token: str | None = None,
    idempotency_key: str | None = None,
):
    body = (
        None
        if payload is None
        else json.dumps(payload, ensure_ascii=False).encode("utf-8")
    )
    headers = {"Accept": "application/json"}
    if body is not None:
        headers["Content-Type"] = "application/json"
    if token:
        headers["Authorization"] = f"Bearer {token}"
    if idempotency_key:
        headers["Idempotency-Key"] = idempotency_key
    request = Request(
        f"{base_url.rstrip('/')}{path}", data=body, headers=headers, method=method
    )
    try:
        with urlopen(request, timeout=15) as response:
            raw = response.read().decode("utf-8")
            return response.status, json.loads(raw) if raw else None
    except HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"{method} {path} -> HTTP {exc.code}: {detail}") from exc
    except URLError as exc:
        raise RuntimeError(
            f"{method} {path} -> connection failed: {exc.reason}"
        ) from exc


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


def run(base_url: str, payment_secret: str, concurrency: int) -> None:
    if concurrency < 2:
        raise ValueError("concurrency must be at least 2")
    if "sqlite" in os.getenv("DATABASE_URL", "").lower():
        raise RuntimeError("MYSQL_REQUIRED_FOR_CONCURRENCY_EVIDENCE")
    suffix = str(int(time() * 1000))[-9:]
    phone = f"137{suffix[-8:]}"
    password = "Concurrency#123"
    status, account = _request(
        base_url,
        "POST",
        "/api/v1/iam/accounts",
        payload={"phone": phone, "password": password},
    )
    if status != 201:
        raise RuntimeError(f"account creation expected 201, got {status}")
    account_id = str(account["account_id"])
    status, session = _request(
        base_url,
        "POST",
        "/api/v1/iam/sessions",
        payload={"phone": phone, "password": password},
    )
    if status != 200:
        raise RuntimeError(f"session creation expected 200, got {status}")
    token = str(session["access_token"])
    _request(
        base_url,
        "POST",
        f"/api/v1/iam/accounts/{account_id}/real-name",
        payload={
            "name": "并发验收",
            "identity_document": f"11010119900101{suffix[-3:]}1",
        },
        token=token,
    )
    status, recharge = _request(
        base_url,
        "POST",
        "/api/v1/recharge",
        payload={
            "account_id": account_id,
            "product_code": "RECHARGE_100",
            "channel": os.getenv("PAYMENT_PROVIDER", "SANDBOX_ALIPAY"),
        },
        token=token,
        idempotency_key=f"concurrency-recharge-{suffix}",
    )
    if status != 200:
        raise RuntimeError(f"recharge creation expected 200, got {status}")

    provider_name = os.getenv("PAYMENT_PROVIDER", "SANDBOX_ALIPAY").strip().upper()
    provider = build_payment_provider(provider_name, payment_secret)
    provider.create_checkout(str(recharge["payment_no"]), int(recharge["paid_cents"]))
    event = provider.generate_callback_event(str(recharge["payment_no"]))
    payload = _event_payload(event)

    def callback(_: int):
        status_code, result = _request(
            base_url, "POST", "/api/v1/recharge/provider-callback", payload=payload
        )
        if status_code != 200:
            raise RuntimeError(f"callback expected 200, got {status_code}: {result}")
        return result

    with ThreadPoolExecutor(max_workers=concurrency) as pool:
        results = list(pool.map(callback, range(concurrency)))
    if len({str(result["recharge_no"]) for result in results}) != 1:
        raise RuntimeError("duplicate callbacks returned different recharge orders")

    status, wallet = _request(
        base_url, "GET", f"/api/v1/wallet?account_id={account_id}", token=token
    )
    if status != 200 or int(wallet["total_coin"]) != int(recharge["recharge_coin"]):
        raise RuntimeError(f"wallet credit mismatch: {wallet}")
    print(
        json.dumps(
            {
                "status": "PASS",
                "database_requirement": "MYSQL",
                "concurrent_callbacks": concurrency,
                "account_id": account_id,
                "payment_no": recharge["payment_no"],
                "wallet_total_coin": wallet["total_coin"],
            },
            ensure_ascii=False,
        )
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
    parser.add_argument("--concurrency", type=int, default=8)
    args = parser.parse_args()
    run(args.api, args.payment_secret, args.concurrency)


if __name__ == "__main__":
    main()
