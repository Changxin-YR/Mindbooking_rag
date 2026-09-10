"""Verify the dedicated MindBook ingress and the real Staff login."""

from __future__ import annotations

import argparse
import json
import os
import ssl
import subprocess
import urllib.error
import urllib.request
from dataclasses import dataclass


@dataclass(frozen=True)
class Check:
    name: str
    url: str


def request(url: str, *, method: str = "GET", payload: dict | None = None) -> tuple[int, str]:
    body = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(
        url,
        data=body,
        method=method,
        headers={"Accept": "text/html,application/json", "Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=15, context=ssl.create_default_context()) as response:
            return response.status, response.read(300_000).decode("utf-8", "replace")
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read(300_000).decode("utf-8", "replace")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default=os.getenv("QA_BASE_URL", "https://23331.cloud/books"))
    parser.add_argument("--staff-code", default=os.getenv("STAFF_BOOTSTRAP_EMPLOYEE_CODE", "qa-admin"))
    parser.add_argument("--staff-password", default=os.getenv("STAFF_BOOTSTRAP_PASSWORD", "QaAdmin#123456"))
    parser.add_argument("--compose-file", default="infra/docker-compose.yml")
    parser.add_argument("--skip-compose", action="store_true")
    args = parser.parse_args()
    base = args.base_url.rstrip("/")

    checks = (
        Check("backend readiness", f"{base}/api/v1/health/ready"),
        Check("reader page", f"{base}/"),
        Check("writer page", f"{base}/writer/"),
        Check("admin login page", f"{base}/admin/"),
    )
    for check in checks:
        status, body = request(check.url)
        if status != 200 or not body.strip():
            raise SystemExit(f"FAIL {check.name}: HTTP {status}")
        print(f"PASS {check.name}: HTTP {status}")

    status, body = request(
        f"{base}/admin/api/v1/auth/staff/sessions",
        method="POST",
        payload={"employee_code": args.staff_code, "password": args.staff_password},
    )
    if status != 200:
        raise SystemExit(f"FAIL Staff login: HTTP {status}")
    if not json.loads(body).get("access_token"):
        raise SystemExit("FAIL Staff login: response did not contain access_token")
    print("PASS Staff login: authenticated")

    if not args.skip_compose:
        result = subprocess.run(
            ["docker", "compose", "-f", args.compose_file, "--env-file", ".env.example", "config", "--quiet"],
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode:
            raise SystemExit(f"FAIL compose config: {result.stderr.strip()}")
        print("PASS compose config")


if __name__ == "__main__":
    main()
