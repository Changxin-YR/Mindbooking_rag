from pathlib import Path
from tempfile import gettempdir

from playwright.sync_api import sync_playwright

BASE_URL = "http://127.0.0.1:8080"


def main() -> None:
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        api = playwright.request.new_context(base_url=BASE_URL)
        try:
            checks = (
                ("/", "今天读什么", "reader"),
                ("/writer/", "进入 Writer Center", "writer"),
                ("/admin/", "登录运营后台", "admin"),
            )
            for path, marker, name in checks:
                errors: list[str] = []
                page = browser.new_page()
                page.on(
                    "pageerror", lambda error, errors=errors: errors.append(str(error))
                )
                page.goto(f"{BASE_URL}{path}", wait_until="networkidle")
                assert marker in page.locator("body").inner_text()
                assert not errors, errors
                page.screenshot(
                    path=str(Path(gettempdir()) / f"mindbooking-compose-{name}.png"),
                    full_page=True,
                )
                page.close()

            assert api.get("/healthz").ok
            assert api.get("/api/v1/health/live").ok
            assert api.get("/writer/api/v1/health/live").status == 401
            assert api.get("/admin/api/v1/health/live").status == 401
            print("compose browser smoke: ok")
        finally:
            api.dispose()
            browser.close()


if __name__ == "__main__":
    main()
