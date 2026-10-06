# Response language and process notices

## Language flow

`TranscriptUpdate.language` describes the language attributed by the STT
backend. A multilingual backend may detect it; a fixed-language backend such
as the current Vosk adapter reports its configured model language. The field
does not, by itself, prove language detection.

For a final transcript, `CommandCoordinator` copies this language to its
`CommandResolution` and any `ResponseRequest`. `ActionGate` carries it through
`ActionRequest`, `ActionNotice`, pending confirmation, and `ActionFeedback`.
Each event therefore retains its own language even when an action result
arrives after a later command in another language. Partial command candidates
remain advisory and do not produce responses or actions.

`ResponsePresenter` selects a supported event language first, then the
configured session language, then English. The selected language is returned
in `PresentedResponse.language`, so a future UI can see which language was
actually used. The microphone diagnostic accepts `--response-language` for
the session preference; without it, the configured STT model language is the
preference. Errors before a transcript exists use that session preference.

Only Persian and English message catalogs exist today. An unsupported event
language falls back to the session language when available. Adding a language
requires reviewed translations for every user-facing message and, for spoken
output, a separately selected offline TTS voice. This work does not add a
translation service or claim automatic detection or recognition of all
languages.

## Process notices

`SystemNotice` is a structured user-facing status. `notice_for_backlog` turns
a backlog warning into a pause request with `TEXT_AND_VOICE`, and recovery
into a `TEXT_ONLY` message. `notice_for_error` classifies known audio,
compute-device, model-path, and STT failures; it does not copy raw exception
text into the response. An audio queue overflow warns that speech **may have
been lost**, rather than implying that it was preserved.

The live microphone diagnostic prints localized notices. In `commands` mode,
events requesting `TEXT_AND_VOICE` also use the optional local Speech Dispatcher
output; `--no-voice-responses` keeps it text-only. This still is a dry run for
desktop actions: no recognized command is executed and no product UI exists.
Speech playback and microphone echo suppression are described in
`docs/responses/OFFLINE_SPEECH_OUTPUT.md`. The diagnostic loads `sounddevice`
only after parsing arguments, so help works without an audio server.
