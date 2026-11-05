"""Run the same full quality gate locally and in CI, retaining every exit code."""

import argparse
import json
import os
import shlex
import subprocess
import sys
from pathlib import Path
from tempfile import TemporaryDirectory

ROOT = Path(__file__).resolve().parents[2]

# Only the package initializer is imported; no audio, Qt or model entry point.
SOURCE_PROBE = """
import json
import sys
from pathlib import Path

root = Path.cwd().resolve()
# Match the checker's explicit pytest pythonpath, including with PYTHONSAFEPATH.
sys.path.insert(0, str(root))
report = {
    "interpreter": sys.executable,
    "resolved_interpreter": str(Path(sys.executable).resolve()),
    "python_version": sys.version,
    "checkout_root": str(root),
    "expected_source": str((root / "src").resolve()),
    "module_origin": None,
    "spec_origin": None,
    "package_search_locations": None,
    "import_error": None,
}
try:
    import kyrin
    report["module_origin"] = kyrin.__file__
    report["spec_origin"] = kyrin.__spec__.origin
    report["package_search_locations"] = list(kyrin.__path__)
except ImportError as error:
    report["import_error"] = str(error)
finally:
    print(json.dumps(report))
"""


def _source_failure(observed: dict[str, object]) -> str | None:
    """Validate child evidence against resolved paths, never string prefixes."""
    for key in (
        "interpreter", "resolved_interpreter", "python_version",
        "checkout_root", "expected_source",
    ):
        if not isinstance(observed.get(key), str) or not observed[key]:
            return f"invalid_probe_output: {key}"
    source = (ROOT / "src").resolve()
    initializer = source / "kyrin" / "__init__.py"
    if not initializer.is_file():
        return "expected_source_missing: src/kyrin/__init__.py"
    if observed.get("import_error") is not None:
        return "kyrin_import_failed"
    for key, expected in (
        ("checkout_root", ROOT.resolve()),
        ("expected_source", source),
        ("resolved_interpreter", Path(sys.executable).resolve()),
        ("module_origin", initializer.resolve()),
        ("spec_origin", initializer.resolve()),
    ):
        value = observed.get(key)
        if not isinstance(value, str) or not value:
            return f"invalid_probe_output: {key}"
        if Path(value).resolve() != expected:
            return f"source_mismatch: {key}"
    locations = observed.get("package_search_locations")
    if not isinstance(locations, list) or not locations:
        return "invalid_probe_output: package_search_locations"
    if not all(isinstance(value, str) and value for value in locations):
        return "invalid_probe_output: package_search_locations"
    if [Path(value).resolve() for value in locations] != [initializer.parent.resolve()]:
        return "source_mismatch: package_search_locations"
    if not initializer.resolve().is_relative_to(source):
        return "source_mismatch: initializer outside src"
    return None


def _check_source(output_dir: Path, environment: dict[str, str]) -> bool:
    """Probe with exactly the interpreter, cwd and environment used by pytest."""
    fields = (
        "interpreter", "resolved_interpreter", "python_version",
        "checkout_root", "expected_source", "module_origin", "spec_origin",
        "package_search_locations", "import_error",
    )
    report: dict[str, object] = dict.fromkeys(fields)
    report["probe_exit_code"] = None
    reason: str | None = None
    try:
        result = subprocess.run(
            [sys.executable, "-c", SOURCE_PROBE],
            cwd=ROOT,
            env=environment,
            capture_output=True,
            text=True,
            timeout=15,
            check=False,
        )
        (output_dir / "source-provenance.log").write_text(result.stdout + result.stderr)
        report["probe_exit_code"] = result.returncode
        observed: object = json.loads(result.stdout)
        if isinstance(observed, dict):
            # Retain only known evidence fields, never an environment dump.
            for key in fields:
                report[key] = observed.get(key)
            reason = _source_failure(report)
        else:
            reason = "invalid_probe_output: expected JSON object"
        if result.returncode:
            reason = f"probe_failed: exit {result.returncode}"
    except json.JSONDecodeError:
        reason = "invalid_probe_output: invalid JSON"
    except subprocess.TimeoutExpired:
        reason = "probe_failed: timeout"
        (output_dir / "source-provenance.log").write_text(reason + "\n")
    except (OSError, ValueError, RuntimeError) as error:
        reason = f"probe_failed: {type(error).__name__}"
        (output_dir / "source-provenance.log").write_text(reason + "\n")
    report.update(status="passed" if reason is None else "failed", reason=reason)
    (output_dir / "source-provenance.json").write_text(
        json.dumps(report, indent=2) + "\n"
    )
    return reason is None


def run_checks(output_dir: Path) -> int:
    """Write per-stage logs; any failed check makes the overall gate fail."""
    output_dir.mkdir(parents=True, exist_ok=True)
    commands = {
        "syntax": ["compileall", "-q", "src", "tests", "scripts"],
        "lint": ["ruff", "check", "src", "tests", "scripts"],
        "type": ["mypy", "src", "tests", "scripts"],
        # Last override wins over inherited PYTEST_ADDOPTS; quote for pytest's
        # own shlex parser, not a shell. Keep cwd imports consistent with the probe.
        "tests": [
            "pytest", "-q", "tests", "-o",
            f"pythonpath={shlex.quote(str(ROOT.resolve()))}",
        ],
    }
    results: dict[str, int] = {}
    with TemporaryDirectory(prefix="kyrin-check-", dir=output_dir) as temporary:
        base = Path(temporary).resolve()
        environment = dict(os.environ)
        # Replace inherited paths: an old checkout must not supply project code.
        environment["PYTHONPATH"] = str((ROOT / "src").resolve())
        for key, name in (
            ("HOME", "home"),
            ("XDG_CONFIG_HOME", "config"),
            ("XDG_DATA_HOME", "data"),
            ("XDG_CACHE_HOME", "cache"),
            ("XDG_STATE_HOME", "state"),
            ("XDG_RUNTIME_DIR", "runtime"),
        ):
            directory = base / name
            directory.mkdir(mode=0o700)
            environment[key] = str(directory)
        environment["QT_QPA_PLATFORM"] = "offscreen"
        environment["HF_HUB_OFFLINE"] = "1"
        environment["TRANSFORMERS_OFFLINE"] = "1"
        environment["HF_HOME"] = str(base / "cache" / "huggingface")
        environment["PYTHONPYCACHEPREFIX"] = str(base / "cache" / "pycache")
        for key in ("DBUS_SESSION_BUS_ADDRESS", "DISPLAY", "WAYLAND_DISPLAY"):
            environment.pop(key, None)
        for stage, arguments in commands.items():
            print(f"Running {stage} ...", flush=True)
            if stage == "tests" and not _check_source(output_dir, environment):
                (output_dir / "tests.log").write_text(
                    "NOT RUN: pytest blocked by invalid source provenance. "
                    "See source-provenance.json and source-provenance.log.\n"
                )
                results[stage] = 1
                print("tests: NOT RUN (invalid source provenance)", flush=True)
                continue
            with (output_dir / f"{stage}.log").open("w") as log:
                result = subprocess.run(
                    [sys.executable, "-m", *arguments],
                    cwd=ROOT,
                    env=environment,
                    stdout=log,
                    stderr=subprocess.STDOUT,
                    check=False,
                )
            results[stage] = result.returncode
            print(f"{stage}: exit {result.returncode}", flush=True)
    (output_dir / "summary.json").write_text(json.dumps(results, indent=2) + "\n")
    return int(any(results.values()))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output-dir", type=Path, default=ROOT / "local-data" / "quality"
    )
    return run_checks(parser.parse_args().output_dir)


if __name__ == "__main__":
    raise SystemExit(main())
