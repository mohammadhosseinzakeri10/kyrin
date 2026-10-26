"""The GNOME adapter never calls a forced D-Bus method."""

from kyrin.system_power.flow import PowerAction
from kyrin.system_power.gnome import GnomePowerBackend


def test_normal_system_requests_only(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    backend = GnomePowerBackend()
    calls: list[tuple[str, ...]] = []
    monkeypatch.setattr(backend, "_call", lambda *args: calls.append(args))
    for action in PowerAction:
        backend.request(action)
    methods = [args[args.index("--method") + 1] for args in calls]
    assert methods == [
        "org.gnome.SessionManager.Shutdown",
        "org.gnome.SessionManager.Reboot",
        "org.gnome.SessionManager.Logout",
        "org.gnome.SessionManager.Suspend",
    ]
    assert calls[2][-1] == "0"
    assert calls[3][-1] == "org.gnome.SessionManager.Suspend"


def test_blocker_check_matches_requested_action(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    backend = GnomePowerBackend()
    calls: list[tuple[str, ...]] = []

    def fake_call(*args: str, timeout: float = 8.0) -> str:
        calls.append(args)
        return "(true,)"

    monkeypatch.setattr(backend, "_call", fake_call)
    assert "blocker" in backend.work_warning(PowerAction.POWER_OFF)
    assert "blocker" in backend.work_warning(PowerAction.SUSPEND)
    assert calls[0][-1] == "1"
    assert calls[1][-1] == "4"
