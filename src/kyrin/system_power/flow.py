"""Persistent power consent, with an explicit legacy/inert confirmation flow."""

import re
from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum
from threading import Lock, Thread
from time import monotonic
from typing import Protocol

from kyrin.app.permissions import PermissionPolicy
from kyrin.commands.wake_names import DEFAULT_WAKE_NAMES


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
    PowerAction.POWER_OFF: "Power off",
    PowerAction.RESTART: "Restart computer",
    PowerAction.LOG_OUT: "Log out",
    PowerAction.SUSPEND: "Suspend computer",
}
_REQUESTS = {
    "power off": PowerAction.POWER_OFF,
    "shut down": PowerAction.POWER_OFF,
    "shutdown": PowerAction.POWER_OFF,
    "power off this computer": PowerAction.POWER_OFF,
    "shut down this computer": PowerAction.POWER_OFF,
    "خاموش کن": PowerAction.POWER_OFF,
    "این رایانه را خاموش کن": PowerAction.POWER_OFF,
    "سیستم را خاموش کن": PowerAction.POWER_OFF,
    "restart this computer": PowerAction.RESTART,
    "restart the computer": PowerAction.RESTART,
    "restart my computer": PowerAction.RESTART,
    "restart the system": PowerAction.RESTART,
    "reboot this computer": PowerAction.RESTART,
    "reboot the computer": PowerAction.RESTART,
    "reboot this machine": PowerAction.RESTART,
    "این رایانه را ریستارت کن": PowerAction.RESTART,
    "سیستم را ریستارت کن": PowerAction.RESTART,
    "این رایانه را دوباره راه اندازی کن": PowerAction.RESTART,
    "log out": PowerAction.LOG_OUT,
    "logout": PowerAction.LOG_OUT,
    "خروج از حساب": PowerAction.LOG_OUT,
    "suspend": PowerAction.SUSPEND,
    "sleep": PowerAction.SUSPEND,
    "تعلیق کن": PowerAction.SUSPEND,
}
_AFFIRMATIVE = frozenset({"yes", "بله", "آره"})
_NEGATIVE = frozenset({"no", "cancel", "نه", "لغو", "خیر"})
_PERSIAN_COMPUTER_POWER_OFF = re.compile(
    r"^(?:سیستم|رایانه|کامپیوتر)(?:م| من)?\s+(?:را|رو)\s+خاموش\s+کن(?:ید)?$"
)


def _normalize(text: str) -> str:
    text = text.casefold().replace("ي", "ی").replace("ك", "ک").replace("\u200c", " ")
    return " ".join(re.sub(r"[.,!?؟،؛:]", " ", text).split())


def recognized_power_request(text: str) -> PowerAction | None:
    """Recognize an explicit request; model proposals cannot supply this proof."""
    normalized = _normalize(text)
    for name in DEFAULT_WAKE_NAMES:
        prefix = f"{name} "
        if normalized.startswith(prefix):
            normalized = normalized[len(prefix) :]
            break
    for prefix in ("please ", "لطفا ", "لطفاً "):
        if normalized.startswith(prefix):
            normalized = normalized[len(prefix) :]
            break
    if _PERSIAN_COMPUTER_POWER_OFF.fullmatch(normalized):
        return PowerAction.POWER_OFF
    return _REQUESTS.get(normalized)


@dataclass(frozen=True, slots=True)
class PowerPrompt:
    request_id: int
    action: PowerAction
    stage: PowerStage
    text: str
    spoken: bool = False
    phrase: str | None = None
    speech_text: str | None = None
    preview: bool = False


class PowerBackend(Protocol):
    def work_warning(self, action: PowerAction) -> str: ...

    def request(self, action: PowerAction) -> None: ...


class InertPowerBackend:
    """Exercise confirmations without sending any operating-system request."""

    def work_warning(self, action: PowerAction) -> str:
        return "Safe preview: no operating-system request will be sent."

    def request(self, action: PowerAction) -> None:
        return


class SystemPowerFlow:
    """One pending request. Neither a partial transcript nor stale click can act."""

    def __init__(
        self,
        backend: PowerBackend,
        publish: Callable[[PowerPrompt], None],
        *,
        enabled: bool,
        permissions: PermissionPolicy | None = None,
        voice_ready: Callable[[], bool] = lambda: True,
        preview_backend: PowerBackend | None = None,
        timeout_s: float = 45.0,
        clock: Callable[[], float] = monotonic,
    ) -> None:
        self._backend = backend
        self._preview_backend = preview_backend
        self._request_backend: PowerBackend = backend
        self._publish = publish
        self._announcement: Callable[[PowerPrompt], None] | None = None
        self._enabled = enabled
        self._permissions = permissions
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
            # Without echo cancellation, the microphone source is muted during playback.
            if not self._voice_ready():
                return True
            self.respond(pending.request_id, phrase)
            return True
        action = recognized_power_request(text)
        if action is None:
            return False
        self.start(action)
        return True

    def configure(
        self, *, enabled: bool, permissions: PermissionPolicy | None = None
    ) -> None:
        with self._lock:
            changed = self._permissions != permissions
            self._enabled = enabled
            self._permissions = permissions
            pending = self._pending if not enabled or changed else None
            if pending is not None:
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

    def is_current_prompt(self, prompt: PowerPrompt) -> bool:
        """Keep a delayed voice announcement tied to its visible confirmation."""
        with self._lock:
            return self._pending == prompt

    def _emit(self, prompt: PowerPrompt) -> None:
        self._publish(prompt)
        with self._lock:
            announcement = self._announcement
        if announcement is not None and prompt.spoken:
            announcement(prompt)

    def start(self, action: PowerAction) -> bool:
        with self._lock:
            permissions = self._permissions
        if permissions is not None:
            return self._start_authorized(action)
        return self._start(action, preview=False)

    def _start_authorized(self, action: PowerAction) -> bool:
        with self._lock:
            if (
                not self._enabled
                or self._permissions is None
                or not self._permissions.allows("system_power")
                or self._pending is not None
                or self._inflight
            ):
                return False
            self._next_id += 1
            prompt = PowerPrompt(
                self._next_id,
                action,
                PowerStage.SUBMITTING,
                "Sending the authorized request to the operating system…",
            )
            self._pending = prompt
            self._deadline = self._clock() + self._timeout_s
            self._inflight = True
        self._emit(prompt)
        Thread(target=self._execute_authorized, args=(prompt,), daemon=True).start()
        return True

    def _execute_authorized(self, prompt: PowerPrompt) -> None:
        with self._lock:
            if self._next_id != prompt.request_id:
                return
            if (
                self._pending != prompt
                or not self._enabled
                or self._permissions is None
                or not self._permissions.allows("system_power")
                or self._clock() >= self._deadline
            ):
                if self._pending == prompt:
                    self._pending = None
                self._inflight = False
                return
            # Dispatch boundary: cancellation cannot undo a request already sent.
            self._pending = None
        self._execute(prompt, self._backend)

    def start_preview(self, action: PowerAction) -> bool:
        if self._preview_backend is None:
            return False
        return self._start(action, preview=True)

    def _start(self, action: PowerAction, *, preview: bool) -> bool:
        with self._lock:
            enabled = self._enabled
        if not enabled and not preview:
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
            if (
                (not self._enabled and not preview)
                or self._pending is not None
                or self._inflight
            ):
                return False
            self._next_id += 1
            request_id = self._next_id
            self._request_backend = (
                self._preview_backend
                if preview and self._preview_backend
                else self._backend
            )
            self._pending = PowerPrompt(
                request_id,
                action,
                PowerStage.CHECKING,
                (
                    "Safe preview: checking the confirmation flow…"
                    if preview
                    else "Checking whether the session reports unfinished work…"
                ),
                preview=preview,
            )
            self._deadline = self._clock() + self._timeout_s
            prompt = self._pending
        self._emit(prompt)
        Thread(
            target=self._check,
            args=(request_id, action, self._request_backend, preview),
            daemon=True,
        ).start()
        return True

    def _check(
        self, request_id: int, action: PowerAction, backend: PowerBackend, preview: bool
    ) -> None:
        try:
            warning = backend.work_warning(action)
        except Exception:
            warning = "Could not inspect session blockers."
        text = (
            f"{_PHRASES[action]} requested. {warning} "
            "KYRIN cannot verify unsaved files in every app. "
            "Save your work. Say Yes or Continue, or click Continue to proceed."
        )
        with self._lock:
            if (
                self._pending is None
                or self._pending.request_id != request_id
                or self._pending.stage is not PowerStage.CHECKING
            ):
                return
            prompt = PowerPrompt(
                request_id,
                action,
                PowerStage.FIRST,
                text,
                True,
                speech_text=(
                    f"{_PHRASES[action]} requested. {warning} Save your work. "
                    "Say Yes or Continue to proceed."
                ),
                preview=preview,
            )
            self._pending = prompt
            self._deadline = self._clock() + self._timeout_s
        self._emit(prompt)

    def respond(self, request_id: int, answer: str) -> bool:
        answer = _normalize(answer)
        reminder_only = False
        with self._lock:
            pending = self._pending
            if pending is None or pending.request_id != request_id:
                return False
            if pending.stage is PowerStage.SUBMITTING and answer not in _NEGATIVE:
                return False
            if self._clock() >= self._deadline:
                stage = PowerStage.EXPIRED
                text = "Confirmation expired. No system action was requested."
            elif answer in _NEGATIVE or answer == "cancel":
                stage = PowerStage.CANCELLED
                text = "System action cancelled."
            elif pending.stage is PowerStage.FIRST and answer in (
                _AFFIRMATIVE | {"continue"}
            ):
                stage = PowerStage.SECOND
                phrase = _PHRASES[pending.action]
                text = (
                    f"Final confirmation: say exactly '{phrase}' or click the "
                    "matching button. You can still cancel."
                )
                self._deadline = self._clock() + self._timeout_s
            elif pending.stage is PowerStage.SECOND and answer == _normalize(
                _PHRASES[pending.action]
            ):
                stage = PowerStage.SUBMITTING
                text = "Sending the request to the operating system…"
            else:
                # Keep the same request and deadline. Unclear speech never
                # becomes a confirmation or a new power action.
                phrase = _PHRASES[pending.action]
                text = "I could not confirm that. " + (
                    "Say Yes or Continue."
                    if pending.stage is PowerStage.FIRST
                    else f"Say '{phrase}' or choose its button."
                )
                reminder = PowerPrompt(
                    request_id,
                    pending.action,
                    pending.stage,
                    text,
                    False,
                    phrase if pending.stage is PowerStage.SECOND else None,
                    preview=pending.preview,
                )
                self._pending = reminder
                prompt = reminder
                stage = pending.stage
                # Repetition stays visual and cannot feed another voice loop.
                reminder_only = True
            if not reminder_only:
                prompt = PowerPrompt(
                    request_id,
                    pending.action,
                    stage,
                    text,
                    stage
                    in (PowerStage.SECOND, PowerStage.CANCELLED, PowerStage.EXPIRED),
                    _PHRASES[pending.action] if stage is PowerStage.SECOND else None,
                    speech_text=(
                        f"Final confirmation. Say exactly {_PHRASES[pending.action]}, "
                        "or click the matching button. You can still cancel."
                        if stage is PowerStage.SECOND
                        else None
                    ),
                    preview=pending.preview,
                )
                self._pending = prompt if stage is PowerStage.SECOND else None
                if stage is PowerStage.SUBMITTING:
                    self._inflight = True
        self._emit(prompt)
        if stage is PowerStage.SUBMITTING:
            Thread(
                target=self._execute,
                args=(prompt, self._request_backend),
                daemon=True,
            ).start()
        return True

    def _execute(self, prompt: PowerPrompt, backend: PowerBackend) -> None:
        try:
            backend.request(prompt.action)
        except Exception:
            final = PowerPrompt(
                prompt.request_id,
                prompt.action,
                PowerStage.FAILED,
                "The operating system did not accept the request. "
                "No forced action was attempted.",
                True,
                preview=prompt.preview,
            )
        else:
            final = PowerPrompt(
                prompt.request_id,
                prompt.action,
                PowerStage.FINISHED,
                (
                    "Safe preview complete. No operating-system request was sent."
                    if prompt.preview
                    else "Request sent. Review any operating-system or application "
                    "warning before proceeding."
                ),
                preview=prompt.preview,
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
