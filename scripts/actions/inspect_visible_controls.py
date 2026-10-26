"""Owner-run, read-only focused-window accessibility diagnostic.

Wait briefly so the owner can focus the test window. No input or capture occurs.
Reports counters and only the explicitly requested labels; never a tree dump.
Window rectangles are included only with the owner's explicit --geometry option.
"""

import argparse
import json
import subprocess
from pathlib import Path
from time import sleep

ROOT = Path(__file__).resolve().parents[2]
HELPER = ROOT / "src/kyrin/actions/platforms/desktop_accessibility_inventory.py"


def inspect_controls(
    labels: list[str],
    *,
    system_python: str = "/usr/bin/python3",
    include_geometry: bool = False,
) -> dict[str, object]:
    try:
        result = subprocess.run(
            [
                system_python,
                str(HELPER),
                "--diagnose-current-geometry"
                if include_geometry
                else "--diagnose-current",
                json.dumps(labels),
            ],
            capture_output=True,
            text=True,
            timeout=8,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return {"status": "helper_timeout"}
    except OSError:
        return {"status": "helper_unavailable"}
    if result.returncode != 0:
        # Raw stderr may contain private data; never forward it.
        return {"status": "helper_error", "returncode": result.returncode}
    try:
        report = json.loads(result.stdout)
    except ValueError:
        return {"status": "invalid_helper_reply"}
    if not isinstance(report, dict) or not isinstance(report.get("status"), str):
        return {"status": "invalid_helper_reply"}
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--delay", type=float, default=5.0)
    parser.add_argument("--label", action="append", default=[])
    parser.add_argument(
        "--geometry",
        action="store_true",
        help="include focused-frame and accessibility rectangles for bounds diagnosis",
    )
    args = parser.parse_args()
    if (
        not 0 <= args.delay <= 30
        or len(args.label) > 20
        or any(not 1 <= len(label.strip()) <= 80 for label in args.label)
    ):
        parser.error(
            "delay must be 0..30 seconds; at most 20 labels of 1..80 characters"
        )
    sleep(args.delay)
    report = inspect_controls(args.label, include_geometry=args.geometry)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return int(report["status"] != "ok")


if __name__ == "__main__":
    raise SystemExit(main())
