# Desktop operation lifetime

Implemented 2026-10-24 (P09, F08 and the active-helper part of F05).

Desktop input admission and the generic control, scroll and Telegram entry
points now establish an absolute monotonic operation deadline. Nested calls
inherit its remaining time and cancellation generation through a context-local
`Operation`. Independent Telegram selection/paging calls establish their own
operation and also observe their existing cancellation event. No timeout was
increased: generic input remains bounded by 45 seconds, Telegram by 65 seconds,
OCR verification by 18 seconds, and settle/scan loops by their existing limits.
The budget begins before broker admission; time waiting for input ownership is
included. A completed earlier operation does not supply a stale deadline to a
later human selection.

Qt requests explicitly carry this context across the thread boundary. Capture,
OCR and every fallback use that same budget. Caller timeout cancels the context
and queues request-specific cleanup; late capture, OCR and permission callbacks
cannot start another read or authorize input. The ten-second visible-list
settle loop no longer grants an extra read beyond its deadline. Focus identity
reads used by actions/OCR also receive the remaining budget.

Tesseract and Paddle run in owned subprocesses. Cancellation/expiry stops and
reaps the process before its owner returns: SIGTERM, up to 300 ms for cleanup,
then SIGKILL and reap. A helper's descendant busctl stays in its process group.
Each input helper receives the absolute deadline and a private inherited
socket-pair descriptor. Before every portal `Notify*` call it checks deadline,
asks its owner whether the action generation is still valid, and compares the
current restore token with its expected permission epoch. Unlink/replacement
invalidates active input; authorized rotation updates the helper's expected
value. A revoked token is not recreated by a late `Start` response. Standalone
setup helpers have a finite local budget and the same token checks.

Portal calls and response timers receive only remaining time. Timeout closes
an outstanding Request; every acquired Session is closed in `finally`, including
revocation and interruption. The helper's D-Bus connection disappears on forced
process termination. These are still one-shot sessions; persistent reuse is not
introduced by this change. See the official [Request Close contract](https://flatpak.github.io/xdg-desktop-portal/docs/doc-org.freedesktop.portal.Request.html)
and [Session lifetime contract](https://flatpak.github.io/xdg-desktop-portal/docs/doc-org.freedesktop.portal.Session.html).

Limits are explicit:

- Cancellation cannot undo input already dispatched. An interrupted action
  reports `UNKNOWN` / `action_interrupted`, so it does not authorize a retry.
- OS process creation and a kernel uninterruptible native call cannot have a
  strict wall-clock return guarantee. Cleanup can outlast the work deadline;
  the owner remains held until reap instead of abandoning a worker. This is
  consistent with Python's [subprocess timeout contract](https://docs.python.org/3.14/library/subprocess.html).
- An in-process third-party OCR plugin cannot be forcibly killed as a Python
  thread. The reader cancels its context, retains its worker and busy ownership,
  discards its result, and refuses another read until actual completion. Built-in
  OCR uses the killable process boundary. Future native plugins requiring hard
  cancellation must also use a process boundary.
- The GNOME screenshot service has no per-capture cancellation method in the
  current interface. A timed-out client discards its callback and does not
  begin OCR; this does not claim to stop an already issued Shell screenshot.
- The last authorization check precedes dispatch; revocation cannot recall an
  already authorized D-Bus call. Portal input/focus behavior and device release
  still require a live GNOME test. None was performed for this change.

Deterministic tests cover fake clocks/processes, remaining budgets, expiry,
late callbacks, request/session cleanup, revocation, refusal of pending input,
kill/reap escalation, and native-worker ownership. A tiny subprocess checks
private descriptor inheritance/authorization without desktop access.

Validation on 2026-10-24: the two original regressions failed before the fix;
all 1,584 tests passed afterward, with native tests outside the restricted
sandbox so isolated D-Bus and GJS image decoding could run. `ruff check src
tests`, compilation, and strict mypy on the 13 changed implementation files
passed. Full-source mypy still reports nine errors in the untouched
`app/qt/dashboard.py` and `actions/platforms/desktop_accessibility_inventory.py`.
The repository-wide format check also has outstanding differences; unrelated
formatting was not swept into this change.
