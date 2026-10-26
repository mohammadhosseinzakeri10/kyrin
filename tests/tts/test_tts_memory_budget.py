"""CPU Qwen must keep memory headroom and apply its limit before model loading."""

import io
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from kyrin.tts.memory_budget import cpu_qwen_budget

_GIB = 1024**3


def test_cpu_qwen_budget_reserves_half_of_available_ram() -> None:
    assert cpu_qwen_budget(32 * _GIB, 20 * _GIB) == 10 * _GIB
    with pytest.raises(ValueError, match="Not enough free RAM"):
        cpu_qwen_budget(16 * _GIB, 6 * _GIB)


def test_qwen_worker_sets_cpu_limit_before_loading(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import kyrin.tts.worker as worker

    steps: list[str] = []

    class FakeAdapter:
        def inspect(self, folder: Path) -> object:
            return object()

        def load(self, model: object, folder: Path, provider: str) -> object:
            steps.append("load")
            return SimpleNamespace()

    monkeypatch.setattr(worker, "mark_worker_process", lambda: None)
    monkeypatch.setattr(worker, "_adapter", lambda family: FakeAdapter())
    monkeypatch.setattr(worker, "_provider", lambda adapter, requested: "cpu")
    monkeypatch.setattr(worker, "limit_cpu_qwen_worker", lambda: steps.append("limit"))
    monkeypatch.setattr(sys, "argv", ["worker", "serve", "qwen3tts"])
    monkeypatch.setattr(
        sys,
        "stdin",
        io.StringIO(
            json.dumps({"op": "load", "folder": str(tmp_path), "provider": "cpu"})
            + "\n"
        ),
    )
    output = io.StringIO()
    monkeypatch.setattr(sys, "stdout", output)

    assert worker.main() == 0
    assert steps == ["limit", "load"]
    assert json.loads(output.getvalue()) == {"ok": True}
