# Conversation memory

## Current storage and retention

Fresh settings disable persistent history. Older settings through version 15
retain their earlier enabled behavior on read. Disabling persistence keeps
existing records and detaches the database from microphone and file sessions.
The short-lived session context and in-memory diagnostics have their own
lifecycles. Explicit archive browsing remains available.

Preferences expose independent count and age limits for active and archived
turns. The default is 2,000 active turns, with no age limit and no automatic
archive limit. Limits use the original recorded time and run during storage
operations. There is no background retention job when KYRIN is closed.
Restoring records respects active limits and keeps newer active records.

Archive, delete active history, and delete all history are separately
confirmed. Stop microphone capture and finish or cancel file processing
before clearing history. Archiving is reversible within retention limits.
Deletion applies to the selected SQLite records. External backups and source
audio are separate, and row deletion does not guarantee physical erasure.

When persistence is enabled, KYRIN stores only finalized speech text, its reported
language, a UTC time,
and session/stream/segment identifiers. Partial STT text and audio are not
saved. The SQLite database is created at the standard XDG data path
`~/.local/share/kyrin/memory/conversation.sqlite3` by default. The app honors
`XDG_DATA_HOME`. See [local data locations](../app/LOCAL_DATA_STORAGE.md) for
the boundary between application data and the source checkout.

By default, the database retains at most 2,000 active finalized turns; archived
turns are preserved outside that active limit. Both limits and optional ages
can now be configured as described above. The interpreter sees no more than six
active recent turns, shortened to 240 characters each, and only on a final
transcript. These are background context for the local command model;
the current utterance still has to independently support any executable
operation and target. Old transcripts cannot grant confirmation or action
permission. An operation fragment such as `Open`, `Open chat`, `Minimize`, or `کوچک کن`
can join a nearby final target such as `Telegram` for up to four seconds
within the same STT stream. English prefix and Persian suffix forms are
assembled according to the existing interpreter grammar; fragments are never
restored from the database. A new command, negation, yes/no
answer, system-power dialogue, or stream restart discards that fragment. A
language-label change alone does not discard it because multilingual STT labels
can vary between segments.

Preferences provides **Clear active conversation memory…** with a separate
confirmation. It clears active turns only; archived historical rows remain
available for separate review. **Review archived speech transcripts…** opens
a paged local list only when requested. Selecting a row reveals its full text;
**Restore selected transcript…** requires another confirmation and restores
only that row. Neither reviewing nor restoring authorizes an action. Storage
errors are reported without stopping listening. The
history and fragment interfaces are independent of STT and model backends.
The SQLite connection is guarded for the UI thread that creates a session and
the worker thread that processes speech.

Ubuntu session composition tests set `XDG_DATA_HOME` to a fresh temporary
directory for each test. Their fake transcripts therefore exercise persistence
without reading or writing the user's conversation database. A regression
assertion checks the temporary path and its saved test turns.

The synthetic benchmark `scripts/commands/benchmark_conversation_history.py`
uses a temporary database on the XDG data drive. It measures SQLite operations
separately from speech-to-action latency.

The control center also records text-free latency markers in the current
listening session. After action feedback, Speech Recognition diagnostics show
the interval from the confirmed start of speech activity to action result and
the interval from final STT text to action result. This includes command
understanding, policy, execution and verification, but excludes startup and
the first roughly 64 ms of VAD confirmation. It does not retain audio or
transcript text beyond the separately configured conversation history.

The supervised safe latency probe in
`scripts/commands/measure_safe_live_latency.py` reads the saved local STT and
command-model selections, uses a temporary conversation database, and replaces
the desktop executor with an inert result. Its timing is a warm-session
diagnostic and depends on the recognition and command route.
