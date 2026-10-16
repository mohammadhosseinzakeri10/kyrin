"""UI-facing runtime events without a graphical or platform dependency."""

from dataclasses import dataclass

from kyrin.actions.models import ActionDecision, ActionFeedback
from kyrin.audio.live_speech_pipeline import LiveSpeechEvent
from kyrin.commands.models import CommandEvent
from kyrin.responses.presenter import PresentedResponse
from kyrin.responses.speech import SpeechSynthesisError
from kyrin.runtime.speech_sessions import SpeechSessionEnded
from kyrin.runtime.voice_control import VoiceModeChanged
from kyrin.stt.device import ComputeDevice
from kyrin.system_power.flow import PowerPrompt


@dataclass(frozen=True, slots=True)
class SttDeviceReady:
    """The device reported by the opened STT session, not a saved preference."""

    device: ComputeDevice


@dataclass(frozen=True, slots=True)
class AudioCaptureReady:
    """The selected microphone has supplied its first audio chunk."""


ApplicationEvent = (
    LiveSpeechEvent
    | CommandEvent
    | ActionDecision
    | ActionFeedback
    | SpeechSessionEnded
    | PresentedResponse
    | SpeechSynthesisError
    | SttDeviceReady
    | AudioCaptureReady
    | PowerPrompt
    | VoiceModeChanged
)
