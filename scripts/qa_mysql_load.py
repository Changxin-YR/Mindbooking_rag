"""Bounded MySQL-backed smoke load; this is not a production capacity claim."""

from __future__ import annotations

import argparse
import json
import os
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from time import perf_counter, time
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

_backend_src = Path(__file__).resolve().parents[1] / "services" / "backend" / "src"
if str(_backend_src) not in sys.path:
    sys.path.insert(0, str(_backend_src))

from novel_platform.modules.payment import build_payment_provider


def request(
    base: str,
    method: str,
    path: str,
    *,
    payload=None,
    token: str | None = None,
    idem: str | None = None,
):
    body = None if payload is None else json.dumps(payload, ensure_ascii=False).encode()
    headers = {"Accept": "application/json"}
    if body is not None:
        headers["Content-Type"] = "application/json"
    if token:
        headers["Authorization"] = f"Bearer {token}"
    if idem:
        headers["Idempotency-Key"] = idem
    started = perf_counter()
    try:
        with urlopen(
            Request(
                f"{base.rstrip('/')}{path}", data=body, headers=headers, method=method
            ),
            timeout=15,
        ) as response:
            raw = response.read().decode()
            return (
                response.status,
                (json.loads(raw) if raw else None),
                perf_counter() - started,
            )
    except HTTPError as exc:
        raw = exc.read().decode(errors="replace")
        try:
            body = json.loads(raw)
        except json.JSONDecodeError:
            body = raw
        return exc.code, body, perf_counter() - started
    except URLError as exc:
        return 599, {"error": str(exc.reason)}, perf_counter() - started


def must(result, status: int):
    if result[0] != status:
        raise RuntimeError(f"expected HTTP {status}, got {result[0]}: {result[1]}")
    return result[1]


def event_payload(event):
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


def db_metrics(database_url: str) -> dict[str, int]:
    parsed = urlparse(database_url.replace("mysql+pymysql://", "mysql://", 1))
    if parsed.scheme != "mysql":
        raise RuntimeError("MYSQL_REQUIRED_FOR_LOAD")
    try:
        import pymysql
    except ImportError as exc:
        raise RuntimeError("pymysql is required for load evidence") from exc
    connection = pymysql.connect(
        host=parsed.hostname or "127.0.0.1",
        port=parsed.port or 3306,
        user=parsed.username,
        password=parsed.password,
        database=(parsed.path or "/").lstrip("/"),
        connect_timeout=5,
    )
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT COUNT(*) FROM wallet_accounts WHERE recharge_coin < 0 OR gift_coin < 0"
            )
            negative = int(cursor.fetchone()[0])
            cursor.execute(
                "SELECT COUNT(*) FROM (SELECT account_id, idempotency_key FROM wallet_journals WHERE idempotency_key IS NOT NULL GROUP BY account_id, idempotency_key HAVING COUNT(*) > 1) d"
            )
            duplicate = int(cursor.fetchone()[0])
        return {
            "negative_wallet_accounts": negative,
            "duplicate_wallet_idempotency_keys": duplicate,
        }
    finally:
        connection.close()


def run(
    base: str,
    database_url: str,
    concurrency: int,
    payment_secret: str,
    max_p95_ms: float,
    min_throughput_rps: float,
) -> None:
    if concurrency < 2 or concurrency > 32:
        raise ValueError("concurrency must be between 2 and 32")
    if not database_url.lower().startswith(("mysql://", "mysql+pymysql://")):
        raise RuntimeError("MYSQL_REQUIRED_FOR_LOAD")
    timings: list[float] = []
    statuses: list[int] = []
    suffix = str(int(time() * 1000))[-9:]
    password = "Load#Password123"
    phone = f"136{suffix[-8:]}"
    account = must(
        request(
            base,
            "POST",
            "/api/v1/iam/accounts",
            payload={"phone": phone, "password": password},
        ),
        201,
    )
    account_id = str(account["account_id"])
    token = str(
        must(
            request(
                base,
                "POST",
                "/api/v1/iam/sessions",
                payload={"phone": phone, "password": password},
            ),
            200,
        )["access_token"]
    )
    must(
        request(
            base,
            "POST",
            f"/api/v1/iam/accounts/{account_id}/real-name",
            token=token,
            payload={
                "name": "压测实名",
                "identity_document": f"11010119900101{suffix[-3:]}1",
            },
        ),
        201,
    )

    def hit(path: str):
        return request(base, "GET", path, token=token)

    def login_hit(_: int):
        return request(
            base,
            "POST",
            "/api/v1/iam/sessions",
            payload={"phone": phone, "password": password},
        )

    def wallet_hit(_: int):
        return request(
            base, "GET", f"/api/v1/wallet?account_id={account_id}", token=token
        )

    paths = ["/health/ready", "/api/v1/books", "/api/v1/rankings"] * concurrency
    benchmark_started = perf_counter()
    with ThreadPoolExecutor(max_workers=concurrency) as pool:
        auth_results = list(pool.map(login_hit, range(concurrency)))
        wallet_results = list(pool.map(wallet_hit, range(concurrency)))
        results = list(pool.map(hit, paths))
    benchmark_elapsed = perf_counter() - benchmark_started
    all_read_results = [*auth_results, *wallet_results, *results]
    if any(code != 200 for code, _, _ in all_read_results):
        raise RuntimeError(
            f"read/auth load had non-200 responses: {sorted({code for code, _, _ in all_read_results})}"
        )
    statuses.extend(code for code, _, _ in all_read_results)
    timings.extend(duration for _, _, duration in all_read_results)

    provider_name = os.getenv("PAYMENT_PROVIDER", "SANDBOX_ALIPAY").upper()
    recharge = must(
        request(
            base,
            "POST",
            "/api/v1/recharge",
            token=token,
            idem=f"load-recharge-{suffix}",
            payload={
                "account_id": account_id,
                "product_code": "RECHARGE_100",
                "channel": provider_name,
            },
        ),
        200,
    )
    provider = build_payment_provider(provider_name, payment_secret)
    provider.create_checkout(recharge["payment_no"], recharge["paid_cents"])
    event = provider.generate_callback_event(recharge["payment_no"])
    callback_payload = event_payload(event)
    with ThreadPoolExecutor(max_workers=concurrency) as pool:
        callbacks = list(
            pool.map(
                lambda _: request(
                    base,
                    "POST",
                    "/api/v1/recharge/provider-callback",
                    payload=callback_payload,
                ),
                range(concurrency),
            )
        )
    if any(code != 200 for code, _, _ in callbacks):
        raise RuntimeError(
            f"payment callback load failed: {sorted({code for code, _, _ in callbacks})}"
        )
    statuses.extend(code for code, _, _ in callbacks)
    timings.extend(duration for _, _, duration in callbacks)

    books = must(request(base, "GET", "/api/v1/books", token=token), 200).get(
        "items", []
    )
    chapter = None
    for book in books:
        detail = request(base, "GET", f"/api/v1/books/{book['id']}", token=token)
        if detail[0] == 200 and detail[1].get("chapters"):
            chapter = detail[1]["chapters"][0]
            break
    if chapter is None:
        raise RuntimeError("NO_PUBLISHED_CHAPTER_FOR_PURCHASE_LOAD")
    with ThreadPoolExecutor(max_workers=concurrency) as pool:
        purchases = list(
            pool.map(
                lambda _: request(
                    base,
                    "POST",
                    "/api/v1/purchases",
                    token=token,
                    payload={"account_id": account_id, "chapter_id": chapter["id"]},
                ),
                range(concurrency),
            )
        )
    if any(code != 200 for code, _, _ in purchases):
        failed = [(code, body) for code, body, _ in purchases if code != 200]
        raise RuntimeError(f"purchase load failed: {failed}")
    statuses.extend(code for code, _, _ in purchases)
    timings.extend(duration for _, _, duration in purchases)
    benchmark_elapsed = perf_counter() - benchmark_started
    purchase_nos = {str(body["purchase_no"]) for _, body, _ in purchases}
    if len(purchase_nos) != 1:
        raise RuntimeError(
            f"purchase idempotency returned multiple orders: {purchase_nos}"
        )
    metrics = db_metrics(database_url)
    if (
        metrics["negative_wallet_accounts"]
        or metrics["duplicate_wallet_idempotency_keys"]
    ):
        raise RuntimeError(f"financial invariant failed: {metrics}")
    sorted_timings = sorted(timings)
    p50 = sorted_timings[len(sorted_timings) // 2] if sorted_timings else 0.0
    p95 = (
        sorted_timings[max(0, int(len(sorted_timings) * 0.95) - 1)]
        if sorted_timings
        else 0.0
    )
    throughput_rps = len(statuses) / max(benchmark_elapsed, 0.001)
    if p95 * 1000 > max_p95_ms:
        raise RuntimeError(
            f"LOAD_P95_THRESHOLD_EXCEEDED:{p95 * 1000:.2f}ms>{max_p95_ms:.2f}ms"
        )
    if throughput_rps < min_throughput_rps:
        raise RuntimeError(
            f"LOAD_THROUGHPUT_BELOW_THRESHOLD:{throughput_rps:.2f}<{min_throughput_rps:.2f}"
        )
    print(
        json.dumps(
            {
                "status": "PASS",
                "database": "MYSQL",
                "requests": len(timings),
                "successes": sum(code == 200 for code in statuses),
                "failures": sum(code != 200 for code in statuses),
                "throughput_rps": round(throughput_rps, 2),
                "p50_seconds": round(p50, 4),
                "p95_seconds": round(p95, 4),
                "max_seconds": round(max(sorted_timings, default=0.0), 4),
                **metrics,
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
        "--database-url",
        default=os.getenv(
            "DATABASE_URL",
            "mysql+pymysql://novel:novel_dev_only@127.0.0.1:13306/novel_platform",
        ),
    )
    parser.add_argument("--concurrency", type=int, default=8)
    parser.add_argument(
        "--max-p95-ms",
        type=float,
        default=float(os.getenv("LOAD_MAX_P95_MS", "5000")),
    )
    parser.add_argument(
        "--min-throughput-rps",
        type=float,
        default=float(os.getenv("LOAD_MIN_THROUGHPUT_RPS", "1")),
    )
    parser.add_argument(
        "--payment-secret",
        default=os.getenv(
            "PAYMENT_CALLBACK_SECRET", "development-only-payment-callback-secret"
        ),
    )
    args = parser.parse_args()
    run(
        args.api,
        args.database_url,
        args.concurrency,
        args.payment_secret,
        args.max_p95_ms,
        args.min_throughput_rps,
    )


if __name__ == "__main__":
    main()
