"""Optional GNOME Shell visual feedback transport; no UI dependency in core."""

import subprocess
from queue import Empty, Full, Queue
from threading import Thread

from kyrin.responses.visual_status import VisualPresentation


class GnomeVisualStatusSink:
    """Send short state and caption to Shell off the audio path."""

    @staticmethod
    def available() -> bool:
        """Check the optional D-Bus endpoint once before a session starts."""
        try:
            result = subprocess.run(
                [
                    "busctl",
                    "--user",
                    "introspect",
                    "org.gnome.Shell",
                    "/org/kyrin/VisualStatus",
                    "org.kyrin.VisualStatus",
                ],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                check=False,
                timeout=0.5,
            )
        except OSError, subprocess.TimeoutExpired:
            return False
        return result.returncode == 0

    def __init__(self) -> None:
        self._updates: Queue[VisualPresentation] = Queue(maxsize=8)
        self._thread = Thread(target=self._run, name="kyrin-visual", daemon=True)
        self._thread.start()

    def publish(self, presentation: VisualPresentation) -> None:
        try:
            self._updates.put_nowait(presentation)
        except Full:
            try:
                self._updates.get_nowait()
            except Empty:
                pass
            try:
                self._updates.put_nowait(presentation)
            except Full:
                pass

    def _run(self) -> None:
        while True:
            presentation = self._updates.get()
            try:
                result = subprocess.run(
                    [
                        "busctl",
                        "--user",
                        "call",
                        "org.gnome.Shell",
                        "/org/kyrin/VisualStatus",
                        "org.kyrin.VisualStatus",
                        "SetPresentation",
                        "ss",
                        presentation.status.value,
                        presentation.caption[:160],
                    ],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    check=False,
                    timeout=0.5,
                )
                if result.returncode != 0:
                    # The active Shell may still cache the previous extension
                    # until the next login. Keep its status-only API working.
                    subprocess.run(
                        [
                            "busctl",
                            "--user",
                            "call",
                            "org.gnome.Shell",
                            "/org/kyrin/VisualStatus",
                            "org.kyrin.VisualStatus",
                            "SetStatus",
                            "s",
                            presentation.status.value,
                        ],
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                        check=False,
                        timeout=0.5,
                    )
            except OSError, subprocess.TimeoutExpired:
                # Visual feedback is optional; text feedback remains available.
                pass
