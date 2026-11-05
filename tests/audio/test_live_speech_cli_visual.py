"""The optional diagnostic mascot follows the same English lifecycle contract."""

import argparse

import pytest

from kyrin.responses.visual_status import VisualPresentation, VisualStatusController
from kyrin.runtime.voice_control import VoiceMode, VoiceModeChanged
from kyrin.stt.transcript import TranscriptStatus, TranscriptUpdate
from scripts.audio import check_live_speech as diagnostic


@pytest.mark.parametrize("fail", [False, True])
def test_diagnostic_visual_uses_english_and_reports_startup_failure_or_close(
    monkeypatch: pytest.MonkeyPatch, fail: bool
) -> None:
    presentations: list[VisualPresentation] = []

    class Sink:
        @staticmethod
        def available() -> bool:
            return True

        def publish(self, value: VisualPresentation) -> None:
            presentations.append(value)

    def inert_run(
        args: argparse.Namespace, visual: VisualStatusController | None
    ) -> None:
        assert visual is not None
        assert presentations[-1].caption == "Starting microphone…"
        if fail:
            raise RuntimeError("private backend error")
        visual.on_capture_ready()
        assert presentations[-1].caption == "Ready to listen…"
        visual.on_live_event(TranscriptUpdate(0, "سلام", TranscriptStatus.FINAL, "fa"))
        assert presentations[-1].caption == "Understanding request…"
        visual.on_voice_state(VoiceModeChanged(VoiceMode.STANDBY, session_id="s"))
        assert presentations[-1].caption == "Standby. Say Start listening to speak."

    monkeypatch.setattr(diagnostic, "GnomeVisualStatusSink", Sink)
    monkeypatch.setattr(diagnostic, "_run", inert_run)
    args = argparse.Namespace(
        visual_feedback=True, language="fa", response_language="fa"
    )
    if fail:
        with pytest.raises(RuntimeError, match="private backend error"):
            diagnostic.run(args)
        assert "Listening unavailable" in presentations[-1].caption
        assert "private backend error" not in presentations[-1].caption
    else:
        diagnostic.run(args)
        assert "Microphone off" in presentations[-1].caption
