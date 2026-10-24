"""Process finite audio files without the real-time microphone backlog."""

from collections import deque
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from functools import partial
from threading import Event, Lock
from time import perf_counter_ns
from typing import cast

from kyrin.audio.activity.speech_activity_monitor import (
    SpeechActivityFrame,
    SpeechActivityMonitor,
    SpeechTransition,
)
from kyrin.audio.activity.voice_activity_detector import VoiceActivityDetector
from kyrin.audio.audio_data import AudioData
from kyrin.audio.audio_framer import AudioFramer
from kyrin.audio.file_input import AudioFileInput
from kyrin.audio.live_speech_pipeline import LiveSpeechEvent
from kyrin.audio.sample_rate_converter import SampleRateConverter
from kyrin.audio.speech_timing import SpeechTiming
from kyrin.stt.contracts import (
    CancellableSpeechToTextEngine,
    SpeechToTextEngine,
    TurnAwareSpeechToTextSession,
)
from kyrin.stt.device import ComputeDevice, SpeechToTextOptions


class FileSpeechPipeline:
    """Feed VAD and STT in order, waiting only for decoding or inference.

    A file has no real-time capture deadline. Processing it synchronously
    avoids both artificial playback waits and dropped backlog audio.
    """

    def __init__(
        self,
        source: AudioFileInput,
        detector: VoiceActivityDetector,
        engine: SpeechToTextEngine,
        *,
        options: SpeechToTextOptions | None = None,
        pause_confirm_ms: int = 384,
        on_compute_device: Callable[[ComputeDevice], None] | None = None,
        on_audio_ready: Callable[[], None] | None = None,
        clock_ns: Callable[[], int] = perf_counter_ns,
    ) -> None:
        self._clock_ns = clock_ns
        self.source = source
        self.detector = detector
        self.engine = engine
        self.options = options or SpeechToTextOptions()
        self.pause_confirm_ms = pause_confirm_ms
        self.on_compute_device = on_compute_device
        self.on_audio_ready = on_audio_ready
        self._stopped = Event()
        self._lock = Lock()

    def stop(self) -> None:
        self._stopped.set()
        self.source.stop_capture()
        if isinstance(self.engine, CancellableSpeechToTextEngine):
            self.engine.cancel_pending_inference()

    @contextmanager
    def open(self) -> Iterator[Iterator[LiveSpeechEvent]]:
        if not self._lock.acquire(blocking=False):
            raise RuntimeError("file speech pipeline already has an active session")
        try:
            if self._stopped.is_set():
                yield iter(())
                return
            session = self.engine.open_session(self.options)
            try:
                if self.on_compute_device is not None:
                    self.on_compute_device(session.compute_device)
                turn_session = (
                    cast(TurnAwareSpeechToTextSession, session)
                    if isinstance(session, TurnAwareSpeechToTextSession)
                    else None
                )
                vad_converter = SampleRateConverter(
                    self.source.audio_format, self.detector.input_format.sample_rate
                )
                if vad_converter.output_format != self.detector.input_format:
                    raise ValueError(
                        "audio source cannot be converted to detector format"
                    )
                if (
                    turn_session is not None
                    and session.input_format != self.detector.input_format
                ):
                    raise ValueError(
                        "turn-aware STT must accept the detector audio format"
                    )
                stt_converter = SampleRateConverter(
                    self.detector.input_format, session.input_format.sample_rate
                )
                if stt_converter.output_format != session.input_format:
                    raise ValueError("audio source cannot be converted to STT format")
                monitor = SpeechActivityMonitor(
                    self.detector, pause_confirm_ms=self.pause_confirm_ms
                )
                framer = AudioFramer(
                    self.detector.input_format, self.detector.frames_per_window
                )

                def events() -> Iterator[LiveSpeechEvent]:
                    ready = False
                    timing = SpeechTiming(self._clock_ns)

                    def chunks() -> Iterator[AudioData]:
                        nonlocal ready
                        for chunk in self.source.capture():
                            if self._stopped.is_set():
                                return
                            if not ready:
                                ready = True
                                if self.on_audio_ready is not None:
                                    self.on_audio_ready()
                            yield chunk

                    windows = framer.frame(vad_converter.convert(chunks()))
                    if turn_session is not None:
                        for window in windows:
                            if self._stopped.is_set():
                                return
                            frame = monitor.process(window)
                            timing.boundary(frame)
                            if frame.transition is not None:
                                yield frame
                            if frame.transition is SpeechTransition.STARTED:
                                yield from timing.call(turn_session.start_turn)
                            yield from timing.call(
                                partial(session.accept_audio, window)
                            )
                            if frame.transition is SpeechTransition.PAUSED:
                                yield from timing.call(turn_session.end_turn)
                    else:
                        pending: deque[SpeechActivityFrame] = deque()

                        def observed_windows() -> Iterator[AudioData]:
                            for window in windows:
                                if self._stopped.is_set():
                                    return
                                pending.append(monitor.process(window))
                                yield window

                        for converted in stt_converter.convert(observed_windows()):
                            if self._stopped.is_set():
                                return
                            while pending:
                                frame = pending.popleft()
                                if frame.transition is not None:
                                    yield frame
                            yield from timing.call(
                                partial(session.accept_audio, converted)
                            )
                        while pending:
                            frame = pending.popleft()
                            if frame.transition is not None:
                                yield frame
                    if not self._stopped.is_set():
                        yield from timing.call(session.finish)

                yield events()
            finally:
                self.source.stop_capture()
                session.close()
        finally:
            self._lock.release()
