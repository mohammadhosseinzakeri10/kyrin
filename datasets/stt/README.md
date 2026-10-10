# Local STT evaluation data

`manifest.template.csv` lists the first six Persian commands and their exact
reference texts. Put one spoken WAV for each row in `recordings/`, then copy
the template to `manifest.csv` and correct any reference to what was actually
spoken. Keep the same WAV files for every STT candidate.

`recordings/`, `results/`, and `manifest.csv` are local and excluded from Git.
This avoids publishing voice recordings or accidental private transcriptions.
The template and instructions remain tracked so the evaluation is repeatable.

For the first local six-command set (2026-10-05), one speaker read each
reference aloud through the USB2.0 mono microphone. The recording utility is
`scripts/stt/record_command_corpus.py`; it refuses to overwrite an existing
WAV and rejects nearly silent captures. The files were cropped to one utterance
each, with these intervals measured from each original diagnostic capture:

| ID | Original interval kept |
| --- | --- |
| `fa-01` | 1.5–5.4 s, first complete reading of four repetitions |
| `fa-02` | 0.0–2.5 s |
| `fa-03` | 2.6–6.2 s |
| `fa-04` | 0.7–3.3 s |
| `fa-05` | 1.6–5.2 s |
| `fa-06` | 0.6–6.3 s |

The original long diagnostic captures were discarded. The speaker confirmed
that the `fa-05` reference matches what they said. These six clips are a small
development baseline from one speaker, not a representative accuracy dataset.
On 2026-10-05 the same speaker additionally recorded `en-02`. An initially
near-silent capture was rejected and never saved. A second 20-second capture
contained the spoken command around 17 seconds; its 16.7–19.2 second interval
is the 2.5-second `recordings/en-02.wav` used for scoring. The original full
capture is retained locally at `recordings/raw/en-02-2026-10-05.wav`. Whisper
small transcribed the crop as “Open Telegram.” The ignored
`manifest.multilingual.csv` currently contains only this recorded English row;
unrecorded template rows are not treated as evaluation data.
The speaker also recorded `en-03`; its 22.2–24.9 second interval was cropped
to a 2.7-second scoring WAV. The full 30-second capture remains locally at
`recordings/raw/en-03-2026-10-05.wav`. Whisper small transcribed the crop as
“Do not open Telegram.” The local English manifest now lists `en-02` and
`en-03` only.

On 2026-10-05 the speaker consented to three more English prompts. The first
`en-01` attempt was nearly silent and was rejected without saving. The active
USB microphone source was found at 14% input volume and adjusted to 60% for
the repeat and subsequent prompts. Each accepted 30-second capture remains in
`recordings/raw/`; a single utterance was cropped for scoring:

| ID | Original interval kept | Raw capture |
| --- | --- | --- |
| `en-01` | 9.9–12.7 s | `recordings/raw/en-01-2026-10-05.wav` |
| `en-04` | 14.3–17.5 s | `recordings/raw/en-04-2026-10-05.wav` |
| `en-05` | 16.1–19.1 s | `recordings/raw/en-05-2026-10-05.wav` |

Separate second-utterance crops for `en-01` (20.1–22.8 s) and `en-04`
(19.3–22.5 s) are in ignored `results/` for a limited repeat check. The
first `en-04` utterance actually named **Telegram**, as the speaker confirmed
after the test; the template's WhatsApp reference does not match that crop.
The original five-command scoring files have been marked
`UNVERIFIED-REFERENCE` and must not be used for accuracy claims. A separate
four-command manifest and report exclude `en-04`. The wording of the later
`en-04` crop was not confirmed, so it is exploratory only. All artifacts are
in ignored `results/`. Each recording has one speaker and cannot establish
general English accuracy.

The speaker then confirmed a new, separately recorded `en-06` utterance of
“Open Ali's chat in WhatsApp.” Its accepted 30-second raw recording is kept at
`recordings/raw/en-06-2026-10-05.wav`; the 19.0–22.5 s interval is the scoring
clip `recordings/en-06.wav`. The speaker explicitly confirmed saying WhatsApp
this time. The ignored `results/vosk-en-lgraph-five-verified-manifest.csv`
contains `en-01`, `en-02`, `en-03`, `en-05`, and `en-06` with usable reference
texts. It does not include the misread `en-04` crop.

About 0.005% of the samples in `fa-01` reached the 16-bit clipping limit;
the other five clips had no clipped samples. This minor capture artifact and
the differing lead-in silence should be considered when interpreting latency
or the wake-name error.

Required WAV format: uncompressed mono 16-bit PCM. Sample rate may vary; the
evaluator resamples to the selected engine's input format. The first six rows
use `fa`, so they can be evaluated with the local Persian Vosk model. Other
languages need separately labeled rows and a compatible engine/model.

`manifest.multilingual.template.csv` contains additional English commands;
`manifest.german.template.csv` contains one optional exploratory German command.
Their read-aloud text and interpretation limits
are in `docs/stt/MULTILINGUAL_COMMAND_PROMPTS_FA.md`. New voice recordings
require a separate start announcement and explicit consent; the template alone
does not authorize microphone use. The local `manifest.multilingual.csv` is
also Git-ignored, as is `manifest.german.csv`. General-speech samples from public corpora must have their
source, license and item IDs recorded separately from KYRIN commands.

See `docs/stt/STT_EVALUATION_FA.md` for the evaluation command and metrics.

`manifest.safety.template.csv` adds four short English/Persian commands for a
separate source-to-action safety check: closing versus opening an application,
the browser target, and a negated browser request. The recording utility knows
these IDs but does not start the microphone until it is explicitly run after
consent. The corresponding local `manifest.safety.csv` and recordings are
Git-ignored. A human must confirm the spoken wording of every accepted clip
before the reference can be scored; a saved template is not proof of speech.

The owner authorized and recorded all four prompts on 2026-10-10. A first
near-silent English close attempt was rejected; the owner reported missing its
start cue. The accepted captures are 20 seconds each, with the USB microphone
input set to 60%. Full original WAVs remain in `recordings/`. Candidate
single-utterance crops are in `recordings/segments/`:

| ID | Candidate interval from original | Note |
| --- | --- | --- |
| `safety-en-01` | 7.7–10.1 s | Complete first utterance; a second follows |
| `safety-en-02` | 15.6–18.1 s | One complete utterance |
| `safety-fa-01` | 15.2–18.1 s | More complete of two candidate utterances |
| `safety-fa-02` | 13.7–16.9 s | Complete first utterance; later audio reaches file end |

The speaker confirmed saying each prompt and intentionally repeating it. The
four selected crops above are now listed in the ignored `manifest.safety.csv`,
with speaker-verified references. Whisper `small` on GPU returned exact
normalized text for both English crops, `مرورگی را باز کن` for the Persian
affirmative, and `مارورگره باز نکن` for the Persian negative. Its four-clip
character error rate was 5/59 (8.5%). The detailed ignored report is
`results/whisper-small-gpu-safety-2026-10-10.json`. This tiny one-speaker
sample does not estimate population accuracy. No desktop action was executed.
In a separate dry interpreter call, the current `DemoCommandInterpreter`
recognized both English operations, requested clarification for the misspelled
Persian browser name, and returned no action for the negative Persian text.
This does not exercise the full live microphone-to-executor path.
