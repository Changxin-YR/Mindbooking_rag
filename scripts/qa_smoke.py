import os
from pathlib import Path
from tempfile import gettempdir

from playwright.sync_api import sync_playwright


def main() -> None:
    web_base_url = os.environ.get("WEB_BASE_URL", "http://127.0.0.1:8080").rstrip("/")
    api_base_url = os.environ.get("API_BASE_URL", "http://127.0.0.1:8000").rstrip("/")
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        try:
            checks = (
                ("/", "今天读什么", "reader"),
                ("/writer/", "进入 Writer Center", "writer"),
                ("/admin/", "登录运营后台", "admin"),
            )
            for path, marker, name in checks:
                page = browser.new_page()
                page.goto(
                    f"{web_base_url}{path}",
                    wait_until="domcontentloaded",
                    timeout=10_000,
                )
                page.wait_for_timeout(500)
                assert marker in page.locator("body").inner_text()
                page.screenshot(
                    path=str(Path(gettempdir()) / f"mindbooking-{name}.png")
                )
                print(f"web {name}: ok")
                page.close()

            api = browser.new_page()
            response = api.goto(
                f"{api_base_url}/api/v1/books", wait_until="domcontentloaded"
            )
            assert response is not None and response.ok
            payload = response.json()
            assert isinstance(payload.get("total"), int)
            assert isinstance(payload.get("items"), list)
            print("api: ok")
            api.close()
        finally:
            browser.close()


if __name__ == "__main__":
    main()
