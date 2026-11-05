"""Group replies cannot widen the app or turn partial close into success."""

import json
from time import monotonic

import pytest

from kyrin.desktop.platforms.gnome_window_control import GnomeAppWindowController
from kyrin.desktop.window_control import WindowControlStatus
from kyrin.desktop.window_group import WindowGroupObservation
from tests.actions.test_window_group_close import GroupController


@pytest.mark.parametrize(
    "change", ["none", "wrong_app", "duplicate", "missing", "boolean_pid", "too_many"]
)
def test_prepare_group_reply_is_strictly_bound(
    monkeypatch: pytest.MonkeyPatch,
    change: str,
) -> None:
    now = monotonic()
    payload = {
        "app_id": "test.desktop",
        "generation": "g",
        "observed_at": now,
        "deadline": now + 10,
        "windows": [
            {"window_token": "1", "process_id": 42},
            {"window_token": "2", "process_id": 42},
        ],
    }
    if change == "wrong_app":
        payload["app_id"] = "other.desktop"
    elif change == "duplicate":
        payload["windows"] = [{"window_token": "1", "process_id": 42}] * 2
    elif change == "missing":
        del payload["generation"]
    elif change == "boolean_pid":
        payload["windows"] = [{"window_token": "1", "process_id": True}]
    elif change == "too_many":
        payload["windows"] = [
            {"window_token": str(i), "process_id": 42} for i in range(33)
        ]
    controller = GnomeAppWindowController({"test": "test.desktop"})
    monkeypatch.setattr(controller, "_call", lambda *a: (json.dumps(payload),))
    group = controller.prepare_close_all("test")
    assert isinstance(group, WindowGroupObservation) == (change == "none")


@pytest.mark.parametrize("reply", ["requested", "partial", "stale"])
@pytest.mark.parametrize("present", [True, False])
@pytest.mark.parametrize("saved", [True, False])
def test_close_group_requires_every_original_window_gone_without_retry(
    monkeypatch: pytest.MonkeyPatch,
    reply: str,
    present: bool,
    saved: bool,
) -> None:
    controller = GnomeAppWindowController({"telegram": "test.desktop"}, attempts=1)
    group = GroupController().group
    calls = []

    def call(method: str, *_args: str) -> tuple[str, ...]:
        calls.append(method)
        if method in {"CloseConfirmedAppWindows", "CloseAuthorizedAppWindows"}:
            return (reply,)
        return ('{"minimized":false}',) if present else ("no_window",)

    monkeypatch.setattr(controller, "_call", call)
    result = (
        controller.close_all_authorized(group) if saved
        else controller.close_all_confirmed(group)
    )
    assert (result is WindowControlStatus.CONFIRMED) == (
        reply == "requested" and not present
    )
    assert calls.count(
        "CloseAuthorizedAppWindows" if saved else "CloseConfirmedAppWindows"
    ) == 1
    assert not any(
        method in {"CloseAuthorizedWindow", "ControlAppWindow"} for method in calls
    )


def test_group_dialog_keeps_original_deadline_and_language(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    controller = GnomeAppWindowController({"telegram": "test.desktop"})
    group = GroupController().group

    def call(
        method: str, signature: str, *args: str, timeout_s: float | None = None
    ) -> tuple[str, ...]:
        assert (method, signature, args) == (
            "ConfirmAppWindowsClose",
            "ss",
            (group.generation, "fa-IR"),
        )
        assert timeout_s is not None and 0 < timeout_s <= 10
        return ("approved",)

    monkeypatch.setattr(controller, "_call", call)
    assert controller.confirm_close_all(group, "fa-IR")


def test_old_loaded_extension_cannot_start_bulk_close(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import subprocess

    from kyrin.desktop.platforms import gnome_window_control
    from tests.desktop.test_backend_protocol import bus_reply

    calls: list[str] = []

    def run(args: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        calls.append(args[-1])
        assert args[-1] == "GetCapabilities"
        return bus_reply("GetAppWindowState", "PrepareWindowClose")

    monkeypatch.setattr(gnome_window_control, "run_process", run)
    controller = GnomeAppWindowController({"test": "test.desktop"})
    assert controller.prepare_close_all("test") is None
    assert "PrepareAppWindowsClose" in controller.backend_status.reason
    assert calls == ["GetCapabilities"]


def test_saved_group_close_never_falls_back_to_dialog_on_old_backend(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import subprocess

    from kyrin.desktop.platforms import gnome_window_control
    from tests.desktop.test_backend_protocol import bus_reply

    calls: list[str] = []

    def run(args: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        calls.append(args[-1])
        assert args[-1] == "GetCapabilities"
        return bus_reply(
            "PrepareAppWindowsClose", "ConfirmAppWindowsClose",
            "CloseConfirmedAppWindows", "GetAppWindowState",
        )

    monkeypatch.setattr(gnome_window_control, "run_process", run)
    controller = GnomeAppWindowController({"telegram": "test.desktop"})
    assert controller.close_all_authorized(GroupController().group) is (
        WindowControlStatus.UNKNOWN
    )
    assert "CloseAuthorizedAppWindows" in controller.backend_status.reason
    assert calls == ["GetCapabilities"]
