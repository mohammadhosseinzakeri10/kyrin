"""Move blocking audio capture to a worker with bounded buffering."""

from collections.abc import Callable, Iterator
from dataclasses import replace
from queue import Empty, Full, Queue
from threading import Event, Thread
from time import perf_counter_ns
from types import TracebackType

from kyrin.audio.audio_data import AudioData
from kyrin.audio.audio_errors import AudioCaptureStopError, AudioQueueOverflowError
from kyrin.audio.audio_input import AudioInput


class AudioCaptureQueue:
    """One capture session with one producer and one consumer.

    The worker owns the source iterator. On overflow, the stream fails visibly
    instead of discarding audio that might form part of a command.
    """

    def __init__(
        self,
        source: AudioInput,
        *,
        max_chunks: int = 8,
        stop_timeout_s: float = 1.0,
        clock_ns: Callable[[], int] = perf_counter_ns,
    ) -> None:
        if max_chunks <= 0:
            raise ValueError("max_chunks must be positive")
        if stop_timeout_s <= 0:
            raise ValueError("stop_timeout_s must be positive")

        self._source = source
        self._clock_ns = clock_ns
        self._queue: Queue[AudioData] = Queue(maxsize=max_chunks)
        self._stop_requested = Event()
        self._done = Event()
        self._error: Exception | None = None
        self._thread: Thread | None = None
        self._stop_timeout_s = stop_timeout_s

    def __enter__(self) -> AudioCaptureQueue:
        if self._thread is not None:
            raise RuntimeError("capture queue cannot be started twice")
        self._thread = Thread(
            target=self._produce, name="kyrin-audio-capture", daemon=True
        )
        self._thread.start()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self.stop()

    def _produce(self) -> None:
        iterator: Iterator[AudioData] | None = None
        try:
            iterator = self._source.capture()
            while not self._stop_requested.is_set():
                try:
                    chunk = next(iterator)
                except StopIteration:
                    break
                if self._stop_requested.is_set():
                    break
                try:
                    if chunk.capture_start_ns is None:
                        frames = len(chunk.data) // chunk.audio_format.bytes_per_frame
                        chunk = replace(
                            chunk,
                            capture_start_ns=self._clock_ns()
                            - (
                                frames * 1_000_000_000 // chunk.audio_format.sample_rate
                            ),
                        )
                    self._queue.put_nowait(chunk)
                except Full:
                    self._error = AudioQueueOverflowError(
                        "Audio capture queue filled before processing caught up"
                    )
                    break
        except Exception as exc:
            # A worker exception must reach the consuming thread.
            self._error = exc
        finally:
            if iterator is not None:
                close = getattr(iterator, "close", None)
                if callable(close):
                    try:
                        close()
                    except Exception as exc:
                        if self._error is None:
                            self._error = exc
            self._done.set()

    def chunks(self) -> Iterator[AudioData]:
        """Yield captured chunks in order, or propagate a capture failure."""
        if self._thread is None:
            raise RuntimeError("capture queue must be started before reading")
        while not self._stop_requested.is_set():
            if self._done.is_set() and self._error is not None:
                raise self._error
            try:
                chunk = self._queue.get(timeout=0.05)
            except Empty:
                if self._done.is_set():
                    return
                continue
            if self._done.is_set() and self._error is not None:
                raise self._error
            yield chunk

    def stop(self) -> None:
        """Request stop, release a pending source read, and join the worker."""
        first_stop = not self._stop_requested.is_set()
        self._stop_requested.set()
        stop_error: Exception | None = None
        if first_stop:
            try:
                self._source.stop_capture()
            except Exception as exc:
                stop_error = exc

        if self._thread is not None:
            self._thread.join(self._stop_timeout_s)
            if self._thread.is_alive():
                raise AudioCaptureStopError("Audio capture worker did not stop") from (
                    stop_error
                )
        if stop_error is not None:
            raise AudioCaptureStopError("Could not stop audio source") from stop_error
