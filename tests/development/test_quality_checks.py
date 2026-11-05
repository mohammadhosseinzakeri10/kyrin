"""Quality checks must report failures without skipping subsequent checks."""

import json
import os
import shlex
import subprocess
import sys
from pathlib import Path
from typing import TextIO

import pytest

from scripts.development import check as checker
from scripts.development.check import run_checks


def _valid_evidence() -> str:
    package = checker.ROOT / "src" / "kyrin"
    return json.dumps({
        "interpreter": sys.executable,
        "resolved_interpreter": str(Path(sys.executable).resolve()),
        "python_version": sys.version,
        "checkout_root": str(checker.ROOT.resolve()),
        "expected_source": str(package.parent.resolve()),
        "module_origin": str(package / "__init__.py"),
        "spec_origin": str(package / "__init__.py"),
        "package_search_locations": [str(package)],
        "import_error": None,
    })


@pytest.mark.parametrize("scenario, reason", [
    ("healthy", None),
    ("inherited-old", None),
    ("safe-path", None),
    ("inherited-pytest-path", None),
    ("symlink-checkout", None),
    ("missing-source", "expected_source_missing"),
    ("missing-initializer", "expected_source_missing"),
    ("import-fails", "kyrin_import_failed"),
    ("initializer-crashes", "probe_failed"),
    ("wrong-package", "source_mismatch: module_origin"),
    ("wrong-package-safe-path", "source_mismatch: module_origin"),
    ("extended-path", "source_mismatch: package_search_locations"),
    ("symlink-outside", "source_mismatch: initializer outside src"),
])
def test_current_checkout_wins_over_inherited_package(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    scenario: str, reason: str | None,
) -> None:
    """Use real pytest/imports, even when an old package is importable first."""
    root = tmp_path / "current checkout"
    package = root / "src" / "kyrin"
    package.mkdir(parents=True)
    (package / "__init__.py").write_text("")
    old = tmp_path / "old source"
    (old / "kyrin").mkdir(parents=True)
    (old / "kyrin" / "__init__.py").write_text("OLD_COPY = True\n")
    if scenario == "missing-source":
        (package / "__init__.py").unlink()
        package.rmdir()
        package.parent.rmdir()
    elif scenario == "missing-initializer":
        (package / "__init__.py").unlink()
    elif scenario == "import-fails":
        (package / "__init__.py").write_text("raise ImportError('fixture failure')\n")
    elif scenario == "initializer-crashes":
        (package / "__init__.py").write_text("raise RuntimeError('fixture crash')\n")
    elif scenario in ("wrong-package", "wrong-package-safe-path"):
        # -c and -m both search cwd before PYTHONPATH. Import success is insufficient.
        (root / "kyrin").mkdir()
        (root / "kyrin" / "__init__.py").write_text("")
    elif scenario == "extended-path":
        (package / "__init__.py").write_text(f"__path__.append({str(old)!r})\n")
    elif scenario == "symlink-outside":
        # This sibling shares the src prefix but is outside the resolved source.
        sibling = root / "src-other"
        sibling.mkdir()
        (sibling / "__init__.py").write_text("")
        (package / "__init__.py").unlink()
        package.rmdir()
        package.symlink_to(sibling, target_is_directory=True)
    (root / "tests").mkdir()
    (root / "pyproject.toml").write_text(
        '[tool.pytest.ini_options]\npythonpath = ["."]\n'
    )
    (root / "tests" / "test_import.py").write_text(
        "from pathlib import Path\nimport kyrin\n"
        "def test_source():\n"
        "    assert Path(kyrin.__file__).resolve() == "
        f"Path({str(package / '__init__.py')!r})\n"
    )
    if scenario in ("safe-path", "wrong-package-safe-path"):
        monkeypatch.setenv("PYTHONSAFEPATH", "1")
    if scenario == "wrong-package-safe-path":
        (root / "tests" / "test_import.py").write_text(
            "import kyrin\ndef test_must_not_run():\n"
            f"    assert kyrin.__file__ == {str(root / 'kyrin/__init__.py')!r}\n"
        )
    if scenario == "symlink-checkout":
        alias = tmp_path / "checkout alias"
        alias.symlink_to(root, target_is_directory=True)
        root = alias
    monkeypatch.setattr(checker, "ROOT", root)
    if scenario == "healthy":
        monkeypatch.delenv("PYTHONPATH", raising=False)
    else:
        monkeypatch.setenv("PYTHONPATH", str(old))
    if scenario == "inherited-pytest-path":
        monkeypatch.setenv(
            "PYTEST_ADDOPTS",
            shlex.join(["-o", f"pythonpath={shlex.quote(str(old))}"]),
        )
    original = dict(os.environ)
    real_run = subprocess.run
    commands: list[list[str]] = []
    environments: list[dict[str, str]] = []

    def run(
        command: list[str], *, cwd: Path, env: dict[str, str],
        stdout: TextIO | int | None = None, stderr: int | None = None, check: bool,
        text: bool = False, timeout: float | None = None, capture_output: bool = False,
    ) -> subprocess.CompletedProcess[str]:
        commands.append(command)
        environments.append(env)
        if command[1] == "-c" or command[2] == "pytest":
            return real_run(
                command, cwd=cwd, env=env, stdout=stdout, stderr=stderr,
                check=check, text=True, timeout=timeout, capture_output=capture_output,
            )
        assert stdout is not None and not isinstance(stdout, int)
        stdout.write("static check fixture\n")
        return subprocess.CompletedProcess(command, 0)

    monkeypatch.setattr(subprocess, "run", run)
    output = tmp_path / "reports"
    assert run_checks(output) == int(reason is not None)
    report = json.loads((output / "source-provenance.json").read_text())
    assert report["interpreter"] == sys.executable
    assert report["python_version"] == sys.version
    assert report["checkout_root"] == str(root.resolve())
    assert report["expected_source"] == str((root / "src").resolve())
    if reason is None:
        assert report["status"] == "passed" and report["reason"] is None
        assert report["module_origin"] == str(package / "__init__.py")
        assert report["package_search_locations"] == [str(package)]
        assert commands[-1][2] == "pytest"
        assert "1 passed" in (output / "tests.log").read_text()
        assert environments[-1] is environments[-2]
    else:
        assert report["status"] == "failed"
        assert report["reason"].startswith(reason)
        assert all(command[1] == "-c" or command[2] != "pytest" for command in commands)
        assert "NOT RUN" in (output / "tests.log").read_text()
        assert json.loads((output / "summary.json").read_text())["tests"] == 1
    if scenario == "wrong-package":
        assert report["probe_exit_code"] == 0
        assert report["module_origin"] == str(root / "kyrin" / "__init__.py")
    assert dict(os.environ) == original
    assert not Path(environments[-1]["HOME"]).exists()


@pytest.mark.parametrize("failed", [None, "syntax", "lint", "type", "tests"])
def test_checks_preserve_failures_and_run_every_stage(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, failed: str | None
) -> None:
    commands: list[list[str]] = []
    environments: list[dict[str, str]] = []
    probe_environment: dict[str, str] | None = None

    def run(
        command: list[str], *, cwd: Path, env: dict[str, str],
        stdout: TextIO | int | None = None, stderr: int | None = None, check: bool,
        text: bool = False, timeout: float | None = None, capture_output: bool = False,
    ) -> subprocess.CompletedProcess[str]:
        nonlocal probe_environment
        if command[1] == "-c":
            probe_environment = env
            assert cwd == checker.ROOT
            assert text and timeout == 15 and capture_output
            return subprocess.CompletedProcess(command, 0, _valid_evidence(), "")
        stage = ["syntax", "lint", "type", "tests"][len(commands)]
        commands.append(command)
        environments.append(env)
        assert stdout is not None and not isinstance(stdout, int)
        stdout.write(f"{stage} output\n")
        assert cwd == Path(__file__).resolve().parents[2]
        assert stderr == subprocess.STDOUT and not check
        if stage == "tests":
            assert Path(env["HOME"]).is_dir()
            assert env["QT_QPA_PLATFORM"] == "offscreen"
            assert "DBUS_SESSION_BUS_ADDRESS" not in env
            assert "WAYLAND_DISPLAY" not in env
            assert "DISPLAY" not in env
            assert env["HF_HUB_OFFLINE"] == env["TRANSFORMERS_OFFLINE"] == "1"
            assert env["PYTHONPATH"] == str(checker.ROOT / "src")
            assert probe_environment is env
            for key in (
                "HOME", "XDG_CONFIG_HOME", "XDG_DATA_HOME", "XDG_CACHE_HOME",
                "XDG_STATE_HOME", "XDG_RUNTIME_DIR",
            ):
                assert Path(env[key]).is_dir()
                assert Path(env[key]).stat().st_mode & 0o777 == 0o700
        return subprocess.CompletedProcess(command, 1 if stage == failed else 0)

    monkeypatch.setenv("DBUS_SESSION_BUS_ADDRESS", "private-owner-bus")
    monkeypatch.setenv("WAYLAND_DISPLAY", "private-owner-display")
    monkeypatch.setenv("DISPLAY", "private-owner-x-display")
    monkeypatch.setenv("PYTHONPATH", "/old/path")
    original = dict(os.environ)
    monkeypatch.setattr(subprocess, "run", run)
    assert run_checks(tmp_path) == (1 if failed else 0)
    assert len(commands) == 4
    assert commands[0][-3:] == ["src", "tests", "scripts"]
    assert commands[1][-3:] == ["src", "tests", "scripts"]
    assert commands[2][-3:] == ["src", "tests", "scripts"]
    assert commands[3][2:] == [
        "pytest", "-q", "tests", "-o",
        f"pythonpath={shlex.quote(str(checker.ROOT.resolve()))}",
    ]
    summary = json.loads((tmp_path / "summary.json").read_text())
    assert summary == {
        stage: (1 if stage == failed else 0)
        for stage in ["syntax", "lint", "type", "tests"]
    }
    assert (tmp_path / "type.log").read_text() == "type output\n"
    assert dict(os.environ) == original
    assert not Path(environments[-1]["HOME"]).exists()


@pytest.mark.parametrize("failure", [
    "nonzero", "timeout", "launch-error", "invalid-json", "extra-output",
    "json-list", "missing-fields", "invalid-locations", "wrong-spec",
    "wrong-root", "wrong-interpreter",
])
def test_invalid_probe_blocks_pytest_without_hiding_other_failures(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, failure: str,
) -> None:
    commands: list[list[str]] = []
    environments: list[dict[str, str]] = []

    def run(
        command: list[str], *, cwd: Path, env: dict[str, str],
        stdout: TextIO | int | None = None, stderr: int | None = None, check: bool,
        text: bool = False, timeout: float | None = None, capture_output: bool = False,
    ) -> subprocess.CompletedProcess[str]:
        commands.append(command)
        environments.append(env)
        if command[1] != "-c":
            assert command[2] != "pytest"
            assert stdout is not None and not isinstance(stdout, int)
            stdout.write("independent failure\n")
            return subprocess.CompletedProcess(command, len(commands))
        if failure == "timeout":
            raise subprocess.TimeoutExpired(command, 15)
        if failure == "launch-error":
            raise FileNotFoundError("fixture interpreter unavailable")
        evidence = json.loads(_valid_evidence())
        if failure == "invalid-locations":
            evidence["package_search_locations"] = [123]
        elif failure == "wrong-spec":
            evidence["spec_origin"] = str(tmp_path / "old" / "__init__.py")
        elif failure == "wrong-root":
            evidence["checkout_root"] = str(tmp_path)
        elif failure == "wrong-interpreter":
            evidence["resolved_interpreter"] = str(tmp_path / "python")
        payload = {
            "invalid-json": "not JSON",
            "extra-output": "package noise\n" + json.dumps(evidence),
            "json-list": "[]",
            "missing-fields": "{}",
        }.get(failure, json.dumps(evidence))
        return subprocess.CompletedProcess(
            command, 7 if failure == "nonzero" else 0, payload, "probe stderr\n",
        )

    original = dict(os.environ)
    monkeypatch.setattr(subprocess, "run", run)
    assert run_checks(tmp_path) == 1
    assert len(commands) == 4  # three static stages plus the probe, never pytest
    assert json.loads((tmp_path / "summary.json").read_text()) == {
        "syntax": 1, "lint": 2, "type": 3, "tests": 1,
    }
    report = json.loads((tmp_path / "source-provenance.json").read_text())
    assert report["status"] == "failed" and report["reason"]
    assert "NOT RUN" in (tmp_path / "tests.log").read_text()
    for stage in ("syntax", "lint", "type"):
        assert (tmp_path / f"{stage}.log").read_text() == "independent failure\n"
    assert dict(os.environ) == original
    assert not Path(environments[-1]["HOME"]).exists()
