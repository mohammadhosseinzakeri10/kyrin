# Spoken application names (initial offline design)

KYRIN can use the operating system's registered application list as a source
of candidate names. On XDG desktops, `XdgDesktopAppCatalog` reads `.desktop`
entries. This requires no access to the system Settings application or elevated
privileges. The catalog does not prove which application is in focus.

The flow is:

```text
final/partial STT text -> command interpreter -> spoken name resolver
    -> exact app ID OR clarification -> final command -> ActionGate -> executor
```

`CatalogSpokenAppResolver` caches catalog labels plus configured aliases. Call
`refresh()` after installing or removing apps; the live audio path does not scan
the desktop files for every partial transcript. Only platform IDs explicitly
bound to KYRIN app IDs are considered. The `ActionGate` still has its own
allowlist, and the executor still needs an explicit platform-specific launch
mapping. An arbitrary installed app does not become executable merely because
its name appears in the catalog.

In the live command diagnostic, an explicit `--launch-app` path that exactly
matches a registered XDG desktop entry also supplies that entry's display name
and KYRIN app ID to the spoken-name resolver. This removes the need to repeat
the same app in `--spoken-app-binding`. A custom or unregistered launch path
keeps its earlier behavior; no name is inferred from its filename. If an
explicit spoken binding disagrees with the launch binding for the same desktop
ID, startup fails instead of choosing one silently. The configured KYRIN app
ID is also an exact spoken alias, so a binding named `browser` still accepts
"Open browser". The catalog snapshot is prepared at startup; future settings
changes can call `refresh()` explicitly. Active-app observation remains a
separate, fresh final-transcript check when configured.

Exact label and alias matches can produce an app intent. A near spelling match
is only a suggestion and asks for confirmation first. If several bound apps
share a name or score similarly, KYRIN asks which app was intended. Duplicate
labels need a distinct configured alias before voice selection can distinguish
them. A weak match asks the user to repeat the command. The conservative
similarity cutoff and near-score margin are provisional; they must be measured
against confirmed speech examples before product use. No STT confidence value
is assumed. This layer cannot recover a severely misheard name reliably.

English `close`, `exit`, and `quit` requests currently use the bounded close-window
operation. A close request with an approximate app name asks for the app name
and then separately confirms the close action; an approximate name never closes
a window by itself. This operation closes an application window, not necessarily
the entire process. Apps that stay in the system tray, including some V2RayN
setups, may require a future explicit quit adapter and its own verification.

An exact registered app name alone opens an operation menu. The user can say a
number, say `yes` to open or bring the app forward, or say `no` to cancel. If
opening is the only available operation, the question is simply whether to
open the app. Clear aliases such as `launch`, `start`, `switch to`, `hide`, and
`bring ... to front` use the existing open, minimize, and restore actions.
"Make Telegram smaller" is ambiguous between minimizing it and returning a
maximized window to normal size, so it offers those two choices instead of
acting. A name or a targetless size request must not authorize a window action.

For the microphone diagnostic, pass `--mode commands`, a `--spoken-app-binding`
for each permitted desktop ID, and optional `--spoken-app-alias` phrases. For
example:

```bash
.venv/bin/python scripts/audio/check_live_speech.py --mode commands \
  --model-path models/local/by-model/stt/vosk/vosk-model-en-us-0.22-lgraph --language en \
  --spoken-app-binding org.example.WhatsApp.desktop=whatsapp \
  --spoken-app-alias "whatsapp=what's up"
```

The desktop ID above is illustrative; use an ID found on the actual machine.
This diagnostic only prints decisions. It never launches an application.
There is no end-user settings interface for bindings or aliases yet. The
current demo interpreter still recognizes only a few command patterns and
does not resolve contact names, chat contents, or arbitrary natural language.
Some installed app names overlap with command syntax (for example, a name
beginning with "Chat"). For one plausible registered app name that also reads
as a chat command, the interpreter asks whether the user means the app or a chat.
Only the explicit reply "app" may authorize the app; "chat" follows the
existing chat-app context rules. A vague "yes" repeats the question. Such an
ambiguity inside a multi-step utterance blocks the whole plan rather than
executing a fragment. Multiple plausible app names ask for repetition rather
than selecting a chat. Approximate names outside this overlap and arbitrary
natural language still remain limited by the demo parser.
Other operating systems need their own `AppCatalog` implementations.
