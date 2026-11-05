# Decision records

Short engineering decision records (DRs) that preserve the reasoning behind
important KYRIN design choices: the problem, the decision, alternatives, and
known limits. They complement, and do not replace, the current references in
Project context (`PROJECT_CONTEXT.md`, source repository only) and the linked documents. Each
record states a status; **Accepted** does not mean live-accepted on every
system (see [Validation](../VALIDATION.md)).

| ID | Decision | Status |
| --- | --- | --- |
| [DR-0001](DR-0001-english-primary-v1-and-replaceable-stt.md) | English-primary V1 and replaceable speech-to-text engines | Accepted; live acceptance open |
| [DR-0002](DR-0002-model-proposals-need-independent-verification.md) | Model and recovery proposals need independent verification | Accepted |
| [DR-0003](DR-0003-persistent-permissions-and-remembered-input-consent.md) | Persistent permissions and remembered desktop-input consent | Accepted; supersedes per-action confirmation and per-run setup |
| [DR-0004](DR-0004-guards-against-late-and-stale-results.md) | Generation, sequence and deadline guards against late results | Accepted; live acceptance open |
| [DR-0005](DR-0005-semantic-first-control-targeting.md) | Semantic-first control targeting | Accepted direction; native behavior open |
| [DR-0006](DR-0006-local-command-model-hosting-and-resources.md) | Local command-model hosting, device reporting and limited latency work | Accepted; resources open |
| [DR-0007](DR-0007-tts-adapter-boundary-and-isolated-runtimes.md) | TTS adapter boundary and isolated optional runtimes | Accepted; packaging open |
| [DR-0008](DR-0008-dashboard-2d-particle-scene.md) | Dashboard uses the 2D particle scene | Accepted; supersedes a 3D option |
| [DR-0009](DR-0009-evaluation-integrity-and-data-handling.md) | Evaluation integrity and data handling | Accepted practice |
| [DR-0010](DR-0010-voice-listening-modes.md) | Voice listening modes reuse the selected speech engine | Accepted; first-wake reliability unverified |

## Superseded or removed approaches

- Per-action confirmation for already-permitted actions and desktop-input setup
  on every run ([DR-0003](DR-0003-persistent-permissions-and-remembered-input-consent.md)).
- Vosk English as the development default candidate, replaced for development by
  Whisper `small` ([DR-0001](DR-0001-english-primary-v1-and-replaceable-stt.md)).
- Interactive 3D dashboard option ([DR-0008](DR-0008-dashboard-2d-particle-scene.md)).

## Conventions

Records are written in English, avoid personal data and machine-specific
paths, and cite only public documents and source files. Raw evidence, recordings
and detailed development logs are not part of the distribution.
