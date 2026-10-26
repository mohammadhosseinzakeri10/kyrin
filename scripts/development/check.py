"""Run the same full quality gate locally and in CI, retaining every exit code."""

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path
from tempfile import TemporaryDirectory

ROOT = Path(__file__).resolve().parents[2]


def run_checks(output_dir: Path) -> int:
    """Write per-stage logs; any failed check makes the overall gate fail."""
    output_dir.mkdir(parents=True, exist_ok=True)
    commands = {
        "syntax": ["compileall", "-q", "src", "tests", "scripts"],
        "lint": ["ruff", "check", "src", "tests", "scripts"],
        "type": ["mypy", "src", "tests", "scripts"],
        "tests": ["pytest", "-q", "tests"],
    }
    results: dict[str, int] = {}
    with TemporaryDirectory(prefix="kyrin-check-", dir=output_dir) as temporary:
        base = Path(temporary).resolve()
        environment = dict(os.environ)
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
