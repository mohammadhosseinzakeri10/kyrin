"""The GNOME adapter confirms state instead of trusting a request reply."""

from time import monotonic

import pytest

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
