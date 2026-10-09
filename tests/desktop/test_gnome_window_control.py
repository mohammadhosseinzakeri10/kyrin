"""The GNOME adapter confirms state instead of trusting a request reply."""

from kyrin.desktop.platforms.gnome_window_control import GnomeAppWindowController
from kyrin.desktop.window_control import WindowControlStatus, WindowOperation


def test_minimize_needs_observed_minimized_state(monkeypatch) -> None:
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


def test_close_does_not_claim_success_while_window_remains(monkeypatch) -> None:
    controller = GnomeAppWindowController(
        {"telegram": "telegram.desktop"}, attempts=2, retry_delay_s=0
    )
    replies = iter(
        (
            ("requested", "17"),
            ('{"minimized":false}',),
            ('{"minimized":false}',),
        )
    )
    monkeypatch.setattr(controller, "_call", lambda *args: next(replies))

    assert (
        controller.control("telegram", WindowOperation.CLOSE)
        is WindowControlStatus.UNKNOWN
    )


def test_unknown_app_never_contacts_shell(monkeypatch) -> None:
    controller = GnomeAppWindowController({"telegram": "telegram.desktop"})
    monkeypatch.setattr(
        controller,
        "_call",
        lambda *args: (_ for _ in ()).throw(AssertionError("called GNOME")),
    )
    assert (
        controller.control("other", WindowOperation.CLOSE)
        is WindowControlStatus.UNKNOWN
    )
