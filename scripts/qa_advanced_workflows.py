"""Exercise the implemented Review/Operation/Risk/Legal/Governance workflows."""

from __future__ import annotations

import argparse
import base64
import hashlib
import hmac
import json
import os
import struct
from datetime import UTC, datetime
from time import time
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


def call(
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
    try:
        with urlopen(
            Request(
                f"{base.rstrip('/')}{path}", data=body, headers=headers, method=method
            ),
            timeout=15,
        ) as response:
            raw = response.read().decode()
            return response.status, (json.loads(raw) if raw else None)
    except HTTPError as exc:
        raw = exc.read().decode(errors="replace")
        try:
            value = json.loads(raw)
        except json.JSONDecodeError:
            value = raw
        return exc.code, value
    except URLError as exc:
        return 599, {"error": str(exc.reason)}


def must(result, status: int):
    if result[0] != status:
        raise RuntimeError(f"expected HTTP {status}, got {result[0]}: {result[1]}")
    return result[1]


def totp(secret: str) -> str:
    raw = base64.b32decode(secret + "=" * ((8 - len(secret) % 8) % 8), casefold=True)
    digest = hmac.new(raw, struct.pack(">Q", int(time()) // 30), hashlib.sha1).digest()
    offset = digest[-1] & 0x0F
    return str(
        (struct.unpack(">I", digest[offset : offset + 4])[0] & 0x7FFFFFFF) % 1_000_000
    ).zfill(6)


def provision_staff(
    base: str,
    bootstrap: str,
    suffix: str,
    department: str,
    permissions: tuple[str, ...],
) -> tuple[str, str]:
    code = f"qa-{department}-{suffix}"
    staff = must(
        call(
            base,
            "POST",
            "/admin/api/v1/platform/staff",
            payload={"employee_code": code, "department": department},
            token=bootstrap,
        ),
        201,
    )
    staff_id = str(staff["id"])
    for permission in permissions:
        must(
            call(
                base,
                "POST",
                f"/admin/api/v1/platform/staff/{staff_id}/permissions",
                payload={"permission": permission},
                token=bootstrap,
            ),
            204,
        )
    must(
        call(
            base,
            "POST",
            f"/admin/api/v1/platform/staff/{staff_id}/data-scopes",
            payload={"scope_type": "ALL", "scope_value": "*"},
            token=bootstrap,
        ),
        204,
    )
    must(
        call(
            base,
            "POST",
            f"/admin/api/v1/auth/staff/credentials/{staff_id}",
            payload={"password": "Governance#123456"},
            token=bootstrap,
        ),
        204,
    )
    otp = None
    if department.lower().replace("-", "_") in {
        "finance",
        "risk",
        "admin",
        "security",
        "super_admin",
    }:
        factor = must(
            call(
                base,
                "POST",
                f"/admin/api/v1/auth/staff/mfa/totp/{staff_id}",
                token=bootstrap,
            ),
            200,
        )
        otp = totp(str(factor["secret"]))
    login = must(
        call(
            base,
            "POST",
            "/admin/api/v1/auth/staff/sessions",
            payload={
                "employee_code": code,
                "password": "Governance#123456",
                **({"otp": otp} if otp else {}),
            },
        ),
        200,
    )
    return str(login["access_token"]), staff_id


def run(base: str, staff_code: str, staff_password: str) -> None:
    suffix = str(int(time() * 1000))[-9:]
    bootstrap_login = must(
        call(
            base,
            "POST",
            "/admin/api/v1/auth/staff/sessions",
            payload={"employee_code": staff_code, "password": staff_password},
        ),
        200,
    )
    staff = str(bootstrap_login["access_token"])
    reviewer, reviewer_id = provision_staff(
        base, staff, suffix, "reviewer", ("review.read", "review.decide")
    )
    operator, operator_id = provision_staff(
        base, staff, suffix, "operation", ("operation.read", "operation.write")
    )
    risk, _risk_id = provision_staff(
        base, staff, suffix, "risk", ("risk.read", "risk.write")
    )
    legal_staff, _legal_id = provision_staff(
        base, staff, suffix, "legal", ("legal.write",)
    )
    governance_maker, governance_maker_id = provision_staff(
        base, staff, suffix, "governance-maker", ("governance.read", "governance.write")
    )
    finance, _finance_id = provision_staff(
        base,
        staff,
        suffix,
        "finance",
        ("finance.read", "finance.write"),
    )
    checker, checker_id = provision_staff(
        base,
        staff,
        suffix,
        "governance-checker",
        ("governance.read", "governance.write"),
    )
    agent, agent_id = provision_staff(
        base,
        staff,
        suffix,
        "agent",
        ("agent.execute", "agent.audit.read", "content.read"),
    )
    denied = call(
        base,
        "POST",
        "/admin/api/v1/operation/campaigns",
        token=reviewer,
        payload={
            "title": "forbidden",
            "start_date": "2026-01-01",
            "end_date": "2026-12-31",
        },
    )
    if denied[0] != 403:
        raise RuntimeError(f"reviewer cross-domain write was not denied: {denied}")
    denied = call(
        base,
        "POST",
        "/admin/api/v1/risk/login-signals",
        token=operator,
        payload={
            "account_id": "missing",
            "device_id": "forbidden",
            "browser": "Chromium",
            "operating_system": "Windows",
            "ip": "198.51.100.8",
            "region": "CN",
            "user_agent": "advanced-e2e",
        },
    )
    if denied[0] != 403:
        raise RuntimeError(f"operator cross-domain write was not denied: {denied}")
    account = must(
        call(
            base,
            "POST",
            "/api/v1/iam/accounts",
            payload={"phone": f"135{suffix[-8:]}", "password": "Advanced#123"},
        ),
        201,
    )
    account_id = str(account["account_id"])
    reader = str(
        must(
            call(
                base,
                "POST",
                "/api/v1/iam/sessions",
                payload={"phone": f"135{suffix[-8:]}", "password": "Advanced#123"},
            ),
            200,
        )["access_token"]
    )
    books = must(call(base, "GET", "/api/v1/books"), 200).get("items", [])
    book_id = str(books[0]["id"]) if books else f"book-{suffix}"

    must(call(base, "GET", "/admin/api/v1/reviews", token=reviewer), 200)
    must(
        call(
            base,
            "POST",
            "/admin/api/v1/reviewer-quality",
            token=reviewer,
            payload={
                "reviewer_id": reviewer_id,
                "accuracy_bps": 9800,
                "false_positive_bps": 100,
                "miss_bps": 100,
                "overturn_bps": 50,
                "avg_handle_seconds": 30,
                "complaint_bps": 50,
            },
        ),
        201,
    )
    must(
        call(
            base,
            "POST",
            "/admin/api/v1/operation/rankings",
            token=operator,
            payload={
                "book_ids": [book_id],
                "kind": "ALGORITHM",
                "scores": [100],
                "snapshot_id": f"adv-{suffix}",
            },
        ),
        201,
    )
    must(
        call(
            base,
            "POST",
            "/admin/api/v1/operation/editorial-slots",
            token=operator,
            payload={
                "book_id": book_id,
                "position": 1,
                "snapshot_id": f"slot-{suffix}",
            },
        ),
        201,
    )
    must(
        call(
            base,
            "POST",
            "/admin/api/v1/operation/recommendations",
            token=operator,
            payload={
                "account_id": account_id,
                "book_ids": [book_id],
                "personalized": True,
            },
        ),
        201,
    )
    must(
        call(
            base,
            "POST",
            "/admin/api/v1/operation/exports",
            token=operator,
            payload={"requester_id": operator_id, "resource_type": "BOOKS"},
        ),
        202,
    )
    must(
        call(
            base,
            "POST",
            "/admin/api/v1/operation/retention-policies",
            token=operator,
            payload={"resource_type": "DRAFT", "action": "ANONYMIZE", "days": 365},
        ),
        201,
    )
    must(
        call(
            base,
            "POST",
            "/admin/api/v1/operation/campaigns",
            token=operator,
            payload={
                "title": f"沙盒活动-{suffix}",
                "start_date": "2026-01-01",
                "end_date": "2026-12-31",
            },
        ),
        201,
    )
    reward = must(
        call(
            base,
            "POST",
            "/admin/api/v1/operation/rewards",
            token=operator,
            idem=f"reward-{suffix}",
            payload={
                "subject_id": account_id,
                "reward_type": "GIFT_COIN",
                "amount": 10,
            },
        ),
        201,
    )
    duplicate_reward = must(
        call(
            base,
            "POST",
            "/admin/api/v1/operation/rewards",
            token=operator,
            idem=f"reward-{suffix}",
            payload={
                "subject_id": account_id,
                "reward_type": "GIFT_COIN",
                "amount": 10,
            },
        ),
        201,
    )
    if reward.get("id") != duplicate_reward.get("id"):
        raise RuntimeError("reward idempotency failed")

    must(
        call(
            base,
            "POST",
            "/admin/api/v1/risk/login-signals",
            token=risk,
            payload={
                "account_id": account_id,
                "device_id": f"device-{suffix}",
                "browser": "Chromium",
                "operating_system": "Windows",
                "ip": "198.51.100.21",
                "region": "CN",
                "user_agent": "advanced-e2e",
            },
        ),
        201,
    )
    watch = must(
        call(
            base,
            "POST",
            "/admin/api/v1/risk/watchlist",
            token=risk,
            payload={
                "target_type": "IP",
                "target_value": f"198.51.100.{suffix[-2:]}",
                "reason": "sandbox review",
                "case_id": f"case-{suffix}",
            },
        ),
        201,
    )
    must(
        call(
            base,
            "POST",
            f"/admin/api/v1/risk/watchlist/{watch['id']}/release",
            token=risk,
            payload={
                "reason": "cleared",
                "evidence_id": f"evidence-{suffix}",
                "case_id": f"case-{suffix}",
            },
        ),
        200,
    )

    dossier = must(
        call(
            base,
            "POST",
            "/admin/api/v1/copyright/dossiers",
            token=legal_staff,
            payload={"book_id": book_id},
        ),
        201,
    )
    must(
        call(
            base,
            "POST",
            f"/admin/api/v1/copyright/dossiers/{dossier['id']}/rights",
            token=legal_staff,
            payload={
                "region": "CN",
                "language": "zh-CN",
                "media": "WEB",
                "exclusive": False,
                "start_year": 2026,
                "end_year": 2030,
            },
        ),
        201,
    )
    complaint = must(
        call(
            base,
            "POST",
            "/admin/api/v1/copyright/complaints",
            token=legal_staff,
            payload={
                "book_id": book_id,
                "claimant_id": f"claimant-{suffix}",
                "reason": "sandbox",
            },
        ),
        201,
    )
    must(
        call(
            base,
            "POST",
            f"/admin/api/v1/copyright/complaints/{complaint['id']}/evidence",
            token=legal_staff,
            payload={"evidence_id": f"evidence-{suffix}"},
        ),
        200,
    )
    must(
        call(
            base,
            "POST",
            f"/admin/api/v1/copyright/complaints/{complaint['id']}/counter-notice",
            token=legal_staff,
            payload={"notice": "sandbox counter notice"},
        ),
        200,
    )
    legal = must(
        call(
            base,
            "POST",
            "/admin/api/v1/legal/cases",
            token=legal_staff,
            payload={"subject": f"sandbox-{suffix}"},
        ),
        201,
    )
    hold = must(
        call(
            base,
            "POST",
            f"/admin/api/v1/legal/cases/{legal['id']}/holds",
            token=legal_staff,
            payload={"resource_id": book_id},
        ),
        201,
    )
    must(
        call(
            base,
            "POST",
            f"/admin/api/v1/legal/holds/{hold['id']}/release",
            token=legal_staff,
        ),
        200,
    )

    must(
        call(
            base,
            "POST",
            "/api/v1/privacy/requests",
            token=reader,
            payload={"account_id": account_id, "kind": "EXPORT"},
        ),
        201,
    )
    must(
        call(
            base,
            "POST",
            "/api/v1/agreements/acceptances",
            token=reader,
            payload={
                "account_id": account_id,
                "agreement_code": "TERMS",
                "version": "SANDBOX-1",
            },
        ),
        201,
    )
    parameter = must(
        call(
            base,
            "POST",
            "/admin/api/v1/parameters",
            token=governance_maker,
            payload={
                "key": f"sandbox.param.{suffix}",
                "value": "100",
                "maker_id": governance_maker_id,
            },
        ),
        201,
    )
    approved = must(
        call(
            base,
            "POST",
            f"/admin/api/v1/parameters/{parameter['id']}/approve",
            token=checker,
            payload=None,
        ),
        200,
    )
    if approved.get("checker_id") != checker_id:
        raise RuntimeError("parameter checker identity was not persisted")
    must(
        call(
            base,
            "POST",
            f"/admin/api/v1/parameters/{parameter['id']}/activate",
            token=checker,
            payload={"effective_at": datetime.now(UTC).isoformat()},
        ),
        200,
    )
    batch = must(
        call(
            base,
            "POST",
            "/admin/api/v1/reconciliation/batches",
            token=checker,
            payload={"business_date": datetime.now(UTC).strftime("%Y-%m-%d")},
        ),
        201,
    )
    must(
        call(
            base,
            "POST",
            f"/admin/api/v1/reconciliation/batches/{batch['id']}/items",
            token=checker,
            payload={
                "reference": f"ref-{suffix}",
                "difference": "DUPLICATE",
                "amount_cents": 1,
            },
        ),
        201,
    )
    must(
        call(
            base,
            "POST",
            f"/admin/api/v1/reconciliation/batches/{batch['id']}/repair",
            token=checker,
        ),
        200,
    )
    must(
        call(
            base,
            "POST",
            f"/admin/api/v1/reconciliation/batches/{batch['id']}/close",
            token=checker,
        ),
        200,
    )
    invoice = must(
        call(
            base,
            "POST",
            "/api/v1/invoices",
            token=reader,
            payload={
                "account_id": account_id,
                "amount_cents": 100,
                "title": "沙盒发票",
                "tax_id": "91310000SANDBOX",
            },
        ),
        201,
    )
    denied = call(
        base,
        "POST",
        f"/admin/api/v1/invoices/{invoice['id']}/issue",
        token=checker,
        payload={"document_id": f"forbidden-invoice-doc-{suffix}"},
    )
    if denied[0] != 403:
        raise RuntimeError(f"governance token unexpectedly issued invoice: {denied}")
    must(
        call(
            base,
            "POST",
            f"/admin/api/v1/invoices/{invoice['id']}/issue",
            token=finance,
            payload={"document_id": f"invoice-doc-{suffix}"},
        ),
        200,
    )
    must(
        call(
            base,
            "POST",
            f"/admin/api/v1/invoices/{invoice['id']}/reverse",
            token=finance,
            payload={"document_id": f"invoice-reverse-{suffix}"},
        ),
        200,
    )
    must(call(base, "GET", "/admin/api/v1/agent/resources", token=agent), 200)
    agent_result = must(
        call(
            base,
            "POST",
            "/admin/api/v1/agent/tools/execute",
            token=agent,
            payload={
                "agent_id": f"advanced-agent-{suffix}",
                "actor_id": agent_id,
                "tool_name": "content.get_book",
                "arguments": {"book_id": book_id},
            },
        ),
        200,
    )
    if agent_result.get("tool_name") != "content.get_book":
        raise RuntimeError("agent tool did not execute")
    audits = must(
        call(
            base,
            "GET",
            "/admin/api/v1/agent/audits?tool_name=content.get_book",
            token=agent,
        ),
        200,
    )
    if int(audits.get("total", 0)) < 1:
        raise RuntimeError("agent audit was not persisted")
    print(
        json.dumps(
            {
                "status": "PASS",
                "workflows": [
                    "review",
                    "operation",
                    "risk",
                    "copyright",
                    "legal",
                    "governance",
                    "agent",
                ],
                "maker": governance_maker_id,
                "checker": checker_id,
                "reward_id": reward.get("id"),
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
        "--staff-code", default=os.getenv("STAFF_BOOTSTRAP_EMPLOYEE_CODE", "qa-admin")
    )
    parser.add_argument(
        "--staff-password",
        default=os.getenv("STAFF_BOOTSTRAP_PASSWORD", "QaAdmin#123456"),
    )
    args = parser.parse_args()
    run(args.api, args.staff_code, args.staff_password)


if __name__ == "__main__":
    main()
