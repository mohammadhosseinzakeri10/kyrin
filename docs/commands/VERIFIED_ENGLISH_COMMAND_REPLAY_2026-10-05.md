# Verified English command replay — 2026-10-05

> Reference status update: the speaker re-listened to `en-01`, `en-02`, and
> `en-06` and confirmed their displayed references. `en-03` and `en-05` retain
> earlier references without a fresh review. See
> `docs/stt/ENGLISH_AUDIO_REFERENCE_AUDIT_2026-10-05.md`.

## Scope and method

Five single-speaker recordings have user-confirmed reference wording:
`en-01`, `en-02`, `en-03`, `en-05`, and `en-06`. The earlier `en-04` clip is
excluded because the spoken app did not match its original template. The same
local `vosk-model-en-us-0.22-lgraph` was replayed on CPU with paced 20 ms audio
chunks and KYRIN's audio conversion. The new transcripts matched the earlier
five-file run exactly. The normalized character error rate was again 29/107
(27.1%). This tiny sample is diagnostic, not an estimate for future users.

Each *reference* and *STT transcript* was then separately submitted as one
`FINAL` update to a fresh `CommandCoordinator` and optional
`CatalogSpokenAppResolver`. The controlled app catalog contained Telegram,
Google Chrome, and WhatsApp, with the spoken alias `what's up` for WhatsApp.
These entries are an evaluation fixture, not proof that those apps are installed
on a user's machine. The `ActionGate` allowed the fixture app IDs for dry-run
inspection. No desktop executor was called, and no application was opened.

| Clip | STT transcript | Reference decision | STT decision | Main cause |
| --- | --- | --- | --- | --- |
| `en-01` — “KYRIN, open Telegram” | `corinne opened the door` | `OPEN_APP(telegram)` dry-run request | No command or clarification | STT changed both the wake name and target, so the demo parser treated the output as ordinary speech. |
| `en-02` — “Open Telegram” | `open filler drum` | `OPEN_APP(telegram)` dry-run request | Asked to repeat; no action | STT target is too far from Telegram for safe name matching. |
| `en-03` — “Do not open Telegram” | `do not open telegram` | No action | No action | Negation was preserved. |
| `en-05` — “Open Chrome and go to Google” | `open chrome and go to google` | Asked to repeat; no action | Asked to repeat; no action | STT was exact, but the demo interpreter does not implement compound commands. |
| `en-06` — “Open Ali's chat in WhatsApp” | `open alleys child in what's up` | Asked to repeat; no action | Asked to repeat; no action | The demo interpreter does not parse that English chat form even with perfect text; STT also changed the contact/chat words. An app-name alias cannot recover the whole intent. |

For this corpus, no transcript authorized a wrong action. The two simple
positive Telegram examples both failed to produce their intended action from
STT output. The exact-reference pass shows two additional command-understanding
gaps. These observations should not be combined into a single “accuracy” score:
compound navigation and chat execution are outside the current demo's scope.

## Reproduction

The generated WAV files, STT JSON, and decision JSON remain in Git-ignored
`datasets/stt/`. From the repository root:

```bash
.venv/bin/python scripts/stt/evaluate_offline_stt.py \
  --manifest datasets/stt/results/vosk-en-lgraph-five-verified-manifest.csv \
  --model-path models/local/vosk-model-en-us-0.22-lgraph \
  --model-language en --device cpu \
  > datasets/stt/results/vosk-en-lgraph-five-verified-command-replay.json

.venv/bin/python scripts/commands/replay_stt_decisions.py \
  --stt-report datasets/stt/results/vosk-en-lgraph-five-verified-command-replay.json \
  --app telegram=Telegram --app browser='Google Chrome' \
  --app whatsapp=WhatsApp --alias "whatsapp=what's up" \
  > datasets/stt/results/vosk-en-lgraph-five-verified-command-decisions.json
```

## Engineering decision from this run

Do not loosen approximate app matching to force `filler drum` into Telegram;
the risk of a wrong launch would rise without evidence that this helps other
speakers. Do not tune Vosk or the interpreter to these five phrases alone.
The next design task is to define the supported command forms and clarification
policy for English V1, especially compound commands and named chats, then
collect enough additional labeled commands to measure each layer separately.
Live timing and partial-transcript revisions were not evaluated by this
final-text replay. A user-assisted microphone check belongs after the command
forms and safe fallback behavior are agreed and implemented.
