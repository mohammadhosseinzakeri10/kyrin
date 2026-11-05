"""UI-facing runtime events without a graphical or platform dependency."""

from dataclasses import dataclass
from pathlib import Path

from kyrin.actions.models import ActionDecision, ActionFeedback
from kyrin.audio.live_speech_pipeline import LiveSpeechEvent
from kyrin.commands.models import CommandEvent
from kyrin.commands.ollama_device import CommandDeviceReport
from kyrin.responses.presenter import PresentedResponse
from kyrin.responses.speech import SpeechSynthesisError
from kyrin.runtime.speech_sessions import SpeechSessionEnded
from kyrin.runtime.voice_control import VoiceModeChanged
from kyrin.stt.device import ComputeDevice
from kyrin.system_power.flow import PowerPrompt
from kyrin.timing import TimingEvent


@dataclass(frozen=True, slots=True)
class CommandDeviceReported:
    """A single command inference attempt from one model store and session."""

    report: CommandDeviceReport
    session_id: str
    store_path: Path


@dataclass(frozen=True, slots=True)
class SttDeviceReady:
    """The device reported by the opened STT session, not a saved preference."""

    device: ComputeDevice


@dataclass(frozen=True, slots=True)
class AudioCaptureReady:
    """The selected microphone has supplied its first audio chunk."""

    session_id: str = ""
    generation: int = 0


@dataclass(frozen=True, slots=True)
class AudioDuplexChanged:
    """AEC routing is available, or conservative half-duplex is in use."""

    echo_cancelled: bool


ApplicationEvent = (
    TimingEvent
    | LiveSpeechEvent
    | CommandEvent
    | ActionDecision
    | ActionFeedback
    | SpeechSessionEnded
    | PresentedResponse
    | SpeechSynthesisError
    | CommandDeviceReported
    | SttDeviceReady
    | AudioCaptureReady
    | AudioDuplexChanged
    | PowerPrompt
    | VoiceModeChanged
)
