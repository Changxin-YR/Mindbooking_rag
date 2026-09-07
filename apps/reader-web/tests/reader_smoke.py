from playwright.sync_api import sync_playwright


def main() -> None:
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page()
        for path, markers in (
            ("/", ("今天读什么",)),
            ("/search?q=不存在的书", ("暂无结果", "搜索暂时不可用")),
            ("/library?mode=discover", ("书库",)),
            ("/rankings/hot", ("热读榜",)),
        ):
            page.goto(f"http://127.0.0.1:3100{path}")
            page.wait_for_load_state("networkidle")
            body = page.locator("body").inner_text()
            assert any(marker in body for marker in markers)
            assert "ADP" not in page.url
        page.goto("http://127.0.0.1:3100/search?q=不存在的书")
        page.wait_for_load_state("networkidle")
        assert page.url.endswith("/search?q=%E4%B8%8D%E5%AD%98%E5%9C%A8%E7%9A%84%E4%B9%A6")
        page.goto("http://127.0.0.1:3100/")
        page.get_by_label("搜索作品").fill("斗破")
        page.get_by_label("搜索作品").press("Enter")
        page.wait_for_load_state("networkidle")
        assert page.url.endswith("/search?q=%E6%96%97%E7%A0%B4")
        page.goto("http://127.0.0.1:3100/")
        page.get_by_role("link", name="探索更多好书").click()
        page.wait_for_load_state("networkidle")
        assert "/library?mode=discover" in page.url
        page.goto("http://127.0.0.1:3100/rankings/hot")
        page.wait_for_load_state("networkidle")
        page.get_by_role("button", name="榜单说明").click()
        page.wait_for_selector('[role="dialog"]')
        assert page.get_by_role("dialog").is_visible()
        browser.close()


if __name__ == "__main__":
    main()
