"""Convert a continuous mono PCM stream to a configured sample rate."""

from collections.abc import Iterable, Iterator

import numpy as np
import soxr  # type: ignore[import-untyped]

from kyrin.audio.audio_data import AudioData
from kyrin.audio.audio_format import AudioFormat, AudioSampleFormat


class SampleRateConverter:
    """Resample mono INT16 audio while preserving state between input chunks."""

    def __init__(self, input_format: AudioFormat, target_sample_rate: int) -> None:
        if (
            input_format.channels != 1
            or input_format.sample_format is not AudioSampleFormat.INT16
        ):
            raise ValueError("sample rate conversion requires mono INT16 input")
        if target_sample_rate <= 0:
            raise ValueError("target_sample_rate must be positive")

        self.input_format = input_format
        self.output_format = AudioFormat(
            sample_rate=target_sample_rate,
            channels=1,
            sample_format=AudioSampleFormat.INT16,
        )

    def convert(self, chunks: Iterable[AudioData]) -> Iterator[AudioData]:
        """Yield converted chunks and flush the filter when the stream ends.

        Each call starts an independent stream. Empty output chunks are omitted;
        output chunk sizes need not match input chunk sizes.
        """
        if self.input_format.sample_rate == self.output_format.sample_rate:
            resampler = None
        else:
            resampler = soxr.ResampleStream(
                self.input_format.sample_rate,
                self.output_format.sample_rate,
                1,
                dtype="int16",
                quality="MQ",
            )

        origin_ns: int | None = None
        output_frames = 0
        seen_input = False

        def timed_audio(data: bytes) -> AudioData:
            nonlocal output_frames
            start_ns = (
                origin_ns
                + output_frames * 1_000_000_000 // self.output_format.sample_rate
                if origin_ns is not None
                else None
            )
            output_frames += len(data) // self.output_format.bytes_per_frame
            return AudioData(data, self.output_format, start_ns)

        for chunk in chunks:
            if chunk.audio_format != self.input_format:
                raise ValueError("audio chunk format changed during conversion")
            if not chunk.data:
                continue

            if resampler is None:
                yield chunk
                continue

            if not seen_input:
                origin_ns = chunk.capture_start_ns
                seen_input = True
            samples = np.frombuffer(chunk.data, dtype=np.int16)
            converted = resampler.resample_chunk(samples)
            if converted.size:
                yield timed_audio(converted.tobytes())

        if resampler is not None:
            tail = resampler.resample_chunk(np.empty(0, dtype=np.int16), last=True)
            if tail.size:
                yield timed_audio(tail.tobytes())
