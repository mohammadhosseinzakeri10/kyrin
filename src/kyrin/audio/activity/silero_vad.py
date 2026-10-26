"""Offline Silero ONNX adapter for fixed mono PCM windows."""

import math
import os
from importlib import resources

import numpy as np

from kyrin.audio.audio_data import AudioData
from kyrin.audio.audio_format import AudioFormat, AudioSampleFormat


class SileroVad:
    """Detect speech in 512-sample windows at 16 kHz.

    One instance belongs to one continuous audio stream. Call ``reset`` when
    starting a new stream; pauses within the same stream do not reset state.
    """

    input_format = AudioFormat(16000, 1, AudioSampleFormat.INT16)
    frames_per_window = 512
    _context_samples = 64

    def __init__(self, threshold: float = 0.5) -> None:
        if not math.isfinite(threshold) or not 0.0 < threshold < 1.0:
            raise ValueError("threshold must be finite and between 0 and 1")

        # ONNX Runtime must see this before its first import, otherwise its
        # official build may initialize network telemetry and a device ID.
        os.environ["ORT_DISABLE_TELEMETRY"] = "1"
        import onnxruntime as ort  # type: ignore[import-untyped]

        self.threshold = threshold
        ort.disable_telemetry_events()
        options = ort.SessionOptions()
        options.inter_op_num_threads = 1
        options.intra_op_num_threads = 1
        model = resources.files("kyrin.audio.activity.models").joinpath(
            "silero_vad.onnx"
        )
        self._session = ort.InferenceSession(
            model.read_bytes(),
            sess_options=options,
            providers=["CPUExecutionProvider"],
        )
        self.reset()

    def reset(self) -> None:
        """Start model processing from a fresh audio stream."""
        self._state = np.zeros((2, 1, 128), dtype=np.float32)
        self._context = np.zeros((1, self._context_samples), dtype=np.float32)

    def detect(self, window: AudioData) -> bool:
        """Return whether this complete window contains speech."""
        if window.audio_format != self.input_format:
            raise ValueError("SileroVad requires mono INT16 audio at 16000 Hz")
        expected_bytes = self.frames_per_window * self.input_format.bytes_per_frame
        if len(window.data) != expected_bytes:
            raise ValueError("SileroVad requires exactly 512 samples per window")

        samples = np.frombuffer(window.data, dtype=np.int16).astype(np.float32)
        samples /= 32768.0
        model_input = np.concatenate((self._context, samples.reshape(1, -1)), axis=1)
        outputs = self._session.run(
            None,
            {
                "input": model_input,
                "state": self._state,
                "sr": np.array(16000, dtype=np.int64),
            },
        )
        self._state = outputs[1]
        self._context = model_input[:, -self._context_samples :].copy()
        return bool(outputs[0][0, 0] > self.threshold)
