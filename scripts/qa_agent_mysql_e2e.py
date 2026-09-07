"""Verify the authenticated Agent write path against the live MySQL compose stack."""

from __future__ import annotations

import argparse
import json
import os
import time
import uuid
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


def request(
    base: str, method: str, path: str, *, payload=None, token: str | None = None
):
    body = None if payload is None else json.dumps(payload, ensure_ascii=False).encode()
    headers = {"Accept": "application/json"}
    if body is not None:
        headers["Content-Type"] = "application/json"
    if token:
        headers["Authorization"] = f"Bearer {token}"
    try:
        with urlopen(
            Request(
                f"{base.rstrip('/')}{path}", data=body, headers=headers, method=method
            ),
            timeout=30,
        ) as response:
            raw = response.read().decode()
            return response.status, json.loads(raw) if raw else None
    except HTTPError as exc:
        raw = exc.read().decode(errors="replace")
        try:
            detail = json.loads(raw)
        except json.JSONDecodeError:
            detail = raw
        return exc.code, detail
    except URLError as exc:
        raise RuntimeError(f"{method} {path}: {exc.reason}") from exc


def must(result, expected: int):
    if result[0] != expected:
        raise RuntimeError(f"expected HTTP {expected}, got {result[0]}: {result[1]}")
    return result[1]


def create_submission(base: str, suffix: str) -> tuple[str, str]:
    phone = f"139{int(time.time_ns()) % 100_000_000:08d}"
    password = "AgentMysql#123"
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
    account_token = str(
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
    profile = must(
        request(
            base,
            "POST",
            "/writer/api/v1/author/profiles",
            token=account_token,
            payload={"account_id": account_id, "pen_name": f"Agent QA {suffix}"},
        ),
        201,
    )
    book = must(
        request(
            base,
            "POST",
            "/writer/api/v1/books",
            token=account_token,
            payload={"author_id": profile["id"], "title": f"Agent MySQL {suffix}"},
        ),
        201,
    )
    volume = must(
        request(
            base,
            "POST",
            f"/writer/api/v1/books/{book['id']}/volumes",
            token=account_token,
            payload={"title": "Volume", "number": 1},
        ),
        201,
    )
    chapter = must(
        request(
            base,
            "POST",
            f"/writer/api/v1/volumes/{volume['id']}/chapters",
            token=account_token,
            payload={"title": "Chapter", "commercial_policy": "FREE"},
        ),
        201,
    )
    draft = must(
        request(
            base,
            "POST",
            f"/writer/api/v1/chapters/{chapter['id']}/drafts",
            token=account_token,
            payload={"content": "mysql agent acceptance"},
        ),
        201,
    )
    version = must(
        request(
            base,
            "POST",
            f"/writer/api/v1/chapters/{chapter['id']}/versions",
            token=account_token,
            payload={"snapshot_id": draft["id"]},
        ),
        201,
    )
    submission = must(
        request(
            base,
            "POST",
            f"/writer/api/v1/books/{book['id']}/first-listing-submissions",
            token=account_token,
            payload={"fixed_version_ids": [version["id"]]},
        ),
        201,
    )
    return str(submission["id"]), str(book["id"])


def db_connection():
    try:
        import pymysql
    except ImportError as exc:
        raise RuntimeError("pymysql is required for MySQL Agent evidence") from exc
    password = os.environ.get("MYSQL_PASSWORD")
    if not password:
        raise RuntimeError(
            "MYSQL_PASSWORD is required; load it from the compose environment"
        )
    return pymysql.connect(
        host=os.environ.get("MYSQL_HOST", "127.0.0.1"),
        port=int(os.environ.get("MYSQL_PORT", "13306")),
        user=os.environ.get("MYSQL_USER", "novel"),
        password=password,
        database=os.environ.get("MYSQL_DATABASE", "novel_platform"),
        autocommit=True,
    )


def facts(connection, submission_id: str, book_id: str) -> dict[str, object]:
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT status FROM review_submissions WHERE id=%s", (submission_id,)
        )
        status = cursor.fetchone()[0]
        cursor.execute(
            "SELECT reviewer_id, decision, actor_type FROM review_decisions "
            "WHERE submission_id=%s ORDER BY created_at DESC LIMIT 1",
            (submission_id,),
        )
        decision = cursor.fetchone()
        cursor.execute(
            "SELECT lifecycle, visibility FROM books WHERE id=%s", (book_id,)
        )
        book = cursor.fetchone()
        cursor.execute(
            "SELECT COUNT(*) FROM review_submission_versions WHERE submission_id=%s",
            (submission_id,),
        )
        versions = cursor.fetchone()[0]
        cursor.execute("SELECT COUNT(*) FROM outbox_events")
        outbox = cursor.fetchone()[0]
    return {
        "status": status,
        "decision": tuple(decision) if decision else None,
        "book": tuple(book) if book else None,
        "version_links": versions,
        "outbox_total": outbox,
    }


def assign(connection, submission_id: str, staff_id: str) -> None:
    with connection.cursor() as cursor:
        cursor.execute(
            "UPDATE review_tasks SET assigned_staff_id=%s WHERE submission_id=%s",
            (staff_id, submission_id),
        )
        if cursor.rowcount != 1:
            raise RuntimeError("review assignment fixture was not created")


def run(base: str, staff_code: str, staff_password: str) -> None:
    suffix = uuid.uuid4().hex[:10]
    staff_login = must(
        request(
            base,
            "POST",
            "/admin/api/v1/auth/staff/sessions",
            payload={"employee_code": staff_code, "password": staff_password},
        ),
        200,
    )
    staff_token = str(staff_login["access_token"])
    staff_id = str(staff_login["staff_id"])
    connection = db_connection()
    try:
        manual_submission, manual_book = create_submission(base, f"{suffix}m")
        agent_submission, agent_book = create_submission(base, f"{suffix}a")
        assign(connection, manual_submission, staff_id)
        assign(connection, agent_submission, staff_id)

        manual_before = facts(connection, manual_submission, manual_book)
        must(
            request(
                base,
                "POST",
                f"/admin/api/v1/reviews/{manual_submission}/decisions",
                token=staff_token,
                payload={"reviewer_id": staff_id, "decision": "APPROVE"},
            ),
            201,
        )
        manual_after = facts(connection, manual_submission, manual_book)

        session = must(
            request(
                base,
                "POST",
                "/admin/api/v1/agent/sessions",
                token=staff_token,
                payload={},
            ),
            200,
        )
        session_id = str(session["id"])
        agent_before = facts(connection, agent_submission, agent_book)
        pending_status, pending_body = request(
            base,
            "POST",
            "/admin/api/v1/agent/tools/execute",
            token=staff_token,
            payload={
                "agent_id": f"qa-agent-{suffix}",
                "actor_id": staff_id,
                "session_id": session_id,
                "tool_name": "review.decide",
                "arguments": {"submission_id": agent_submission, "decision": "APPROVE"},
            },
        )
        if pending_status != 409:
            raise RuntimeError(
                f"expected PendingAction, got {pending_status}: {pending_body}"
            )
        detail = pending_body.get("error", {}).get("details", {})
        action = detail.get("pending_action")
        if not isinstance(action, dict):
            raise TypeError(f"PendingAction payload missing: {pending_body}")
        confirmed = must(
            request(
                base,
                "POST",
                f"/admin/api/v1/agent/actions/{action['id']}/confirm",
                token=staff_token,
                payload={
                    "session_id": session_id,
                    "confirmation_token": f"{action['id']}:{action['arguments_hash']}",
                },
            ),
            200,
        )
        if confirmed.get("tool_name") != "review.decide":
            raise RuntimeError(f"unexpected Agent confirmation result: {confirmed}")
        agent_after = facts(connection, agent_submission, agent_book)

        if (
            manual_after["status"] != agent_after["status"]
            or manual_after["decision"][1:] != agent_after["decision"][1:]
        ):
            raise RuntimeError(
                f"manual/agent semantic mismatch: {manual_after} != {agent_after}"
            )
        if manual_after["book"] != agent_after["book"]:
            raise RuntimeError(
                f"manual/agent book mismatch: {manual_after['book']} != {agent_after['book']}"
            )
        if manual_after["version_links"] != agent_after["version_links"]:
            raise RuntimeError("manual/agent review association mismatch")

        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT status FROM agent_pending_actions WHERE id=%s", (action["id"],)
            )
            pending_status_db = cursor.fetchone()[0]
            cursor.execute(
                "SELECT outcome, pending_action_id FROM agent_audit_events "
                "WHERE pending_action_id=%s ORDER BY occurred_at DESC LIMIT 1",
                (action["id"],),
            )
            audit = cursor.fetchone()
        if pending_status_db != "EXECUTED" or not audit or audit[0] != "SUCCESS":
            raise RuntimeError(
                f"Agent confirmation facts not durable: {pending_status_db}, {audit}"
            )
        print(
            json.dumps(
                {
                    "status": "PASS",
                    "database": "MYSQL",
                    "manual": manual_after,
                    "agent": agent_after,
                    "pending_action": pending_status_db,
                    "audit": tuple(audit),
                    "outbox_delta_manual": manual_after["outbox_total"]
                    - manual_before["outbox_total"],
                    "outbox_delta_agent": agent_after["outbox_total"]
                    - agent_before["outbox_total"],
                },
                ensure_ascii=False,
                default=str,
            )
        )
    finally:
        connection.close()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--api", default=os.getenv("API_BASE_URL", "http://127.0.0.1:8000")
    )
    parser.add_argument(
        "--staff-code", default=os.getenv("STAFF_BOOTSTRAP_EMPLOYEE_CODE", "qa-admin")
    )
    parser.add_argument(
        "--staff-password", default=os.getenv("STAFF_BOOTSTRAP_PASSWORD")
    )
    args = parser.parse_args()
    if not args.staff_password:
        raise SystemExit("STAFF_BOOTSTRAP_PASSWORD is required")
    run(args.api, args.staff_code, args.staff_password)


if __name__ == "__main__":
    main()
