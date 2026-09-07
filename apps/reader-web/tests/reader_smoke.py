import json

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
        page.get_by_label("题材").select_option("玄幻")
        page.get_by_role("button", name="筛选").last.click()
        page.wait_for_url("**category=%E7%8E%84%E5%B9%BB")
        assert "category=%E7%8E%84%E5%B9%BB" in page.url
        page.goto("http://127.0.0.1:3100/")
        page.get_by_role("button", name="换一批推荐").click()
        page.wait_for_url("**recommendation_page=1")
        assert "recommendation_page=1" in page.url
        page.goto("http://127.0.0.1:3100/rankings/hot")
        page.wait_for_load_state("networkidle")
        page.get_by_role("button", name="榜单说明").click()
        page.wait_for_selector('[role="dialog"]')
        assert page.get_by_role("dialog").is_visible()

        def fulfill_json(route, payload):
            route.fulfill(status=200, content_type="application/json", body=json.dumps(payload))

        page.route("**/api/v1/books/BK_E2E", lambda route: fulfill_json(route, {
            "id": "BK_E2E", "title": "E2E 作品", "synopsis": "测试简介", "author_id": "AUTHOR_E2E",
            "channel": "MALE", "category": "玄幻", "tags": ["系统"], "lifecycle": "SERIALIZING",
            "visibility": "PUBLIC", "chapters": [{"id": "CH_E2E", "number": 1, "title": "第一章", "commercial_policy": "FREE"}],
        }))
        page.route("**/api/v1/books/BK_E2E/chapters/CH_E2E", lambda route: fulfill_json(route, {
            "id": "CH_E2E", "book_id": "BK_E2E", "number": 1, "title": "第一章", "content": "这是阅读器回归内容。",
            "commercial_policy": "FREE", "access": "FREE",
        }))
        page.goto("http://127.0.0.1:3100/read/BK_E2E/CH_E2E")
        page.wait_for_load_state("networkidle")
        page.get_by_role("button", name="设置").click()
        assert page.get_by_role("complementary", name="阅读设置").is_visible()
        page.get_by_role("complementary", name="阅读设置").get_by_label("背景").select_option("eye")
        page.get_by_role("complementary", name="阅读设置").get_by_role("button", name="保存阅读设置").click()
        assert page.locator(".reading-shell.reader-bg-eye").count() == 1
        browser.close()


if __name__ == "__main__":
    main()
