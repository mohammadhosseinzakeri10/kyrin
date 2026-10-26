"""Remembered permission tokens stay private and reject malformed content."""

from pathlib import Path

from kyrin.app.permission_token import (
    new_token,
    read_opaque_token,
    read_token,
    save_opaque_token,
    save_token,
)


def test_screen_token_is_private_and_round_trips(tmp_path: Path) -> None:
    path = tmp_path / "permissions" / "screen.token"
    token = new_token()
    save_token(path, token)
    assert read_token(path) == token
    assert path.stat().st_mode & 0o077 == 0
    path.chmod(0o644)
    assert read_token(path) is None


def test_portal_token_is_opaque_and_rotates_privately(tmp_path: Path) -> None:
    path = tmp_path / "permissions" / "keyboard.token"
    save_opaque_token(path, "backend-token-with-dashes")
    assert read_opaque_token(path) == "backend-token-with-dashes"
    save_opaque_token(path, "replacement")
    assert read_opaque_token(path) == "replacement"
    assert path.stat().st_mode & 0o077 == 0
