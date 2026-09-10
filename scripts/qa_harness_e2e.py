"""Verify that the authenticated native Harness page can be embedded by Admin."""

from __future__ import annotations

import os
from urllib.parse import urlsplit

from playwright.sync_api import sync_playwright


def main() -> None:
    api_url = os.environ.get("API_BASE_URL", "http://127.0.0.1:8000").rstrip("/")
    employee_code = os.environ.get("STAFF_BOOTSTRAP_EMPLOYEE_CODE", "qa-admin")
    password = os.environ.get("STAFF_BOOTSTRAP_PASSWORD", "QaAdmin#123456")
    with sync_playwright() as playwright:
        api = playwright.request.new_context(base_url=api_url)
        browser = playwright.chromium.launch(headless=True)
        try:
            login = api.post(
                "/admin/api/v1/auth/staff/sessions",
                data={"employee_code": employee_code, "password": password},
            )
            assert login.ok, login.text()
            headers = {"Authorization": f"Bearer {login.json()['access_token']}"}
            harness = api.get("/admin/api/v1/agent/harness-url", headers=headers, timeout=125_000)
            assert harness.ok, harness.text()
            harness_url = harness.json()["url"]
            parsed = urlsplit(harness_url)
            assert parsed.scheme == "http"
            assert parsed.hostname in {"localhost", "127.0.0.1"}
            assert parsed.query.startswith("token=")

            page = browser.new_page()
            response = page.goto(harness_url, wait_until="domcontentloaded", timeout=30_000)
            assert response is not None
            assert response.status == 200
            frame_ancestors = response.headers.get("content-security-policy", "")
            assert "frame-ancestors 'none'" not in frame_ancestors
            assert response.headers.get("x-frame-options", "").upper() not in {"DENY", "SAMEORIGIN"}
            page.locator("body").wait_for(timeout=10_000)

            admin = browser.new_page()
            admin.add_init_script(
                "localStorage.setItem('admin_access_token', "
                + repr(login.json()["access_token"])
                + ");"
            )
            admin.goto(
                "http://127.0.0.1:8080/admin/?view=AI%20%E8%BF%90%E8%90%A5%E5%8A%A9%E6%89%8B",
                wait_until="domcontentloaded",
            )
            frame = admin.locator("iframe.native-harness-frame")
            frame.wait_for(timeout=15_000)
            assert "暂时不可用" not in admin.locator("body").inner_text()
            assert frame.get_attribute("src") == harness_url
            admin.close()
            print("harness browser e2e: ok")
        finally:
            api.dispose()
            browser.close()


if __name__ == "__main__":
    main()
