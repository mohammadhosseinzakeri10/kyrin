"""Optional GNOME Shell visual feedback transport; no UI dependency in core."""

import subprocess
from queue import Empty, Full, Queue
from threading import Thread

from kyrin.backend_protocol import BackendStatus, probe_gnome
from kyrin.responses.visual_status import VisualPresentation


class GnomeVisualStatusSink:
    """Send short state and caption to Shell off the audio path."""

    @staticmethod
    def available() -> bool:
        return probe_gnome(
            "VisualStatus", {"SetPresentation"}, run=subprocess.run
        ).ready

    def __init__(self) -> None:
        self.backend_status = BackendStatus(False, "not_probed")
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
            self.backend_status = probe_gnome(
                "VisualStatus", {"SetPresentation"}, run=subprocess.run
            )
            if not self.backend_status.ready:
                continue
            try:
                subprocess.run(
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
                        presentation.caption,
                    ],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    check=False,
                    timeout=0.5,
                )
            except OSError, subprocess.TimeoutExpired:
                # Visual feedback is optional; text feedback remains available.
                pass
