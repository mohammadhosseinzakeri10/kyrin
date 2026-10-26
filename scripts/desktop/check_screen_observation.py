"""One-shot, read-only preview of the active accessible window."""

import argparse

from kyrin.desktop.platforms.atspi import UbuntuAtspiScreenObserver
from kyrin.desktop.platforms.gnome import GnomeShellActiveAppObserver
from kyrin.desktop.platforms.xdg import XdgDesktopAppCatalog


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--show-labels",
        action="store_true",
        help="print visible labels, which may contain private on-screen text",
    )
    args = parser.parse_args()
    observer = UbuntuAtspiScreenObserver(
        XdgDesktopAppCatalog(), GnomeShellActiveAppObserver({})
    )
    observation = observer.observe()
    if observation is None:
        print("No unambiguous accessibility observation is available.")
        return 1
    print(
        f"App: {observation.platform_app_id}; "
        f"labeled elements: {len(observation.elements)}; "
        f"truncated: {observation.truncated}"
    )
    if args.show_labels:
        for element in observation.elements:
            print(f"{element.role}: {element.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
