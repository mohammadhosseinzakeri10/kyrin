"""Two-step voice-or-click confirmation for disruptive session actions."""

import re
from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum
from threading import Lock, Thread
from time import monotonic
from typing import Protocol


class PowerAction(StrEnum):
    POWER_OFF = "power_off"
    RESTART = "restart"
    LOG_OUT = "log_out"
    SUSPEND = "suspend"


class PowerStage(StrEnum):
    CHECKING = "checking"
    FIRST = "first"
    SECOND = "second"
    SUBMITTING = "submitting"
    FINISHED = "finished"
    CANCELLED = "cancelled"
    EXPIRED = "expired"
    FAILED = "failed"


_PHRASES = {
    PowerAction.POWER_OFF: "Power off this computer",
    PowerAction.RESTART: "Restart this computer",
    PowerAction.LOG_OUT: "Log out of this session",
    PowerAction.SUSPEND: "Suspend this computer",
}
_REQUESTS = {
    "power off": PowerAction.POWER_OFF,
    "shut down": PowerAction.POWER_OFF,
    "shutdown": PowerAction.POWER_OFF,
    "خاموش کن": PowerAction.POWER_OFF,
    "restart": PowerAction.RESTART,
    "reboot": PowerAction.RESTART,
    "ریستارت کن": PowerAction.RESTART,
    "راه اندازی مجدد": PowerAction.RESTART,
    "log out": PowerAction.LOG_OUT,
    "logout": PowerAction.LOG_OUT,
    "خروج از حساب": PowerAction.LOG_OUT,
    "suspend": PowerAction.SUSPEND,
    "sleep": PowerAction.SUSPEND,
    "تعلیق کن": PowerAction.SUSPEND,
}
_AFFIRMATIVE = frozenset({"yes", "بله", "آره"})
_NEGATIVE = frozenset({"no", "cancel", "نه", "لغو", "خیر"})


def _normalize(text: str) -> str:
    text = text.casefold().replace("ي", "ی").replace("ك", "ک")
    return " ".join(re.sub(r"[.,!?؟،؛:]", " ", text).split())


def _requested_action(text: str) -> PowerAction | None:
    normalized = _normalize(text)
    for prefix in ("kyrin ", "kairin ", "kyreen ", "کایرین "):
        if normalized.startswith(prefix):
            normalized = normalized[len(prefix) :]
            break
    for prefix in ("please ", "لطفا ", "لطفاً "):
        if normalized.startswith(prefix):
            normalized = normalized[len(prefix) :]
            break
    return _REQUESTS.get(normalized)


@dataclass(frozen=True, slots=True)
class PowerPrompt:
    request_id: int
    action: PowerAction
    stage: PowerStage
    text: str
    spoken: bool = False
    phrase: str | None = None


class PowerBackend(Protocol):
    def work_warning(self, action: PowerAction) -> str: ...

    def request(self, action: PowerAction) -> None: ...


class SystemPowerFlow:
    """One pending request. Neither a partial transcript nor stale click can act."""

    def __init__(
        self,
        backend: PowerBackend,
        publish: Callable[[PowerPrompt], None],
        *,
        enabled: bool,
        voice_ready: Callable[[], bool] = lambda: True,
        timeout_s: float = 45.0,
        clock: Callable[[], float] = monotonic,
    ) -> None:
        self._backend = backend
        self._publish = publish
        self._announcement: Callable[[PowerPrompt], None] | None = None
        self._enabled = enabled
        self._voice_ready = voice_ready
        self._timeout_s = timeout_s
        self._clock = clock
        self._lock = Lock()
        self._next_id = 0
        self._pending: PowerPrompt | None = None
        self._inflight = False
        self._deadline = 0.0

    def on_final_speech(self, text: str) -> bool:
        """Return true when the utterance belongs to the power flow."""
        phrase = _normalize(text)
        with self._lock:
            pending = self._pending
        if pending is not None:
            # The microphone source is muted throughout KYRIN's own playback.
            if not self._voice_ready():
                return True
            self.respond(pending.request_id, phrase, spoken=True)
            return True
        action = _requested_action(text)
        if action is None:
            return False
        self.start(action)
        return True

    def configure(self, *, enabled: bool) -> None:
        with self._lock:
            self._enabled = enabled
            pending = self._pending if not enabled else None
            if not enabled:
                self._pending = None
        if pending is not None:
            self._emit(
                PowerPrompt(
                    pending.request_id,
                    pending.action,
                    PowerStage.CANCELLED,
                    "System action cancelled because its permission was disabled.",
                )
            )

    def set_voice_ready(self, callback: Callable[[], bool]) -> None:
        with self._lock:
            self._voice_ready = callback

    def set_announcement(self, callback: Callable[[PowerPrompt], None] | None) -> None:
        with self._lock:
            self._announcement = callback

    def _emit(self, prompt: PowerPrompt) -> None:
        self._publish(prompt)
        with self._lock:
            announcement = self._announcement
        if announcement is not None and prompt.spoken:
            announcement(prompt)

    def start(self, action: PowerAction) -> bool:
        with self._lock:
            enabled = self._enabled
        if not enabled:
            self._emit(
                PowerPrompt(
                    0,
                    action,
                    PowerStage.FAILED,
                    "System power actions are disabled in Desktop Actions.",
                )
            )
            return False
        with self._lock:
            if not self._enabled or self._pending is not None or self._inflight:
                return False
            self._next_id += 1
            request_id = self._next_id
            self._pending = PowerPrompt(
                request_id,
                action,
                PowerStage.CHECKING,
                "Checking whether the session reports unfinished work…",
            )
            self._deadline = self._clock() + self._timeout_s
            prompt = self._pending
        self._emit(prompt)
        Thread(target=self._check, args=(request_id, action), daemon=True).start()
        return True

    def _check(self, request_id: int, action: PowerAction) -> None:
        try:
            warning = self._backend.work_warning(action)
        except Exception:
            warning = "Could not inspect session blockers."
        text = (
            f"{warning} KYRIN cannot verify unsaved files in every app. "
            "Save your work. Say Yes or click Continue to proceed."
        )
        with self._lock:
            if (
                self._pending is None
                or self._pending.request_id != request_id
                or self._pending.stage is not PowerStage.CHECKING
            ):
                return
            prompt = PowerPrompt(request_id, action, PowerStage.FIRST, text, True)
            self._pending = prompt
        self._emit(prompt)

    def respond(self, request_id: int, answer: str, *, spoken: bool = False) -> bool:
        answer = _normalize(answer)
        with self._lock:
            pending = self._pending
            if pending is None or pending.request_id != request_id:
                return False
            if self._clock() >= self._deadline:
                stage = PowerStage.EXPIRED
                text = "Confirmation expired. No system action was requested."
            elif answer in _NEGATIVE or answer == "cancel":
                stage = PowerStage.CANCELLED
                text = "System action cancelled."
            elif pending.stage is PowerStage.FIRST and answer in (
                _AFFIRMATIVE if spoken else _AFFIRMATIVE | {"continue"}
            ):
                stage = PowerStage.SECOND
                phrase = _PHRASES[pending.action]
                text = (
                    f"Final confirmation: say exactly '{phrase}' or click the "
                    "matching button. You can still cancel."
                )
            elif pending.stage is PowerStage.SECOND and answer == _normalize(
                _PHRASES[pending.action]
            ):
                stage = PowerStage.SUBMITTING
                text = "Sending the request to the operating system…"
            else:
                return True  # Other speech cannot escape into ordinary commands.
            prompt = PowerPrompt(
                request_id,
                pending.action,
                stage,
                text,
                stage in (PowerStage.SECOND, PowerStage.CANCELLED, PowerStage.EXPIRED),
                _PHRASES[pending.action] if stage is PowerStage.SECOND else None,
            )
            self._pending = prompt if stage is PowerStage.SECOND else None
            if stage is PowerStage.SUBMITTING:
                self._inflight = True
        self._emit(prompt)
        if stage is PowerStage.SUBMITTING:
            Thread(target=self._execute, args=(prompt,), daemon=True).start()
        return True

    def _execute(self, prompt: PowerPrompt) -> None:
        try:
            self._backend.request(prompt.action)
        except Exception:
            final = PowerPrompt(
                prompt.request_id,
                prompt.action,
                PowerStage.FAILED,
                "The operating system did not accept the request. "
                "No forced action was attempted.",
                True,
            )
        else:
            final = PowerPrompt(
                prompt.request_id,
                prompt.action,
                PowerStage.FINISHED,
                "Request sent. Review any operating-system or application "
                "warning before proceeding.",
            )
        with self._lock:
            self._inflight = False
        self._emit(final)

    def expire(self) -> None:
        with self._lock:
            pending = self._pending
            if pending is None or self._clock() < self._deadline:
                return
            self._pending = None
        self._emit(
            PowerPrompt(
                pending.request_id,
                pending.action,
                PowerStage.EXPIRED,
                "Confirmation expired. No system action was requested.",
                True,
            )
        )

    def cancel(self) -> None:
        with self._lock:
            pending = self._pending
            self._pending = None
        if pending is not None:
            self._emit(
                PowerPrompt(
                    pending.request_id,
                    pending.action,
                    PowerStage.CANCELLED,
                    "System action cancelled.",
                    True,
                )
            )
