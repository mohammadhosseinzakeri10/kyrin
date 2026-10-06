"""Replaceable offline speech output for localized response text."""

import shutil
import subprocess
from collections.abc import Callable
from queue import Empty, Full, Queue
from threading import Event, Lock, Thread
from time import sleep
from typing import Protocol

from kyrin.commands.models import ResponseChannel
from kyrin.responses.presenter import PresentedResponse


class SpeechSynthesisError(RuntimeError):
    """The configured local speech backend could not complete playback."""


class SpeechSynthesizer(Protocol):
    def speak(self, text: str, language: str) -> None:
        """Return after speech has finished or raise a playback error."""
        ...


class SpeechDispatcherSynthesizer:
    """Use Ubuntu's local eSpeak NG module through Speech Dispatcher."""

    def __init__(self, executable: str | None = None, *, timeout_s: float = 15) -> None:
        resolved = executable or shutil.which("spd-say")
        if resolved is None:
            raise SpeechSynthesisError("spd-say is not installed")
        self._executable = resolved
        if timeout_s <= 0:
            raise ValueError("timeout_s must be positive")
        self._timeout_s = timeout_s

    def speak(self, text: str, language: str) -> None:
        if not text.strip():
            return
        primary = language.replace("_", "-").split("-", maxsplit=1)[0].casefold()
        try:
            result = subprocess.run(
                [
                    self._executable,
                    "--wait",
                    "--output-module",
                    "espeak-ng",
                    "--application-name",
                    "KYRIN",
                    "--language",
                    primary,
                    text,
                ],
                capture_output=True,
                text=True,
                timeout=self._timeout_s,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise SpeechSynthesisError("offline speech playback failed") from exc
        if result.returncode != 0:
            raise SpeechSynthesisError("offline speech playback failed")


class ResponseSpeaker:
    """Play requested voice responses off the event loop and expose an echo guard."""

    def __init__(
        self,
        synthesizer: SpeechSynthesizer,
        *,
        on_error: Callable[[SpeechSynthesisError], None],
        tail_s: float = 0.35,
        max_pending: int = 8,
    ) -> None:
        if tail_s < 0:
            raise ValueError("tail_s must be nonnegative")
        if max_pending <= 0:
            raise ValueError("max_pending must be positive")
        self._synthesizer = synthesizer
        self._on_error = on_error
        self._tail_s = tail_s
        self._queue: Queue[PresentedResponse] = Queue(maxsize=max_pending)
        self._active = Event()
        self._idle = Event()
        self._idle.set()
        self._lock = Lock()
        self._closed = Event()
        self._worker = Thread(
            target=self._run, name="kyrin-response-speech", daemon=True
        )
        self._worker.start()

    @property
    def is_active(self) -> bool:
        return self._active.is_set()

    def submit(self, response: PresentedResponse) -> bool:
        """Queue voice without blocking capture; text is displayed by the caller."""
        if response.channel is ResponseChannel.TEXT_ONLY:
            return True
        with self._lock:
            if self._closed.is_set():
                return False
            self._active.set()
            self._idle.clear()
            try:
                self._queue.put_nowait(response)
            except Full:
                return False
        return True

    def _run(self) -> None:
        while not self._closed.is_set() or not self._queue.empty():
            try:
                response = self._queue.get(timeout=0.05)
            except Empty:
                continue
            try:
                self._synthesizer.speak(response.text, response.language)
            except SpeechSynthesisError as exc:
                self._on_error(exc)
            finally:
                if self._tail_s:
                    sleep(self._tail_s)
                with self._lock:
                    if self._queue.empty():
                        self._active.clear()
                        self._idle.set()
                self._queue.task_done()

    def wait_until_idle(self, timeout_s: float) -> bool:
        """Wait for queued voice to finish, with a bounded shutdown deadline."""
        if timeout_s < 0:
            raise ValueError("timeout_s must be nonnegative")
        return self._idle.wait(timeout_s)

    def close(self) -> None:
        """Finish current playback; discard queued voice when the session ends."""
        with self._lock:
            self._closed.set()
            while True:
                try:
                    self._queue.get_nowait()
                    self._queue.task_done()
                except Empty:
                    break
        self._worker.join(timeout=16)
        if self._worker.is_alive():
            raise SpeechSynthesisError("speech worker did not stop")
        self._active.clear()
        self._idle.set()
