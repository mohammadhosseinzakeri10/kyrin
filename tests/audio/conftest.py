"""Audio unit tests replace capture devices and never initialize PortAudio."""

import sys
from types import ModuleType


class FakePortAudioError(Exception):
    pass


fake_sounddevice = ModuleType("sounddevice")
fake_sounddevice.PortAudioError = FakePortAudioError  # type: ignore[attr-defined]
fake_sounddevice.RawInputStream = None  # type: ignore[attr-defined]
sys.modules["sounddevice"] = fake_sounddevice
