"""Fresh recordings cannot be scored using the read-aloud plan as reference."""

import hashlib
import json
from pathlib import Path
from unittest.mock import patch

import pytest

from scripts.commands.evaluate_l04_audio import load_audio_cases


def test_new_audio_requires_separate_speaker_reference(tmp_path: Path) -> None:
    private = tmp_path / "local-data"
    private.mkdir()
    audio = private / "test.wav"
    audio.write_bytes(b"fixture bytes; no real voice")
    digest = hashlib.sha256(audio.read_bytes()).hexdigest()
    reference = private / "test.reference.json"
    row = {
        "id": "independent",
        "audio_path": "local-data/test.wav",
        "sha256": digest,
        "spoken_reference": "Scroll up",
        "reference_proof": "local-data/test.reference.json",
    }
    manifest = private / "cases.jsonl"
    manifest.write_text(json.dumps(row) + "\n")
    proof = {
        "audio_sha256": digest,
        "intended_prompt": "Scroll up",
        "verified_by_speaker": False,
    }
    reference.write_text(json.dumps(proof))
    with patch("scripts.commands.evaluate_l04_audio.ROOT", tmp_path):
        with pytest.raises(ValueError, match="speaker-verified"):
            load_audio_cases(manifest)
        proof.update(verified_by_speaker=True, actually_spoken_reference="Scroll up")
        reference.write_text(json.dumps(proof))
        assert load_audio_cases(manifest)[0]["spoken_reference"] == "Scroll up"
        audio.write_bytes(b"changed")
        with pytest.raises(ValueError, match="audio changed"):
            load_audio_cases(manifest)


def test_stt_startup_failure_is_preserved_without_model_inference(
    tmp_path: Path,
) -> None:
    from contextlib import ExitStack

    from kyrin.stt.errors import DeviceUnavailableError
    from scripts.commands.evaluate_l04_audio import run

    plan = {"profiles": [{"model": {"tag": "test:1", "artifact_sha256": "artifact"}}]}
    audio_manifest = tmp_path / "audio.jsonl"
    audio_manifest.write_text("{}\n")
    output = tmp_path / "run"
    with ExitStack() as stack:
        for name, value in (
            ("ROOT", tmp_path),
            ("validate_plan", lambda _: plan),
            ("read_json", lambda _: {}),
            ("load_audio_cases", lambda _: [{"id": "unused"}]),
            ("source_snapshot", lambda: {"sha256": "source"}),
            (
                "environment_snapshot",
                lambda *_: {
                    "models": {
                        "value": [{"tag": "test:1", "manifest_sha256": "artifact"}]
                    }
                },
            ),
        ):
            stack.enter_context(
                patch("scripts.commands.evaluate_l04_audio." + name, value)
            )
        stack.enter_context(patch("scripts.commands.evaluate_l04_audio.signal.signal"))
        whisper = stack.enter_context(
            patch(
                "scripts.commands.evaluate_l04_audio.WhisperEngine",
                side_effect=DeviceUnavailableError("no GPU backend"),
            )
        )
        server = stack.enter_context(
            patch("scripts.commands.evaluate_l04_audio.LocalOllamaServer")
        )
        with pytest.raises(DeviceUnavailableError):
            run(tmp_path / "plan.json", output, audio_manifest)
    assert whisper.call_args.args[0].name == "whisper-server-gpu"
    server.assert_not_called()
    result = json.loads((output / "run.json").read_text())
    assert result["inference_attempts"] == 0 and result["records"] == 0
    assert result["run_error"]["type"] == "DeviceUnavailableError"
    assert result["resources_quiescent"]
    assert result["stt_configuration"]["engine_requested_device"] == (
        whisper.call_args.kwargs["compute_device"].value
    )
    assert result["stt_configuration"]["observed_session_devices"] == []
    assert result["bound_profile_scope"] == "command_model_inherited_from_text_plan"
