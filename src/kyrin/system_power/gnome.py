"""Normal GNOME session requests; never force or ignore inhibitors."""

import subprocess

from kyrin.system_power.flow import PowerAction


class GnomePowerBackend:
    def _call(self, *arguments: str, timeout: float = 8.0) -> str:
        result = subprocess.run(
            ["gdbus", "call", *arguments],
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
        if result.returncode:
            raise RuntimeError("D-Bus request was rejected")
        return result.stdout

    def work_warning(self, action: PowerAction) -> str:
        try:
            output = self._call(
                "--session",
                "--dest",
                "org.gnome.SessionManager",
                "--object-path",
                "/org/gnome/SessionManager",
                "--method",
                "org.gnome.SessionManager.IsInhibited",
                "4" if action is PowerAction.SUSPEND else "1",
                timeout=3.0,
            )
        except OSError, subprocess.TimeoutExpired, RuntimeError:
            return "Could not inspect GNOME session blockers."
        if output.strip() == "(true,)":
            return "GNOME reports a blocker for this system action."
        if output.strip() == "(false,)":
            return "GNOME reports no blocker for this system action."
        return "GNOME blocker status could not be interpreted."

    def request(self, action: PowerAction) -> None:
        method = {
            PowerAction.POWER_OFF: "Shutdown",
            PowerAction.RESTART: "Reboot",
            PowerAction.LOG_OUT: "Logout",
            PowerAction.SUSPEND: "Suspend",
        }[action]
        arguments = (
            "--session",
            "--dest",
            "org.gnome.SessionManager",
            "--object-path",
            "/org/gnome/SessionManager",
            "--method",
            f"org.gnome.SessionManager.{method}",
            *(("0",) if action is PowerAction.LOG_OUT else ()),
        )
        self._call(*arguments)
