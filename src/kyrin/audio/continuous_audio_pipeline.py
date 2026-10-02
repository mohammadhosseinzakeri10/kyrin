"""Connect live capture to conversion, framing, and speech activity."""

from collections.abc import Iterator
from contextlib import contextmanager
from threading import Lock

from kyrin.audio.activity.speech_activity_monitor import (
    SpeechActivityFrame,
    SpeechActivityMonitor,
)
from kyrin.audio.activity.voice_activity_detector import VoiceActivityDetector
from kyrin.audio.audio_capture_queue import AudioCaptureQueue
from kyrin.audio.audio_format import AudioFormat
from kyrin.audio.audio_framer import AudioFramer
from kyrin.audio.audio_input import AudioInput
from kyrin.audio.sample_rate_converter import SampleRateConverter


class ContinuousAudioPipeline:
    """Produce activity observations from one continuously captured stream.

    The caller owns the ``open`` context. Listening stops when that context
    exits, even if its consumer stops early or raises an exception.
    """

    def __init__(
        self,
        source: AudioInput,
        source_format: AudioFormat,
        detector: VoiceActivityDetector,
        *,
        max_queued_chunks: int = 8,
        start_confirm_ms: int = 64,
        pause_confirm_ms: int = 384,
    ) -> None:
        converter = SampleRateConverter(
            source_format, detector.input_format.sample_rate
        )
        if converter.output_format != detector.input_format:
            raise ValueError("audio source cannot be converted to detector format")
        if max_queued_chunks <= 0:
            raise ValueError("max_queued_chunks must be positive")

        self.source = source
        self.detector = detector
        self.max_queued_chunks = max_queued_chunks
        self.start_confirm_ms = start_confirm_ms
        self.pause_confirm_ms = pause_confirm_ms
        self._converter = converter
        self._framer = AudioFramer(detector.input_format, detector.frames_per_window)
        self._session_lock = Lock()

    @contextmanager
    def open(self) -> Iterator[Iterator[SpeechActivityFrame]]:
        """Start capture and yield an iterator of immediately available frames."""
        if not self._session_lock.acquire(blocking=False):
            raise RuntimeError("audio pipeline already has an active session")
        try:
            monitor = SpeechActivityMonitor(
                self.detector,
                start_confirm_ms=self.start_confirm_ms,
                pause_confirm_ms=self.pause_confirm_ms,
            )
            with AudioCaptureQueue(
                self.source, max_chunks=self.max_queued_chunks
            ) as capture:
                converted = self._converter.convert(capture.chunks())
                framed = self._framer.frame(converted)
                yield monitor.observe(framed)
        finally:
            self._session_lock.release()
