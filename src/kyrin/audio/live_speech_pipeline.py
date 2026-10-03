"""Run activity detection and streaming transcription from one audio source."""

from collections.abc import Callable, Iterator
from contextlib import contextmanager
from queue import Empty, Full, Queue
from threading import Event, Lock, Thread

from kyrin.audio.activity.speech_activity_monitor import (
    SpeechActivityFrame,
    SpeechActivityMonitor,
)
from kyrin.audio.activity.voice_activity_detector import VoiceActivityDetector
from kyrin.audio.audio_backlog import AudioBacklog, BacklogNotice
from kyrin.audio.audio_capture_queue import AudioCaptureQueue
from kyrin.audio.audio_data import AudioData
from kyrin.audio.audio_errors import AudioCaptureStopError
from kyrin.audio.audio_format import AudioFormat
from kyrin.audio.audio_framer import AudioFramer
from kyrin.audio.audio_input import AudioInput
from kyrin.audio.sample_rate_converter import SampleRateConverter
from kyrin.stt.contracts import SpeechToTextEngine
from kyrin.stt.device import SpeechToTextOptions
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
    ) -> None:
        vad_converter = SampleRateConverter(
            source_format, detector.input_format.sample_rate
        )
        if vad_converter.output_format != detector.input_format:
            raise ValueError("audio source cannot be converted to detector format")
        if max_capture_chunks <= 0:
            raise ValueError("max_capture_chunks must be positive")
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
        self._vad_converter = vad_converter
        self._session_lock = Lock()

    @contextmanager
    def open(self) -> Iterator[Iterator[LiveSpeechEvent]]:
        if not self._session_lock.acquire(blocking=False):
            raise RuntimeError("live speech pipeline already has an active session")
        try:
            session = self.engine.open_session(self.options)
            worker_owns_session = False
            try:
                stt_converter = SampleRateConverter(
                    self.source_format, session.input_format.sample_rate
                )
                if stt_converter.output_format != session.input_format:
                    raise ValueError("audio source cannot be converted to STT format")
                backlog = AudioBacklog(
                    self.source_format,
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
                notice_lock = Lock()

                def publish(event: LiveSpeechEvent) -> None:
                    while not stopped.is_set():
                        try:
                            events.put(event, timeout=0.05)
                            return
                        except Full:
                            continue

                def stt_worker() -> None:
                    try:
                        converted = stt_converter.convert(
                            _backlog_chunks(backlog, notice_lock, publish)
                        )
                        for chunk in converted:
                            if stopped.is_set():
                                return
                            for update in session.accept_audio(chunk):
                                publish(update)
                        if not stopped.is_set() and not errors:
                            for update in session.finish():
                                publish(update)
                    except Exception as exc:
                        errors.append(exc)
                        backlog.abort()
                    finally:
                        try:
                            session.close()
                        except Exception as exc:
                            errors.append(exc)
                        stt_done.set()

                def source_chunks(capture: AudioCaptureQueue) -> Iterator[AudioData]:
                    for chunk in capture.chunks():
                        if errors or stopped.is_set():
                            return
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
                    while True:
                        if errors:
                            raise errors[0]
                        if vad_done.is_set() and stt_done.is_set() and events.empty():
                            return
                        try:
                            yield events.get(timeout=0.05)
                        except Empty:
                            continue

                stt_thread = Thread(target=stt_worker, name="kyrin-stt", daemon=True)
                vad_thread: Thread | None = None
                try:
                    with AudioCaptureQueue(
                        self.source, max_chunks=self.max_capture_chunks
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
                        stt_thread.join(5)
                    if (vad_thread is not None and vad_thread.is_alive()) or (
                        stt_thread.is_alive()
                    ):
                        raise AudioCaptureStopError("live speech worker did not stop")
            finally:
                if not worker_owns_session:
                    session.close()
        finally:
            self._session_lock.release()


def _backlog_chunks(
    backlog: AudioBacklog,
    notice_lock: Lock,
    publish: Callable[[LiveSpeechEvent], None],
) -> Iterator[AudioData]:
    while (chunk := backlog.get()) is not None:
        yield chunk
        with notice_lock:
            notice = backlog.complete(chunk)
            if notice is not None:
                publish(notice)
