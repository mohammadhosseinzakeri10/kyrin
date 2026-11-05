# Offline speech-recognition evaluation

English is the primary V1 acceptance language. Evaluate it independently from
Persian and other languages; see the [language policy](../LANGUAGE_POLICY.md).
This procedure uses existing, consented local WAV files. It does not record a
microphone or execute desktop actions, and no new evaluation has been performed
merely by adding this guide.

## Prepare references

The tracked templates under `datasets/stt/` are prompts, not recordings or
verified speech. `manifest.l04.template.csv` describes English command cases;
`manifest.multilingual.template.csv` also contains historical English prompts.
Preserve those files and create a separate ignored local manifest for the
recordings actually available. Include only rows whose exact spoken reference
has been checked; do not assume that the speaker read the template correctly.
See the [corpus history](../../datasets/stt/README.md) for excluded or uncertain
recordings and the distinction between original captures and scoring crops.

Each manifest needs `id`, `path`, `language` and `reference`. Paths are relative
to the manifest directory. WAV files must be uncompressed mono 16-bit PCM;
sample rates can differ because the evaluator uses the engine input format.
Keep one utterance per scoring clip and use the same clips across models.

Use separate language-homogeneous manifests/reports. Alternatively, repeat
`--case-id` to select an explicitly reviewed single-language subset. A fixed
`--model-language en` rejects selected rows labeled with another language.
With `auto`, the evaluator can accept mixed-language rows and its aggregate
summary is not a per-language English acceptance result. New reports include
`by_language` with reference-weighted CER/WER and file/reference/edit counts
for each source language label. Existing top-level totals and per-item results
are retained. Labels such as `en` and `en-US` stay distinct rather than being
silently merged; existing saved reports are not rewritten.

## Run an installed backend

Inspect the available arguments without starting recognition:

```bash
PYTHONPATH="$PWD/src" .venv/bin/python scripts/stt/evaluate_offline_stt.py --help
```

For an already installed Whisper runtime and model, replace these example
absolute paths with the actual existing local paths and select a verified
English manifest. The output path must be new; reports are not overwritten.

```bash
PYTHONPATH="$PWD/src" .venv/bin/python scripts/stt/evaluate_offline_stt.py \
  --backend whisper \
  --manifest datasets/stt/manifest.english-verified.csv \
  --model-path /absolute/path/to/english-capable-model.bin \
  --whisper-server /absolute/path/to/whisper-server \
  --model-language en \
  --device cpu \
  --output datasets/stt/results/english-verified-whisper-cpu.json
```

The manifest and paths above are examples, not supplied recordings or installed
model locations. Vosk instead takes its model directory and a fixed matching
language. Omnilingual uses its selected checkpoint and isolated runtime.
GPU evaluation needs the corresponding working runtime; a requested device
alone is not evidence of actual GPU execution. No model installation or download
is part of this command example.

## Interpret the report

Keep backend/model identity, corpus and verified references, selected language,
device configuration, speaker coverage and the per-item results. Report word
and character error rates for that language rather than merging it with other
languages. Read the matching `by_language` entry for a mixed-language report;
do not use its overall total as English performance. Preserve failed attempts;
do not replace them with selected successes.

Word accuracy is not action accuracy. A recognizer can turn one valid app name
into a different valid app name. Downstream evaluation must separately check
exact operation/target, clarification and false action proposals on negative
or ordinary speech. Use the [command corpus](../../datasets/commands/README.md)
and the existing evaluation contracts rather than authorizing a real executor
to score recognition.

Model load time, first partial text, final text, command result and real audio
onset are distinct timing boundaries. `--unpaced` runs faster than realtime;
it does not establish live microphone latency. Small curated or single-speaker
sets do not prove general English accuracy, accent coverage or long-run
stability. Deterministic [language tests](../development/QUALITY_GATE.md) cover
software routing, not these acoustic or hardware acceptance requirements.

The Persian evaluation notes retain historical methods
and results; they are not silently translated into new English evidence.
