# Bounded application launcher

English reference for the Linux application launcher. The Persian original,
OS_EXECUTOR_FA.md (source repository only), is kept unchanged.

- **Status:** current for `OPEN_APP`; checked against
  `src/kyrin/actions/platforms/linux.py` and
  `src/kyrin/actions/observed_executor.py`. Other platforms are unimplemented
  and untested.

## Role

`ActionExecutor` is the OS-independent contract: it takes an `ActionRequest`
and returns an `ActionResult`. `LinuxDesktopEntryExecutor` is the Linux
implementation and handles only `OPEN_APP`. It depends on no microphone, STT
engine or command language. Windows, macOS and Android would need separate
implementations under the same contract.

## Linux method

A configurable mapping connects an internal application id (for example
`telegram`) to the absolute path of an installed `.desktop` file; no
machine-specific path is hard-coded in the core. The executor runs
`gio launch` with separate arguments and no shell. Speech text and chat names
never become shell commands. `OPEN_CHAT` and an unconfigured application id
return controlled errors (`unsupported_action`, `app_not_configured`,
`app_not_installed`). The launcher requires the `gio` tool and a Linux desktop
session; it adds no Python dependency.

The launcher process starts in its own session (`start_new_session=True`) so a
launched application is not closed when a short KYRIN run ends. KYRIN does not
send close or terminate to the application. This was observed on the current
Ubuntu/GNOME with one browser; other desktop environments are untested.

## Result meaning

| Outcome | Meaning | Effect on verified active app |
| --- | --- | --- |
| `LAUNCH_ACCEPTED` | The launcher accepted the request; a window is not confirmed. | The previous app is no longer verified. |
| `CONFIRMED` | A valid observer confirmed the result. | The reported active app name is recorded, if any. |
| `UNKNOWN` | Like a launcher timeout: the app may or may not have opened. | The previous app is no longer verified. |
| `FAILED` | The launcher reported a definite error. | Previous context is kept. |

A zero exit status from `gio launch` yields only `LAUNCH_ACCEPTED`. The base
executor never fabricates `CONFIRMED` or `observed_active_app`. The optional
`ObservedAppExecutor` may upgrade to `CONFIRMED` only after a fresh
observation matching the foreground app; otherwise the result stays
`LAUNCH_ACCEPTED`. Launcher failures map to bounded codes in the current code:
`launcher_timeout` (outcome `UNKNOWN`), `launcher_unavailable`,
`launcher_permission_denied`, `launcher_os_error` and the generic
`launcher_failed`. Human wording, language
and voice belong to the response layer.

To resolve a later command without an app name, `CommandCoordinator` keeps the
history of the named app separately from a fresh observation of the active app.
The executor only reports launching; it is not a window observer.

## Validation and scope

Automated tests cover safe launcher arguments, the independent session,
unknown applications, unsupported commands, errors and timeouts without
opening any application. A manual run on the development machine received
`LAUNCH_ACCEPTED` for an installed messaging application; a human observation
of a window does not turn the automatic result into `CONFIRMED`. The
diagnostic microphone tool calls this executor only with `--execute-actions`
and `--launch-app`. See [Live open-app integration](LIVE_OPEN_APP_INTEGRATION.md).
