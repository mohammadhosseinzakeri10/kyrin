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

Exact label and alias matches can produce an app intent. A near spelling match
is only a suggestion and asks for confirmation first. If several bound apps
share a name or score similarly, KYRIN asks which app was intended. Duplicate
labels need a distinct configured alias before voice selection can distinguish
them. A weak match asks the user to repeat the command. The conservative
similarity cutoff and near-score margin are provisional; they must be measured
against confirmed speech examples before product use. No STT confidence value
is assumed. This layer cannot recover a severely misheard name reliably.

For the microphone diagnostic, pass `--mode commands`, a `--spoken-app-binding`
for each permitted desktop ID, and optional `--spoken-app-alias` phrases. For
example:

```bash
.venv/bin/python scripts/audio/check_live_speech.py --mode commands \
  --model-path models/local/vosk-model-en-us-0.22-lgraph --language en \
  --spoken-app-binding org.example.WhatsApp.desktop=whatsapp \
  --spoken-app-alias "whatsapp=what's up"
```

The desktop ID above is illustrative; use an ID found on the actual machine.
This diagnostic only prints decisions. It never launches an application.
There is no end-user settings interface for bindings or aliases yet. The
current demo interpreter still recognizes only a few command patterns and
does not resolve contact names, chat contents, or arbitrary natural language.
Other operating systems need their own `AppCatalog` implementations.
