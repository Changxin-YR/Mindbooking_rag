from pathlib import Path
from tempfile import gettempdir

from playwright.sync_api import sync_playwright


def main() -> None:
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        api = playwright.request.new_context(base_url="http://127.0.0.1:8000")
        book = api.post("/writer/api/v1/books", data={"author_id": "author-smoke", "title": "浏览器验收作品", "synopsis": "用于端到端验收"})
        assert book.ok
        book_id = book.json()["id"]
        volume = api.post(f"/writer/api/v1/books/{book_id}/volumes", data={"number": 1, "title": "第一卷"})
        chapter = api.post(f"/writer/api/v1/volumes/{volume.json()['id']}/chapters", data={"number": 1, "title": "序章", "commercial_policy": "FREE"})
        chapter_id = chapter.json()["id"]
        draft = api.post(f"/writer/api/v1/chapters/{chapter.json()['id']}/drafts", data={"content": "浏览器测试正文"})
        version = api.post(f"/writer/api/v1/chapters/{chapter.json()['id']}/versions", data={"snapshot_id": draft.json()["id"]})
        submission = api.post(f"/writer/api/v1/books/{book_id}/first-listing-submissions", data={"fixed_version_ids": [version.json()["id"]]})
        decision = api.post(f"/admin/api/v1/reviews/{submission.json()['id']}/decisions", data={"reviewer_id": "staff-smoke", "decision": "APPROVE"})
        assert decision.ok
        try:
            page = browser.new_page()
            page.goto("http://127.0.0.1:3100", wait_until="networkidle")
            assert "今天读什么" in page.locator("body").inner_text()
            page.screenshot(path=str(Path(gettempdir()) / "mindbooking-reader-home.png"), full_page=True)
            page.goto(f"http://127.0.0.1:3100/books/{book_id}", wait_until="networkidle")
            page.get_by_text("浏览器验收作品", exact=True).wait_for(timeout=5000)
            assert "浏览器验收作品" in page.locator("body").inner_text()
            chapter_link = page.get_by_role("link", name="打开章节")
            assert chapter_link.get_attribute("href") == f"/read/{book_id}/{chapter_id}"
            chapter_link.click()
            page.wait_for_url(f"**/read/{book_id}/{chapter_id}")
            page.locator(".reading-content").wait_for(timeout=5000)
            assert "浏览器测试正文" in page.locator("body").inner_text()
            page.goto(f"http://127.0.0.1:3100/books/{book_id}", wait_until="networkidle")
            page.get_by_role("button", name="加入书架").click()
            page.get_by_text("已加入书架").wait_for(timeout=5000)
            page.goto("http://127.0.0.1:3100/library", wait_until="networkidle")
            assert book_id in page.locator("body").inner_text()
            page.goto("http://127.0.0.1:3100/wallet", wait_until="networkidle")
            assert "我的资产" in page.locator("body").inner_text()
            page.goto("http://127.0.0.1:3100/support", wait_until="networkidle")
            page.get_by_label("问题描述").fill("浏览器 smoke 工单")
            page.get_by_role("button", name="提交工单").click()
            page.get_by_text("工单已提交").wait_for(timeout=5000)
            page.goto("http://127.0.0.1:3100/settings", wait_until="networkidle")
            page.get_by_label("开启未成年人保护").check()
            page.get_by_role("button", name="保存设置").click()
            page.get_by_text("阅读保护设置已保存").wait_for(timeout=5000)
            page.close()

            writer = browser.new_page()
            writer.goto("http://127.0.0.1:3101/?view=%E6%88%91%E7%9A%84%E4%BD%9C%E5%93%81", wait_until="networkidle")
            assert "作品空间" in writer.locator("body").inner_text()
            writer.get_by_label("作品名").fill("浏览器创建作品")
            writer.get_by_role("button", name="创建作品").click()
            writer.get_by_text("浏览器创建作品", exact=True).wait_for(timeout=5000)
            writer.screenshot(path=str(Path(gettempdir()) / "mindbooking-writer.png"), full_page=True)
            writer.close()

            admin = browser.new_page()
            admin.goto("http://127.0.0.1:3102/?view=%E7%94%A8%E6%88%B7%20360", wait_until="networkidle")
            admin.get_by_role("button", name="查询").click()
            admin.wait_for_timeout(300)
            assert "138****5678" in admin.locator("body").inner_text()
            admin.screenshot(path=str(Path(gettempdir()) / "mindbooking-admin.png"), full_page=True)
            admin.close()

            error = browser.new_page()
            error.goto("http://127.0.0.1:3100/?state=error", wait_until="networkidle")
            assert "书库暂时没有响应" in error.locator("body").inner_text()
            error.close()
            print("v1.2 browser smoke: ok")
        finally:
            api.dispose()
            browser.close()


if __name__ == "__main__":
    main()
