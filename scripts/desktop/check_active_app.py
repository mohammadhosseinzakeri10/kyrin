"""Print focused GNOME app IDs and registered labels without reading windows."""

import argparse
import time

from kyrin.desktop.platforms.gnome import GnomeShellActiveAppObserver
from kyrin.desktop.platforms.xdg import XdgDesktopAppCatalog


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seconds", type=float, default=20.0)
    parser.add_argument("--interval", type=float, default=0.5)
    args = parser.parse_args()
    if not 0 < args.seconds <= 60 or not 0.1 <= args.interval <= 5:
        parser.error("seconds must be in (0, 60] and interval in [0.1, 5]")

    observer = GnomeShellActiveAppObserver({})
    catalog = XdgDesktopAppCatalog()
    app_names = {app.platform_id: app.display_name for app in catalog.list_apps()}
    deadline = time.monotonic() + args.seconds
    previous: object = object()
    while time.monotonic() < deadline:
        current = observer.read_active_app_id()
        if current != previous:
            name = app_names.get(current) if current is not None else None
            label = f" ({name})" if name is not None else ""
            print(f"{current}{label}" if current is not None else "unknown", flush=True)
            previous = current
        time.sleep(args.interval)


if __name__ == "__main__":
    main()
