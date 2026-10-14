"""A local, owner-readable capability for remembered desktop permissions."""

import os
import secrets
import tempfile
from pathlib import Path


def permission_token_path(name: str) -> Path:
    if name not in {"screen", "telegram-keyboard"}:
        raise ValueError("unknown permission")
    configured = os.environ.get("XDG_DATA_HOME")
    root = Path(configured) if configured else Path.home() / ".local/share"
    if not root.is_absolute():
        root = Path.home() / ".local/share"
    return root / "kyrin" / "permissions" / f"{name}.token"


def read_token(path: Path) -> str | None:
    try:
        if path.stat().st_mode & 0o077:
            return None
        token = path.read_text(encoding="ascii").strip()
    except OSError, UnicodeError:
        return None
    return (
        token
        if len(token) == 64 and all(c in "0123456789abcdef" for c in token)
        else None
    )


def save_token(path: Path, token: str) -> None:
    if len(token) != 64 or any(c not in "0123456789abcdef" for c in token):
        raise ValueError("invalid permission token")
    path.parent.mkdir(parents=True, mode=0o700, exist_ok=True)
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="ascii",
            dir=path.parent,
            prefix=".permission-",
            delete=False,
        ) as output:
            temporary = Path(output.name)
            output.write(token)
            output.flush()
            os.fsync(output.fileno())
        os.replace(temporary, path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def new_token() -> str:
    return secrets.token_hex(32)


def read_opaque_token(path: Path) -> str | None:
    try:
        if path.stat().st_mode & 0o077 or path.stat().st_size > 4096:
            return None
        token = path.read_text(encoding="utf-8")
    except OSError, UnicodeError:
        return None
    return token if 0 < len(token) <= 4096 and "\x00" not in token else None


def save_opaque_token(path: Path, token: str) -> None:
    if not isinstance(token, str) or not 0 < len(token) <= 4096 or "\x00" in token:
        raise ValueError("invalid portal restore token")
    path.parent.mkdir(parents=True, mode=0o700, exist_ok=True)
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", dir=path.parent, prefix=".portal-", delete=False
        ) as output:
            temporary = Path(output.name)
            output.write(token)
            output.flush()
            os.fsync(output.fileno())
        os.replace(temporary, path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
