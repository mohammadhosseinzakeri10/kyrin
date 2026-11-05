# Command-model device reporting

English reference for the Ollama command-model device report. The Persian
original, `COMMAND_MODEL_DEVICE_REPORTING_FA.md`, is a development report kept
privately and unchanged; it is not linked here. Related: [DR-0006](../decisions/DR-0006-local-command-model-hosting-and-resources.md).

- **Status:** current for the Ollama command-model path (review of 2026-10-27).
  Types checked in `src/kyrin/commands/ollama_device.py` and
  `src/kyrin/app/events.py` (`CommandDeviceReported`, `SttDeviceReady`). Tests
  use fake data, transport and sockets (`tests/commands/test_command_device.py`);
  no live model or hardware run was performed.

## What the report means

The CPU/GPU/Auto option is the user's *request*. The *observed* report is where
the runtime loaded the model's memory at the time of the latest inference. It is
not instantaneous processor activity, a share of compute time or a speed
benchmark. A present GPU, a `num_gpu` setting and a weight file size are not
evidence of a full GPU load.

Evidence comes from the row for the same model in `/api/ps` (installed version
checked: 0.31.1, against official documentation and that version's source; the
`size` there differs from the file size in `/api/tags`):

| Valid evidence in the model's `/api/ps` row | Report |
| --- | --- |
| positive total size, VRAM zero | CPU memory |
| positive total size, VRAM equals total | GPU memory |
| positive VRAM below total | mixed CPU/GPU |
| total absent, valid positive VRAM | GPU participation only; completeness unknown |
| incomplete or invalid data, or observation error | unknown |
| model absent from a valid response | not loaded when observed |

No ratio is estimated from weights. `null`, a boolean instead of a number, a
wrong type, a non-positive total, or VRAM greater than the total are not
complete device evidence. The model name must be exact and unique; a different
name, a shared prefix and ambiguous duplicates are rejected. Selected models are
verified by full tag in the local repository and the private server's
`/api/tags`; aliases are not guessed.

Sources: [Ollama running models](https://docs.ollama.com/api/ps),
[load-location FAQ](https://docs.ollama.com/faq#how-can-i-tell-if-my-model-was-loaded-onto-the-gpu),
[version 0.31.1 server source](https://github.com/ollama/ollama/blob/v0.31.1/server/routes.go).

## Contract and lifecycle

`CommandDeviceReport` carries, separately: requested device, model, attempt
state (running, completed, failed), observation before cleanup, acceptance of
the cleanup request, current residency and a controlled reason. `CleanupState`
distinguishes not requested, accepted and unconfirmed.

A `done_reason=unload` response naming the exact model proves only that the
expiry request was accepted; in Ollama the unload is performed later by the
scheduler. Residency afterwards therefore stays `UNKNOWN`; no post-unload check
or new budget was added to prove memory was freed. An earlier wording claiming
"unload confirmed" was corrected. "Completed" describes the end of
inference/JSON reading; it implies no execution permission, semantic acceptance
of the proposal or desktop-action success. Before the first inference the UI
says "not run yet"; template preparation or the fast rules path produces no
fresh inference report.

After a fresh, complete response from the same endpoint and model name, one GET
to `/api/ps` is made. A mismatched or absent identity, or an absent, non-boolean
or false end marker, is a controlled error in all three device choices and no
observation is made; without a valid response identity an earlier runner's
observation is not accepted. Command understanding, conversational replies and
confirmation-answer classification all go through the same `_run`; the direct
Qwen generation path has the same check.

The network check takes at most three seconds, always within the remaining
operation time. Waiting uses a non-blocking socket with cancellation checks at
most every 50 ms; trickled bytes do not extend the deadline, and the deadline is
checked again after the wait returns. Readiness or connection end after the
deadline yields no valid observation. The GET performs no load, re-inference,
retry or residency extension. The earlier 30-second residency and the explicit
unload in `finally` are kept. The existing three-second cleanup is attempted even
after cancellation; its failure blocks resources and reports failure with unknown
residency. A truncated HTTP body is handled as `HTTPException`: in inference as a
controlled error with cleanup still attempted; in cleanup as failed, unconfirmed
unload request and blocked resources. A partial response never enters the report.

## Selection policy and UI

- Explicit CPU is accepted only with CPU evidence.
- Explicit GPU is accepted with GPU, mixed or valid GPU-participation evidence;
  no new requirement of 100% loading was created. Pure CPU or unknown is
  rejected.
- Auto reports what was observed; an observation error with a valid model reply
  yields an unknown result, and no device is constructed from the selection.
- Inference failure and device-policy failure are reported as failed.

`CommandDeviceReported` carries the session id and model repository through the
existing Qt signal bridge. The UI accepts a report only for the currently running
session and the same model, repository and device selection. An audio-file
session is matched to its own active owner. A normal event from a cancelled or
finished file is not accepted; for a short session that ends before the UI
processes signals, the last final report travels with `AudioImportResult` and the
job's unique id, shown as "last audio-file session (finished)", never as a fresh
microphone run. Cancelling, the next file and a manual new session invalidate it,
and a file result never replaces a newer microphone observation. Changing the
page selection clears the report; stop or restart does not attribute a previous
session's report to the new one.

The command-understanding page shows the user's choice and "observed load
location at the last inference" separately, in Persian and English, with cleanup
acceptance and unknown residency. Reasons are recorded in the existing
diagnostic section. The report contains no speech, prompt, raw response,
transport error content or private repository path. `SttDeviceReady` still
reports the STT session's device; TTS device options belong to that voice's
adapter selection and are not command-model device evidence. Independent
STT/TTS adapters, permissions and command-execution guards are unchanged.

## Limits

No live model or hardware run was done. The reported load location is limited to
runtime evidence; it does not prove instantaneous CPU/GPU activity or model
quality/speed, and an accepted unload response does not prove memory was freed.
No model or dependency was installed or downloaded. Validation counts and logs
from the review are private development records.
