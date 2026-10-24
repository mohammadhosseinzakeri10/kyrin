"""Run activity detection and streaming transcription from one audio source."""

from collections.abc import Callable, Iterator
from contextlib import contextmanager
from functools import partial
from queue import Empty, Full, Queue
from threading import Event, Lock, Thread
from time import perf_counter_ns
from typing import cast

from kyrin.audio.activity.speech_activity_monitor import (
    SpeechActivityFrame,
    SpeechActivityMonitor,
    SpeechTransition,
)
from kyrin.audio.activity.voice_activity_detector import VoiceActivityDetector
from kyrin.audio.audio_backlog import AudioBacklog, BacklogMarker, BacklogNotice
from kyrin.audio.audio_capture_queue import AudioCaptureQueue
from kyrin.audio.audio_data import AudioData
from kyrin.audio.audio_errors import AudioCaptureStopError
from kyrin.audio.audio_format import AudioFormat
from kyrin.audio.audio_framer import AudioFramer
from kyrin.audio.audio_input import AudioInput
from kyrin.audio.sample_rate_converter import SampleRateConverter
from kyrin.audio.speech_timing import SpeechTiming, TimedSpeechBoundary
from kyrin.stt.contracts import (
    CancellableSpeechToTextEngine,
    SpeechToTextEngine,
    TurnAwareSpeechToTextSession,
)
from kyrin.stt.device import ComputeDevice, SpeechToTextOptions
from kyrin.stt.transcript import TranscriptUpdate

LiveSpeechEvent = SpeechActivityFrame | TranscriptUpdate | BacklogNotice


class LiveSpeechPipeline:
    """Keep capture, VAD, and STT independent while preserving audio order.

    The event iterator must be consumed promptly. Activity events are emitted
    only for confirmed state transitions; every audio window is still examined.
    """

    def __init__(
        self,
        source: AudioInput,
        source_format: AudioFormat,
        detector: VoiceActivityDetector,
        engine: SpeechToTextEngine,
        *,
        options: SpeechToTextOptions | None = None,
        max_capture_chunks: int = 32,
        backlog_warning_ms: int = 1000,
        backlog_recovery_ms: int = 250,
        backlog_maximum_ms: int = 5000,
        start_confirm_ms: int = 64,
        pause_confirm_ms: int = 384,
        on_compute_device: Callable[[ComputeDevice], None] | None = None,
        on_audio_ready: Callable[[], None] | None = None,
        on_speech_started: Callable[[], None] | None = None,
        clock_ns: Callable[[], int] = perf_counter_ns,
    ) -> None:
        vad_converter = SampleRateConverter(
            source_format, detector.input_format.sample_rate
        )
        if vad_converter.output_format != detector.input_format:
            raise ValueError("audio source cannot be converted to detector format")
        if max_capture_chunks <= 0:
            raise ValueError("max_capture_chunks must be positive")
        self._clock_ns = clock_ns
        self.source = source
        self.source_format = source_format
        self.detector = detector
        self.engine = engine
        self.options = options or SpeechToTextOptions()
        self.max_capture_chunks = max_capture_chunks
        self.backlog_warning_ms = backlog_warning_ms
        self.backlog_recovery_ms = backlog_recovery_ms
        self.backlog_maximum_ms = backlog_maximum_ms
        self.start_confirm_ms = start_confirm_ms
        self.pause_confirm_ms = pause_confirm_ms
        self.on_compute_device = on_compute_device
        self.on_audio_ready = on_audio_ready
        self.on_speech_started = on_speech_started
        self._vad_converter = vad_converter
        self._session_lock = Lock()
        self._stop_requested = Event()

    def stop(self) -> None:
        """End event consumption even if STT is blocked; cleanup verifies shutdown."""
        self._stop_requested.set()
        try:
            self.source.stop_capture()
        finally:
            if isinstance(self.engine, CancellableSpeechToTextEngine):
                self.engine.cancel_pending_inference()

    @contextmanager
    def open(self) -> Iterator[Iterator[LiveSpeechEvent]]:
        if not self._session_lock.acquire(blocking=False):
            raise RuntimeError("live speech pipeline already has an active session")
        try:
            if self._stop_requested.is_set():
                yield iter(())
                return
            session = self.engine.open_session(self.options)
            worker_owns_session = False
            try:
                if self.on_compute_device is not None:
                    self.on_compute_device(session.compute_device)
                turn_aware = isinstance(session, TurnAwareSpeechToTextSession)
                turn_session = (
                    cast(TurnAwareSpeechToTextSession, session) if turn_aware else None
                )
                # Existing streaming engines keep their direct source-to-STT
                # conversion. A turn-aware engine needs the VAD frames so the
                # ordered boundary markers refer to exactly the audio it saw.
                stt_source_format = (
                    self.detector.input_format if turn_aware else self.source_format
                )
                if turn_aware and session.input_format != stt_source_format:
                    raise ValueError(
                        "turn-aware STT must accept the detector audio format"
                    )
                stt_converter = SampleRateConverter(
                    stt_source_format, session.input_format.sample_rate
                )
                if stt_converter.output_format != session.input_format:
                    raise ValueError("audio source cannot be converted to STT format")
                backlog = AudioBacklog(
                    stt_source_format,
                    warning_ms=self.backlog_warning_ms,
                    recovery_ms=self.backlog_recovery_ms,
                    maximum_ms=self.backlog_maximum_ms,
                )
                monitor = SpeechActivityMonitor(
                    self.detector,
                    start_confirm_ms=self.start_confirm_ms,
                    pause_confirm_ms=self.pause_confirm_ms,
                )
                framer = AudioFramer(
                    self.detector.input_format, self.detector.frames_per_window
                )
                events: Queue[LiveSpeechEvent] = Queue(maxsize=256)
                stopped = Event()
                vad_done = Event()
                stt_done = Event()
                errors: list[Exception] = []
                close_errors: list[Exception] = []
                notice_lock = Lock()

                def publish(event: LiveSpeechEvent) -> None:
                    while not stopped.is_set():
                        try:
                            events.put(event, timeout=0.05)
                            return
                        except Full:
                            continue

                def stt_worker() -> None:
                    timing = SpeechTiming(self._clock_ns)
                    try:

                        def on_marker(
                            marker: BacklogMarker | TimedSpeechBoundary,
                        ) -> None:
                            if isinstance(marker, TimedSpeechBoundary):
                                timing.boundary(marker.frame, marker.queued_ns)
                                marker = marker.marker
                            if turn_session is None:
                                return
                            updates = timing.call(
                                turn_session.start_turn
                                if marker is BacklogMarker.SPEECH_STARTED
                                else turn_session.end_turn
                            )
                            for update in updates:
                                publish(update)

                        converted = stt_converter.convert(
                            _backlog_chunks(backlog, notice_lock, publish, on_marker)
                        )
                        for chunk in converted:
                            if stopped.is_set():
                                return
                            for update in timing.call(
                                partial(session.accept_audio, chunk)
                            ):
                                publish(update)
                        if not stopped.is_set() and not errors:
                            for update in timing.call(session.finish):
                                publish(update)
                    except Exception as exc:
                        errors.append(exc)
                        backlog.abort()
                    finally:
                        try:
                            session.close()
                        except Exception as exc:
                            close_errors.append(exc)
                            errors.append(exc)
                        stt_done.set()

                audio_ready = False

                def source_chunks(capture: AudioCaptureQueue) -> Iterator[AudioData]:
                    nonlocal audio_ready
                    for chunk in capture.chunks():
                        if errors or stopped.is_set():
                            return
                        if not audio_ready:
                            audio_ready = True
                            if self.on_audio_ready is not None:
                                self.on_audio_ready()
                        if not turn_aware:
                            with notice_lock:
                                notice = backlog.put(chunk)
                                if notice is not None:
                                    publish(notice)
                        yield chunk

                def vad_worker(capture: AudioCaptureQueue) -> None:
                    try:
                        converted = self._vad_converter.convert(source_chunks(capture))
                        for window in framer.frame(converted):
                            frame = monitor.process(window)
                            # Playback interruption must not wait behind STT or the
                            # UI event queue. All windows still enter STT in order,
                            # including the onset before VAD confirmation.
                            if (
                                frame.transition is SpeechTransition.STARTED
                                and self.on_speech_started is not None
                            ):
                                self.on_speech_started()
                            if turn_aware:
                                with notice_lock:
                                    notice = backlog.put(window)
                                    if notice is not None:
                                        publish(notice)
                                    if frame.transition is SpeechTransition.STARTED:
                                        backlog.put_marker(
                                            TimedSpeechBoundary(
                                                BacklogMarker.SPEECH_STARTED,
                                                frame,
                                                self._clock_ns(),
                                            )
                                        )
                                    elif frame.transition is SpeechTransition.PAUSED:
                                        backlog.put_marker(
                                            TimedSpeechBoundary(
                                                BacklogMarker.SPEECH_PAUSED,
                                                frame,
                                                self._clock_ns(),
                                            )
                                        )
                            if frame.transition is not None:
                                publish(frame)
                        if errors:
                            return
                        backlog.close()
                    except Exception as exc:
                        errors.append(exc)
                        backlog.abort()
                    finally:
                        vad_done.set()

                def read_events() -> Iterator[LiveSpeechEvent]:
                    while not self._stop_requested.is_set():
                        if errors:
                            raise errors[0]
                        if vad_done.is_set() and stt_done.is_set() and events.empty():
                            return
                        try:
                            event = events.get(timeout=0.05)
                            if not self._stop_requested.is_set():
                                yield event
                        except Empty:
                            continue

                stt_thread = Thread(target=stt_worker, name="kyrin-stt", daemon=True)
                vad_thread: Thread | None = None
                try:
                    with AudioCaptureQueue(
                        self.source,
                        max_chunks=self.max_capture_chunks,
                        clock_ns=self._clock_ns,
                    ) as capture:
                        vad_thread = Thread(
                            target=vad_worker,
                            args=(capture,),
                            name="kyrin-vad",
                            daemon=True,
                        )
                        stt_thread.start()
                        worker_owns_session = True
                        vad_thread.start()
                        try:
                            yield read_events()
                        finally:
                            stopped.set()
                            backlog.abort()
                finally:
                    if vad_thread is not None and vad_thread.ident is not None:
                        vad_thread.join(5)
                    if stt_thread.ident is not None:
                        # A windowed local backend may still be completing its
                        # bounded inference request when capture stops.
                        stt_thread.join(10)
                    if (vad_thread is not None and vad_thread.is_alive()) or (
                        stt_thread.is_alive()
                    ):
                        raise AudioCaptureStopError("live speech worker did not stop")
                    if close_errors:
                        raise AudioCaptureStopError("STT session did not close") from (
                            close_errors[0]
                        )
            finally:
                if not worker_owns_session:
                    try:
                        session.close()
                    except Exception as exc:
                        raise AudioCaptureStopError(
                            "STT session did not close"
                        ) from exc
        finally:
            self._session_lock.release()


def _backlog_chunks(
    backlog: AudioBacklog,
    notice_lock: Lock,
    publish: Callable[[LiveSpeechEvent], None],
    on_marker: Callable[[BacklogMarker | TimedSpeechBoundary], None],
) -> Iterator[AudioData]:
    while (item := backlog.get()) is not None:
        if isinstance(item, (BacklogMarker, TimedSpeechBoundary)):
            on_marker(item)
            continue
        yield item
        with notice_lock:
            notice = backlog.complete(item)
            if notice is not None:
                publish(notice)
