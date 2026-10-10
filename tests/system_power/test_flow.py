"""Power requests stay inert until two independent, current confirmations."""

from threading import Event
from time import monotonic, sleep

from kyrin.system_power.flow import (
    PowerAction,
    PowerPrompt,
    PowerStage,
    SystemPowerFlow,
    recognized_power_request,
)


class FakeBackend:
    def __init__(self) -> None:
        self.actions: list[PowerAction] = []
        self.done = Event()

    def work_warning(self, action: PowerAction) -> str:
        return "GNOME reports one session blocker."

    def request(self, action: PowerAction) -> None:
        self.actions.append(action)
        self.done.set()


def _wait_for(events: list[PowerPrompt], stage: PowerStage) -> PowerPrompt:
    deadline = monotonic() + 2
    while monotonic() < deadline:
        matching = [event for event in events if event.stage is stage]
        if matching:
            return matching[-1]
        sleep(0.01)
    raise AssertionError(f"missing {stage} prompt")


def test_restart_requires_explicit_computer_scope() -> None:
    events: list[PowerPrompt] = []
    flow = SystemPowerFlow(FakeBackend(), events.append, enabled=False)

    for phrase in (
        "Restart",
        "KYRIN, please restart",
        "Restart Telegram",
        "Restart the browser",
        "تلگرام را دوباره راه‌اندازی کن",
        "ریستارت کن",
    ):
        assert not flow.on_final_speech(phrase)
    assert events == []

    for phrase in (
        "Restart this computer",
        "Reboot this machine",
        "این رایانه را دوباره راه‌اندازی کن",
    ):
        assert flow.on_final_speech(phrase)
        assert events[-1].action is PowerAction.RESTART
        assert events[-1].stage is PowerStage.FAILED
    assert recognized_power_request("Restart Telegram") is None


def test_voice_and_click_share_two_step_flow() -> None:
    backend = FakeBackend()
    events: list[PowerPrompt] = []
    flow = SystemPowerFlow(backend, events.append, enabled=True)
    assert flow.on_final_speech("KYRIN, power off")
    first = _wait_for(events, PowerStage.FIRST)
    assert "cannot verify unsaved" in first.text
    assert backend.actions == []
    assert flow.on_final_speech("Yes")
    second = _wait_for(events, PowerStage.SECOND)
    assert second.phrase == "Power off this computer"
    assert not flow.respond(first.request_id + 1, second.phrase)
    assert flow.on_final_speech("Restart this computer")
    assert backend.actions == []
    assert flow.respond(second.request_id, second.phrase)
    assert backend.done.wait(2)
    assert backend.actions == [PowerAction.POWER_OFF]


def test_click_first_and_spoken_second_with_voice_guard() -> None:
    backend = FakeBackend()
    events: list[PowerPrompt] = []
    voice_ready = False
    flow = SystemPowerFlow(
        backend, events.append, enabled=True, voice_ready=lambda: voice_ready
    )
    assert flow.start(PowerAction.RESTART)
    first = _wait_for(events, PowerStage.FIRST)
    assert flow.respond(first.request_id, "continue")
    second = _wait_for(events, PowerStage.SECOND)
    assert second.phrase is not None
    assert flow.on_final_speech(second.phrase)
    assert not backend.done.is_set()
    voice_ready = True
    assert flow.on_final_speech(second.phrase)
    assert backend.done.wait(2)
    assert backend.actions == [PowerAction.RESTART]


def test_permission_cancel_and_expiry_never_execute() -> None:
    backend = FakeBackend()
    events: list[PowerPrompt] = []
    now = 10.0
    flow = SystemPowerFlow(
        backend, events.append, enabled=False, clock=lambda: now, timeout_s=5
    )
    assert flow.on_final_speech("suspend")
    assert events[-1].stage is PowerStage.FAILED
    flow.configure(enabled=True)
    assert flow.start(PowerAction.SUSPEND)
    first = _wait_for(events, PowerStage.FIRST)
    assert flow.respond(first.request_id, "cancel")
    assert any(event.stage is PowerStage.CANCELLED for event in events)
    assert flow.start(PowerAction.LOG_OUT)
    deadline = monotonic() + 2
    while monotonic() < deadline and not any(
        event.stage is PowerStage.FIRST and event.action is PowerAction.LOG_OUT
        for event in events
    ):
        sleep(0.01)
    second_request = next(
        event
        for event in events
        if event.stage is PowerStage.FIRST and event.action is PowerAction.LOG_OUT
    )
    now = 16.0
    flow.expire()
    assert events[-1].stage is PowerStage.EXPIRED
    assert not flow.respond(second_request.request_id, "continue")
    assert backend.actions == []


def test_fresh_request_waits_for_running_backend() -> None:
    class SlowBackend(FakeBackend):
        def __init__(self) -> None:
            super().__init__()
            self.release = Event()

        def request(self, action: PowerAction) -> None:
            assert self.release.wait(2)
            super().request(action)

    backend = SlowBackend()
    events: list[PowerPrompt] = []
    flow = SystemPowerFlow(backend, events.append, enabled=True)
    assert flow.start(PowerAction.SUSPEND)
    first = _wait_for(events, PowerStage.FIRST)
    assert flow.respond(first.request_id, "continue")
    second = _wait_for(events, PowerStage.SECOND)
    assert flow.respond(second.request_id, second.phrase or "")
    assert not flow.start(PowerAction.POWER_OFF)
    backend.release.set()
    assert backend.done.wait(2)
