import json
import os
from pathlib import Path
from tempfile import gettempdir
from time import monotonic, sleep, time

from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import sync_playwright


def wait_for_backend(api, timeout_seconds: float = 90) -> None:
    deadline = monotonic() + timeout_seconds
    last_status = "unreachable"
    while monotonic() < deadline:
        try:
            response = api.get("/health/ready", timeout=3000)
            last_status = str(response.status)
            if response.ok:
                return
        except (OSError, PlaywrightError) as exc:
            last_status = str(exc)
        sleep(0.5)
    raise AssertionError(f"backend did not become ready: {last_status}")


def main() -> None:
    web_base_url = os.environ.get("WEB_BASE_URL", "http://127.0.0.1:8080").rstrip("/")
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        api = playwright.request.new_context(base_url="http://127.0.0.1:8000")
        wait_for_backend(api)
        phone = f"139{int(time() * 1000) % 100_000_000:08d}"
        account = api.post(
            "/api/v1/iam/accounts",
            data={"phone": phone, "password": "Correct#123"},
        )
        assert account.status == 201, account.text()
        account_id = account.json()["account_id"]
        login = api.post(
            "/api/v1/iam/sessions",
            data={"phone": phone, "password": "Correct#123"},
        )
        assert login.ok, login.text()
        account_headers = {"Authorization": f"Bearer {login.json()['access_token']}"}
        profile = api.post(
            "/writer/api/v1/author/profiles",
            headers=account_headers,
            data={"account_id": account_id, "pen_name": f"验收作者{phone[-4:]}"},
        )
        assert profile.status == 201, profile.text()
        author_id = profile.json()["id"]
        book = api.post(
            "/writer/api/v1/books",
            headers=account_headers,
            data={
                "author_id": author_id,
                "title": "浏览器验收作品",
                "synopsis": "用于端到端验收",
            },
        )
        assert book.ok
        book_id = book.json()["id"]
        volume = api.post(
            f"/writer/api/v1/books/{book_id}/volumes",
            headers=account_headers,
            data={"number": 1, "title": "第一卷"},
        )
        assert volume.ok, volume.text()
        chapter = api.post(
            f"/writer/api/v1/volumes/{volume.json()['id']}/chapters",
            headers=account_headers,
            data={"number": 1, "title": "序章", "commercial_policy": "FREE"},
        )
        assert chapter.ok, chapter.text()
        chapter_id = chapter.json()["id"]
        draft = api.post(
            f"/writer/api/v1/chapters/{chapter_id}/drafts",
            headers=account_headers,
            data={"content": "浏览器测试正文"},
        )
        assert draft.ok, draft.text()
        version = api.post(
            f"/writer/api/v1/chapters/{chapter_id}/versions",
            headers=account_headers,
            data={"snapshot_id": draft.json()["id"]},
        )
        assert version.ok, version.text()
        submission = api.post(
            f"/writer/api/v1/books/{book_id}/first-listing-submissions",
            headers=account_headers,
            data={"fixed_version_ids": [version.json()["id"]]},
        )
        assert submission.ok, submission.text()
        staff_code = os.environ.get("STAFF_BOOTSTRAP_EMPLOYEE_CODE", "qa-admin")
        staff_password = os.environ.get("STAFF_BOOTSTRAP_PASSWORD", "QaAdmin#123456")
        staff_login = api.post(
            "/admin/api/v1/auth/staff/sessions",
            data={"employee_code": staff_code, "password": staff_password},
        )
        assert staff_login.ok, staff_login.text()
        staff_headers = {
            "Authorization": f"Bearer {staff_login.json()['access_token']}"
        }
        decision = api.post(
            f"/admin/api/v1/reviews/{submission.json()['id']}/decisions",
            headers=staff_headers,
            data={"reviewer_id": "staff-smoke", "decision": "APPROVE"},
        )
        assert decision.ok
        try:
            guest = browser.new_page()
            guest.goto(web_base_url, wait_until="networkidle")
            guest.get_by_role("link", name="登录", exact=True).click()
            guest.wait_for_url("**/settings")
            guest.get_by_label("手机号").wait_for(timeout=5000)
            guest.close()

            page = browser.new_page()
            page.add_init_script(
                "localStorage.setItem('reader-web-session', "
                + json.dumps(
                    json.dumps(
                        {"token": login.json()["access_token"], "accountId": account_id}
                    )
                )
                + ");"
            )
            page.goto(web_base_url, wait_until="networkidle")
            assert "今天读什么" in page.locator("body").inner_text()
            page.screenshot(
                path=str(Path(gettempdir()) / "mindbooking-reader-home.png"),
                full_page=True,
            )
            page.goto(f"{web_base_url}/books/{book_id}", wait_until="networkidle")
            page.get_by_text("浏览器验收作品", exact=True).wait_for(timeout=5000)
            assert "浏览器验收作品" in page.locator("body").inner_text()
            chapter_link = page.get_by_role("link", name="打开章节")
            assert chapter_link.get_attribute("href") == f"/read/{book_id}/{chapter_id}"
            chapter_link.click()
            page.wait_for_url(f"**/read/{book_id}/{chapter_id}")
            page.locator(".reading-content").wait_for(timeout=5000)
            assert "浏览器测试正文" in page.locator("body").inner_text()
            page.goto(f"{web_base_url}/books/{book_id}", wait_until="networkidle")
            page.get_by_role("button", name="加入书架").click()
            page.get_by_text("已加入书架").wait_for(timeout=5000)
            page.goto(f"{web_base_url}/library", wait_until="networkidle")
            assert "浏览器验收作品" in page.locator("body").inner_text()
            page.goto(f"{web_base_url}/wallet", wait_until="networkidle")
            assert "我的资产" in page.locator("body").inner_text()
            page.goto(f"{web_base_url}/support", wait_until="networkidle")
            page.get_by_label("问题描述").fill("浏览器 smoke 工单")
            page.get_by_role("button", name="提交工单").click()
            page.get_by_text("工单提交成功").wait_for(timeout=5000)
            page.goto(f"{web_base_url}/settings", wait_until="networkidle")
            page.get_by_label("开启未成年人保护").check()
            page.get_by_role("button", name="保存设置").click()
            page.get_by_text("阅读保护设置已保存").wait_for(timeout=5000)
            page.close()

            writer = browser.new_page()
            writer.add_init_script(
                "localStorage.setItem('writer-web-session', "
                + json.dumps(
                    json.dumps(
                        {"token": login.json()["access_token"], "accountId": account_id}
                    )
                )
                + ");"
            )
            writer.goto(
                f"{web_base_url}/writer/?view=%E6%88%91%E7%9A%84%E4%BD%9C%E5%93%81",
                wait_until="networkidle",
            )
            assert "创作空间" in writer.locator("body").inner_text()
            writer.get_by_label("作品名").fill("浏览器创建作品")
            writer.get_by_role("button", name="创建作品").click()
            writer.get_by_text("浏览器创建作品", exact=True).wait_for(timeout=5000)
            writer.screenshot(
                path=str(Path(gettempdir()) / "mindbooking-writer.png"), full_page=True
            )
            writer.close()

            admin = browser.new_page()
            admin.add_init_script(
                "localStorage.setItem('admin_access_token', "
                + json.dumps(staff_login.json()["access_token"])
                + ");"
            )
            admin.goto(
                f"{web_base_url}/admin/?view=%E7%94%A8%E6%88%B7%20360",
                wait_until="networkidle",
            )
            admin.get_by_label("查询账号 ID").fill(account_id)
            admin.get_by_label("查询手机号").fill(phone)
            admin.get_by_role("button", name="查询").click()
            admin.wait_for_timeout(300)
            assert f"{phone[:3]}****{phone[-4:]}" in admin.locator("body").inner_text()
            admin.screenshot(
                path=str(Path(gettempdir()) / "mindbooking-admin.png"), full_page=True
            )
            admin.close()

            error = browser.new_page()
            error.goto(f"{web_base_url}/?state=error", wait_until="networkidle")
            assert "书库暂时没有响应" in error.locator("body").inner_text()
            error.close()
            print("v1.2 browser smoke: ok")
        finally:
            api.dispose()
            browser.close()


if __name__ == "__main__":
    main()
