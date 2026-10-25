"""The GNOME adapter confirms state instead of trusting a request reply."""

import json
import subprocess
from time import monotonic

import pytest

from kyrin.backend_protocol import BackendStatus
from kyrin.desktop.platforms import gnome_window_control
from kyrin.desktop.platforms.gnome_window_control import GnomeAppWindowController
from kyrin.desktop.window_control import WindowControlStatus, WindowOperation
from kyrin.desktop.window_observation import WindowObservation


def test_minimize_needs_observed_minimized_state(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    controller = GnomeAppWindowController(
        {"telegram": "telegram.desktop"}, attempts=2, retry_delay_s=0
    )
    replies = iter(
        (
            ("requested", "17"),
            ('{"minimized":false}',),
            ('{"minimized":true}',),
        )
    )
    calls: list[tuple[str, str, tuple[str, ...]]] = []

    def call(method: str, signature: str, *args: str) -> tuple[str, ...]:
        calls.append((method, signature, args))
        return next(replies)

    monkeypatch.setattr(controller, "_call", call)
    assert (
        controller.control("telegram", WindowOperation.MINIMIZE)
        is WindowControlStatus.CONFIRMED
    )
    assert calls == [
        ("ControlAppWindow", "ss", ("telegram.desktop", "minimize")),
        ("GetAppWindowState", "ss", ("telegram.desktop", "17")),
        ("GetAppWindowState", "ss", ("telegram.desktop", "17")),
    ]


def test_close_does_not_claim_success_while_window_remains(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    controller = GnomeAppWindowController(
        {"telegram": "telegram.desktop"}, attempts=2, retry_delay_s=0
    )
    replies = iter(
        (
            ("requested",),
            ('{"minimized":false}',),
            ('{"minimized":false}',),
        )
    )
    monkeypatch.setattr(controller, "_call", lambda *args: next(replies))

    assert controller.close_confirmed(_window()) is WindowControlStatus.UNKNOWN
    assert controller.close_error_code == "window_close_unverified:window_present"


def _window() -> WindowObservation:
    now = monotonic()
    return WindowObservation("telegram", 42, "17", "decision", now, now + 10)


def test_prepared_close_uses_mapped_window_and_verifies_exact_token(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    controller = GnomeAppWindowController({"telegram": "telegram.desktop"})
    original = _window()
    replies = iter(
        (
            (original.to_json().replace('"telegram"', '"telegram.desktop"'),),
            ("requested",),
            ("no_window",),
        )
    )
    calls: list[tuple[str, str, tuple[str, ...]]] = []

    def call(method: str, signature: str, *args: str) -> tuple[str, ...]:
        calls.append((method, signature, args))
        return next(replies)

    monkeypatch.setattr(controller, "_call", call)
    window = controller.prepare_close("desktop", 2)
    assert window == original
    assert controller.close_confirmed(window) is WindowControlStatus.CONFIRMED
    assert controller.close_error_code is None
    assert calls == [
        ("PrepareWindowClose", "su", ("", "2")),
        ("CloseConfirmedWindow", "s", ("decision",)),
        ("GetAppWindowState", "ss", ("telegram.desktop", "17")),
    ]


def test_rejected_commit_never_retries_or_calls_legacy_close(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    controller = GnomeAppWindowController({"telegram": "telegram.desktop"})
    calls: list[str] = []

    def call(method: str, *_args: str) -> tuple[str, ...]:
        calls.append(method)
        return ("stale",)

    monkeypatch.setattr(controller, "_call", call)
    assert controller.close_confirmed(_window()) is WindowControlStatus.UNKNOWN
    assert calls == ["CloseConfirmedWindow"]


@pytest.mark.parametrize("reply", ["stale", "unavailable", "confirmation_required"])
def test_rejection_is_distinct_from_an_issued_but_unverified_close(
    monkeypatch: pytest.MonkeyPatch, reply: str
) -> None:
    controller = GnomeAppWindowController({"telegram": "telegram.desktop"})
    calls: list[str] = []

    def call(method: str, *_args: str) -> tuple[str, ...]:
        calls.append(method)
        return (reply,)

    monkeypatch.setattr(controller, "_call", call)
    assert controller.close_confirmed(_window()) is WindowControlStatus.UNKNOWN
    assert controller.close_error_code == "window_close_rejected:" + reply
    assert calls == ["CloseConfirmedWindow"]


@pytest.mark.parametrize(
    ("response", "reason"),
    [
        ("timeout", "timeout"),
        ("os_error", "transport_unavailable"),
        ("failed", "call_failed"),
        ("malformed", "invalid_reply"),
        ("unexpected", "invalid_reply"),
    ],
)
def test_commit_failure_is_content_free_and_never_retried(
    monkeypatch: pytest.MonkeyPatch, response: str, reason: str
) -> None:
    controller = GnomeAppWindowController({"telegram": "telegram.desktop"})
    monkeypatch.setattr(
        gnome_window_control,
        "probe_gnome",
        lambda *args, **kwargs: BackendStatus(True, "ready"),
    )
    calls: list[list[str]] = []
    private = "private-window-title-and-payload"

    def run(args: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
        calls.append(args)
        if response == "timeout":
            raise subprocess.TimeoutExpired(args, 1, output=private, stderr=private)
        if response == "os_error":
            raise OSError(private)
        return subprocess.CompletedProcess(
            args,
            1 if response == "failed" else 0,
            private
            if response != "unexpected"
            else json.dumps({"type": "s", "data": [private]}),
            private,
        )

    monkeypatch.setattr(gnome_window_control, "run_process", run)
    assert controller.close_confirmed(_window()) is WindowControlStatus.UNKNOWN
    assert controller.close_error_code == "window_close_commit_unknown:" + reason
    assert len(calls) == 1 and "CloseConfirmedWindow" in calls[0]
    assert private not in controller.close_error_code


def test_failed_state_read_is_not_reported_as_a_rejected_close(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    controller = GnomeAppWindowController(
        {"telegram": "telegram.desktop"}, attempts=2, retry_delay_s=0
    )
    replies = iter((("requested",), None, ("unknown",)))
    monkeypatch.setattr(controller, "_call", lambda *args: next(replies))
    assert controller.close_confirmed(_window()) is WindowControlStatus.UNKNOWN
    assert controller.close_error_code == "window_close_unverified:state_unavailable"


def test_new_success_clears_a_previous_close_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    controller = GnomeAppWindowController({"telegram": "telegram.desktop"})
    replies = iter((("stale",), ("requested",), ("no_window",)))
    monkeypatch.setattr(controller, "_call", lambda *args: next(replies))
    assert controller.close_confirmed(_window()) is WindowControlStatus.UNKNOWN
    assert controller.close_error_code == "window_close_rejected:stale"
    assert controller.close_confirmed(_window()) is WindowControlStatus.CONFIRMED
    assert controller.close_error_code is None


def test_unknown_app_never_contacts_shell(monkeypatch: pytest.MonkeyPatch) -> None:
    controller = GnomeAppWindowController({"telegram": "telegram.desktop"})
    monkeypatch.setattr(
        controller,
        "_call",
        lambda *args: (_ for _ in ()).throw(AssertionError("called GNOME")),
    )
    assert (
        controller.control("other", WindowOperation.CLOSE)
        is WindowControlStatus.UNAVAILABLE
    )


def test_native_confirmation_uses_original_generation_language_and_deadline(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    controller = GnomeAppWindowController({"telegram": "telegram.desktop"})
    window = _window()
    calls: list[tuple[str, str, tuple[str, ...]]] = []

    def call(
        method: str, signature: str, *args: str, timeout_s: float | None = None
    ) -> tuple[str, ...]:
        calls.append((method, signature, args))
        assert timeout_s is not None and 0 < timeout_s <= 10
        return ("approved",)

    monkeypatch.setattr(controller, "_call", call)
    assert controller.confirm_close(window, "fa")
    assert calls == [("ConfirmWindowClose", "ss", (window.generation, "fa"))]
    monkeypatch.setattr(gnome_window_control, "monotonic", lambda: window.deadline)
    assert not controller.confirm_close(window, "fa")
    assert len(calls) == 1


def test_old_loaded_extension_cannot_prepare_close_or_open_legacy_dialog(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[str] = []

    def run(args: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        calls.append(args[-1])
        assert args[-1] == "GetCapabilities"
        manifest = json.dumps(
            {
                "protocol_version": 1,
                "build_id": "old-loaded-build",
                "capabilities": [
                    "PrepareWindowClose",
                    "CloseConfirmedWindow",
                    "GetAppWindowState",
                ],
            }
        )
        return subprocess.CompletedProcess(
            args, 0, json.dumps({"type": "s", "data": [manifest]})
        )

    monkeypatch.setattr(gnome_window_control, "run_process", run)
    controller = GnomeAppWindowController({"telegram": "telegram.desktop"})
    assert controller.prepare_close("telegram") is None
    assert (
        controller.backend_status.reason == "missing_capabilities:CloseAuthorizedWindow"
    )
    assert calls == ["GetCapabilities"]
