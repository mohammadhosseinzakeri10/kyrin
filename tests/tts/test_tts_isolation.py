"""A model-free subprocess check for separately installed TTS engines."""

import os
import sys
from pathlib import Path

import pytest

from kyrin.tts.isolation import (
    IsolatedTtsWorker,
    isolated_runtime_python,
    probe_isolated_runtime,
)


def test_chatterbox_worker_keeps_model_loaded_and_returns_audio(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    package = tmp_path / "chatterbox"
    package.mkdir()
    (package / "__init__.py").write_text("", encoding="utf-8")
    (package / "mtl_tts.py").write_text(
        """
import numpy as np

class Wave:
    def squeeze(self): return self
    def detach(self): return self
    def cpu(self): return self
    def numpy(self): return np.array([0.25, -0.25], dtype=np.float32)

class ChatterboxMultilingualTTS:
    sr = 24000
    @classmethod
    def from_local(cls, folder, provider, *, t3_model):
        return cls()
    def get_supported_languages(self): return {'en': 'English'}
    def generate(self, text, *, language_id): return Wave()
""",
        encoding="utf-8",
    )
    model = tmp_path / "model"
    model.mkdir()
    for name in (
        "ve.pt",
        "s3gen.pt",
        "grapheme_mtl_merged_expanded_v1.json",
        "conds.pt",
        "t3_mtl23ls_v3.safetensors",
    ):
        (model / name).write_bytes(b"fixture")
    project_src = Path(__file__).resolve().parents[2] / "src"
    monkeypatch.setenv("PYTHONPATH", os.pathsep.join((str(tmp_path), str(project_src))))
    from kyrin.tts import isolation as tts_isolation

    runtime_environment = tts_isolation._runtime_environment
    monkeypatch.setattr(
        tts_isolation,
        "_runtime_environment",
        lambda *args: {**runtime_environment(), "PYTHONPATH": os.environ["PYTHONPATH"]},
    )
    probe_isolated_runtime(Path(sys.executable), "chatterbox", "cpu")
    worker = IsolatedTtsWorker(Path(sys.executable), "chatterbox", model, "cpu")
    try:
        samples, rate = worker.generate("Hello", "0", 1.0, "en")
        assert rate == 24000
        assert samples.tolist() == [0.25, -0.25]
        second, _ = worker.generate("Again", "0", 1.0, "en")
        assert second.tolist() == [0.25, -0.25]
    finally:
        worker.close()


def test_isolated_runtime_accepts_normal_venv_python_symlink(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    executable = tmp_path / "kyrin/runtimes/tts/qwen3tts/bin/python"
    executable.parent.mkdir(parents=True)
    executable.symlink_to(sys.executable)
    assert isolated_runtime_python("qwen3tts") == executable
    from kyrin.tts import isolation

    monkeypatch.setattr(isolation, "_IN_WORKER_PROCESS", True)
    assert isolated_runtime_python("qwen3tts") is None


def test_sherpa_worker_finds_its_local_cuda_libraries(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from kyrin.tts import isolation

    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    executable = tmp_path / "kyrin/runtimes/tts/sherpa-gpu/bin/python"
    executable.parent.mkdir(parents=True)
    executable.symlink_to(sys.executable)
    library = (
        executable.parent.parent
        / "lib/python3.14/site-packages/nvidia/cu13/lib"
    )
    library.mkdir(parents=True)
    assert isolated_runtime_python("sherpa-gpu") == executable
    environment = isolation._runtime_environment(executable, "kokoro")
    assert str(library) in environment["LD_LIBRARY_PATH"]
