# Short-command language routing diagnostic

`scripts/stt/compare_language_candidates.py` replays the same verified WAV
through one local whisper.cpp model in three modes: automatic language
detection, fixed English, and fixed Persian. It then passes each final text
to a fresh `DemoCommandInterpreter` and compares *proposed* actions with the
owner-verified command labels. It does not access a microphone, run an action,
change the product's active STT language, or choose a production route.

The report also shows the highest language probability among English and
Persian as a **diagnostic** candidate. The server supplies only a top-language
list; a missing language probability is reported as `null`, never as zero.
Expected labels are used only to score outcomes, not to pick a language.
The script refuses to overwrite an existing report.

Example using the eight currently linked recordings:

```bash
.venv/bin/python scripts/stt/compare_language_candidates.py \
  --manifest datasets/stt/manifest.safety.csv \
  --manifest datasets/stt/results/benchmark-extra-manifest-2026-10-10.csv \
  --verified-links datasets/commands/verified_speech_links.jsonl \
  --server build/tools/whisper.cpp-v1.9.4/build-gpu/bin/whisper-server \
  --model models/local/by-model/stt/whisper.cpp/ggml-small/ggml-small.bin --device gpu \
  --output datasets/stt/results/language-candidates-small-2026-10-10.json
```

## Result on this workstation, 2026-10-10

The two already installed Whisper models used the same eight one-speaker,
owner-verified recordings: five positive actions and three negated requests.
All eight were decoded three times on the GPU. Reports are stored outside Git
under `datasets/stt/results/language-candidates-{small,turbo}-2026-10-10.json`.

| Model and condition | Correct proposals among five positive requests | Missed positives | Unsafe proposals among three negatives |
| --- | ---: | ---: | ---: |
| `small`, automatic | 3 | 2 | 0 |
| `small`, highest reported English/Persian probability | 4 | 1 | 0 |
| `turbo-q5`, automatic | 2 | 3 | 0 |
| `turbo-q5`, restricted probability | 1 of 1 classifiable positive | 4 recordings unclassifiable | 0 among three classifiable negatives |

The restricted-probability result for `small` is an *offline hypothetical*;
it is not the current product behavior. It recovered the English `Close
Telegram` request, but the problematic Persian `مرورگر را باز کن` still favored
English (`en` probability 0.062 versus `fa` 0.025). Even forcing Persian on
that recording yielded `مرورگی را باز کن`, which the current interpreter did
not resolve to the browser. For `turbo-q5`, Persian was absent from the
server's probability list on four of eight recordings, so no restricted
winner can be stated for them. Forcing Persian did not reliably repair its
phonetic Latin-script output.

`no_action_or_abstention` on a negated request is *not* proof that negation
was understood: the text may simply be unreadable. There were no unsafe
proposals on these three negatives, but the sample is much too small to infer
a false-execution rate. These results do not justify enabling restricted
language routing or switching the default model. The next useful work is a
larger, speaker-diverse safety corpus and a bounded evaluation of candidate
selection that treats missing language scores and unclear transcripts as
reasons to ask the user, before changing any live action path.
