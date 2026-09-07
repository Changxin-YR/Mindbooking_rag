import sys
from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient

from novel_platform.core.auth import SessionSigner
from novel_platform.modules.agent.api import ToolResource, build_agent_runtime_router
from novel_platform.modules.agent.application import AgentGateway, InMemoryAgentAuditLog
from novel_platform.modules.agent.runtime import HarnessRuntimeError, HarnessSessionManager
from novel_platform.modules.platform.application import PlatformApplication
from novel_platform.modules.platform.repository import InMemoryPlatformRepository


class FakeHarness:
    def __init__(self, **kwargs: object) -> None:
        self.kwargs = kwargs
        self.prompts: list[tuple[str, str]] = []

    def run(self, prompt: str, *, session_id: str) -> SimpleNamespace:
        self.prompts.append((prompt, session_id))
        return SimpleNamespace(final_response="找到 1 条记录。", finish_reason="completed")

    def close(self) -> None:
        return None


def test_harness_session_manager_binds_actor_and_rotates_token(tmp_path) -> None:
    created: list[FakeHarness] = []

    def factory(**kwargs: object) -> FakeHarness:
        harness = FakeHarness(**kwargs)
        created.append(harness)
        return harness

    manager = HarnessSessionManager(
        backend_url="http://127.0.0.1:8000",
        dsh_home=str(tmp_path),
        project_root=str(tmp_path),
        provider="deepseek-official",
        model="deepseek-v4-flash",
        harness_factory=factory,
    )
    result = manager.run(
        actor_id="staff-1", session_id="session-1", access_token="token-a", prompt="x"
    )
    assert result.final_response == "找到 1 条记录。"
    manager.run(actor_id="staff-1", session_id="session-1", access_token="token-b", prompt="y")
    assert len(created) == 2
    try:
        manager.run(actor_id="staff-2", session_id="session-1", access_token="token-c", prompt="z")
    except HarnessRuntimeError as exc:
        assert str(exc) == "AGENT_SESSION_ACTOR_MISMATCH"
    else:
        raise AssertionError("actor binding must reject session reuse")


def _web_command(url: str) -> tuple[str, ...]:
    script = f"import sys,time; print({('dsh web: ' + url)!r}, flush=True); time.sleep(30)"
    return (sys.executable, "-u", "-c", script)


def test_native_web_runtime_captures_url_and_isolates_staff_sessions(tmp_path) -> None:
    repo = tmp_path / "harness"
    repo.mkdir()
    manager = HarnessSessionManager(
        backend_url="http://127.0.0.1:8000",
        dsh_home=str(tmp_path / "dsh"),
        project_root=str(tmp_path),
        provider="deepseek-official",
        model="deepseek-v4-flash",
        web_command=_web_command("http://127.0.0.1:43101/?token=first"),
        harness_repo=str(repo),
        web_start_timeout_seconds=2.0,
    )
    process = None
    try:
        first = manager.start_web(
            actor_id="staff/1", session_id="session-1", access_token="token-a"
        )
        assert first == "http://127.0.0.1:43101/?token=first"
        assert (
            manager.start_web(actor_id="staff/1", session_id="session-1", access_token="token-a")
            == first
        )
        process = manager._web_sessions["session-1"][2].process
        args = tuple(str(argument) for argument in process.args)
        assert args[args.index("--profile") : args.index("--profile") + 2] == (
            "--profile",
            "web",
        )
        assert ("--no-open", "--host", "127.0.0.1", "--port", "0") == tuple(
            args[args.index("--no-open") : args.index("--no-open") + 5]
        )
        home = manager._web_sessions["session-1"][2].home
        assert home == (tmp_path / "dsh" / "staff_1" / "session-1").resolve()
        assert manager._web_sessions["session-1"][2].cwd == repo.resolve()

        second = manager.start_web(
            actor_id="staff/2", session_id="session-2", access_token="token-b"
        )
        assert second == first
        second_home = manager._web_sessions["session-2"][2].home
        assert second_home != home
        assert second_home == (tmp_path / "dsh" / "staff_2" / "session-2").resolve()
    finally:
        manager.close_all()
        if process is not None:
            assert process.poll() is not None


def test_native_web_runtime_rotates_on_token_and_rejects_actor_mismatch(tmp_path) -> None:
    manager = HarnessSessionManager(
        backend_url="http://127.0.0.1:8000",
        dsh_home=str(tmp_path),
        project_root=str(tmp_path),
        provider="deepseek-official",
        model="deepseek-v4-flash",
        web_command=_web_command("http://localhost:43102/?token=rotated"),
        web_start_timeout_seconds=2.0,
    )
    try:
        manager.start_web(actor_id="staff-1", session_id="session-1", access_token="a")
        old_process = manager._web_sessions["session-1"][2].process
        manager.start_web(actor_id="staff-1", session_id="session-1", access_token="b")
        assert old_process.poll() is not None
        assert manager._web_sessions["session-1"][1] == "b"
        try:
            manager.start_web(actor_id="staff-2", session_id="session-1", access_token="c")
        except HarnessRuntimeError as exc:
            assert str(exc) == "AGENT_SESSION_ACTOR_MISMATCH"
        else:
            raise AssertionError("actor binding must reject native web session reuse")
    finally:
        manager.close_all()


def test_native_web_runtime_rejects_non_loopback_or_unauthenticated_url(tmp_path) -> None:
    manager = HarnessSessionManager(
        backend_url="http://127.0.0.1:8000",
        dsh_home=str(tmp_path),
        project_root=str(tmp_path),
        provider="deepseek-official",
        model="deepseek-v4-flash",
        web_command=_web_command("https://attacker.example/?token=secret"),
        web_start_timeout_seconds=0.2,
    )
    try:
        try:
            manager.start_web(actor_id="staff-1", session_id="session-1", access_token="a")
        except HarnessRuntimeError as exc:
            assert str(exc) == "AGENT_WEB_RUNTIME_START_FAILED"
        else:
            raise AssertionError("non-loopback startup URLs must be rejected")
    finally:
        manager.close_all()


def test_chat_and_mcp_use_staff_session_and_filtered_tools() -> None:
    repository = InMemoryPlatformRepository()
    platform = PlatformApplication(repository)
    staff = platform.create_staff("qa", "review")
    platform.grant_permission(staff.id, "agent.execute")
    platform.grant_permission(staff.id, "content.read")
    platform.grant_data_scope(staff.id, "ALL", "*")
    gateway = AgentGateway(platform, InMemoryAgentAuditLog())
    gateway.register(
        ToolResource(
            name="content.get_book",
            description="Read book",
            permission="content.read",
            input_schema={"type": "object"},
        ),
        lambda args: {"book_id": args["book_id"]},
    )
    signer = SessionSigner("harness-test-secret", ttl_seconds=3600)
    app = FastAPI()
    app.state.session_signer = signer
    app.state.agent_gateway = gateway
    app.include_router(
        build_agent_runtime_router(
            gateway,
            SimpleNamespace(
                run=lambda **_: SimpleNamespace(final_response="ok", finish_reason="completed"),
                web_url=lambda **_: "http://localhost:3080/?token=test-token",
            ),
            auth_required=True,
            authorize_staff=lambda *_: None,
        )
    )
    token = signer.issue_staff(staff.id)
    client = TestClient(app)
    headers = {"Authorization": f"Bearer {token}"}
    chat = client.post("/admin/api/v1/agent/chat", headers=headers, json={"message": "查询"})
    assert chat.status_code == 200
    assert chat.json()["response"] == "ok"
    resources = client.get("/admin/api/v1/agent/mcp", headers=headers)
    assert resources.status_code in {405, 422}
    mcp = client.post(
        "/admin/api/v1/agent/mcp",
        headers=headers,
        json={"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}},
    )
    assert mcp.status_code == 200
    assert mcp.json()["result"]["tools"][0]["name"] == "content.get_book"
    harness = client.get("/admin/api/v1/agent/harness-url", headers=headers)
    assert harness.status_code == 200
    assert harness.json()["url"].startswith("http://localhost:3080/")
