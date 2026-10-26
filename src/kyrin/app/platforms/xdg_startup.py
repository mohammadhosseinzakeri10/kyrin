"""Per-user Linux desktop launcher and login-startup registration."""

import os
import tempfile
from pathlib import Path

DESKTOP_FILE_ID = "local.kyrin.KYRIN"
_ENTRY_NAME = f"{DESKTOP_FILE_ID}.desktop"
_MARKER = "X-KYRIN-Managed=true"


class DesktopRegistrationError(RuntimeError):
    """A launcher could not be safely installed or removed."""


def _xdg_home(variable: str, fallback: Path) -> Path:
    value = os.environ.get(variable)
    path = Path(value) if value else fallback
    return path if path.is_absolute() else fallback


def user_desktop_paths() -> tuple[Path, Path]:
    """Return menu and autostart paths without creating either directory."""
    home = Path.home()
    data = _xdg_home("XDG_DATA_HOME", home / ".local" / "share")
    config = _xdg_home("XDG_CONFIG_HOME", home / ".config")
    return data / "applications" / _ENTRY_NAME, config / "autostart" / _ENTRY_NAME


def _desktop_argument(argument: str) -> str:
    if "\n" in argument or "\r" in argument:
        raise DesktopRegistrationError("Launcher path contains a line break")
    escaped = argument.replace("\\", "\\\\")
    for character in ('"', "`", "$"):
        escaped = escaped.replace(character, "\\" + character)
    escaped = escaped.replace("%", "%%")
    return f'"{escaped}"'


def _entry(executable: Path, icon_path: Path) -> str:
    return (
        "[Desktop Entry]\n"
        "Type=Application\n"
        "Name=KYRIN\n"
        "Comment=Offline desktop voice assistant\n"
        f"Exec={_desktop_argument(str(executable))}\n"
        f"Icon={icon_path}\n"
        "Terminal=false\n"
        "Categories=Utility;\n"
        f"{_MARKER}\n"
    )


def _read_managed(path: Path) -> bool:
    try:
        contents = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return False
    except (OSError, UnicodeError) as error:
        raise DesktopRegistrationError(f"Could not read {path}") from error
    return _MARKER in contents.splitlines()


def _replace_managed(path: Path, contents: str) -> None:
    if path.exists() and not _read_managed(path):
        raise DesktopRegistrationError(f"Unmanaged desktop entry exists: {path}")
    temporary: Path | None = None
    try:
        path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=path.parent,
            prefix=".kyrin-",
            suffix=".desktop",
            delete=False,
        ) as stream:
            temporary = Path(stream.name)
            stream.write(contents)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        temporary = None
    except OSError as error:
        raise DesktopRegistrationError(f"Could not install {path}") from error
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


class XdgDesktopRegistration:
    """Own only KYRIN's named entries; never edit another application's file."""

    def __init__(
        self,
        executable: Path,
        menu_path: Path,
        autostart_path: Path,
        *,
        icon_path: Path,
    ) -> None:
        if not executable.is_absolute() or not executable.is_file():
            raise DesktopRegistrationError("Installed KYRIN launcher was not found")
        if not os.access(executable, os.X_OK):
            raise DesktopRegistrationError("Installed KYRIN launcher is not executable")
        if not menu_path.is_absolute() or not autostart_path.is_absolute():
            raise ValueError("Desktop entry paths must be absolute")
        if not icon_path.is_absolute() or not icon_path.is_file():
            raise DesktopRegistrationError("Packaged KYRIN icon was not found")
        if "\n" in str(icon_path) or "\r" in str(icon_path):
            raise DesktopRegistrationError("Icon path contains a line break")
        self.executable = executable
        self.icon_path = icon_path
        self.menu_path = menu_path
        self.autostart_path = autostart_path

    def enabled(self) -> bool:
        return _read_managed(self.autostart_path)

    def set_enabled(self, enabled: bool) -> None:
        if enabled:
            contents = _entry(self.executable, self.icon_path)
            _replace_managed(self.menu_path, contents)
            _replace_managed(self.autostart_path, contents)
        else:
            if self.autostart_path.exists():
                if not _read_managed(self.autostart_path):
                    raise DesktopRegistrationError(
                        f"Unmanaged desktop entry exists: {self.autostart_path}"
                    )
                try:
                    self.autostart_path.unlink()
                except OSError as error:
                    raise DesktopRegistrationError(
                        "Could not disable login startup"
                    ) from error
