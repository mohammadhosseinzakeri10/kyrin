# V1 language policy

English is the primary development and acceptance language for KYRIN V1.
Persian speech commands remain limited, experimental compatibility; their
presence in code does not establish general Persian speech reliability.
The existing Persian interface remains selectable. Other speech languages
depend on the selected models and the reviewed command/response paths.

This is a product scope decision, not a claim that English live acceptance
is complete or that no suitable Persian recognizer exists. Recognition
quality must be measured for the actual model, device and command corpus.

## Independent language choices

| Surface | Current rule |
| --- | --- |
| Interface | A fresh installation uses English. Explicit English, Persian, system-locale and imported-pack selections remain saved. |
| Speech recognition | The selected STT model/language controls recognition; changing UI language does not change it. |
| Built-in command responses | Use the supported event language, then the session language, then English. A delayed result retains its own command language. |
| Conversation replies | Preserve the model's response text and attributed language; no automatic translation is added. |
| Status character | Use its configured visual language, independently of transcript language. The current desktop composition defaults to English. |
| Voice output | Route the presented response's language to a separately configured voice. A message catalog is not proof that a usable voice is installed. |
| Targets and observations | Preserve original application names, chat titles, labels, paths and OCR text in any script. |

An English command may address a Persian chat title. Preserve the title;
transliteration or translation must not silently substitute a different
target. A deterministic test of a mixed-script transcript does not establish
that an English-only recognizer can produce that transcript from speech.

Control and window-close confirmation dialogs use the request language with
English fallback; region separators, case and surrounding whitespace do not
turn a Persian request into an English dialog. Built-in English/Persian
voice-preview samples follow the voice's primary language, including `fa-IR`,
independently of interface language. Other voice languages currently start
with editable English sample text; enter suitable text for that language.
Changing the interface does not overwrite a user-edited preview phrase.

## Source and documentation

- Use English for new technical reference documentation, identifiers,
  docstrings and developer diagnostics. Public setup, architecture, command
  and verification entry points should be usable in English.
- Keep `PROJECT_CONTEXT.md` exclusively English, as required by `AGENTS.md`.
- Preserve Persian learning notes and historical reports. Add current English
  references with links instead of rewriting the historical evidence.
- Keep reviewed translations in their existing catalogs. Do not replace the
  Persian catalog with duplicate English text.
- Treat command vocabulary, normalization rules, literal target names and
  test fixtures as behavior or evidence, not prose to translate in bulk.
- Do not overwrite an existing user's language, model or voice selections
  when applying V1 defaults. Do not introduce a translator, dependency or
  model download merely to enforce this policy.

The current interface already has a central translation catalog. Response
messages use a separate existing presenter. Move strings only when a concrete
maintenance problem warrants it; this policy does not require a new language
framework or wholesale refactoring.

## Acceptance and evaluation

The deterministic language contract covers fresh/saved UI preferences,
English questions and process notices, permission notices, outcome language,
mixed-script target preservation, an inert voice queue, and status captions.
English and retained Persian negation cases both remain non-executable.
These tests start at the transcript boundary or presentation layer; they do
not measure STT, acoustic quality or live desktop behavior.

Report model results separately by language, corpus/version, speaker coverage,
device and configuration. Do not publish a combined English/Persian score as
English acceptance. Keep original recordings and references unchanged; add
new language examples as separate labeled cases. Designed text, synthetic
audio, consented recordings and live microphone runs are distinct evidence.

The offline STT summary now includes weighted metrics in `by_language` as well
as the existing overall totals and raw per-item results. Source locale labels
remain distinct, and historical reports/references are not rewritten.

For English speech acceptance, examine transcription errors, exact action
and target accuracy, false action proposals on negatives, clarification rate,
latency and cleanup. Partial speech, negation, unrelated speech and ambiguous
targets must retain their existing authorization behavior. Performance and
accuracy thresholds require their own measured acceptance decision; this
policy invents no new thresholds and claims no speedup from removing text.

The existing [command corpus](../datasets/commands/README.md),
[STT corpus](../datasets/stt/README.md) and
[validation notes](VALIDATION.md) retain their evidence limits. Current L01/L04
live acceptance work remains separate; this change does not close it.

See the [English command guide](commands/USER_COMMAND_GUIDE.md),
[response-language contract](responses/RESPONSE_LANGUAGE.md),
[interface settings](app/UI_LANGUAGE_SETTINGS.md), and
[quality gate](development/QUALITY_GATE.md).
