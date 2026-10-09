# Telegram chat navigation: first bounded action

## Status and evidence

The Ubuntu application now has a narrowly scoped `Saved Messages` action.
`OPEN_CHAT` is enabled only when Telegram is allowed, a separate Telegram chat
permission is saved, the active-app observer is present, and the Qt screen
verifier and focused-window identity reader are supplied. Other chat targets
remain unsupported. The initial settings grant no chat permission.

The session-scoped GNOME capture path identified the real Telegram Desktop
window by desktop ID and PID. English OCR found several known Settings labels
and one visible `Saved Messages` title in controlled read-only tests. Those
tests did not select a row. The installed OCR data is English only. Telegram
has not yielded a dependable AT-SPI tree in earlier repository diagnostics.

`kyrin.vision.text_targets.find_exact_phrases` now returns all adjacent,
same-line exact OCR matches and their image boxes. It deliberately keeps
duplicates and does not authorize a click. The box is relative to the captured
image, not a verified desktop action coordinate.

## First vertical slice

Start with Telegram's built-in Saved Messages action. The Telegram Desktop
source lists a `ChatSelf` keyboard command and a default `Ctrl+0` binding on
non-Mac platforms. Verify that binding on the installed version before using
it; users can customize shortcuts. This slice needs keyboard permission only,
not pointer permission or OCR-derived coordinates. After invoking it, KYRIN
must capture a fresh Telegram window and verify the expected chat title.
No message text is typed and no message is sent. The installed Telegram
shortcut file maps `self_chat` to `Ctrl+0`; its custom shortcut file contained
no override. In one owner-approved live diagnostic, the non-persistent portal
granted keyboard access, the fixed shortcut was dispatched only after matching
Telegram's desktop ID and PID, and the portal session was closed. A subsequent
read-only capture found `Saved Messages`, and the owner independently confirmed
the chat opened. The first OCR result alone did not prove that the title was in
the opened-chat header. A later read-only capture found one `Saved Messages`
phrase in the upper chat pane at x=679, y=45 in a 1853×1048 image. The product
verifier now requires a fresh matching desktop ID/PID and one sufficiently
confident phrase in that pane. This may reject changed Telegram layouts.

The application requests temporary keyboard access only after checking screen
access and Telegram focus. The helper rechecks desktop ID and PID before
dispatching `Ctrl+0`, closes the portal session, and the Qt-owned OCR reader
verifies the result. Uncertain verification never reports completion. This
combined application path has deterministic tests, but no end-to-end live
microphone test yet.

The broader `OPEN_CHAT` behavior for arbitrary contacts remains a separate
slice: establish a dependable search entry point, inspect results, reject zero
or multiple exact matches, select one verified result, and verify the opened
header. A recognized name anywhere in an image is not proof that it is a chat
result. Search result location and target identity must be established before
selection. Missing OCR language data, uncertain layout, changed focus, or
revoked permission must stop the action and request clarification or report
failure.

## Ubuntu input boundary

This GNOME session is Wayland; `xdotool`, `ydotool`, and `wtype` are not
installed. The local XDG Desktop Portal exposes `RemoteDesktop` version 2 and
reports a keyboard device. The portal's standard flow requests a session,
selects keyboard input, then presents a system consent dialog. Choose
non-persistent permission, request keyboard only, and close the session after
the action. The portal controls the desktop keyboard, not one named window;
KYRIN must check the Telegram desktop ID and PID before each short input
sequence and verify the result afterwards. A focus change between a check and
an input event remains a residual risk. The owner accepted this permission
scope for a one-shot diagnostic. The same helper now lives in
`src/kyrin/actions/platforms/telegram_portal_helper.py`. The app settings and
action gate apply a separate chat allowlist before it can run. The portal
dialog grants desktop-wide keyboard access for that temporary session. The
helper waits briefly after the dialog so Telegram can return to the foreground,
checks its ID and PID, then sends only the fixed shortcut. This is not yet
hands-free chat navigation.

Keep this permission-aware input adapter separate from `OcrEngine`,
`ScreenTextReader`, `ActionGate`, and the Telegram-specific navigation logic.
Other operating systems can supply their own adapters without changing the
command contract. The action gate still requires an explicit allowed chat app.

References: [XDG RemoteDesktop portal](https://flatpak.github.io/xdg-desktop-portal/docs/doc-org.freedesktop.portal.RemoteDesktop.html),
[Telegram Desktop shortcut source](https://github.com/telegramdesktop/tdesktop/blob/dev/Telegram/SourceFiles/core/shortcuts.cpp).
