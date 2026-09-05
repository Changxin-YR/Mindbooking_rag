import json
from time import time

from playwright.sync_api import sync_playwright


def main() -> None:
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        api = playwright.request.new_context(base_url="http://127.0.0.1:8000")
        phone = f"137{int(time() * 1000) % 100_000_000:08d}"
        account = api.post(
            "/api/v1/iam/accounts", data={"phone": phone, "password": "Correct#123"}
        )
        assert account.status == 201, account.text()
        account_id = account.json()["account_id"]
        login = api.post(
            "/api/v1/iam/sessions", data={"phone": phone, "password": "Correct#123"}
        )
        assert login.ok, login.text()
        token = login.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}
        profile = api.post(
            "/writer/api/v1/author/profiles",
            headers=headers,
            data={"account_id": account_id, "pen_name": f"编辑验收{phone[-4:]}"},
        )
        assert profile.status == 201, profile.text()

        page = browser.new_page()
        page.add_init_script(
            "localStorage.setItem('writer-web-session', "
            + json.dumps(json.dumps({"token": token, "accountId": account_id}))
            + ");"
        )
        page.goto(
            "http://127.0.0.1:8080/writer/?view=%E6%88%91%E7%9A%84%E4%BD%9C%E5%93%81",
            wait_until="networkidle",
        )
        page.get_by_label("作品名").fill("编辑器验收作品")
        page.get_by_role("button", name="创建作品").click()
        page.get_by_text("作品已创建，可以继续添加卷和章节。").wait_for(timeout=5000)
        page.get_by_role("link", name="章节编辑").click()
        page.wait_for_url("**view=%E7%AB%A0%E8%8A%82%E7%BC%96%E8%BE%91")

        page.get_by_label("卷标题").fill("第一卷")
        page.get_by_label("卷序号").fill("1")
        page.get_by_role("button", name="创建卷").click()
        page.get_by_text("卷已创建").wait_for(timeout=5000)
        page.get_by_label("章节标题").fill("序章")
        page.get_by_label("章节序号").fill("1")
        page.get_by_role("button", name="创建章节").click()
        page.get_by_text("章节已创建").wait_for(timeout=5000)
        page.get_by_label("章节正文").fill("编辑器 smoke 正文")
        page.get_by_role("button", name="保存草稿").click()
        page.get_by_text("草稿已保存").wait_for(timeout=5000)
        page.get_by_role("button", name="生成固定版本").click()
        page.get_by_text("固定版本已生成").wait_for(timeout=5000)
        assert page.get_by_label("章节正文").input_value() == "编辑器 smoke 正文"
        print("writer editor smoke: ok")
        api.dispose()
        browser.close()


if __name__ == "__main__":
    main()
