"""Replaceable offline speech output for localized response text."""

import shutil
import subprocess
from collections.abc import Callable
from queue import Empty, Full, Queue
from threading import Event, Lock, Thread
from time import monotonic, sleep
from typing import Protocol

from kyrin.commands.models import ResponseChannel
from kyrin.responses.presenter import PresentedResponse
from kyrin.responses.speech_dispatcher import LocalSpeechConnection


class SpeechSynthesisError(RuntimeError):
    """The configured local speech backend could not complete playback."""


class SpeechSynthesizer(Protocol):
    def speak(self, text: str, language: str) -> None:
        """Return after speech has finished or raise a playback error."""
        ...


class SpeechDispatcherSynthesizer:
    """Use Ubuntu's local eSpeak NG module through Speech Dispatcher."""

    def __init__(
        self,
        executable: str | None = None,
        *,
        timeout_s: float = 15,
        rate: int = 0,
        voice_type: str = "default",
    ) -> None:
        resolved = executable or shutil.which("spd-say")
        if resolved is None:
            raise SpeechSynthesisError("spd-say is not installed")
        self._executable = resolved
        if timeout_s <= 0:
            raise ValueError("timeout_s must be positive")
        if not -100 <= rate <= 100:
            raise ValueError("rate must be between -100 and 100")
        if voice_type not in {"default", "male1", "male2", "female1", "female2"}:
            raise ValueError("unsupported Speech Dispatcher voice type")
        self._timeout_s = timeout_s
        self._rate = rate
        self._voice_type = voice_type
        self._cancelled = Event()
        self._is_playing = False
        self.last_playback_end = 0.0

    @property
    def is_playing(self) -> bool:
        return self._is_playing

    def interrupt(self) -> None:
        self._cancelled.set()

    def _playing(self, value: bool) -> None:
        if self._is_playing and not value:
            self.last_playback_end = monotonic()
        self._is_playing = value

    def speak(self, text: str, language: str) -> None:
        if not text.strip():
            return
        self.speak_if_current(text, language, lambda: True)

    def speak_if_current(
        self, text: str, language: str, is_current: Callable[[], bool]
    ) -> None:
        if self._is_playing:
            raise SpeechSynthesisError("previous system playback stop is unconfirmed")
        self._cancelled.clear()
        primary = language.replace("_", "-").split("-", maxsplit=1)[0].casefold()
        if not primary.isalpha():
            raise SpeechSynthesisError("invalid speech language")
        connection = None
        try:
            if not is_current():
                return
            try:
                connection = LocalSpeechConnection(self._timeout_s)
            except FileNotFoundError, ConnectionRefusedError:
                # Keep the existing local service autospawn behavior, without
                # submitting any speech or touching another client's queue.
                subprocess.run(
                    [self._executable, "--list-output-modules"],
                    capture_output=True,
                    timeout=2,
                    check=True,
                )
                connection = LocalSpeechConnection(self._timeout_s)
            connection.speak(
                text,
                primary,
                self._rate,
                self._voice_type,
                self._cancelled,
                is_current,
                self._playing,
            )
        except (OSError, subprocess.SubprocessError) as exc:
            if connection is not None and connection.output_uncertain:
                raise SpeechSynthesisError(
                    "System voice stop is unconfirmed; microphone stays guarded. "
                    "Restore the speech service and restart KYRIN."
                ) from exc
            raise SpeechSynthesisError("offline speech playback failed") from exc
        finally:
            if connection is not None and connection.output_uncertain:
                # A lost control connection is not proof that the service
                # stopped speaking. Retain the conservative microphone guard.
                self._is_playing = True
            else:
                self._playing(False)
            if connection is not None:
                connection.close()


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
        self._queue: Queue[
            tuple[
                int,
                PresentedResponse,
                Callable[[str, str, Callable[[], bool]], None] | None,
                Callable[[], bool] | None,
            ]
        ] = Queue(maxsize=max_pending)
        self._generation = 0
        self._enabled = True
        self._speaking = False
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

    @property
    def is_playing(self) -> bool:
        """Echo guard state; queueing and known model synthesis are not audio.

        Backends without playback telemetry retain the conservative guard.
        """
        playing = getattr(self._synthesizer, "is_playing", None)
        if playing is None:
            return self.is_active
        ended = getattr(self._synthesizer, "last_playback_end", 0.0)
        return bool(playing) or (ended > 0 and monotonic() < ended + self._tail_s)

    @property
    def is_enabled(self) -> bool:
        with self._lock:
            return self._enabled

    def submit(
        self,
        response: PresentedResponse,
        *,
        speak: Callable[[str, str, Callable[[], bool]], None] | None = None,
        still_current: Callable[[], bool] | None = None,
    ) -> bool:
        """Queue voice without blocking capture; text is displayed by the caller."""
        if response.channel is ResponseChannel.TEXT_ONLY:
            return True
        with self._lock:
            if self._closed.is_set():
                return False
            if not self._enabled:
                return True
            self._active.set()
            self._idle.clear()
            try:
                self._queue.put_nowait(
                    (self._generation, response, speak, still_current)
                )
            except Full:
                return False
        return True

    def replace(
        self,
        response: PresentedResponse,
        *,
        speak: Callable[[str, str, Callable[[], bool]], None] | None = None,
        still_current: Callable[[], bool] | None = None,
    ) -> bool:
        """Interrupt current voice and make this the only pending announcement."""
        with self._lock:
            if self._closed.is_set():
                return False
            if not self._enabled:
                self._interrupt_locked()
                return True
            self._interrupt_locked()
            self._active.set()
            self._idle.clear()
            self._queue.put_nowait((self._generation, response, speak, still_current))
        return True

    def interrupt(self) -> None:
        """Stop an obsolete announcement without replacing it."""
        with self._lock:
            self._interrupt_locked()

    def set_enabled(self, enabled: bool) -> None:
        """Apply the saved voice preference and stop speech when turned off."""
        with self._lock:
            self._enabled = enabled
            if not enabled:
                self._interrupt_locked()

    def _interrupt_locked(self) -> None:
        self._generation += 1
        self._clear_pending()
        interrupt = getattr(self._synthesizer, "interrupt", None)
        if callable(interrupt):
            interrupt()
        if not self._speaking:
            self._active.clear()
            self._idle.set()

    def _clear_pending(self) -> None:
        while True:
            try:
                self._queue.get_nowait()
                self._queue.task_done()
            except Empty:
                return

    def _run(self) -> None:
        while not self._closed.is_set() or not self._queue.empty():
            try:
                generation, response, speak, still_current = self._queue.get(
                    timeout=0.05
                )
            except Empty:
                continue
            started = False
            try:
                with self._lock:
                    current = generation == self._generation and (
                        still_current is None or still_current()
                    )
                    if current:
                        self._speaking = True
                if current:
                    started = True

                    def is_current(
                        generation: int = generation,
                        validity: Callable[[], bool] | None = still_current,
                    ) -> bool:
                        return (
                            generation == self._generation
                            and not self._closed.is_set()
                            and (validity is None or validity())
                        )

                    if speak is not None:
                        speak(response.text, response.language, is_current)
                    else:
                        guarded_speak = getattr(
                            self._synthesizer, "speak_if_current", None
                        )
                        if callable(guarded_speak):
                            guarded_speak(
                                response.text,
                                response.language,
                                is_current,
                            )
                        else:
                            self._synthesizer.speak(response.text, response.language)
            except SpeechSynthesisError as exc:
                self._on_error(exc)
            finally:
                if started and self._tail_s and generation == self._generation:
                    sleep(self._tail_s)
                with self._lock:
                    if started:
                        self._speaking = False
                    if self._queue.empty():
                        self._active.clear()
                        self._idle.set()
                self._queue.task_done()

    def wait_until_idle(self, timeout_s: float) -> bool:
        """Wait for queued voice to finish, with a bounded shutdown deadline."""
        if timeout_s < 0:
            raise ValueError("timeout_s must be nonnegative")
        return self._idle.wait(timeout_s)

    def close(self, *, timeout_s: float = 27) -> None:
        """Finish current playback; discard queued voice when the session ends."""
        if timeout_s < 0:
            raise ValueError("timeout_s must be nonnegative")
        with self._lock:
            self._closed.set()
            while True:
                try:
                    self._queue.get_nowait()
                    self._queue.task_done()
                except Empty:
                    break
        # Speech Dispatcher has a 25-second deadline in the desktop adapter.
        self._worker.join(timeout=timeout_s)
        if self._worker.is_alive():
            raise SpeechSynthesisError("speech worker did not stop")
        self._active.clear()
        self._idle.set()
