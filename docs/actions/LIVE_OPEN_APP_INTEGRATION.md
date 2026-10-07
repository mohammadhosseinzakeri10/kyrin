# Controlled live application launch on Ubuntu

The microphone diagnostic can now connect a final command decision to the
existing Linux desktop-entry executor. It remains a dry run by default. Real
execution requires `--mode commands`, `--execute-actions`, and at least one
explicit `--launch-app KYRIN_APP_ID=/absolute/path.desktop` binding. The
binding is both the action allowlist and the path the executor may launch.
Nothing is inferred from the spoken text as a shell command.

For a controlled long listening trial, `--mode commands --until-stopped` keeps
the same pipeline and dialogue coordinator alive until Ctrl+C. The normal
`--seconds` mode still defaults to 10 seconds and is capped at 120 seconds.
`--until-stopped` and `--seconds` cannot be combined. Silence between commands
does not reset the dialogue or terminate capture. This is still a terminal
diagnostic; application launch still needs the separate explicit flags above.
No microphone audio is saved by this mode.

For example, after locating a locally installed STT model and Telegram's
desktop entry:

```text
.venv/bin/python scripts/audio/check_live_speech.py \
  --mode commands --stt-backend whisper \
  --model-path /absolute/path/to/model.bin \
  --whisper-server /absolute/path/to/whisper-server \
  --language en --seconds 60 \
  --execute-actions \
  --launch-app telegram=/absolute/path/to/telegram.desktop
```

The paths are examples, not project defaults. Additional bound application IDs
must also be understood by the command interpreter. A registered desktop app
whose exact desktop-entry path is supplied with `--launch-app` now contributes
its installed display name automatically. Custom paths and extra apps can use
`--spoken-app-binding DESKTOP_ID=KYRIN_APP_ID` and, when needed,
`--spoken-app-alias KYRIN_APP_ID=PHRASE`. A launch binding alone still does not
authorize any other app or teach arbitrary command phrasing.

On GNOME, an optional exact `--active-app-binding DESKTOP_ID=KYRIN_APP_ID`
also lets KYRIN check the foreground app after a launch. After `gio launch`
accepts the request, the action worker makes up to four fresh observations.
If the foreground app matches the requested internal ID, the result becomes
`CONFIRMED` with that observed app. This confirms the app was active at that
moment; it does not prove a new window was created or that the launcher caused
the focus change. Missing or different focus keeps `LAUNCH_ACCEPTED`.
Only a matching observed app reaches the localized response "The requested app
is now active"; a confirmed result without foreground evidence keeps the
generic completion response.
Launcher failures remain failures. Without an active-app binding, no result
verification is attempted. The GNOME extension must be enabled for this option
to return an app ID.

## Decision boundary

```text
microphone -> STT final transcript -> LiveCommandRuntime -> CommandCoordinator
    -> CommandResolution / CommandPlanResolution -> bounded action queue
    -> one ordered worker -> ActionGate (explicit allowlist, duplicate suppression)
    -> LinuxDesktopEntryExecutor (OPEN_APP only)
    -> ActionFeedback / ActionNotice -> localized text or voice
```

`LiveCommandRuntime` owns this event routing and the bounded action worker.
The terminal tool chooses the concrete microphone, STT engine, desktop adapter,
and text or voice presentation; those remain outside the reusable runtime.
The same runtime can therefore serve a later application entry point without
copying the command loop. `stop()` interrupts listening, while `run()` closes
the event iterator and worker. The caller still closes its STT engine and
speaker. Silence leaves the command coordinator and dialogue context alive;
an actual speech-session boundary only clears provisional segment state.

Partial transcripts only display revisable candidates. Unknown and negated
commands do not enter the action queue. A full queue returns a localized busy
notice rather than silently dropping a command. The worker owns the action
gate and executor, so the audio event consumer does not wait for `gio launch`.
Queued commands keep their order; when the diagnostic ends, queued work that
has not started receives a cancelled notice, while the active action is
allowed a bounded time to finish. For an ordered plan, steps run in order and
stop after a block, failure, or uncertain result. With `Open Telegram and open
Alice chat`, the first step may submit a Telegram launch and the second step
reports that chat navigation is unsupported. Earlier accepted steps are not
rolled back. The response for `LAUNCH_ACCEPTED` states that completion has not
been confirmed; a successful `gio launch` is not proof that a window appeared.

An unexpected exception at the executor boundary becomes an `UNKNOWN` action
result, not a claim that the action failed: the desktop operation might already
have taken effect. The gate records this uncertainty, the ordered plan stops,
and the existing text-and-voice response asks the user to check the result.
The exception is logged for diagnosis. If the action worker itself fails before
producing a result, it immediately sends an `UNKNOWN` response, stops accepting
actions, and still raises its internal error at shutdown. Focused tests cover
both paths without launching a desktop app.

## Present limits

- This is a terminal diagnostic, not a packaged always-on application. Runs
  are bounded to at most 120 seconds by default; the optional long-listening
  mode continues until Ctrl+C or a terminal error. It does not start with the
  operating system or survive a process exit.
- Only Linux application launch is connected. Chats, file changes, clicks,
  browser navigation, and other desktop operations are not connected.
- The demo interpreter recognizes a limited set of phrases. STT can still
  mishear a command; final-only gating reduces one source of errors but cannot
  guarantee the recognized words match the user's speech.
- The launcher still has a five-second timeout per step, but now runs on the
  action worker. A slow launch can delay later queued actions; the queue is
  bounded and the listener continues consuming audio events.
- Foreground observation can confirm an app is active, but does not enumerate
  windows. A launch may succeed in the background and remain unverified.

The Linux launcher starts `gio launch` in a separate process session. A
desktop app opened by a short diagnostic should therefore remain open after
the diagnostic exits. This affects process lifetime, not action confirmation:
`gio launch` still only returns `LAUNCH_ACCEPTED` without a matching fresh
foreground observation.

The first 45-second smoke run reported a capture-stop error at the end. The
microphone now lets a short read finish before using its abort fallback. A
five-second VAD run and an eight-second Whisper run exited normally. A later
25-second microphone-to-queued-action run finalized `Open Telegram.`, returned
`LAUNCH_ACCEPTED`, and exited with code zero. The owner confirmed Telegram
opened or became active. This is one local smoke test, not a general latency
or recognition-accuracy result.

In a subsequent 30-second live run with an exact GNOME active-app binding,
Whisper finalized `Open telegram.`, the launch was accepted, and a fresh
foreground observation matched Telegram. The action reported `CONFIRMED`, the
diagnostic exited with code zero, and the owner independently confirmed that
Telegram became active. This validates that one local path, not focus behavior
across all desktops or a newly created window.

A later 45-second, single-session microphone trial heard four separate final
commands: Telegram, browser, Telegram, browser. The owner saw the apps become
active in that order, confirming that listening continued between commands.
The first two launcher results were accepted without focus verification; the
later two were confirmed by fresh focus observations. Chrome then closed when
the diagnostic ended. A local reproduction showed that Chrome inherited the
diagnostic's process session; when `gio launch` was instead started in a new
session, Chrome survived the end of the launching command. The executor now
uses that behavior. This local finding has not yet been tested on other desktop
environments.

The opt-in long-listening mode was then tried for about three minutes with the
owner's microphone, Whisper small on CPU, no voice output, and no OS actions.
It kept the same session through about 90 seconds of silence. Several Telegram
finals were recognized. One browser attempt became `Open Boser.` and was not
authorized; later `Open browser.` was recognized. Two browser finals appeared,
and the owner thinks they repeated the phrase, so this run does not establish a
duplicate-segmentation defect. Backlog wait/ready notices appeared without
overflow. Ctrl+C ended cleanly with exit code zero, and both the diagnostic and
Whisper server processes exited. Two RSS snapshots were about 94 MiB for the
diagnostic and 637–641 MiB for the server. This is a short local stability
sample, not a latency or memory guarantee for persistent product use.

The focused non-hardware checks are in
`tests/commands/test_live_action_dispatch.py`,
`tests/actions/test_queued_dispatch.py`, and
`tests/actions/test_plan_runner.py`, plus
`tests/actions/test_observed_executor.py` for foreground confirmation.
