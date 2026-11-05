# Speech recognition manifests

This directory contains blank or designed read-aloud templates. Each row
describes a proposed reference, not an acoustic result. Select the appropriate
language, command, or safety template for the evaluation you are preparing.
Keep the reference language and exact literal targets in the original script.

Copy the template to a private manifest and supply audio paths for your own
consented recordings. Keep raw audio, references linked to recordings, and
per-item results outside the public repository. See the
[data-handling decision](../../docs/decisions/DR-0009-evaluation-integrity-and-data-handling.md)
and the [STT evaluation guide](../../docs/stt/STT_EVALUATION.md) for recording,
manifest format, scoring, and how to report per-language results.

The public source can run deterministic tests without speech recordings or
recognition models. The separate [command corpus](../commands/README.md)
evaluates behavior at the transcript boundary.
