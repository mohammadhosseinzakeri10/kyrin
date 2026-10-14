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

The application requests keyboard access only after checking screen
access and Telegram focus. The helper rechecks desktop ID and PID before
dispatching `Ctrl+0`, closes the portal session, and the Qt-owned OCR reader
verifies the result. Uncertain verification never reports completion. This
combined application path has deterministic tests and one successful
end-to-end live microphone check on the owner's current Ubuntu desktop.

The first product-path microphone trial recognized `open_chat` and the
foreground Telegram app, but Whisper returned `Saved Massages` for the spoken
`Saved Messages`. The executor rejected that target as `unsupported_chat`
before requesting keyboard access. The observed exact spelling is now an
additional, narrowly scoped alias for the same built-in Telegram action.
All existing permission, foreground identity, and fresh OCR header checks
still apply. After restarting KYRIN, the owner repeated the complete command.
The interpreter again produced `open_chat: saved massages`, the action result
was `confirmed`, and the owner reported that the chat opened. The first two
short fragments in that run produced no action. The reported final-text-to-
result interval was 16,849 ms; this single run includes the temporary input
permission and OCR path and does not isolate their individual costs.

For a repeatable product-path check, start listening in the installed KYRIN
control center, enable remembered screen access, and keep Telegram in the
foreground. Say `Open chat Saved Messages` once. Record the final `Heard`,
`Interpreted command`, and `Action result` or clarification in Speech
Recognition diagnostics, and confirm visually whether the chat opened. No
message should be typed or sent in this check.

The next bounded `OPEN_CHAT` slice for other names uses a Telegram search
shortcut and types at most 64 permitted characters without Enter. A fresh
OCR read must find one exact target in the left results pane below search;
a second read must return the same box and window identity. Only then does a
separate, session-only pointer portal grant allow a click. The helper compares
the focused Telegram desktop ID/PID, the window frame to the OCR image size,
and the resulting cursor position before pressing the left button. A fresh
OCR read must then confirm the exact target in the upper chat header. No text
is sent as a message. If a match is absent or ambiguous, the search layout is
uncertain, the pointer grant is denied, or focus changes, the action stops.
The owner approved the new pointer scope with system consent. This slice has
deterministic tests and awaits extension reload and live validation; it does
not claim general multilingual chat navigation, because installed OCR data is
currently English-only.

## Ubuntu input boundary

This GNOME session is Wayland; `xdotool`, `ydotool`, and `wtype` are not
installed. The local XDG Desktop Portal exposes `RemoteDesktop` version 2 and
reports a keyboard device. The portal's standard flow requests a session,
selects keyboard input, then presents a system consent dialog. The current
helper requests a remembered keyboard grant (`persist_mode=2`) and stores the
opaque restore token with mode 0600 in KYRIN's local data. Each successful
`Start` replaces the previous single-use token. If the backend refuses
restoration or returns no replacement, KYRIN asks again and does not assume
permission. Disabling Telegram chats in Desktop Actions deletes KYRIN's local
keyboard restore token. The pointer grant is never remembered. Each action
still gets a short-lived session that is closed
afterward. The portal controls the desktop keyboard, not one named window;
KYRIN must check the Telegram desktop ID and PID before each short input
sequence and verify the result afterwards. A focus change between a check and
an input event remains a residual risk. The owner accepted this permission
scope for a one-shot diagnostic. The same helper now lives in
`src/kyrin/actions/platforms/telegram_portal_helper.py`. The app settings and
action gate apply a separate chat allowlist before it can run. The portal
dialog grants desktop-wide keyboard access for that temporary session. The
helper polls for the exact Telegram desktop ID and PID for up to ten seconds
after the dialog, requires two matching observations 150 ms apart, then sends
only the fixed shortcut. It no longer waits for all ten seconds when Telegram
is already in the foreground. The identity check cannot eliminate a focus
change between the final observation and the keyboard event. General chat
navigation remains unavailable.

In one owner-confirmed repeat of the complete spoken command after this
change, KYRIN heard `Open Chat Saved Messages`, opened the chat, and reported
`confirmed`. Final-text-to-result time was 6,187 ms, compared with 16,849 ms
in the earlier run with the fixed sleep. The difference is consistent with
removing the unconditional wait, but these two runs do not isolate permission
dialog or OCR timing.

Keep this permission-aware input adapter separate from `OcrEngine`,
`ScreenTextReader`, `ActionGate`, and the Telegram-specific navigation logic.
Other operating systems can supply their own adapters without changing the
command contract. The action gate still requires an explicit allowed chat app.

References: [XDG RemoteDesktop portal](https://flatpak.github.io/xdg-desktop-portal/docs/doc-org.freedesktop.portal.RemoteDesktop.html),
[Telegram Desktop shortcut source](https://github.com/telegramdesktop/tdesktop/blob/dev/Telegram/SourceFiles/core/shortcuts.cpp).
