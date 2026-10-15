"""System-power prompts retain voice output in the Qt desktop composition."""

from typing import cast

import pytest

pytest.importorskip("PySide6")

from kyrin.app.qt.main import _announce_power, _close_speech  # noqa: E402
from kyrin.commands.models import ResponseChannel  # noqa: E402
from kyrin.responses.presenter import PresentedResponse  # noqa: E402
from kyrin.responses.speech import ResponseSpeaker, SpeechSynthesisError  # noqa: E402
from kyrin.system_power.flow import PowerAction, PowerPrompt, PowerStage  # noqa: E402
from kyrin.tts.runtime import ConfiguredSpeechSynthesizer  # noqa: E402


def test_power_announcement_sends_spoken_prompt_to_speaker() -> None:
    class RecordingSpeaker:
        def __init__(self) -> None:
            self.responses: list[PresentedResponse] = []

        def replace(
            self,
            response: PresentedResponse,
            *,
            speak: object = None,
            still_current: object = None,
        ) -> bool:
            self.responses.append(response)
            return True

    speaker = RecordingSpeaker()
    errors: list[SpeechSynthesisError] = []
    prompt = PowerPrompt(
        1,
        PowerAction.RESTART,
        PowerStage.FIRST,
        "Long visible warning",
        spoken=True,
        speech_text="Do you want to restart?",
    )

    _announce_power(prompt, cast(ResponseSpeaker, speaker), errors.append)

    assert len(speaker.responses) == 1
    assert speaker.responses[0].text == "Do you want to restart?"
    assert speaker.responses[0].channel is ResponseChannel.TEXT_AND_VOICE
    assert errors == []


def test_desktop_quit_releases_tts_before_closing_speech_worker() -> None:
    calls: list[str] = []

    class FakeSpeaker:
        def interrupt(self) -> None:
            calls.append("interrupt")

        def close(self) -> None:
            calls.append("speaker close")

    class FakeSynthesizer:
        def close(self) -> None:
            calls.append("models close")

    _close_speech(
        cast(ResponseSpeaker, FakeSpeaker()),
        cast(ConfiguredSpeechSynthesizer, FakeSynthesizer()),
    )

    assert calls == ["interrupt", "models close", "speaker close"]


def test_desktop_quit_closes_speaker_even_if_model_release_fails() -> None:
    calls: list[str] = []

    class FakeSpeaker:
        def interrupt(self) -> None:
            calls.append("interrupt")

        def close(self) -> None:
            calls.append("speaker close")

    class FakeSynthesizer:
        def close(self) -> None:
            calls.append("models close")
            raise RuntimeError("release failed")

    with pytest.raises(RuntimeError, match="release failed"):
        _close_speech(
            cast(ResponseSpeaker, FakeSpeaker()),
            cast(ConfiguredSpeechSynthesizer, FakeSynthesizer()),
        )

    assert calls == ["interrupt", "models close", "speaker close"]


def test_desktop_quit_bounds_speech_wait_when_cpu_model_is_stuck() -> None:
    calls: list[object] = []

    class FakeSpeaker:
        def interrupt(self) -> None:
            calls.append("interrupt")

        def close(self, *, timeout_s: float = 27) -> None:
            calls.append(("speaker close", timeout_s))
            raise SpeechSynthesisError("speech worker did not stop")

    class FakeSynthesizer:
        def close(self) -> bool:
            calls.append("models close")
            return False

    _close_speech(
        cast(ResponseSpeaker, FakeSpeaker()),
        cast(ConfiguredSpeechSynthesizer, FakeSynthesizer()),
    )

    assert calls == ["interrupt", "models close", ("speaker close", 1)]
