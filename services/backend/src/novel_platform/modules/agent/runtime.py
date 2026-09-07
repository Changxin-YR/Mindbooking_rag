from __future__ import annotations

import importlib
import ipaddress
import json
import os
import re
import shlex
import subprocess
import sys
import threading
import urllib.error
import urllib.request
from collections.abc import Sequence
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Protocol, cast
from urllib.parse import parse_qs, urlsplit


class HarnessRuntimeError(RuntimeError):
    pass


class HarnessSession(Protocol):
    def run(self, prompt: str, *, session_id: str) -> Any: ...

    def close(self) -> None: ...


class AgentModelPort(Protocol):
    """Minimal model boundary used by the Agent runtime and deterministic tests."""

    def run(self, prompt: str, *, session_id: str) -> Any: ...

    def close(self) -> None: ...


class DeepSeekHarnessAdapter:
    """Adapter around the optional DeepSeek Harness SDK."""

    def __init__(self, factory: Any, **kwargs: Any) -> None:
        self._session = factory(**kwargs)

    def run(self, prompt: str, *, session_id: str) -> Any:
        return self._session.run(prompt, session_id=session_id)

    def close(self) -> None:
        close = getattr(self._session, "close", None)
        if callable(close):
            close()


class FakeAgentModelAdapter:
    """Deterministic adapter for CI; it never requires live model credentials."""

    def __init__(self, response: str = "已收到请求。请提供要操作的对象或编号。") -> None:
        self.response = response
        self.prompts: list[tuple[str, str]] = []

    def run(self, prompt: str, *, session_id: str) -> Any:
        self.prompts.append((session_id, prompt))
        return SimpleNamespace(final_response=self.response, finish_reason="completed")

    def close(self) -> None:
        return None


_WEB_URL_PATTERN = re.compile(r"\bdsh web:\s+(https?://[^\s()]+)")


def _extract_authenticated_url(line: str) -> str | None:
    """Return only a tokenized loopback URL announced by ``dsh web``."""
    match = _WEB_URL_PATTERN.search(line)
    if match is None:
        return None
    return _validate_authenticated_url(match.group(1).rstrip('.,;"'))


def _validate_authenticated_url(candidate: str) -> str | None:
    """Validate a Harness launch URL before exposing it to the Admin Console."""
    try:
        parsed = urlsplit(candidate)
    except ValueError:
        return None
    if parsed.scheme not in {"http", "https"} or parsed.hostname is None:
        return None
    if parsed.username is not None or parsed.password is not None:
        return None
    try:
        _ = parsed.port
    except ValueError:
        return None
    hostname = parsed.hostname.lower()
    is_loopback = hostname == "localhost"
    if not is_loopback:
        try:
            is_loopback = ipaddress.ip_address(hostname).is_loopback
        except ValueError:
            is_loopback = False
    if not is_loopback:
        return None
    token = parse_qs(parsed.query, keep_blank_values=False).get("token")
    if not token or not token[0]:
        return None
    return candidate


class NativeWebHarnessSession:
    """Own a single authenticated ``dsh --profile web`` process."""

    def __init__(
        self,
        *,
        command: Sequence[str],
        home: Path,
        cwd: Path,
        env: dict[str, str],
        startup_timeout_seconds: float,
        patch: Path,
    ) -> None:
        self.home = home
        self.cwd = cwd
        self.command = tuple(command)
        self.process = self._launch(env, patch)
        self.url: str | None = None
        self._closed = False
        self._url_ready = threading.Event()
        self._stdout_thread = threading.Thread(
            target=self._read_stdout,
            name="dsh-web-stdout",
            daemon=True,
        )
        self._stderr_thread = threading.Thread(
            target=self._read_stderr,
            name="dsh-web-stderr",
            daemon=True,
        )
        self._stdout_thread.start()
        self._stderr_thread.start()
        if not self._url_ready.wait(timeout=max(0.01, startup_timeout_seconds)):
            self.close()
            raise HarnessRuntimeError("AGENT_WEB_RUNTIME_START_FAILED")
        if self.url is None:
            self.close()
            raise HarnessRuntimeError("AGENT_WEB_RUNTIME_START_FAILED")

    def _launch(self, env: dict[str, str], patch: Path) -> subprocess.Popen[str]:
        args = [
            *self.command,
            "--profile",
            "web",
            "--no-open",
            "--host",
            "127.0.0.1",
            "--port",
            "0",
            "--patch",
            str(patch),
        ]
        try:
            return subprocess.Popen(
                args,
                cwd=str(self.cwd),
                env=env,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
                errors="replace",
                bufsize=1,
            )
        except OSError as exc:
            raise HarnessRuntimeError("AGENT_WEB_RUNTIME_START_FAILED") from exc

    def _read_stdout(self) -> None:
        stream = self.process.stdout
        if stream is None:
            self._url_ready.set()
            return
        try:
            for line in stream:
                if self.url is None:
                    url = _extract_authenticated_url(line)
                    if url is not None:
                        self.url = url
                        self._url_ready.set()
        finally:
            self._url_ready.set()

    def _read_stderr(self) -> None:
        stream = self.process.stderr
        if stream is None:
            return
        for _line in stream:
            # Drain diagnostics without exposing secrets or retaining unbounded output.
            continue

    def run(self, _prompt: str, *, session_id: str) -> Any:
        raise HarnessRuntimeError("AGENT_WEB_RUNTIME_INTERACTIVE")

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        process = self.process
        if process.poll() is None:
            try:
                process.terminate()
            except ProcessLookupError:
                pass
        try:
            process.wait(timeout=1.0)
        except subprocess.TimeoutExpired:
            try:
                process.kill()
            except ProcessLookupError:
                pass
            try:
                process.wait(timeout=1.0)
            except subprocess.TimeoutExpired:
                pass
        for stream in (process.stdout, process.stderr):
            if stream is not None:
                try:
                    stream.close()
                except OSError:
                    pass
        current = threading.current_thread()
        for thread in (self._stdout_thread, self._stderr_thread):
            if thread.is_alive() and thread is not current:
                thread.join(timeout=0.5)


def _safe(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]", "_", value)[:96] or "unknown"


class HarnessSessionManager:
    """Owns one real DeepSeek Harness SDK process per staff/session pair."""

    def __init__(
        self,
        *,
        backend_url: str,
        dsh_home: str,
        project_root: str,
        provider: str,
        model: str,
        api_key: str | None = None,
        base_url: str | None = None,
        profile: str = "sdk",
        request_timeout_seconds: float | None = 120.0,
        harness_factory: Any | None = None,
        runtime_mode: str = "sdk",
        web_command: Sequence[str] | str | None = None,
        dsh_command: Sequence[str] | str | None = None,
        dsh_bin: str | None = None,
        harness_repo: str | None = None,
        web_start_timeout_seconds: float = 30.0,
        web_bridge_url: str = "",
        web_bridge_secret: str = "",
    ) -> None:
        self.backend_url = backend_url.rstrip("/")
        self.dsh_home = Path(dsh_home).expanduser().resolve()
        self.project_root = Path(project_root).resolve()
        self.provider = provider
        self.model = model
        self.api_key = api_key
        self.base_url = base_url
        self.profile = profile
        self.request_timeout_seconds = request_timeout_seconds
        self._factory = harness_factory
        self.runtime_mode = runtime_mode
        configured_web_command = web_command if web_command is not None else dsh_command
        if isinstance(configured_web_command, str):
            configured_web_command = tuple(shlex.split(configured_web_command))
        self._web_command = tuple(configured_web_command or ())
        self._dsh_bin = dsh_bin
        self._harness_repo = (
            Path(harness_repo).expanduser().resolve() if harness_repo else self.project_root
        )
        self.web_start_timeout_seconds = web_start_timeout_seconds
        self.web_bridge_url = web_bridge_url.rstrip("/")
        self.web_bridge_secret = web_bridge_secret
        self._sessions: dict[str, tuple[str, str, HarnessSession]] = {}
        self._web_sessions: dict[str, tuple[str, str, NativeWebHarnessSession]] = {}
        self._web_bridge_sessions: dict[str, tuple[str, str]] = {}
        self._lock = threading.RLock()

    def run(self, *, actor_id: str, session_id: str, access_token: str, prompt: str) -> Any:
        with self._lock:
            current = self._sessions.get(session_id)
            if current is not None and current[0] != actor_id:
                raise HarnessRuntimeError("AGENT_SESSION_ACTOR_MISMATCH")
            web_current = self._web_sessions.get(session_id)
            bridge_current = self._web_bridge_sessions.get(session_id)
            if web_current is not None and web_current[0] != actor_id:
                raise HarnessRuntimeError("AGENT_SESSION_ACTOR_MISMATCH")
            if bridge_current is not None and bridge_current[0] != actor_id:
                raise HarnessRuntimeError("AGENT_SESSION_ACTOR_MISMATCH")
            if web_current is not None and web_current[1] != access_token:
                self._web_sessions.pop(session_id, None)
                web_current[2].close()
            if bridge_current is not None and bridge_current[1] != access_token:
                self._web_bridge_sessions.pop(session_id, None)
                self._release_web_bridge(bridge_current[0], session_id)
            if current is not None and current[1] != access_token:
                current[2].close()
                current = None
            if current is None:
                current = (actor_id, access_token, self._create(actor_id, session_id, access_token))
                self._sessions[session_id] = current
            harness = current[2]
        try:
            return harness.run(prompt, session_id=session_id)
        except Exception as exc:
            raise HarnessRuntimeError("AGENT_RUNTIME_FAILED") from exc

    def close(self, session_id: str) -> None:
        with self._lock:
            current = self._sessions.pop(session_id, None)
            web_current = self._web_sessions.pop(session_id, None)
            bridge_current = self._web_bridge_sessions.pop(session_id, None)
        if current is not None:
            current[2].close()
        if web_current is not None:
            web_current[2].close()
        if bridge_current is not None:
            self._release_web_bridge(bridge_current[0], session_id)

    def close_all(self) -> None:
        with self._lock:
            sessions = tuple(self._sessions.values())
            web_sessions = tuple(self._web_sessions.values())
            bridge_sessions = tuple(self._web_bridge_sessions.items())
            self._sessions.clear()
            self._web_sessions.clear()
            self._web_bridge_sessions.clear()
        for _, _, harness in sessions:
            harness.close()
        for _, _, harness in web_sessions:
            harness.close()
        for session_id, (actor_id, _token) in bridge_sessions:
            self._release_web_bridge(actor_id, session_id)

    def start_web(self, *, actor_id: str, session_id: str, access_token: str) -> str:
        """Start or reuse the authenticated native Web UI for a staff session."""
        if self.web_bridge_url and self.web_bridge_secret:
            with self._lock:
                bridge_current = self._web_bridge_sessions.get(session_id)
                if bridge_current is not None and bridge_current[0] != actor_id:
                    raise HarnessRuntimeError("AGENT_SESSION_ACTOR_MISMATCH")
                sdk_current = self._sessions.get(session_id)
                native_current = self._web_sessions.get(session_id)
                if sdk_current is not None and sdk_current[0] != actor_id:
                    raise HarnessRuntimeError("AGENT_SESSION_ACTOR_MISMATCH")
                if native_current is not None and native_current[0] != actor_id:
                    raise HarnessRuntimeError("AGENT_SESSION_ACTOR_MISMATCH")
                if sdk_current is not None and sdk_current[1] != access_token:
                    self._sessions.pop(session_id, None)
                    sdk_current[2].close()
                if native_current is not None and native_current[1] != access_token:
                    self._web_sessions.pop(session_id, None)
                    native_current[2].close()
                if bridge_current is not None and bridge_current[1] != access_token:
                    self._web_bridge_sessions.pop(session_id, None)
                    self._release_web_bridge(bridge_current[0], session_id)
            url = self._start_web_bridge(actor_id, session_id, access_token)
            validated_url = _validate_authenticated_url(url)
            if validated_url is None:
                raise HarnessRuntimeError("AGENT_WEB_RUNTIME_UNAVAILABLE")
            with self._lock:
                self._web_bridge_sessions[session_id] = (actor_id, access_token)
            return validated_url
        with self._lock:
            current = self._web_sessions.get(session_id)
            if current is not None and current[0] != actor_id:
                raise HarnessRuntimeError("AGENT_SESSION_ACTOR_MISMATCH")
            sdk_current = self._sessions.get(session_id)
            bridge_current = self._web_bridge_sessions.get(session_id)
            if sdk_current is not None and sdk_current[0] != actor_id:
                raise HarnessRuntimeError("AGENT_SESSION_ACTOR_MISMATCH")
            if bridge_current is not None and bridge_current[0] != actor_id:
                raise HarnessRuntimeError("AGENT_SESSION_ACTOR_MISMATCH")
            if sdk_current is not None and sdk_current[1] != access_token:
                self._sessions.pop(session_id, None)
                sdk_current[2].close()
            if bridge_current is not None and bridge_current[1] != access_token:
                self._web_bridge_sessions.pop(session_id, None)
                self._release_web_bridge(bridge_current[0], session_id)
            if current is not None and current[1] == access_token and current[2].url:
                return current[2].url
            if current is not None:
                self._web_sessions.pop(session_id, None)
                current[2].close()
            try:
                web = self._create_web(actor_id, session_id, access_token)
            except HarnessRuntimeError:
                raise
            except Exception as exc:
                raise HarnessRuntimeError("AGENT_WEB_RUNTIME_START_FAILED") from exc
            self._web_sessions[session_id] = (actor_id, access_token, web)
            if web.url is None:
                web.close()
                self._web_sessions.pop(session_id, None)
                raise HarnessRuntimeError("AGENT_WEB_RUNTIME_START_FAILED")
            return web.url

    def _start_web_bridge(self, actor_id: str, session_id: str, access_token: str) -> str:
        payload = json.dumps(
            {"actor_id": actor_id, "session_id": session_id, "access_token": access_token}
        ).encode("utf-8")
        request = urllib.request.Request(
            f"{self.web_bridge_url}/allocate",
            data=payload,
            method="POST",
            headers={
                "Content-Type": "application/json",
                "X-Harness-Bridge-Secret": self.web_bridge_secret,
            },
        )
        try:
            with urllib.request.urlopen(
                request, timeout=self.web_start_timeout_seconds
            ) as response:
                body = json.loads(response.read().decode("utf-8"))
        except (OSError, urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
            raise HarnessRuntimeError("AGENT_WEB_RUNTIME_UNAVAILABLE") from exc
        url = body.get("url") if isinstance(body, dict) else None
        if not isinstance(url, str) or not url:
            raise HarnessRuntimeError("AGENT_WEB_RUNTIME_UNAVAILABLE")
        return url

    def _release_web_bridge(self, actor_id: str, session_id: str) -> None:
        if not self.web_bridge_url or not self.web_bridge_secret:
            return
        payload = json.dumps({"actor_id": actor_id, "session_id": session_id}).encode("utf-8")
        request = urllib.request.Request(
            f"{self.web_bridge_url}/release",
            data=payload,
            method="POST",
            headers={
                "Content-Type": "application/json",
                "X-Harness-Bridge-Secret": self.web_bridge_secret,
            },
        )
        try:
            urllib.request.urlopen(request, timeout=2.0).close()
        except OSError, urllib.error.URLError, TimeoutError:
            return

    def web_url(self, *, actor_id: str, session_id: str, access_token: str) -> str:
        """Compatibility alias for callers that request the Web UI URL."""
        return self.start_web(actor_id=actor_id, session_id=session_id, access_token=access_token)

    def _create(self, actor_id: str, session_id: str, access_token: str) -> HarnessSession:
        if self.runtime_mode.lower() in {"fake", "test", "deterministic"} and self._factory is None:
            return cast(HarnessSession, FakeAgentModelAdapter())
        factory = self._factory or _load_harness_factory()
        home = self.dsh_home / _safe(actor_id) / _safe(session_id)
        home.mkdir(parents=True, exist_ok=True)
        patch = self._write_patch(home)
        env = {
            "AGENT_ACCESS_TOKEN": access_token,
            "AGENT_SESSION_ID": session_id,
        }
        return cast(
            HarnessSession,
            DeepSeekHarnessAdapter(
                factory,
                dsh_home=str(home),
                cwd=str(self.project_root),
                provider=self.provider,
                model=self.model,
                profile=self.profile,
                patches=(str(patch),),
                request_timeout_seconds=self.request_timeout_seconds,
                api_key=self.api_key,
                base_url=self.base_url,
                env=env,
            ),
        )

    def _create_web(
        self, actor_id: str, session_id: str, access_token: str
    ) -> NativeWebHarnessSession:
        home = self.dsh_home / _safe(actor_id) / _safe(session_id)
        home.mkdir(parents=True, exist_ok=True)
        patch = self._write_patch(home)
        env = os.environ.copy()
        env.update(
            {
                "DSH_HOME": str(home),
                "AGENT_ACCESS_TOKEN": access_token,
                "AGENT_SESSION_ID": session_id,
            }
        )
        return NativeWebHarnessSession(
            command=self._resolve_web_command(),
            home=home,
            cwd=self._harness_repo,
            env=env,
            startup_timeout_seconds=self.web_start_timeout_seconds,
            patch=patch,
        )

    def _resolve_web_command(self) -> tuple[str, ...]:
        if self._web_command:
            return self._web_command
        configured = os.getenv("DEEPSEEK_HARNESS_WEB_COMMAND", "").strip()
        if configured:
            parsed = tuple(shlex.split(configured))
            if parsed:
                return parsed
        executable = self._dsh_bin or os.getenv("DEEPSEEK_HARNESS_DSH_BIN", "dsh").strip()
        if not executable:
            raise HarnessRuntimeError("AGENT_WEB_RUNTIME_UNAVAILABLE")
        return (executable,)

    def _write_patch(self, home: Path) -> Path:
        patch = home / "agent-tools.cordis.yml"
        patch.write_text(
            "- id: novel-platform-agent-tools\n"
            "  name: '@deepseek-ai/dsh-mcp-client'\n"
            "  config:\n"
            "    serverName: novel_platform\n"
            "    transport: streamable-http\n"
            f"    url: {self.backend_url}/admin/api/v1/agent/mcp\n"
            "    headers:\n"
            "      Authorization: !!js '`Bearer ${process.env.AGENT_ACCESS_TOKEN}`'\n"
            "      X-Agent-Session: !!js 'process.env.AGENT_SESSION_ID'\n",
            encoding="utf-8",
        )
        return patch


def _load_harness_factory() -> Any:
    sdk_path = os.getenv("DEEPSEEK_HARNESS_SDK_PATH", "").strip()
    if sdk_path and sdk_path not in sys.path:
        sys.path.insert(0, sdk_path)
    try:
        return importlib.import_module("deepseek_harness").DeepSeekHarness
    except (ImportError, AttributeError) as exc:
        raise HarnessRuntimeError("AGENT_RUNTIME_UNAVAILABLE") from exc


__all__ = [
    "AgentModelPort",
    "DeepSeekHarnessAdapter",
    "FakeAgentModelAdapter",
    "HarnessRuntimeError",
    "HarnessSessionManager",
]
