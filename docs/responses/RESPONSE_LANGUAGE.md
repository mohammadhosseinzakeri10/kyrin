# Response language and process notices

English is the primary V1 command/acceptance language; the existing Persian
catalog remains available. See the [language policy](../LANGUAGE_POLICY.md).

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

## Interface, captions and literal targets

The Qt interface has its own saved language preference and starts in English
on a fresh installation. A Persian interface does not force an English
command's response into Persian. Conversely, the status character follows
its configured visual language, including the numbered-window selection
prompt; transcript language must not change it. The current desktop composition
defaults that visual preference to English.

Built-in Telegram selection questions supply reviewed alternatives through
`ResponseRequest.message_translations`. The same prompt can therefore remain
Persian in the text/voice response and English in the character caption, or the
reverse. This explicit local catalog uses the selected supported language;
genuine model replies leave it empty and preserve their original text/language.

Targets, labels and titles remain in their original script. An English
response may contain a Persian target without changing its message language.
Voice routing receives `PresentedResponse.language`; retaining a target does
not establish that a selected English voice can pronounce it correctly.

The Qt and GNOME control-confirmation dialogs use the request language.
They recognize regional Persian tags such as `fa-IR` and `fa_IR`, ignoring
case and surrounding whitespace; unsupported languages fall back to English.
This only selects wording and writing direction. Explicit consent, deadlines,
target identity, cancellation and single-use approval remain unchanged.

## Process notices

`SystemNotice` is a structured user-facing status. `notice_for_backlog` turns
a backlog warning into a pause request with `TEXT_AND_VOICE`, and recovery
into a `TEXT_ONLY` message. `notice_for_error` classifies known audio,
compute-device, model-path, and STT failures; it does not copy raw exception
text into the response. An audio queue overflow warns that speech **may have
been lost**, rather than implying that it was preserved.

The live microphone diagnostic prints localized notices. In `commands` mode,
events requesting `TEXT_AND_VOICE` also use the optional local Speech Dispatcher
output; `--no-voice-responses` keeps it text-only. Desktop actions are a dry
run by default, but explicitly allowlisted app launch can be enabled with
`--execute-actions` and `--launch-app`. The Qt control center separately
composes this response layer with saved permissions, selected local TTS and
visual status. Diagnostic flags do not configure the product UI.
Speech playback and microphone echo suppression are described in
`docs/responses/OFFLINE_SPEECH_OUTPUT.md`. The diagnostic loads `sounddevice`
only after parsing arguments, so help works without an audio server.
