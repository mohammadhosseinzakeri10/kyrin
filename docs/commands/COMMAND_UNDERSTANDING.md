# Live command understanding

English reference. The Persian original,
COMMAND_UNDERSTANDING_FA.md (source repository only), is preserved
unchanged. The model-independent proposed contract and reference cases are in
[Semantic understanding contract](SEMANTIC_UNDERSTANDING_CONTRACT.md).

- **Status:** current experimental layer, checked against
  `src/kyrin/commands/` and tests `tests/commands/test_commands.py` and
  `tests/commands/test_live_dry_run.py` (deterministic, no hardware or local
  model). Real STT quality and latency remain unmeasured by these tests.

## Place in the pipeline

`LiveSpeechPipeline` produces interim (`PARTIAL`) and final (`FINAL`) text.
Interim text may change. The command layer sits after STT and before execution:

```text
LiveSpeechPipeline -> TranscriptUpdate -> CommandCoordinator
                                  |
                          CommandInterpreter
                                  |
                CommandCandidateUpdate / CommandResolution / ResponseRequest
                                  |
                   ActionGate / ResponsePresenter
```

`CommandCoordinator` consumes only `TranscriptUpdate`. A VAD pause is neither a
final command end nor the end of a conversation, and its order relative to STT
text is not guaranteed. `BacklogNotice` is not a command. Nothing here touches
the microphone, Vosk or the operating system.

## Components

- `CommandInterpreter` is the replaceable contract turning text, probable
  language and conversation context into one of: ready command, need for a
  question, unfinished command, unintelligible command, or non-command speech.
  Swapping the language-understanding engine must not change the coordinator.
- `CommandCoordinator` immediately issues the first interim text containing a
  clear command as a correctable suggestion; each later meaningful change
  replaces or withdraws the suggestion for that segment. Final text immediately
  gives the definitive result. No repeated interim text or timer is needed.
- `ContextResolver` checks an omitted application name against the **fresh
  observation of the active application** and the **last application named in
  the conversation**. These differ; on conflict a question is generated instead
  of a guess.
- `DemoCommandInterpreter` is a limited offline sample for testing the flow,
  with a few simple Persian and English phrases about opening Telegram, a browser
  and a chat. It is not the product's multilingual engine and is no yardstick for
  other languages.

Optionally the interpreter takes an `AppNameResolver`, currently implemented in
the desktop layer: registered applications with an explicit mapping. An exact or
configured alternative name maps to the internal id; a near-match asks a
confirmation question and an ambiguous name asks which application. This covers
only opening applications; contact-name recognition and free-form commands do
not exist yet (see [Spoken app matching](../desktop/SPOKEN_APP_MATCHING.md)).

If a registered application's name, even with a small spelling difference,
resembles a chat command (such as `Open Chat One`), the final result first asks
"application or chat?". An explicit "application" selects opening the app;
"chat" goes through the current chat-application lookup. A bare "yes" does not
guess the target and the question repeats. Interim text records no question and
executes nothing. If such ambiguity appears in a multi-step command, the whole
command is declared unintelligible and no step runs.

`CommandCandidateUpdate` is only a **correctable suggestion**, never execution
permission, even if complete-looking. A changed interim text replaces the
suggestion with the same id; if no command remains, `None` withdraws it.
`CommandResolution` after `FINAL` supersedes any suggestion for the same
`(stream_id, segment_id)`; a consumer must not treat suggestion and final result
as two commands. Executing reversible actions from interim text would need its
own safety policy and handling of late correction, designed and tested
separately.

## Conversation and disambiguation

The name "Kyrin" is optional; the sample accepts its correct form and the
variant seen in local STT testing at the start of a sentence. The name alone,
without a clear command, does nothing.

For "open Ali's chat": if a fresh, reliable active-application observation does
not conflict with history and the application supports chat, it becomes the
target. If history says Telegram but the fresh observation shows WhatsApp, the
sample asks which one. With no fresh observation, history alone does not set
the target and the application name is asked. An explicit application in the
same command or in the user's answer overrides both. Contact search does not
exist at this stage.

The coordinator tracks segment ids per STT session and keeps the last
application named in a *final* result in that instance's memory. Interim text,
pauses and an STT restart do not clear this history or an open question. The
upstream application must supply a fresh active-application observation per
command; the `VerifiedContext` stored in `ActionGate` does not replace it. The
diagnostic tool can optionally read the active application for each final text.
Temporary conversation memory disappears when the process ends.

For an unfinished or unintelligible command a repeat request is generated after
the final text; ordinary unrelated speech gets no reply. `ResponseRequest`
carries a `ResponseKind`, needed data (contact name, application options) and
the output channel (`TEXT_ONLY` or `TEXT_AND_VOICE`) rather than a sentence;
text is built in `ResponsePresenter`, so the interpreter does not depend on the
reply language. Understanding questions and errors use `TEXT_AND_VOICE`. The
diagnostic tool can play offline voice replies; no product UI exists yet.

The language of each final text travels from `TranscriptUpdate` to
`CommandResolution` and `ResponseRequest` with that command's result. With the
monolingual Vosk engine it is the configured model language, not automatic
detection. See [Response language](../responses/RESPONSE_LANGUAGE.md).

## Tests and limits

`tests/commands/test_commands.py` covers interim change, suggestion withdrawal,
no repetition of a final result, a command without the call name,
Telegram/WhatsApp conflict, no fresh observation, explicit application choice,
pause, new-session start and ordinary speech. `tests/commands/test_live_dry_run.py`
passes a fake audio source and STT through the real `LiveSpeechPipeline`: an
interim "open Telegram" suggestion is corrected to "do not open", the
suggestion is withdrawn and the final result has no command; a VAD pause does
not end the STT session or conversation context.

To observe these decisions with a microphone, use the `commands` mode:

```bash
.venv/bin/python scripts/audio/check_live_speech.py --mode commands --device DEVICE_ID --model-path /path/to/local/model --language fa --seconds 35
```

The tool prints STT text, activity events, command suggestions, final results
and localized reply text. `--response-language` sets the preferred reply
language, defaulting to `--language`; a supported language in an event takes
priority. Persian and English texts exist; other languages fall back to the
session language, then English, which is not a claim of STT or command
understanding in them. Input audio is not stored; `TEXT_AND_VOICE` replies play
with the current offline engine unless `--no-voice-responses`. No application is
opened. By default there is no active-application observation, so after "open
Telegram" the command "open Ali's chat" still asks for the application.

For the optional GNOME active-application observation, find the real application
id with `scripts/desktop/check_active_app.py`, then add
`--active-app-binding DESKTOP_ID=telegram`. The id is installation-specific and
is not fixed in public code. The `command_bridge` takes a fresh observation only
at `FINAL` text; interim text never waits for the OS. If the extension or id is
unavailable the result stays unknown and an ambiguous command leads to a
question. Only the decision is printed (Active app observation (`ACTIVE_APP_OBSERVATION.md`, source repository only)).

The sample knows only a few English two-step shapes ([Multi-step commands](MULTI_STEP_COMMANDS.md)).
Arbitrary application names without explicit mapping, most world languages and
real execution are not covered. This layer adds no dependency. The gate that
turns final results into requests is described in [Action gate](../actions/ACTION_GATE.md),
[Application launcher](../actions/OS_EXECUTOR.md) and
[Live open-app integration](../actions/LIVE_OPEN_APP_INTEGRATION.md); execution
needs `--execute-actions` and an allowed `--launch-app` mapping.
