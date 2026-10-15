"""Recorded reference links, rather than model guesses, govern decision scoring."""

import json
from pathlib import Path

from scripts.stt.score_local_model_commands import main


def test_scores_verified_command_without_executing_it(tmp_path: Path) -> None:
    links = tmp_path / "links.jsonl"
    links.write_text(
        json.dumps(
            {
                "recording_id": "en-1",
                "spoken_reference": "Open Telegram.",
                "expected": {
                    "route": "execute",
                    "steps": [{"operation": "open_app", "target": "telegram"}],
                },
            }
        )
        + "\n",
        encoding="utf-8",
    )
    (tmp_path / "whisper-small-en.json").write_text(
        json.dumps(
            {
                "results": [
                    {
                        "id": "en-1",
                        "language": "en",
                        "reference": "Open Telegram.",
                        "transcript": "Open Telegram",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    summary = tmp_path / "summary.json"
    summary.write_text(
        json.dumps(
            {
                "rows": [
                    {
                        "model": "whisper-small",
                        "language": "en",
                        "status": "completed",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    assert main(["--summary", str(summary), "--verified-links", str(links)]) == 0

    report = json.loads((tmp_path / "decision-summary.json").read_text())
    assert report["rows"][0]["counts"] == {"correct_action": 1}
