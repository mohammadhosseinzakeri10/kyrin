# Model admission and residency (F19)

(English migration of a previously Persian-only note; the original is
preserved in the private migration pre-images and in Git history.)

- **Status:** current policy for models inside the application process; code
  checked in `src/kyrin/model_resources.py` and
  `src/kyrin/commands/{ollama_engine,token_budget}.py`. Real cold/warm
  baselines, hardware peak memory and live concurrency were never measured; no
  speed or memory improvement is claimed.

## Scope and ownership

In the application process, `MODEL_RESOURCES` is shared by the STT session, the
command model, `ScreenTextReader` OCR, document OCR and TTS generation; TTS
preview and file sessions use the same policy. Microphone, action permission and
independent validation of model output are unchanged. Direct use of STT or OCR
backends outside this composition is not managed automatically.

A model load or call has exactly one owner. Wait order: STT, command, interactive
OCR, TTS, then document OCR; FIFO within a priority. Four normal waiters and one
extra place for STT are allowed. A normal wait is capped at five seconds, STT at
120 seconds (`ResourceLimits.wait_seconds`, `stt_wait_seconds`); the existing
operation deadline/cancel is also checked. A full queue, expiry and low memory
fail before loading. A native call already started is not pre-empted; logical
cancel alone does not release its ownership. STT stop and cancel do not pass
through the queue. The policy is not a real-time latency guarantee.

In the L01 correction, the live Whisper and Omnilingual composition keeps
silence in the bounded pre-speech buffer when there is no speech, so waiting
behind a command-model call alone does not fill the STT queue. This is in the
audio line; it does not bypass model ownership or turn order, and a long wait
with real speech can still reach the queue limit. See the
[live speech pipeline](../audio/LIVE_SPEECH_PIPELINE.md).

## Residency

STT stays resident until the engine is actually closed; a second STT session is
not accepted until the first is released. The command model is held only for the
request scope and is explicitly unloaded even after a failure in counting or
inference. The unload answer must confirm completion; a cleanup failure blocks
admission of later model work until restart. Built-in OCRs run in a short-lived
process. TTS releases its model before playback after each generation; the next
call reloads it. Automatic selection of light ONNX families goes to CPU; an
explicit CPU/GPU choice and family/language choice are kept. The system speech
service is not under local-model management.

## Limits and profiles

`ResourceLimits` and `PeakMemory` can be configured by injecting one shared
`ModelResources`. A profile carries the measured RAM/VRAM peak and idle
residency; it must cover runtime, activation, KV cache and measurement margin for
the real input range and settings. Weight file size is not the policy input. An
explicit limit with an unknown peak is rejected. The current work's peak is added
to the residency of other models and compared with the limit; free memory is
rechecked at admission, and a model's own residency is not counted twice. By
default RAM needs at least 512 binary megabytes of headroom
(`ram_headroom_bytes`); RAM is read from `MemAvailable` and VRAM only through an
injected probe. No real peak profile or limit is recorded for this machine; with
no profile, serial execution and unload apply but OOM prevention is not
guaranteed. A change of model, device, context or image/audio scope requires
re-reviewing the profile. Keys are built as below; for interactive OCR the
profile must cover all models and sizes allowed for the backend class.

```text
stt:{backend}:{model_path}:{device}
command:{model_tag}:{device}:{context_tokens}
ocr:{engine_class}:{device}
tts:{backend}:{model_path}:{provider}
document_ocr:{backend}:{device}
```

## Command-model token budget

`CommandTokenBudget` (`ollama_engine.py`) defaults to 4096 context tokens, 768
output tokens and 32 safety tokens; the confirmation question has a 64-token
answer. The full chat template is obtained from Ollama with truncation disabled,
and an installed `llama-tokenize` uses the vocabulary of the GGUF layer in the
selected model's manifest. Private text is passed on standard input, not written
to a file or command line. Character or option counts do not replace token
counts. The tool is discovered in `PATH`, through the explicit path
`KYRIN_COMMAND_TOKENIZER`, or an existing local runtime; nothing is installed or
downloaded automatically. The render API is version-dependent: the contract of
version 0.31.1 was checked, and an older version, a missing tool, an invalid
template or a counting mismatch rejects the model path. Practical support for
all models/future versions is unverified.

The current text, language, application observation, the full list of allowed
application ids, allowed operations and control capability are not dropped; the
confirmation question and answer also stay complete. Applications and controls
are ranked by relevance to the current text and then fitted with full-template
counting; all explicit matches, including ambiguous duplicates, are kept or the
whole request is rejected. Background history is optional and last priority.
Dropping an option comes with an incompleteness marker and never becomes a
discovery permission or a fresh target. If mandatory evidence does not fit,
inference does not run. `truncate=false` and `shift=false` are sent, and the
real `prompt_eval_count` is compared with the count before the request; a
difference of more than one token rejects the output. The model still only
proposes meaning and is not execution permission.

In the E06 correction the template is still rendered for each fresh request;
only the real count of an identical full template, with fixed vocabulary-file and
counter-program identity, can be reused within that counter's memory. Retention
is limited to 32 entries of at most 64 KiB; larger text is fully counted but not
retained. A change or loss of file identity stops reuse and no invalid output is
cached. This cache is not a model or runner response; fresh inference, the
`prompt_eval_count` check, budget, cancellation and unload are kept. A limited
before/after comparison showed an effect for two repeated templates; the gain
for fresh input and the true peak are unknown (the evaluation report is a
private development note).

## Timing and tests

The `model_resource_wait` and `model_resource_run` boundaries are connected to
the F18 timing mechanism ([command latency](COMMAND_LATENCY.md)) and record no
private content. Run time includes loading, counting and cleanup. Fake-model,
race, queue-pressure, cancellation, low-memory, OOM, reload and prompt-evidence
tests cover the behavior. No real cold/warm baseline, hardware peak or live
concurrency test was run in F19. The next step is a controlled measurement with
installed models, recording peak and latency under fixed conditions with the F18
tool. Later limited measurements of existing models and the validity range of
memory/time are recorded in private E45/E06 development notes; real peak and
live acceptance remain separate from sampled peak and file/text replay.

Official sources for the contract:
[Ollama residency and usage counts](https://docs.ollama.com/api/chat),
[checked version types](https://github.com/ollama/ollama/blob/v0.31.1/api/types.go),
[render without inference](https://github.com/ollama/ollama/blob/v0.31.1/server/routes.go),
[local tokenizer with vocabulary loading](https://github.com/ggml-org/llama.cpp/blob/master/tools/tokenize/tokenize.cpp).
