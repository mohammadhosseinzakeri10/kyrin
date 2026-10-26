# English audio and reference audit — three key clips reconfirmed

The owner raised a valid concern that a reference sentence might not match its
WAV. The speaker then listened again to `en-01`, `en-02`, and `en-06` and
confirmed that all three match their displayed references. `en-03` and `en-05`
retain their earlier references without this fresh review. `en-04` remains
excluded because its original WhatsApp template did not match the spoken app.
This small, single-speaker set does not establish a production accuracy rate.

## Local audio check

All five scoring clips are mono, 48 kHz, 16-bit PCM and contain audible-range
signal above a simple -40 dBFS window threshold. This signal check cannot
verify the words or pronunciation. `en-01`, `en-02`, and `en-05` had one or two
samples at the 16-bit amplitude limit; `en-03` and `en-06` had none. Such tiny
counts do not establish that clipping caused a recognition error.

| ID | Duration | Whole-clip RMS | Samples at limit |
| --- | ---: | ---: | ---: |
| `en-01` | 2.80 s | -18.0 dBFS | 1 |
| `en-02` | 2.50 s | -17.8 dBFS | 2 |
| `en-03` | 2.70 s | -26.5 dBFS | 0 |
| `en-05` | 3.00 s | -15.0 dBFS | 2 |
| `en-06` | 3.50 s | -28.1 dBFS | 0 |

The original WAVs were converted with FFmpeg to identical 16 kHz mono PCM
files under ignored `datasets/stt/results/common-english-audit/`. Vosk and both
local `whisper.cpp` models read those same files. Vosk processed 20 ms chunks
without real-time pacing; Whisper processed each complete file in a fresh CPU
process with four threads, explicit English, and no GPU. This is a comparison
of *final text on shared audio*, not a fair live-latency benchmark. The earlier
48 kHz Vosk result remains separate because its resampling path differs.

| ID | Provisional reference | Vosk (16 kHz) | Whisper small | Whisper large-v3-turbo-q5_0 |
| --- | --- | --- | --- | --- |
| `en-01` | KYRIN, open Telegram | `corinne opened the door` | `Kairin Open Telegram` | `Kyrene OpenTelegram` |
| `en-02` | Open Telegram | `open filler drop` | `Open Telegram` | `Open Telegram` |
| `en-03` | Do not open Telegram | `do not open telegram` | `Do not open Telegram` | `Do not open telegram` |
| `en-05` | Open Chrome and go to Google | `open chrome and go to google` | `Open Chrome and go to Google` | `Open Chrome and go to Google` |
| `en-06` | Open Ali's chat in WhatsApp | `open alleys child in what's up` | `Open Alice chart in WhatsApp` | `Open Alice chart in WhatsApp` |

**Limited local comparison:** using the displayed references, normalized character errors
are Vosk 30/107 (28.0%), Whisper small 5/107 (4.7%), and Whisper turbo 6/107
(5.6%). A later correction to either unrechecked reference could change these
values. All clips are from one speaker, so this result does not measure general English accuracy or
accent coverage. Approximate wall time per file was 2.3 s for Whisper small
and 8.6 s for turbo with a fresh model load each time; these cannot be compared
directly with Vosk's single-load, unpaced run or with real-time response.

The current command interpreter authorized a **dry-run** `OPEN_APP(telegram)`
from `en-02` for both Whisper outputs, but not from any Vosk output. None of
the three engines produced an executable command for `en-05` or `en-06`,
because the demo interpreter does not support those command forms. No desktop
action was executed.

## Human validation status

The speaker reconfirmed the wake name, app names, and `Ali's chat` wording in
the three requested clips. The owner chose to stop expanding the comparison
corpus for now and proceed with the existing Whisper `small` candidate for
English development. This is a product direction, not a statistical claim
about all speakers or languages.

This audit used only local files and local CPU processes. No microphone or
network service was used, and no KYRIN action was executed.
