"""The desktop launcher finds speech runtimes beside its installed script."""

from pathlib import Path

import pytest

pytest.importorskip("PySide6")

from kyrin.app.qt.main import (  # noqa: E402
    _source_checkout_model_root,
    _tts_model_root,
    _whisper_server_path,
)


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


def test_tts_model_root_prefers_organized_catalog_with_installed_fallback(
    tmp_path: Path,
) -> None:
    development = tmp_path / "models" / "local" / "by-model" / "tts"
    installed = tmp_path / "local-data" / "kyrin" / "models" / "tts"
    installed.mkdir(parents=True)
    assert _tts_model_root(development, installed) == installed
    assert _tts_model_root(None, installed) == installed
    development.mkdir(parents=True)
    assert _tts_model_root(development, installed) == development


def test_development_models_require_real_source_layout(tmp_path: Path) -> None:
    source_module = tmp_path / "src/kyrin/app/qt/main.py"
    source_module.parent.mkdir(parents=True)
    source_module.write_text("# fixture")
    (tmp_path / "pyproject.toml").write_text("[project]\n")
    assert _source_checkout_model_root(source_module) == (
        tmp_path / "models/local/by-model"
    )

    installed_module = tmp_path / "site-packages/kyrin/app/qt/main.py"
    installed_module.parent.mkdir(parents=True)
    installed_module.write_text("# fixture")
    assert _source_checkout_model_root(installed_module) is None
