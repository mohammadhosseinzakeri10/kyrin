"""UI-facing runtime events without a graphical or platform dependency."""

from kyrin.actions.models import ActionDecision, ActionFeedback
from kyrin.audio.live_speech_pipeline import LiveSpeechEvent
from kyrin.commands.models import CommandEvent
from kyrin.responses.presenter import PresentedResponse
from kyrin.responses.speech import SpeechSynthesisError
from kyrin.runtime.speech_sessions import SpeechSessionEnded

ApplicationEvent = (
    LiveSpeechEvent
    | CommandEvent
    | ActionDecision
    | ActionFeedback
    | SpeechSessionEnded
    | PresentedResponse
    | SpeechSynthesisError
)
