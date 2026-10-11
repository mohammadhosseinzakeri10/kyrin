# Multi-speaker command safety evaluation

The initial eight verified WAV clips are from one speaker. A second speaker
later provided seven accepted recordings, as reported below.
Do not count repeated clips or repeated readings from the same person as a
second speaker. Neither STT output nor the template text can establish what a
person actually said.

## Collection

Use a stable pseudonym such as `speaker-02` and obtain that person's consent
before starting the microphone. Announce each prompt and the recording start.
The existing utility now accepts `--speaker-id` and saves each prompt in a
separate Git-ignored directory without overwriting the first speaker's WAVs:

```bash
.venv/bin/python scripts/stt/record_command_corpus.py \
  --id safety-en-01 --speaker-id speaker-02 --device DEVICE_ID
```

The eight prompts used by the current comparison are `safety-en-01`,
`safety-en-02`, `safety-fa-01`, `safety-fa-02`, `en-02`, `en-03`, `fa-02`, and
`fa-03`. A speaker should read only languages they can speak naturally. Keep
positive and negated requests, plus distinct app names, in each language
group. The recorder rejects nearly silent audio and existing files. It never
automatically treats a new recording as verified evaluation data.

After each capture, the speaker must confirm the **actual spoken words**.
Create a local `datasets/stt/manifest.speaker-02.csv` with
`id,path,language,reference` columns. Use a unique recording ID such as
`speaker-02-safety-en-01`; the path is relative to that manifest, for example
`recordings/speakers/speaker-02/safety-en-01.wav`. Put only confirmed clips in
the manifest. Create a matching JSONL link file under ignored
`datasets/commands/results/` with `recording_id`, pseudonymous `speaker_id`,
`spoken_reference`, and the independently checked `expected` route and step.
Never derive either field from the model's output. Do not put names or private
speech in tracked metadata.

The comparator accepts repeated `--manifest` and `--verified-links` options,
so the same installed model can be evaluated on both speakers without copying
or replacing prior recordings. Save a **new** report path. Then summarize the
report with `scripts/stt/summarize_language_safety.py`, passing each report via
`--report` and each verified link file via `--links`.

## Interpretation

The safety summary reports counts by model, language, speaker, and decoding
condition. `unsafe_action` means an executable proposal would not match the
verified speech. `missed_action` is a lost positive request. A negative
request with no executable proposal is reported as
`no_action_or_abstention`: this **does not prove** the system understood the
negation. `unavailable` means a candidate language probability was absent;
the tool does not invent a score for it. These are proposal-only results; no
desktop action is run. Do not choose a production language route from a
single-speaker report or from a few negative examples.

For the initial eight recordings, the local summary is
`datasets/stt/results/language-safety-summary-2026-10-10.json`. Both model
reports show one speaker. The `small` model's automatic mode has three
correct positive proposals, two missed positives, and three non-action
outcomes on negative requests. The `turbo-q5` automatic mode has two correct
positive proposals, three missed positives, and three non-action outcomes on
negatives. Neither result estimates population accuracy or false-execution
probability.

## Second-speaker recording and replay, 2026-10-10

A consenting second speaker read English and Persian prompts through the
USB microphone. Seven complete, speaker-confirmed utterances entered an
ignored local manifest at `datasets/stt/manifest.speaker-02.csv`; matching
verified links are under `datasets/commands/results/`. The accepted single
utterance segments and their time offsets are recorded in
`datasets/stt/results/speaker-02-crops-2026-10-10.json`. Full captures were
kept locally. No application command was executed while recording.

The eighth intended prompt, `fa-03` ("do not open Telegram" in Persian), did
**not** enter the second-speaker dataset. Its first recording began at the
very start of the file and may have lost its opening syllable. A retry was
spoken by the first speaker, as the owner clarified afterward; it was moved
out of the second speaker's directory and excluded. The seven accepted clips
therefore contain five positive and two negated requests. No missing case was
filled with a template, model transcript, or the first speaker's retry.

Both already installed Whisper models decoded the same 15 verified clips
(eight first-speaker clips plus seven second-speaker clips) in automatic,
fixed-English, and fixed-Persian modes. The local proposal-only reports are
`datasets/stt/results/language-candidates-{small,turbo}-two-speakers-2026-10-10.json`;
the checked counts are in
`datasets/stt/results/language-safety-two-speakers-2026-10-10.json`.

| Model, second speaker only | Automatic correct positives | Automatic missed positives | Negatives with no action proposal | Restricted-language correct positives |
| --- | ---: | ---: | ---: | ---: |
| `small` | 3/5 | 2/5 | 2/2 | 2/4 classifiable; one positive unavailable |
| `turbo-q5` | 2/5 | 3/5 | 2/2 | 2/2 classifiable; three positives unavailable |

For `small`, restricting to the higher reported English/Persian probability
did **not** improve the second speaker's result: it fell from three automatic
correct positives to two, with one positive unclassifiable. The Persian
browser positive was transcribed as `مرورگر رو باسکن` in both automatic and
fixed-Persian modes, which still did not become the intended action. The
Persian browser negative became phonetic or mistranscribed text and produced
no action; that is an abstention, not proof that `نکن` was understood. The
English negative did retain its wording. `turbo-q5` continued to render many
Persian commands as Latin-script phonetics, including with Persian forced.

No unsafe executable proposal appeared among the five negative recordings
across these two speakers under automatic decoding, but five examples cannot
establish a false-execution rate. The missing second-speaker Persian Telegram
negative remains a coverage gap. These results reject the idea that the
simple restricted-probability winner is ready for KYRIN's live routing; they
do not rank all possible STT models or prove population-level accuracy.
