# Direct versus live speech-path comparison

`scripts/stt/compare_live_path.py` replays each labeled mono PCM WAV twice at
recorded speed. The first pass opens the selected STT session directly and,
for a turn-aware engine, explicitly marks the entire file as one turn. The
second pass uses the actual `LiveSpeechPipeline` with Silero VAD, framing,
backlog, and the same STT engine. No microphone, command interpreter, or desktop
executor is used. Both passes share the already-loaded model but open separate
sessions. Model startup time is excluded. The WAV is read from disk twice;
recordings and JSON reports remain in Git-ignored `datasets/stt/` paths.

Example with an existing local model and one verified case:

```bash
.venv/bin/python scripts/stt/compare_live_path.py \
  --manifest datasets/stt/manifest.safety.csv \
  --backend whisper \
  --model-path models/local/whisper.cpp/ggml-small.bin \
  --whisper-server build/tools/whisper.cpp-v1.9.4/build-gpu/bin/whisper-server \
  --language auto --device gpu --case-id safety-fa-01 \
  --output datasets/stt/results/live-path-comparison.json
```

The script refuses to overwrite a report. `final_seconds` is measured from
the start of each pass. `final_offset_from_audio_end_seconds` may be negative
when a speech pause seals a turn before trailing silence ends. These times
include WAV pacing, Python scheduling, VAD, and STT, but exclude model loading.
`cer` is character error rate; it can exceed 1 if a transcript is longer or
in another script. `final_languages` is the engine-attributed language, not a
verified fact about the speaker.

## Initial controlled result, 2026-10-10

The locally stored, owner-verified `safety-fa-01` and `safety-fa-02` clips were
tested on the current `ggml-small.bin` Whisper GPU backend. No hints were used.

| Clip | Engine language | Direct final | Live final | Observation |
| --- | --- | --- | --- | --- |
| `safety-fa-01` (positive) | `fa` | `مرورگی را باز کن` | Same | One character error in both paths. |
| `safety-fa-02` (negated) | `fa` | `مارورگره باز نکن` | Same | Negation survives in both paths. |
| `safety-fa-01` | `auto` | Greek-script text, detected `el` | Greek-script text, detected `el` | Language identification fails in both paths. |
| `safety-fa-02` | `auto` | `مارورگره باز نکن` | Same | Negation survives in both paths. |

Both live runs showed one speech start and one pause per file, and no backlog
notice. On these two clips the live VAD/framing path did not introduce the
observed text errors. This is a tiny, single-speaker sample; it does not prove
that the live path is generally reliable or that fixed Persian is a suitable
default for multilingual users. The immediate question is whether language
selection or another STT model can improve the positive command without
losing negation, while preserving multilingual input.

## Two-model language and device comparison, 2026-10-10

Two already-installed models were compared without hints, downloads, or live
actions: `ggml-small.bin` (466 MiB on disk) and
`ggml-large-v3-turbo-q5_0.bin` (548 MiB). The four owner-verified safety clips
were tested with `auto` on GPU and attempted on CPU (the turbo CPU pass stopped
at the current request timeout); GPU runs additionally used explicit
`en` for the two English clips and `fa` for the two Persian clips. Four more
owner-verified clips (`en-02`, `en-03`, `fa-02`, `fa-03`) were tested with `auto`
on GPU. All runs used the same `whisper.cpp` v1.9.4 adapter, four server
threads, and the same WAVs. Reports and a derived four-case manifest are in
Git-ignored `datasets/stt/results/benchmark-*-2026-10-10.json` and
`benchmark-extra-manifest-2026-10-10.csv`.

| GPU condition | Correct attributed language | Critical text result on the four safety clips |
| --- | ---: | --- |
| `small`, `auto` | 2/4 | English `Close Telegram` became Arabic-script text; Persian positive became Greek-script text. |
| `turbo-q5`, `auto` | 1/4 | The same English close became Arabic-script text; both Persian clips became Icelandic-like Latin text. |
| `small`, explicit language | 4/4 by configuration | Both English clips exact after normalization; Persian positive had one character error, negative retained `باز نکن`. |
| `turbo-q5`, explicit language | 4/4 by configuration | Both English clips exact; Persian clips remained Latin-script phonetic text even with `fa`. |

Across all eight `auto` GPU clips, `small` attributed 5/8 languages correctly
and `turbo-q5` 3/8. A correct English transcript can still have a wrong
language label: `en-02` was transcribed as `Open Telegram` by both models but
attributed to `fa` by `small` and `is` by `turbo-q5`. Direct and live text was
identical on 5/8 clips for each model; the remaining differences were small
word-ending, punctuation, or alternate phonetic renderings, except the already
poor `turbo-q5` Persian positive. All eight live clips had one detected speech
start and one pause, without backlog notices. This does not rule out VAD
failures on other speech.

The current `DemoCommandInterpreter`, called only on the four *live text*
outputs and never connected to an executor, recognized the two English actions
with either model when `en` was explicit. With `auto`, it recognized only
`Open browser`; the misattributed English close and Persian positive produced
no action. With explicit `fa`, `small` still could not act on the misspelled
browser name. Neither model produced an action from either Persian negative;
for `turbo-q5` this is an abstention on unreadable text, not proof that the
negation was understood. These are four cases, not an action-accuracy estimate.

On the warmed GPU, the slowest *first final transcript relative to file end*
among the four safety clips was about 0.10 seconds for `small` and 0.24 seconds
for `turbo-q5` in `auto` mode. Finals can arrive before file end when the
trailing silence confirms a pause. These timings exclude model loading and
do not include command understanding or action execution. On CPU, the `small`
live final arrived about 10.4–11.4 seconds after file end on the same four
clips. `turbo-q5` failed in the current product transport with its eight-second
HTTP request timeout. A separate direct CPU server request with a longer
timeout returned the correct English close after 8.23 seconds of inference;
this identifies a timeout/performance limit, not damaged weights. The product
timeout was not changed by this benchmark.

A local process-memory probe read Linux RSS and `nvidia-smi` for each loaded
server. Idle CPU-server RSS was approximately 564 MiB for `small` and 618 MiB
for `turbo-q5`. Idle GPU allocation was 824 MiB and 914 MiB, respectively.
Sampling at 0.4-second intervals during one Persian two-pass replay observed
up to 1004 MiB for `small` and 1040 MiB for `turbo-q5` on GPU. These are
samples of this workstation's server process, not guaranteed peaks or full
KYRIN RAM/VRAM budgets. They exclude the Python app, VAD, compositor, and
other system activity.

The results do **not** justify switching the product to fixed Persian or
selecting `turbo-q5` as its default. They show that short-utterance language
identification and Persian recognition need further work. Any candidate
language-routing policy should be assessed on more speakers and languages,
with special attention to negation and incorrect app actions.
