"""Safe, language-neutral notices for audio and transcription failures."""

from kyrin.audio.audio_backlog import BacklogNotice, BacklogState
from kyrin.audio.audio_errors import AudioError, AudioQueueOverflowError
from kyrin.commands.models import ResponseChannel
from kyrin.responses.models import SystemNotice, SystemNoticeKind
from kyrin.stt.errors import DeviceUnavailableError, SpeechToTextError


def notice_for_backlog(event: BacklogNotice) -> SystemNotice:
    """Tell the user when to pause and when the STT backlog has recovered."""
    if event.state is BacklogState.WAIT:
        return SystemNotice(
            SystemNoticeKind.PROCESSING_DELAYED, ResponseChannel.TEXT_AND_VOICE
        )
    return SystemNotice(SystemNoticeKind.PROCESSING_READY, ResponseChannel.TEXT_ONLY)


def notice_for_error(error: Exception) -> SystemNotice:
    """Classify known failures without exposing implementation details."""
    if isinstance(error, AudioQueueOverflowError):
        kind = SystemNoticeKind.PROCESSING_OVERLOADED
    elif isinstance(error, AudioError):
        kind = SystemNoticeKind.AUDIO_INPUT_FAILURE
    elif isinstance(error, DeviceUnavailableError):
        kind = SystemNoticeKind.COMPUTE_UNAVAILABLE
    elif isinstance(error, FileNotFoundError):
        kind = SystemNoticeKind.MODEL_UNAVAILABLE
    elif isinstance(error, SpeechToTextError):
        kind = SystemNoticeKind.TRANSCRIPTION_FAILURE
    else:
        kind = SystemNoticeKind.GENERAL_FAILURE
    return SystemNotice(kind, ResponseChannel.TEXT_AND_VOICE)
