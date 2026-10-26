"""Bounded Ubuntu ScreenCast Portal bridge to system GObject bindings."""

import subprocess
from pathlib import Path

_HELPER = Path(__file__).with_name("ubuntu_portal_helper.py")


class UbuntuPortalScreenCapture:
    """Capture one user-selected window; no persistent permission is requested."""

    def __init__(
        self,
        *,
        system_python: str = "/usr/bin/python3",
        timeout_s: float = 45,
        max_image_bytes: int = 32 * 1024 * 1024,
    ) -> None:
        if not system_python or timeout_s <= 0 or max_image_bytes <= 0:
            raise ValueError("capture configuration is invalid")
        self._system_python = system_python
        self._timeout_s = timeout_s
        self._max_image_bytes = max_image_bytes

    def capture_window(self) -> bytes | None:
        try:
            result = subprocess.run(
                [self._system_python, str(_HELPER)],
                capture_output=True,
                check=False,
                timeout=self._timeout_s,
            )
        except (OSError, subprocess.TimeoutExpired):
            return None
        if (
            result.returncode != 0
            or not result.stdout.startswith(b"\x89PNG\r\n\x1a\n")
            or len(result.stdout) > self._max_image_bytes
        ):
            return None
        return result.stdout
