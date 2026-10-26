"""Live session reuse, token semantics and the private owner request lease."""

import json
import socket
import subprocess
import sys
from collections.abc import Iterator
from dataclasses import replace
from inspect import getsource
from pathlib import Path
from threading import Event, Thread
from time import monotonic, sleep
from typing import Any

import pytest

from kyrin.actions.platforms.input_session import InputSessionService, Wire
from kyrin.actions.platforms.portal_input import PortalInputSession
from kyrin.app.permission_token import read_opaque_token, save_opaque_token
from kyrin.app.permissions import PermissionPolicy
from kyrin.app.settings import AppSettings
from kyrin.operations import OperationStopped, budget


class FakePortal:
    connection = object()
    version = 2
    available = 3

    def __init__(self) -> None:
        self.calls: list[tuple[str, tuple[Any, ...]]] = []
        self.live = True
        self.started: dict[str, Any] | None = {"devices": 3, "restore_token": "next"}

    def request(self, method: str, args: tuple[Any, ...]) -> dict[str, Any] | None:
        self.calls.append((method, args))
        if method == "CreateSession":
            return {"session_handle": "/session/one"}
        if method == "Start":
            return self.started
        return {}

    def watch(self, session: str) -> None:
        self.live = True

    def alive(self, session: str) -> bool:
        return self.live

    def close(self, session: str) -> None:
        self.calls.append(("Close", (session,)))

    def options(self, devices: int, token: str | None) -> dict[str, Any]:
        result: dict[str, Any] = {"types": devices}
        if self.version >= 2:
            result["persist_mode"] = 2
            if token:
                result["restore_token"] = token
        return result


def test_live_session_reused_without_start_or_token_per_operation(
    tmp_path: Path,
) -> None:
    portal = FakePortal()
    session = PortalInputSession(portal, tmp_path / "token")
    session.prepare(2, lambda: None)
    acquired = [session.acquire(2) for _ in range(10)]
    first = acquired[0]
    assert first is not None
    assert all(item is not None and item[:2] == first[:2] for item in acquired)
    assert [name for name, _ in portal.calls].count("Start") == 1
    assert not any(name == "Close" for name, _ in portal.calls)
    assert session.status()["state"] == "ready"
    session.close()
    assert session.acquire(2) is None


@pytest.mark.parametrize("token", ["valid", "invalid", None])
def test_token_claim_and_rotation(tmp_path: Path, token: str | None) -> None:
    portal = FakePortal()
    path = tmp_path / "token"
    if token is not None:
        save_opaque_token(path, token)
    if token == "invalid":
        portal.started = None
    session = PortalInputSession(portal, path)
    session.prepare(3, lambda: None)
    options = portal.calls[1][1][1]
    assert options.get("restore_token") == token
    assert read_opaque_token(path) == (None if token == "invalid" else "next")
    assert session.status()["state"] == (
        "interaction_required" if token == "invalid" else "ready"
    )


@pytest.mark.parametrize("version", [1, 2])
def test_current_session_usable_without_persistence(
    tmp_path: Path, version: int
) -> None:
    portal = FakePortal()
    portal.version = version
    portal.started = {"devices": 2}
    save_opaque_token(tmp_path / "token", "consumed")
    session = PortalInputSession(portal, tmp_path / "token")
    result = session.prepare(2, lambda: None)
    assert result["state"] == "ready" and not result["persistent"]
    assert session.acquire(2) is not None
    assert session.acquire(3) is None
    assert not session.token_path.exists()
    if version == 1:
        assert portal.calls[1][1][1] == {"types": 2}


def test_disconnected_or_insufficient_session_never_starts_from_acquire(
    tmp_path: Path,
) -> None:
    portal = FakePortal()
    portal.started = {"devices": 2}
    session = PortalInputSession(portal, tmp_path / "token")
    session.prepare(2, lambda: None)
    assert session.acquire(3) is None
    portal.live = False
    assert session.acquire(2) is None
    assert session.state == "disconnected"
    assert [name for name, _ in portal.calls].count("Start") == 1
    session.prepare(3, lambda: None)  # explicit repair may fail on partial OS grant
    assert session.acquire(3) is None


def test_cancel_setup_before_late_start_can_save_or_publish(tmp_path: Path) -> None:
    portal = FakePortal()
    path = tmp_path / "token"
    save_opaque_token(path, "old")
    session = PortalInputSession(portal, path)

    def check() -> None:
        if any(name == "Start" for name, _ in portal.calls):
            raise OperationStopped("revoked during Start")

    with pytest.raises(OperationStopped):
        session.prepare(2, check)
    assert not path.exists()
    assert session.acquire(2) is None
    assert portal.calls[-1][0] == "Close"


def test_unsupported_devices_never_open_portal(tmp_path: Path) -> None:
    portal = FakePortal()
    portal.available = 2
    session = PortalInputSession(portal, tmp_path / "token")
    assert session.prepare(3, lambda: None)["state"] == "unsupported"
    assert not portal.calls


@pytest.fixture
def service(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> Iterator[InputSessionService]:
    """Real child process and wire, synthetic portal and bounded test actuator."""
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))
    script = tmp_path / "owner.py"
    script.write_text(
        "from typing import Any\n"
        + getsource(FakePortal)
        + """
import socket, sys, types, os, time
from kyrin.actions.platforms.input_session import Wire
from kyrin.actions.platforms.input_session_owner import serve
from kyrin.actions.platforms.helper_lifecycle import INPUT_CHECK
backend = FakePortal()
backend.GLib = types.SimpleNamespace(Error=RuntimeError)
backend.started = {"devices": 2}
if os.environ.get("KYRIN_TEST_PERSISTENT"):
    original_persistent_request = backend.request
    previous_token = "initial"
    def persistent_request(method, args):
        global previous_token
        if method == "SelectDevices":
            previous_token = args[1].get("restore_token", "initial")
        if method == "Start":
            return {"devices": 3, "restore_token": previous_token + "-next"}
        return original_persistent_request(method, args)
    backend.request = persistent_request
if os.environ.get("KYRIN_TEST_BLOCK_START"):
    original_request = backend.request
    def blocked_request(method, args):
        if method == "Start":
            from pathlib import Path
            Path(os.environ["KYRIN_TEST_BLOCK_START"]).touch()
            time.sleep(30)
        return original_request(method, args)
    backend.request = blocked_request
module = types.ModuleType("kyrin.actions.platforms.desktop_scroll_helper")
def action():
    if sys.argv[1:] == ["crash"]:
        os._exit(7)
    if sys.argv[1:] == ["hang"]:
        time.sleep(30)
    INPUT_CHECK.get()()
    print("SCROLL_DISPATCHED", id(backend.connection), sys.argv[1:])
    return 0
module.main = action
sys.modules[module.__name__] = module
for name in ("desktop_control_helper", "telegram_portal_helper"):
    sys.modules["kyrin.actions.platforms." + name] = module
serve(Wire(socket.socket(fileno=int(sys.argv[1]))), backend)
"""
    )
    instance = InputSessionService()
    instance.configure(
        PermissionPolicy(
            AppSettings(action_execution_enabled=True, allow_desktop_scroll=True)
        )
    )

    def launch() -> None:
        parent, child = socket.socketpair()
        parent.settimeout(0.2)
        instance._process = subprocess.Popen(
            [sys.executable, str(script), str(child.fileno())],
            pass_fds=(child.fileno(),),
        )
        child.close()
        instance._wire = Wire(parent)

    monkeypatch.setattr(instance, "_start", launch)
    yield instance
    instance.disconnect()


def execute(
    service: InputSessionService, *args: str, timeout: float = 2
) -> subprocess.CompletedProcess[str]:
    return service.run(
        ["/usr/bin/python3", "desktop_scroll_helper.py", *args], timeout=timeout
    )


def test_owner_wire_reuses_one_live_session_and_checks_new_targets(
    service: InputSessionService,
) -> None:
    assert service.prepare("desktop_scroll")["state"] == "ready"
    outputs = [
        execute(service, "first" if index < 5 else "second").stdout
        for index in range(10)
    ]
    assert len({line.split()[1] for line in outputs}) == 1
    assert "first" in outputs[0] and "second" in outputs[-1]
    status = service.status()
    assert status["starts"] == 1 and status["devices"] == 2
    assert not status["persistent"]
    # Turning off microphone settings is unrelated to the input owner.
    policy = service._policy
    assert policy is not None
    service.configure(
        PermissionPolicy(replace(policy.settings, listening_enabled=False))
    )
    assert service.status()["starts"] == 1
    assert execute(service, "third").returncode == 0


def test_file_token_without_live_owner_is_not_ready(
    service: InputSessionService,
) -> None:
    save_opaque_token(Path(service_token_path()), "old")
    assert execute(service).returncode == 3
    assert service._process is None
    assert service.status()["state"] == "unprepared"


def service_token_path() -> Path:
    from kyrin.app.permission_token import permission_token_path

    return permission_token_path("desktop-input")


def test_one_setup_and_restart_restore_all_selected_input_capabilities(
    service: InputSessionService, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("KYRIN_TEST_PERSISTENT", "1")
    policy = PermissionPolicy(
        AppSettings(action_execution_enabled=True, trust_all_capabilities=True)
    )
    service.configure(policy)
    assert service.startup_capability() is None  # First run needs explicit setup.
    assert service.prepare("desktop_scroll")["devices"] == 3
    assert read_opaque_token(service_token_path()) == "initial-next"
    for index in range(2):
        service.disconnect()  # Same transition as actual application exit.
        # A new application service has no live owner or in-memory grants.
        restarted = InputSessionService()
        restarted.configure(policy)
        # Reuse only the fixture's synthetic process launcher, with the new owner.
        def launch(restarted: InputSessionService = restarted) -> None:
            service._start()
            restarted._process, service._process = service._process, None
            restarted._wire, service._wire = service._wire, None

        monkeypatch.setattr(restarted, "_start", launch)
        try:
            assert restarted.startup_capability() == "telegram_chat"
            restored = restarted.prepare("telegram_chat", restore=True)
            assert restored["state"] == "ready" and restored["devices"] == 3
            assert restored["starts"] == 1
            for name in (
                "desktop_scroll_helper.py", "desktop_control_helper.py",
                "telegram_portal_helper.py",
            ):
                result = restarted.run(["python", name, "target"], timeout=2)
                assert result.returncode == 0
            assert restarted.status()["starts"] == 1
            expected = "initial" + "-next" * (index + 2)
            assert read_opaque_token(service_token_path()) == expected
            assert restarted.startup_capability() is None
        finally:
            restarted.disconnect()


@pytest.mark.parametrize(
    "case", ["missing", "corrupt", "insecure", "disabled", "unselected"]
)
def test_startup_never_requests_fresh_access_without_saved_enabled_grant(
    service: InputSessionService, case: str
) -> None:
    path = service_token_path()
    if case != "missing":
        save_opaque_token(path, "saved")
    if case == "corrupt":
        path.write_bytes(b"\x00")
    elif case == "insecure":
        path.chmod(0o644)
    elif case == "disabled":
        service.configure(PermissionPolicy(AppSettings(allow_desktop_scroll=True)))
    elif case == "unselected":
        service.configure(PermissionPolicy(AppSettings(action_execution_enabled=True)))
    assert service.startup_capability() is None
    assert service.prepare("desktop_scroll", restore=True)["state"] != "ready"
    assert service._process is None


def test_token_removed_after_startup_selection_does_not_open_portal(
    service: InputSessionService,
) -> None:
    save_opaque_token(service_token_path(), "saved")
    assert service.startup_capability() == "desktop_scroll"
    service_token_path().unlink()
    assert service.prepare("desktop_scroll", restore=True)["state"] != "ready"
    assert service._process is None


def test_shared_grant_does_not_authorize_other_capability(
    service: InputSessionService,
) -> None:
    service.prepare("desktop_scroll")
    reply = service.run(["python", "desktop_control_helper.py"], timeout=1)
    assert reply.returncode == 3
    assert service.status()["starts"] == 1
    service.configure(PermissionPolicy(AppSettings(action_execution_enabled=True)))
    assert service.status()["state"] == "disconnected"
    assert execute(service).returncode == 3
    assert not service_token_path().exists()


def test_crash_is_not_retried_and_next_command_requires_setup(
    service: InputSessionService,
) -> None:
    service.prepare("desktop_scroll")
    with pytest.raises(OSError):
        execute(service, "crash")
    assert execute(service).returncode == 3
    assert service._process is None


@pytest.mark.parametrize("cancel", [True, False])
def test_request_cancel_or_deadline_kills_owner_before_late_input(
    service: InputSessionService, cancel: bool
) -> None:
    service.prepare("desktop_scroll")
    stopped = Event()

    def stop() -> None:
        sleep(0.05)
        stopped.set()

    timer = Thread(target=stop, daemon=True)
    timer.start()
    with (
        pytest.raises(OperationStopped),
        budget(
            1 if cancel else 0.06, cancelled=stopped.is_set if cancel else lambda: False
        ),
    ):
        execute(service, "hang")
    assert service._process is None
    assert execute(service).returncode == 3


def test_revoke_during_request_cannot_publish_late_response(
    service: InputSessionService,
) -> None:
    service.prepare("desktop_scroll")
    errors: list[BaseException] = []

    def run() -> None:
        try:
            execute(service, "hang")
        except (OSError, OperationStopped) as error:
            errors.append(error)

    worker = Thread(target=run)
    worker.start()
    sleep(0.05)
    service.configure(PermissionPolicy(AppSettings()))
    worker.join(2)
    assert not worker.is_alive() and errors
    assert execute(service).returncode == 3


def test_wire_rejects_non_object_and_preserves_framing() -> None:
    left, right = socket.socketpair()
    try:
        wire = Wire(left)
        right.sendall(json.dumps(["bad"]).encode() + b"\n")
        with pytest.raises(ValueError):
            wire.receive(0.1)
        right.sendall(b'{"id":"a"}\n{"id":"b"}\n')
        assert wire.receive(0.1) == {"id": "a"}
        assert wire.receive(0.1) == {"id": "b"}
    finally:
        left.close()
        right.close()


def test_revocation_during_setup_consumes_token_and_reaps_owner(
    service: InputSessionService, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    marker = tmp_path / "starting"
    monkeypatch.setenv("KYRIN_TEST_BLOCK_START", str(marker))
    save_opaque_token(service_token_path(), "single-use")
    errors: list[BaseException] = []

    def prepare() -> None:
        try:
            service.prepare("desktop_scroll")
        except (OSError, OperationStopped) as error:
            errors.append(error)

    worker = Thread(target=prepare)
    worker.start()
    deadline = monotonic() + 2
    while not marker.exists() and monotonic() < deadline:
        sleep(0.01)
    assert marker.exists()
    service.configure(PermissionPolicy(AppSettings()))
    worker.join(2)
    assert not worker.is_alive() and errors
    assert not service_token_path().exists()
    assert service._process is None
    assert execute(service).returncode == 3


def test_cancel_waiter_does_not_release_or_cancel_active_owner(
    service: InputSessionService,
) -> None:
    service.prepare("desktop_scroll")
    errors: list[BaseException] = []

    def run() -> None:
        try:
            execute(service, "hang")
        except (OSError, OperationStopped) as error:
            errors.append(error)

    worker = Thread(target=run)
    worker.start()
    deadline = monotonic() + 1
    while not service._wire_lock.locked() and monotonic() < deadline:
        sleep(0.005)
    process = service._process
    with pytest.raises(OperationStopped), budget(0.05):
        execute(service, "waiting")
    assert service._process is process
    service.disconnect()
    worker.join(2)
    assert errors and not worker.is_alive()


def test_unmatched_late_response_drops_owner_without_replay(
    service: InputSessionService, monkeypatch: pytest.MonkeyPatch
) -> None:
    service.prepare("desktop_scroll")
    assert service._wire is not None
    receive = service._wire.receive

    def wrong_id(timeout: float) -> dict[str, Any] | None:
        response = receive(timeout)
        if response is not None:
            response["id"] = "expired-request"
        return response

    monkeypatch.setattr(service._wire, "receive", wrong_id)
    with pytest.raises(ConnectionError):
        execute(service, "once")
    assert execute(service, "next").returncode == 3


@pytest.mark.parametrize("restore", [False, True])
def test_prepare_waiting_before_disconnect_cannot_restart_owner(
    service: InputSessionService, monkeypatch: pytest.MonkeyPatch, restore: bool
) -> None:
    from threading import Lock

    attempted = Event()
    save_opaque_token(service_token_path(), "saved")
    lock = Lock()
    lock.acquire()

    class ObservedLock:
        def acquire(self, *, timeout: float) -> bool:
            attempted.set()
            return lock.acquire(timeout=timeout)

        def release(self) -> None:
            lock.release()

    monkeypatch.setattr(service, "_wire_lock", ObservedLock())
    errors: list[BaseException] = []

    def prepare() -> None:
        try:
            service.prepare("desktop_scroll", restore=restore)
        except OperationStopped as error:
            errors.append(error)

    worker = Thread(target=prepare)
    worker.start()
    assert attempted.wait(1)
    service.disconnect()
    lock.release()
    worker.join(2)
    assert not worker.is_alive() and errors
    assert service._process is None


def test_disconnect_finishes_reaping_before_allowing_new_setup(
    service: InputSessionService, monkeypatch: pytest.MonkeyPatch
) -> None:
    from typing import cast

    reaping, finish = Event(), Event()
    order: list[str] = []

    class OldOwner:
        def terminate(self) -> None:
            pass

        def wait(self, timeout: float) -> int:
            reaping.set()
            assert finish.wait(2)
            order.append("reaped")
            return 0

    service._process = cast(subprocess.Popen[bytes], OldOwner())
    launch = service._start

    def start() -> None:
        order.append("started")
        launch()

    monkeypatch.setattr(service, "_start", start)
    disconnected = Thread(target=service.disconnect)
    disconnected.start()
    assert reaping.wait(1)
    results: list[dict[str, Any]] = []
    prepared = Thread(target=lambda: results.append(service.prepare("desktop_scroll")))
    prepared.start()
    finish.set()
    disconnected.join(2)
    prepared.join(2)
    assert not disconnected.is_alive() and not prepared.is_alive()
    assert order == ["reaped", "started"]
    assert results[0]["state"] == "ready"


@pytest.mark.parametrize(
    "field,value",
    [
        ("capabilities", None),
        ("state", "invented"),
        ("devices", "2"),
        ("starts", -1),
        ("protocol_version", True),
    ],
)
def test_malformed_owner_response_invalidates_session(
    service: InputSessionService,
    monkeypatch: pytest.MonkeyPatch,
    field: str,
    value: object,
) -> None:
    service.prepare("desktop_scroll")
    assert service._wire is not None
    receive = service._wire.receive

    def malformed(timeout: float) -> dict[str, Any] | None:
        response = receive(timeout)
        if response is not None and not response.get("checkpoint"):
            response[field] = value
        return response

    monkeypatch.setattr(service._wire, "receive", malformed)
    with pytest.raises(ConnectionError):
        execute(service, "once")
    assert execute(service, "after").returncode == 3


def test_late_closed_signal_for_replaced_session_cannot_close_new_session() -> None:
    from kyrin.actions.platforms.input_session_owner import GioPortalBackend

    backend = GioPortalBackend.__new__(GioPortalBackend)
    backend.session_path = "/new"
    backend.closed = False
    backend._closed(None, "portal", "/old")
    assert not backend.closed
    backend._closed(None, "portal", "/new")
    assert backend.closed
