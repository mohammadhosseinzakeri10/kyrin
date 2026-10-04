# Active App Observation on GNOME

## Problem and scope

For a command such as “open Ali's chat,” conversation history alone cannot establish which app the user is currently using. The `kyrin.desktop.active_app.ActiveAppObserver` contract provides a fresh observation. `None` means the active app is unknown; command understanding should ask the user when that distinction matters.

This integration targets GNOME Shell 50 only. The extension reports the desktop ID of the focused app. It does not read window titles, text, images, files, or the list of open windows. `GnomeShellActiveAppObserver` maps reported desktop IDs to KYRIN's internal app IDs through an explicit mapping. An unrecognized app, no focused app, an unavailable extension, or a D-Bus error produces `None`. Results are not cached; each request makes a new observation.

## Components

```text
GNOME Shell → small extension → app desktop ID over D-Bus
                                     ↓
                       GnomeShellActiveAppObserver
                                     ↓
                      telegram / whatsapp / None
                                     ↓
                        CommandCoordinator (later)
```

The extension lives under `integrations/gnome-shell/` and runs in the GNOME session. The Python adapter lives under `kyrin.desktop.platforms`, while the shared contract lives under `kyrin.desktop`. The adapter uses Ubuntu's `busctl` and adds no Python dependency. This integration is not yet connected to the microphone pipeline or command execution.

## Manual validation

Build the test package with GNOME's own tool, then install and enable it for the current user:

```bash
gnome-extensions pack --out-dir /tmp integrations/gnome-shell/active-app@kyrin.local
gnome-extensions install /tmp/active-app@kyrin.local.shell-extension.zip
gnome-extensions enable active-app@kyrin.local
```

If the current session does not recognize the new extension, logging out and back in may be necessary. KYRIN must not log the user out automatically. Once the extension is enabled, this diagnostic prints changes in the observed app ID for 20 seconds:

```bash
.venv/bin/python scripts/desktop/check_active_app.py --seconds 20
```

Switch between several apps during that interval. The output should show the app that actually has focus; when no app ID can be determined, the diagnostic prints `unknown`. This test does not execute commands.

### Validation results on 2026-10-05

- The extension package contained only `metadata.json` and `extension.js`.
- A separate headless session loaded the extension with `gnome-shell-test-tool --headless --extension`. With no focused window, the D-Bus method returned an empty app ID, which the diagnostic displayed as `unknown`.
- An attempt to focus Calculator in that headless session still produced `unknown`: the session did not provide an observable focused window. This run therefore did not verify that a real app ID can be reported.
- The extension was installed for a user-session test, but the current GNOME Shell session did not recognize it when `gnome-extensions enable` was called. The two installed files were removed after the test; no extension remained enabled in the main session.
- Switching between Telegram and Chrome with this extension has not yet been validated in a live session. That check requires a fresh login or a test session with an observable focused window.

## Limitations

This approach is specific to GNOME and needs to be retested after a GNOME version change. Some windows may not map to a recognizable installed desktop ID. In that case, the observation must remain unknown. Other Linux desktop environments need separate adapters implementing the same contract; asking the user is the safe fallback when observation is unavailable.
