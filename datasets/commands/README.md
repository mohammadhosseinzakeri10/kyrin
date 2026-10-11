# KYRIN command-understanding reference cases

`semantic_cases.jsonl` defines intended behavior independently of the current
demo interpreter and any future STT, translator, or understanding model. Each
line is one JSON object with:

- `id`: stable case identifier.
- `origin`: `owner_verified` for wording confirmed by the owner in a prior
  live test, `owner_reported` for wording recalled or proposed by the owner,
  or `designed` for a new specification example. None of these labels claims
  that an audio recording exists.
- `input_text`: reference words, a reported phrase, or an observed STT
  spelling, as described by `input_kind`. `language` identifies the source
  language when known.
- `context`: optional known foreground and dialogue facts. Missing context is
  intentionally unknown, not a guess about the user's desktop.
- `expected.route`: `execute`, `clarify`, `confirm`, `no_action`, or
  `unsupported`. `steps` describes the intended structured meaning, including
  polarity; it does **not** grant permission or claim that an executor exists.

Cases marked `designed` are specifications for later validation, **not**
measured model successes. The corpus includes user-observed examples but does
not include voice recordings. A future audio evaluation must reference a
consented recording, its exact spoken words, speaker/language, and the STT
output separately. Do not score an STT error against an uncertain reference.

The corpus deliberately includes negation, unrecognized speech, uncertain app
names, system power, and dependent steps. A safe implementation must never
turn `clarify`, `no_action`, or `unsupported` into an executable action merely
because an STT or language model produced a plausible command.

`verified_speech_links.jsonl` links eight separately consented, locally stored
recordings to the reference wording and intended route. It contains no audio.
`scripts/commands/audit_speech_replay.py` checks those links against local STT
manifests, the STT text sent to command models, and a proposal-only decision
replay. This is how a transcript that changes one valid app name to another is
counted as unsafe relative to what was spoken, even if text-only target
grounding accepts the mistaken transcript. The output is kept under ignored
`results/`; the script does not open a microphone or execute a command.
The four additional safety recordings cover closing Telegram, opening the
browser, a Persian browser request, and its negated form. The owner confirmed
the wording and intentional repetitions. The selected single-utterance crops
and transcript report are described in `datasets/stt/README.md`.

Each of the eight verified links now carries the same pseudonymous
`speaker_id`, `speaker-01`. This records the actual one-speaker coverage
without publishing a personal identity. Additional consented speakers use
separate local, ignored link files. See
`docs/stt/MULTI_SPEAKER_SAFETY_EVALUATION.md`.
