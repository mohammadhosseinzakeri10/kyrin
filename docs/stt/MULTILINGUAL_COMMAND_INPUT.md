# Multilingual command input: current boundary

The speech recognition page now shows an in-memory, bounded trace of the
latest final transcripts, interpreted commands, clarification reasons, and
action results. The trace is cleared by the user or on application exit. It
does not record audio or persist transcripts. A wrong transcript points to
STT or language selection; a correct transcript with no command points to the
command interpreter; an accepted command with a failure reason points to the
action boundary.

The user can enter additional spellings of the KYRIN wake name as a
comma-separated list. These aliases only strip an address prefix from a
command. They do not add permission to launch an app. Settings schema 3 saves
them; older schema 1 and 2 files load with an empty custom list. The built-in
spellings remain available.

A final transcript containing only the KYRIN name now receives a text-only
"I'm listening" acknowledgement and causes no action. This is different from
an unsupported command. The observed English spellings `Kyreen`, `Kyrie`,
`Kairi`, and `Kairin` are built-in aliases; other unknown spellings are not
automatically treated as commands. An alias followed by an unsupported action
still produces the ordinary repeat response.

Two previously recorded commands provide a concrete example of why this
boundary matters. Whisper returned `Kairin Open Telegram` and `تلیگرام را باز
کن`. Both were initially rejected by the interpreter despite usable command
content. The observed wake spelling and Telegram spelling are now recognized;
the same final transcripts resolve to the registered Telegram app in a
deterministic, no-action test. This does not imply that other misspellings are
safe to execute automatically.

For an installed multilingual Whisper model, the speech language field accepts
`auto`. The local whisper.cpp server receives that setting per request and
returns a verbose JSON transcription. The adapter retains the original text
and propagates the detected language code when the server supplies one. Vosk
still requires a selected language model. Auto detection does not establish
which languages an arbitrary user-supplied model actually supports. The
installed development `ggml-small.bin` returned `en` and `fa` on one existing
recording of each language; those two recordings do not measure accuracy or
reliability on mixed-language speech.

`DemoCommandInterpreter` remains an explicitly small English/Persian command
parser. Other languages may be transcribed but their commands are generally
not understood. No general text translation engine has been selected or
installed. A future offline translator must preserve the original transcript,
report its input and output languages, and remain separate from STT and action
permission. Its value and latency should be measured against direct
multilingual command understanding before making it a required pipeline step.

Current supported chat navigation is limited to Telegram Saved Messages with
its own permission and result verification. A transcript such as `Open chat
Save Message` remains a different target and cannot be silently executed as
Saved Messages. The diagnostic trace now makes that mismatch visible.
