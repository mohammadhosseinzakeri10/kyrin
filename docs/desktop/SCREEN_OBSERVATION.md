# Read-only desktop observation (Ubuntu)

## Scope

KYRIN can request a fresh, bounded accessibility snapshot of the focused
window. This is a foundation for future browser and chat navigation, not an
automation executor. It does not click, type, take screenshots, run OCR, or
continuously scan the desktop. Observations are returned in memory and are not
written to disk. The diagnostic hides labels unless `--show-labels` is given;
labels can include private on-screen text.

The platform-neutral `ScreenObserver` contract and immutable observation data
live in `kyrin.desktop.screen_observation`. The Ubuntu adapter lives in
`kyrin.desktop.platforms.atspi`. Other operating systems can implement the
same contract without importing GNOME or AT-SPI.

## How identity is checked

1. The existing GNOME extension reports the focused desktop ID and window PID
   in one `GetActiveWindow` call. The original `GetActiveApp` method remains.
2. The desktop ID must still exist in the installed-app catalog.
3. A short-lived system-Python helper reads AT-SPI. It accepts only one active
   window with the reported PID. If AT-SPI marks none active, it accepts only
   one showing window with that PID.
4. After the helper returns, the adapter reads the GNOME identity again. A
   focus change discards the snapshot.

If any step fails, `observe()` returns `None`. A readable label is not proof
that an element can be safely clicked, and the snapshot is never authority for
a later action. Later actions must re-observe and verify their own target.

## Bounds and platform dependency

The helper reads at most 120 nodes and six levels by default, truncates each
label to 160 characters, and is stopped after eight seconds. This keeps a
damaged or enormous accessibility tree from blocking the application. The
helper runs outside the project's Python environment because Ubuntu's `gi`
and `Atspi` bindings are supplied by the system. This Ubuntu adapter requires
`/usr/bin/python3`, `python3-gi`, `gir1.2-atspi-2.0`, and an accessibility bus.
Those packages are not added to KYRIN's cross-platform Python dependencies.

AT-SPI coverage varies by application. In the development session, v2rayN
exposed a small tree, while Chrome exposed no top-level AT-SPI window and
Codex exposed several showing windows without a unique active window. The
observer must report unknown in those cases; browser-specific observation or
an image/OCR fallback can be evaluated later. No general screen-understanding
or browser navigation claim follows from this first step.

On this machine, the screenshot portal advertises interface version 2, which
does not expose the newer explicit active-window screenshot target. A separate
one-shot ScreenCast Portal window capture and OCR contract now exist under
`kyrin.vision`; see `docs/vision/OCR_ARCHITECTURE.md`. A separate, session-
authorized GNOME adapter now ties one image to the focused desktop ID and PID.
It has been checked with a registered KYRIN test window and, later, with the
real Telegram Desktop window. A local Tesseract runtime is available in KYRIN
user data without a system package install. The Telegram Settings view yielded
several expected English labels, and one controlled chat-list run found the
public title `Saved Messages`. Arbitrary contact matching and Chrome remain
unverified. Neither image text nor accessibility labels authorize actions.

## Diagnostic and validation

The GNOME extension package was installed for the current user on 2026-10-09.
After the owner restarted, the corrected session-access interface passed a
live one-image request and revocation test. KYRIN does not restart GNOME.

After a restart, focus an accessible application and run:

```bash
PYTHONPATH=src .venv/bin/python scripts/desktop/check_screen_observation.py
```

The default output gives only the desktop ID, label count, and truncation
status. To inspect labels intentionally, add `--show-labels`. No action is
performed. Unit tests cover successful snapshots, changing focus, missing
catalog entries, malformed helper responses, and timeouts. A live product
integration and browser-content validation remain separate steps.
