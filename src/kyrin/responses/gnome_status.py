"""Optional GNOME Shell visual feedback transport; no UI dependency in core."""

import subprocess
from queue import Empty, Queue
from threading import Lock, Thread

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
        self._updates: Queue[VisualPresentation] = Queue(maxsize=1)
        self._publish_lock = Lock()
        self._thread = Thread(target=self._run, name="kyrin-visual", daemon=True)
        self._thread.start()

    def publish(self, presentation: VisualPresentation) -> None:
        # A caption is a current state, not an event log. Serialize publishers
        # so an older producer cannot displace a newer pending presentation.
        with self._publish_lock:
            try:
                self._updates.get_nowait()
            except Empty:
                pass
            self._updates.put_nowait(presentation)

    def _run(self) -> None:
        while True:
            presentation = self._updates.get()
            self.backend_status = probe_gnome(
                "VisualStatus", {"SetPresentation"}, run=subprocess.run
            )
            if not self.backend_status.ready:
                continue
            # The capability probe may have waited while the runtime advanced.
            # Use the newest caption before issuing the display call.
            try:
                presentation = self._updates.get_nowait()
            except Empty:
                pass
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
