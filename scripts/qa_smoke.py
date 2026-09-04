from pathlib import Path
from tempfile import gettempdir

from playwright.sync_api import sync_playwright


def main() -> None:
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        try:
            for port, marker in ((3100, "墨页"), (3101, "作者工作台"), (3102, "运营控制台")):
                page = browser.new_page()
                page.goto(f"http://127.0.0.1:{port}", wait_until="domcontentloaded", timeout=10_000)
                page.wait_for_timeout(500)
                assert marker in page.locator("body").inner_text()
                page.screenshot(path=str(Path(gettempdir()) / f"mindbooking-{port}.png"))
                print(f"web {port}: ok")
                page.close()

            api = browser.new_page()
            response = api.goto("http://127.0.0.1:8000/api/v1/books", wait_until="domcontentloaded")
            assert response is not None and response.ok
            assert response.json()["total"] == 0
            print("api: ok")
            api.close()
        finally:
            browser.close()


if __name__ == "__main__":
    main()
