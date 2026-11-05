"""Small, UI-independent visual states derived from structured runtime events."""

from collections.abc import Callable
from dataclasses import dataclass, replace
from enum import StrEnum
from threading import RLock

from kyrin.actions.control_policy import ControlConfirmation
from kyrin.actions.models import (
    ActionDecision,
    ActionFeedback,
    ActionKey,
    ActionNotice,
    ActionNoticeReason,
    ActionOutcome,
    ActionRequest,
)
from kyrin.audio.activity.speech_activity_monitor import (
    SpeechActivityFrame,
    SpeechTransition,
)
from kyrin.audio.audio_backlog import BacklogNotice, BacklogState
from kyrin.audio.live_speech_pipeline import LiveSpeechEvent
from kyrin.commands.models import (
    CommandEvent,
    CommandKind,
    CommandPlanResolution,
    CommandResolution,
    ResponseKind,
    ResponseRequest,
)
from kyrin.responses.models import SystemNotice
from kyrin.responses.presenter import ResponsePresenter
from kyrin.responses.system_notices import notice_for_backlog, notice_for_error
from kyrin.responses.visual_captions import action_caption
from kyrin.runtime.speech_sessions import SpeechSessionEnded
from kyrin.runtime.voice_control import VoiceMode, VoiceModeChanged, control_phrase
from kyrin.stt.transcript import TranscriptStatus, TranscriptUpdate
from kyrin.system_power.flow import PowerPrompt, PowerStage
from kyrin.timing import TimingEvent


class VisualStatus(StrEnum):
    READY = "ready"
    CONVERSATION = "conversation"
    LISTENING = "listening"
    PROCESSING = "processing"
    QUESTION = "question"
    EXECUTING = "executing"
    CONFIRMED = "confirmed"
    UNVERIFIED = "unverified"
    FAILED = "failed"


@dataclass(frozen=True, slots=True)
class VisualPresentation:
    """A short, localized description of the state shown by any visual adapter."""

    status: VisualStatus
    caption: str


_CAPTIONS = {
    "en": {
        VisualStatus.READY: "Ready to listen…",
        VisualStatus.CONVERSATION: "Responding…",
        VisualStatus.LISTENING: "Listening…",
        VisualStatus.PROCESSING: "Understanding request…",
        VisualStatus.QUESTION: "Please clarify…",
        VisualStatus.EXECUTING: "Working…",
        VisualStatus.CONFIRMED: "Done.",
        VisualStatus.UNVERIFIED: "Result not confirmed.",
        VisualStatus.FAILED: "Could not complete that.",
    },
    "fa": {
        VisualStatus.READY: "آمادهٔ شنیدن…",
        VisualStatus.CONVERSATION: "در حال پاسخ‌دادن…",
        VisualStatus.LISTENING: "در حال گوش‌دادن…",
        VisualStatus.PROCESSING: "در حال بررسی درخواست…",
        VisualStatus.QUESTION: "لطفاً توضیح دهید…",
        VisualStatus.EXECUTING: "در حال انجام کار…",
        VisualStatus.CONFIRMED: "انجام شد.",
        VisualStatus.UNVERIFIED: "نتیجه هنوز تأیید نشده است.",
        VisualStatus.FAILED: "نتوانستم کار را انجام دهم.",
    },
}


_LIFECYCLE_CAPTIONS = {
    "en": {
        "starting": "Starting microphone…",
        "standby": "Standby. Say Start listening to speak.",
        "off": "Microphone off. Press Start listening to turn it on.",
        "stopping": "Stopping microphone…",
        "retrying": "Speech recognition interrupted; reconnecting…",
        "failed": "Listening unavailable. Check the microphone and speech model.",
        "transcribing": "Transcribing speech…",
        "file": "Processing audio file…",
        "file_done": "Audio file processing finished.",
        "file_stopped": "Audio file processing stopped.",
        "setup": "Choose a speech model to enable listening.",
        "queued": "Request queued for understanding…",
        "model_wait": "Waiting for the request model…",
        "model_run": "The model is processing your request…",
        "playback_failed": "Voice output failed; the text response is still available.",
        "file_failed": "Audio file processing failed. Check the file and speech model.",
        "file_unavailable": (
            "Audio-file input is unavailable. Check the speech settings."
        ),
        "model_failed": (
            "The request model failed. No action was executed; "
            "check the model settings."
        ),
        "file_save": "Save current settings before importing audio.",
    },
    "fa": {
        "starting": "در حال آماده‌سازی میکروفن…",
        "standby": "آماده‌باش؛ برای صحبت‌کردن بگویید «Start listening».",
        "off": "میکروفن خاموش است؛ برای روشن‌کردن، «شروع شنیدن» را بزنید.",
        "stopping": "در حال خاموش‌کردن میکروفن…",
        "retrying": "تشخیص گفتار قطع شده؛ در حال اتصال مجدد…",
        "failed": "شنیدن در دسترس نیست؛ میکروفن و مدل گفتار را بررسی کنید.",
        "transcribing": "در حال تبدیل گفتار به متن…",
        "file": "در حال پردازش فایل صوتی…",
        "file_done": "پردازش فایل صوتی پایان یافت.",
        "file_stopped": "پردازش فایل صوتی متوقف شد.",
        "setup": "برای فعال‌کردن شنیدن، مدل گفتار را انتخاب کنید.",
        "queued": "درخواست در صفِ فهم گفتار است…",
        "model_wait": "در انتظار آماده‌شدن مدل درخواست…",
        "model_run": "مدل در حال پردازش درخواست شماست…",
        "playback_failed": "خروجی صوتی ناموفق بود؛ پاسخ متنی همچنان در دسترس است.",
        "file_failed": "پردازش فایل صوتی ناموفق بود؛ فایل و مدل گفتار را بررسی کنید.",
        "file_unavailable": (
            "ورودی فایل صوتی در دسترس نیست؛ تنظیمات گفتار را بررسی کنید."
        ),
        "model_failed": (
            "مدل درخواست با خطا روبه‌رو شد؛ کاری اجرا نشد. تنظیمات مدل را بررسی کنید."
        ),
        "file_save": "پیش از واردکردن فایل صوتی، تنظیمات فعلی را ذخیره کنید.",
    },
}


def _caption_language(language: str | None) -> str:
    primary = (language or "en").strip().replace("_", "-").split("-", 1)[0].lower()
    return primary if primary in _CAPTIONS else "en"


def listening_lifecycle_presentation(
    phase: str,
    *,
    language: str = "en",
) -> VisualPresentation:
    """Render app states that also exist before a speech runtime is created."""
    return VisualPresentation(
        VisualStatus.FAILED
        if phase in {"failed", "file_failed", "file_unavailable", "playback_failed"}
        else VisualStatus.READY,
        _LIFECYCLE_CAPTIONS[_caption_language(language)][phase],
    )


def power_presentation(prompt: PowerPrompt) -> VisualPresentation:
    """Report consent stages; accepted OS requests are not verified completion."""
    status = {
        PowerStage.CHECKING: VisualStatus.PROCESSING,
        PowerStage.FIRST: VisualStatus.QUESTION,
        PowerStage.SECOND: VisualStatus.QUESTION,
        PowerStage.SUBMITTING: VisualStatus.EXECUTING,
        PowerStage.FINISHED: VisualStatus.UNVERIFIED,
        PowerStage.CANCELLED: VisualStatus.READY,
        PowerStage.EXPIRED: VisualStatus.READY,
        PowerStage.FAILED: VisualStatus.FAILED,
    }[prompt.stage]
    if prompt.preview and status in {VisualStatus.EXECUTING, VisualStatus.UNVERIFIED}:
        status = (
            VisualStatus.PROCESSING
            if prompt.stage is PowerStage.SUBMITTING
            else VisualStatus.READY
        )
    return VisualPresentation(status, prompt.text)


class VisualStatusController:
    """Publish state changes without confusing execution with completion.

    The action worker and audio consumer may call this concurrently. While an
    action is executing, newer transcripts cannot replace its running state.
    """

    def __init__(
        self,
        publish: Callable[[VisualPresentation], None],
        *,
        language: str = "en",
        capture_ready: bool = True,
        voice_mode: VoiceMode = VoiceMode.ACTIVE,
        file_input: bool = False,
    ) -> None:
        self._publish = publish
        self._language = _caption_language(language)
        self._presenter = ResponsePresenter(language)
        self._lock = RLock()
        self._presentation: VisualPresentation | None = None
        self._executing = False
        self._mode = voice_mode
        self._voice_state: VoiceModeChanged | None = None
        self._capture_ready = capture_ready
        self._phase = "ready" if capture_ready else "starting"
        self._speaking = False
        self._file_input = file_input
        self._closed = False
        self._last_text: tuple[int, int] | None = None
        self._last_final_text: tuple[int, int] | None = None
        self._latest_decision: tuple[int, int] | None = None
        self._awaiting_transcript = False
        self._action_key: ActionKey | None = None
        self._action_label = ""
        self._pending_action: tuple[ActionKey, str] | None = None
        self._before_backlog: VisualPresentation | None = None
        self._backlog_caption: str | None = None
        self._failure_caption: str | None = None
        self._model_failed_request: tuple[int, int] | None = None
        self._show_idle()

    def _set(
        self,
        status: VisualStatus,
        *,
        caption: str | None = None,
        executing: bool | None = None,
        unless_executing: bool = False,
        requires_active: bool = False,
    ) -> None:
        with self._lock:
            if self._closed or (
                requires_active
                and (self._mode is not VoiceMode.ACTIVE or self._phase != "ready")
            ):
                return
            if unless_executing and self._executing:
                return
            # Caption language is an explicit presentation preference. A
            # multilingual transcript must never silently change it.
            if executing is not None:
                self._executing = executing
            text = caption or _CAPTIONS[self._language][status]
            if executing is False and self._phase in {"stopping", "retrying", "failed"}:
                text += " " + self._phase_caption()
            if (
                self._mode is VoiceMode.STANDBY
                and self._phase == "ready"
                and text != _LIFECYCLE_CAPTIONS[self._language]["standby"]
            ):
                text += " " + _LIFECYCLE_CAPTIONS[self._language]["standby"]
            presentation = VisualPresentation(status, text)
            if self._presentation == presentation:
                return
            self._presentation = presentation
            self._publish(presentation)

    def _phase_caption(self) -> str:
        caption = _LIFECYCLE_CAPTIONS[self._language][self._phase]
        if self._phase in {"retrying", "failed"} and self._failure_caption:
            return self._failure_caption + " " + caption
        return caption

    def _show_idle(self, *, unless_executing: bool = False) -> None:
        captions = _LIFECYCLE_CAPTIONS[self._language]
        if self._phase in {"starting", "stopping", "retrying", "failed"}:
            self._set(
                VisualStatus.FAILED if self._phase == "failed" else VisualStatus.READY,
                caption=self._phase_caption(),
                unless_executing=unless_executing,
            )
        elif self._mode is VoiceMode.OFF:
            self._set(
                VisualStatus.READY,
                caption=captions["off"],
                unless_executing=unless_executing,
            )
        elif self._mode is VoiceMode.STANDBY:
            self._set(
                VisualStatus.READY,
                caption=captions["standby"],
                unless_executing=unless_executing,
            )
        else:
            self._set(
                VisualStatus.PROCESSING if self._file_input else VisualStatus.READY,
                caption=captions["file"] if self._file_input else None,
                unless_executing=unless_executing,
            )

    def on_voice_state(self, event: VoiceModeChanged) -> None:
        """Observe authorized routing changes; never interpret them as authority."""
        with self._lock:
            previous = self._voice_state
            if previous is not None and (
                previous.session_id != event.session_id
                or event.revision < previous.revision
            ):
                return
            self._voice_state = event
            self._mode = event.mode
            self._speaking = False
            self._awaiting_transcript = False
            if event.mode is VoiceMode.OFF and self._phase != "failed":
                self._phase = "stopping"
            if not self._executing:
                # An independent app/power caption may have replaced the last
                # runtime caption. Explicit controls must reassert this mode,
                # including a repeated Start listening acknowledgement.
                self._presentation = None
            self._show_idle(unless_executing=True)

    def on_capture_ready(self) -> None:
        with self._lock:
            if (
                self._closed
                or self._phase in {"stopping", "failed"}
                or self._mode is VoiceMode.OFF
            ):
                return
            if self._capture_ready and self._phase == "ready":
                return
            self._capture_ready = True
            self._failure_caption = None
            self._phase = "ready"
            self._show_idle(unless_executing=True)

    def on_session_end(self, event: SpeechSessionEnded) -> None:
        with self._lock:
            if self._closed or self._phase == "stopping":
                return
            self._capture_ready = False
            self._speaking = False
            if event.error is not None:
                self._failure_caption = self._present(notice_for_error(event.error))
                self._phase = (
                    "retrying" if event.retry_delay_s is not None else "failed"
                )
                self._show_idle(unless_executing=True)
            elif not self._file_input:
                self._mode = VoiceMode.OFF
                self._show_idle(unless_executing=True)

    def on_stopping(self) -> None:
        with self._lock:
            self._phase = "stopping"
            self._speaking = False
            self._show_idle(unless_executing=True)

    def on_closed(
        self, *, failed: bool = False, error: Exception | None = None
    ) -> None:
        with self._lock:
            self._executing = False
            self._capture_ready = False
            if error is not None:
                self._failure_caption = self._present(notice_for_error(error))
            if failed or self._phase == "failed":
                self._phase = "failed"
                self._show_idle()
            elif self._file_input:
                was_standby = self._mode is VoiceMode.STANDBY
                self._mode = VoiceMode.OFF
                caption = _LIFECYCLE_CAPTIONS[self._language][
                    "file_stopped" if self._phase == "stopping" else "file_done"
                ]
                if (
                    self._phase != "stopping"
                    and self._presentation is not None
                    and self._presentation.status
                    in {
                        VisualStatus.CONFIRMED,
                        VisualStatus.UNVERIFIED,
                        VisualStatus.FAILED,
                        VisualStatus.QUESTION,
                        VisualStatus.CONVERSATION,
                    }
                ):
                    previous_caption = self._presentation.caption
                    if was_standby:
                        previous_caption = previous_caption.removesuffix(
                            " " + _LIFECYCLE_CAPTIONS[self._language]["standby"]
                        )
                    self._set(
                        self._presentation.status,
                        caption=previous_caption + " " + caption,
                    )
                else:
                    self._set(VisualStatus.READY, caption=caption)
            else:
                self._phase = "ready"
                self._mode = VoiceMode.OFF
                self._show_idle()
            self._closed = True

    def on_live_event(self, event: LiveSpeechEvent, *, stream_id: int = 0) -> None:
        with self._lock:
            if self._closed or self._phase in {"stopping", "failed", "retrying"}:
                return
            if isinstance(event, BacklogNotice):
                if self._mode is not VoiceMode.ACTIVE:
                    return
                if event.state is BacklogState.WAIT:
                    if self._backlog_caption is None:
                        self._before_backlog = self._presentation
                    self._backlog_caption = self._present(notice_for_backlog(event))
                    self._set(
                        VisualStatus.PROCESSING,
                        caption=self._backlog_caption,
                        unless_executing=True,
                        requires_active=True,
                    )
                else:
                    if (
                        self._presentation is not None
                        and self._presentation.caption == self._backlog_caption
                    ):
                        previous = self._before_backlog
                        if previous is not None:
                            self._set(
                                previous.status,
                                caption=previous.caption,
                                unless_executing=True,
                            )
                    self._before_backlog = None
                    self._backlog_caption = None
                return
            if isinstance(event, TranscriptUpdate):
                identity = (stream_id, event.segment_id)
                if (
                    self._last_final_text is not None
                    and identity <= self._last_final_text
                ):
                    return
                if self._last_text is not None and identity < self._last_text:
                    return
                self._last_text = identity
                self._awaiting_transcript = False
                if event.status is TranscriptStatus.FINAL:
                    self._last_final_text = identity
            if isinstance(event, (TranscriptUpdate, SpeechActivityFrame)):
                self._capture_ready = True
                self._phase = "ready"
            if isinstance(event, TranscriptUpdate):
                if (
                    event.status is TranscriptStatus.FINAL
                    and control_phrase(
                        event.text, active=self._mode is VoiceMode.ACTIVE
                    )
                    is not None
                ):
                    # The runtime already consumed this control. Rendering its
                    # raw transcript must not leave "Understanding" on screen.
                    self._show_idle(unless_executing=True)
                    return
                if not event.text.strip():
                    if self._presentation is not None and self._presentation.status in {
                        VisualStatus.LISTENING,
                        VisualStatus.PROCESSING,
                    }:
                        self._show_idle(unless_executing=True)
                    return
                self._set(
                    VisualStatus.LISTENING
                    if self._speaking and event.status is TranscriptStatus.PARTIAL
                    else VisualStatus.PROCESSING,
                    caption=_LIFECYCLE_CAPTIONS[self._language]["transcribing"]
                    if event.status is TranscriptStatus.PARTIAL and not self._speaking
                    else None,
                    unless_executing=True,
                    requires_active=True,
                )
            elif isinstance(event, SpeechActivityFrame):
                if event.transition is SpeechTransition.STARTED:
                    self._speaking = True
                    self._awaiting_transcript = True
                    self._set(
                        VisualStatus.LISTENING,
                        unless_executing=True,
                        requires_active=True,
                    )
                elif event.transition is SpeechTransition.PAUSED:
                    self._speaking = False
                    if self._utterance_finalized():
                        return
                    self._set(
                        VisualStatus.PROCESSING,
                        caption=_LIFECYCLE_CAPTIONS[self._language]["transcribing"],
                        unless_executing=True,
                        requires_active=True,
                    )

    def on_timing(self, event: TimingEvent) -> None:
        """Show queue/model starts without erasing replies on timing finishes."""
        with self._lock:
            if (
                self._speaking and not self._utterance_finalized()
            ) or not self._request_is_current(
                event.key.stream_id, event.key.segment_id
            ):
                return
            if event.stage == "model_failed":
                self._model_failed_request = (event.key.stream_id, event.key.segment_id)
                self._set(
                    VisualStatus.FAILED,
                    caption=_LIFECYCLE_CAPTIONS[self._language]["model_failed"],
                    unless_executing=True,
                    requires_active=True,
                )
                return
            if event.stage == "inference_started":
                self._model_failed_request = None
            phase = {
                "understanding_queued": "queued",
                "understanding_started": "understanding",
                "model_resource_wait_started": "model_wait",
                "model_resource_run_started": "model_run",
                "inference_started": "model_run",
            }.get(event.stage)
            if event.stage == "action_queued" and self._pending_action is not None:
                key, label = self._pending_action
                if (key.stream_id, key.segment_id) != (
                    event.key.stream_id,
                    event.key.segment_id,
                ):
                    return
                caption = (
                    f"در صف اجرا: {label}…"
                    if self._language == "fa"
                    else f"Queued for execution: {label}…"
                )
            elif phase == "understanding":
                caption = _CAPTIONS[self._language][VisualStatus.PROCESSING]
            elif phase is not None:
                caption = _LIFECYCLE_CAPTIONS[self._language][phase]
            else:
                return
            self._set(
                VisualStatus.PROCESSING,
                caption=caption,
                unless_executing=True,
                requires_active=True,
            )

    def on_power_prompt(self, prompt: PowerPrompt) -> None:
        with self._lock:
            presentation = power_presentation(prompt)
            self._set(
                presentation.status, caption=presentation.caption, unless_executing=True
            )

    def on_control_prompt(self, prompt: ControlConfirmation) -> None:
        with self._lock:
            if self._mode is not VoiceMode.ACTIVE or self._phase != "ready":
                return
            if self._action_key is not None and prompt.key != self._action_key:
                return
            label = self._action_label or prompt.target.label
            caption = (
                f"در پنجرهٔ تأیید پاسخ دهید: {label}"
                if self._language == "fa"
                else f"Confirm in the dialog: {label}"
            )
            self._set(VisualStatus.QUESTION, caption=caption)

    def on_control_approved(self) -> None:
        with self._lock:
            if self._mode is not VoiceMode.ACTIVE or self._phase != "ready":
                return
            caption = (
                f"در حال اجرا: {self._action_label}…"
                if self._language == "fa"
                else f"Executing: {self._action_label}…"
            )
            self._set(VisualStatus.EXECUTING, caption=caption)

    def _present(
        self, event: ResponseRequest | ActionNotice | ActionFeedback | SystemNotice
    ) -> str:
        return self._presenter.present(replace(event, language=self._language)).text

    def _request_is_current(self, stream_id: int, segment_id: int) -> bool:
        return not self._awaiting_transcript and (
            self._last_text is None or (stream_id, segment_id) >= self._last_text
        )

    def _utterance_finalized(self) -> bool:
        return (
            not self._awaiting_transcript
            and self._last_text is not None
            and self._last_text == self._last_final_text
        )

    def on_command_event(self, event: CommandEvent) -> None:
        with self._lock:
            if not self._request_is_current(event.stream_id, event.segment_id):
                return
            if isinstance(
                event, (CommandResolution, CommandPlanResolution, ResponseRequest)
            ):
                self._latest_decision = (event.stream_id, event.segment_id)
            if self._model_failed_request == (event.stream_id, event.segment_id) and (
                isinstance(event, CommandResolution)
                and event.intent is None
                or isinstance(event, ResponseRequest)
                and event.kind is ResponseKind.REPEAT_COMMAND
            ):
                self._set(
                    VisualStatus.FAILED,
                    caption=_LIFECYCLE_CAPTIONS[self._language]["model_failed"],
                    unless_executing=True,
                    requires_active=True,
                )
                return
            if isinstance(event, (CommandResolution, CommandPlanResolution)):
                key = ActionKey(event.stream_id, event.segment_id)
                if isinstance(event, CommandPlanResolution):
                    count = len(event.plan.steps)
                    label = (
                        f"طرح {count} مرحله‌ای"
                        if self._language == "fa"
                        else f"{count}-step command plan"
                    )
                elif event.intent is not None:
                    label = action_caption(event.intent, self._language)
                else:
                    label = ""
                if label:
                    self._pending_action = (key, label)
                    caption = (
                        f"در حال بررسی مجوز: {label}…"
                        if self._language == "fa"
                        else f"Checking permission: {label}…"
                    )
                    self._set(
                        VisualStatus.PROCESSING,
                        caption=caption,
                        unless_executing=True,
                        requires_active=True,
                    )
                    return
            self._on_command_event(event)

    def _on_command_event(self, event: CommandEvent) -> None:
        if (
            isinstance(event, ResponseRequest)
            and event.kind is ResponseKind.CONVERSATION
        ):
            self._set(
                VisualStatus.CONVERSATION,
                caption=self._present(event),
                unless_executing=True,
                requires_active=True,
            )
        elif (
            isinstance(event, ResponseRequest)
            and event.kind is ResponseKind.READY_FOR_COMMAND
        ):
            self._set(
                VisualStatus.READY,
                caption=self._present(event),
                unless_executing=True,
                requires_active=True,
            )
        elif isinstance(event, ResponseRequest):
            self._set(
                VisualStatus.QUESTION,
                caption=self._present(event),
                unless_executing=True,
                requires_active=True,
            )
        elif isinstance(event, CommandResolution) and event.intent is None:
            # A final non-command or negation ends processing. A following
            # clarification request, when present, replaces READY with QUESTION.
            self._show_idle(unless_executing=True)

    def on_action_start(self, request: ActionRequest) -> None:
        with self._lock:
            self._action_key = request.key
            self._action_label = action_caption(request.intent, self._language)
            self._set(
                VisualStatus.EXECUTING,
                caption=action_caption(request.intent, self._language, running=True),
                executing=True,
            )

    def on_chat_navigation_start(self, request: ActionRequest) -> None:
        """The existing selection worker is reading another visible results page."""
        with self._lock:
            self._action_key = request.key
            self._action_label = action_caption(request.intent, self._language)
            target = request.intent.target
            self._set(
                VisualStatus.EXECUTING,
                caption=f"در حال بارگذاری گزینه‌های بیشتر چت برای {target}…"
                if self._language == "fa"
                else f"Loading more chat choices for {target}…",
                executing=True,
            )

    def on_action_error(self) -> None:
        """An executor raised before it could return structured feedback."""
        caption = _CAPTIONS[self._language][VisualStatus.UNVERIFIED]
        if self._action_label:
            caption = self._action_label + " — " + caption
        self._set(VisualStatus.UNVERIFIED, caption=caption, executing=False)

    def on_playback_error(self) -> None:
        """Report failed voice output without changing the command's actual state."""
        with self._lock:
            notice = _LIFECYCLE_CAPTIONS[self._language]["playback_failed"]
            current = self._presentation
            if current is not None and notice in current.caption:
                return
            caption = current.caption if current is not None else ""
            standby = _LIFECYCLE_CAPTIONS[self._language]["standby"]
            if self._mode is VoiceMode.STANDBY and self._phase == "ready":
                # _set adds the current mode footer once. Keep it at the end
                # so file closure can remove guidance for ended capture.
                caption = (
                    "" if caption == standby else caption.removesuffix(" " + standby)
                )
            self._set(
                current.status if current is not None else VisualStatus.FAILED,
                caption=(caption + " " + notice).strip(),
            )

    def on_chat_selection_prompt(self, event: ResponseRequest) -> None:
        """A named-chat action has stopped executing and now needs a choice."""
        with self._lock:
            if (
                self._latest_decision is not None
                and (event.stream_id, event.segment_id) < self._latest_decision
            ):
                return
            if self._action_key is not None and (event.stream_id, event.segment_id) != (
                self._action_key.stream_id,
                self._action_key.segment_id,
            ):
                return
            self._set(
                VisualStatus.QUESTION,
                caption=self._present(event),
                executing=False,
                requires_active=True,
            )

    def on_action_output(self, output: ActionDecision | ActionFeedback) -> None:
        with self._lock:
            if (
                not self._executing
                and self._latest_decision is not None
                and (output.key.stream_id, output.key.segment_id)
                < self._latest_decision
            ):
                return
            if (
                isinstance(output, ActionFeedback)
                and self._action_key is not None
                and output.key < self._action_key
            ):
                return
            if (
                self._executing
                and self._action_key is not None
                and isinstance(output, ActionFeedback)
                and output.key != self._action_key
            ):
                return
            self._on_action_output(output)

    def _on_action_output(self, output: ActionDecision | ActionFeedback) -> None:
        if isinstance(output, ActionRequest):
            # An authorized dry-run decision never starts an OS action.
            label = action_caption(output.intent, self._language)
            caption = (
                f"فقط پیش‌نمایش: {label}؛ کاری اجرا نشد."
                if self._language == "fa"
                else f"Preview only: {label}; no action was executed."
            )
            self._set(
                VisualStatus.READY,
                caption=caption,
                unless_executing=True,
                requires_active=True,
            )
            return
        if isinstance(output, ActionNotice):
            # A BUSY notice can arrive while the worker is running another
            # action. Its text is still shown, but it must not stop the run icon.
            self._set(
                {
                    ActionNoticeReason.NOT_ALLOWED: VisualStatus.FAILED,
                    ActionNoticeReason.CONFIRMATION_REQUIRED: VisualStatus.QUESTION,
                    ActionNoticeReason.BUSY: VisualStatus.READY,
                    ActionNoticeReason.CANCELLED: VisualStatus.READY,
                    ActionNoticeReason.UNSUPPORTED: VisualStatus.FAILED,
                    ActionNoticeReason.DEPENDENCY_UNVERIFIED: VisualStatus.UNVERIFIED,
                }[output.reason],
                caption=action_caption(output.intent, self._language)
                + " — "
                + self._present(output),
                unless_executing=True,
                requires_active=True,
            )
            return
        if (
            output.intent.kind
            in (
                CommandKind.SHOW_APP_WINDOWS,
                CommandKind.SHOW_ALL_WINDOWS,
            )
            and output.outcome is ActionOutcome.LAUNCH_ACCEPTED
        ):
            self._set(
                VisualStatus.QUESTION,
                caption=(
                    "شمارهٔ پنجره را بگویید یا روی آن کلیک کنید."
                    if self._language == "fa"
                    else "Say a window number or click its preview."
                ),
                executing=False,
            )
            return
        status = {
            ActionOutcome.CONFIRMED: VisualStatus.CONFIRMED,
            ActionOutcome.LAUNCH_ACCEPTED: VisualStatus.UNVERIFIED,
            ActionOutcome.DISPATCHED_UNVERIFIED: VisualStatus.UNVERIFIED,
            ActionOutcome.UNKNOWN: VisualStatus.UNVERIFIED,
            ActionOutcome.FAILED: VisualStatus.FAILED,
        }[output.outcome]
        if output.error_code in {
            "chat_selection_cancelled",
            "visible_control_confirmation_declined",
            "window_close_confirmation_declined",
        }:
            status = VisualStatus.READY
        elif output.error_code in {
            "chat_selection_expired",
            "visible_control_confirmation_expired",
        }:
            status = VisualStatus.QUESTION
        self._set(
            status,
            caption=action_caption(output.intent, self._language)
            + " — "
            + self._present(output),
            executing=False,
        )
