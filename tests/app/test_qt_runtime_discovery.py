"""The desktop launcher finds speech runtimes beside its installed script."""

from pathlib import Path

import pytest

pytest.importorskip("PySide6")

from kyrin.app.qt.main import _whisper_server_path  # noqa: E402


def test_installed_runtime_is_found_without_path_entry(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    installed = tmp_path / "whisper-server-gpu"
    installed.write_bytes(b"runtime")
    installed.chmod(0o700)
    monkeypatch.delenv("KYRIN_WHISPER_GPU_SERVER", raising=False)
    monkeypatch.setattr("kyrin.app.qt.main.shutil.which", lambda command: None)

    assert (
        _whisper_server_path(
            "KYRIN_WHISPER_GPU_SERVER",
            "whisper-server-gpu",
            scripts_directory=tmp_path,
        )
        == installed
    )


def test_invalid_explicit_path_does_not_select_another_runtime(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    installed = tmp_path / "whisper-server-gpu"
    installed.write_bytes(b"runtime")
    installed.chmod(0o700)
    monkeypatch.setenv("KYRIN_WHISPER_GPU_SERVER", str(tmp_path / "missing"))

    assert (
        _whisper_server_path(
            "KYRIN_WHISPER_GPU_SERVER",
            "whisper-server-gpu",
            scripts_directory=tmp_path,
        )
        is None
    )
