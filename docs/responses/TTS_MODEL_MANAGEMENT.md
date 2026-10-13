# Local, multilingual TTS management

The **Voice Output** page has a default English voice and independent tabs for
additional language codes such as `fa`, `de`, and `fr`. Place a complete,
extracted supported model package in the local TTS folder or select its folder
with **Browse**. KYRIN detects the engine automatically. Each language tab
selects a speaker, speed, and AUTO/CPU/GPU preference. The page never downloads
models. Its preview uses the sample text, language, voice, device, and speed
currently shown in the selected tab, including unsaved edits.
The local-model picker remains available while the default system voice is
selected, so choosing a supported folder does not require choosing an engine
first. Saving checks package structure, the installed runtime, and an explicit
GPU request before changing the active voice. The audible preview validates
the draft selection and tests it without saving or changing the active voice.
The installed-model list accepts both a model directly under its TTS root and
one level of family grouping. On this source checkout, that root is
`models/local/by-model/tts/`, for example
`models/local/by-model/tts/kokoro/kokoro-multi-lang-v1_0/`. Each extracted
model has its own directory; the family directory itself is not a model package.
For the verified Kokoro v1.0 package, the English voice control shows the
speaker names and accent/gender labels instead of requiring a numeric speaker
ID. The selected name is still saved as the corresponding speaker ID used by
sherpa-onnx. The v1.1 package similarly lists its documented English voices.
Unknown or renamed Kokoro packages retain the numeric control because their
speaker-name mapping has not been verified. The v1.0 package's additional
non-English voices are not offered for unsupported language routes.

On the current Ubuntu development machine, the standard user-data directory is
linked to `local-data/kyrin/` on the AI-Projects drive. TTS model weights in
this checkout are kept in the catalog above; optional runtimes remain in
`local-data/kyrin/runtimes/tts/`. See
[local data storage](../app/LOCAL_DATA_STORAGE.md). This mount-specific layout is
not required on other machines.

## Supported package families

| Engine | Local package | Language support |
| --- | --- | --- |
| Speech Dispatcher / eSpeak NG | Operating-system installation | Depends on installed system voices |
| Kitten via sherpa-onnx | Official extracted Kitten archive | English, 8 speakers |
| Kokoro via sherpa-onnx | Official extracted `kokoro-*` archive with lexicon files | Depends on the package; the referenced v1.1 archive supports English and Chinese |
| Piper/VITS via sherpa-onnx | Official extracted `vits-piper-*` or `vits-*` archive | Depends on the chosen model; Persian models exist |
| Chatterbox Multilingual V2/V3 | Complete local archive with V2/V3 T3 weights and built-in voice condition | 23 languages listed by its creator; no Persian |
| Qwen3-TTS CustomVoice 0.6B/1.7B | Complete local checkpoint including `speech_tokenizer/` | 10 languages listed by its creator; no Persian |

Use the complete official [Chatterbox multilingual checkpoint](https://huggingface.co/ResembleAI/chatterbox/tree/main)
or a complete [Qwen3-TTS CustomVoice 0.6B](https://huggingface.co/Qwen/Qwen3-TTS-12Hz-0.6B-CustomVoice/tree/main)
or [1.7B](https://huggingface.co/Qwen/Qwen3-TTS-12Hz-1.7B-CustomVoice/tree/main)
folder. For Qwen, preserve the `speech_tokenizer/` subfolder and the text
tokenizer files; the main `model.safetensors` alone is insufficient.

Chatterbox and Qwen model weights are not bundled. The owner later installed
and audibly tested Qwen3-TTS CustomVoice on GPU and CPU, including preview
speed changes. Chatterbox has not received the same owner validation. Both
adapters load only local checkpoints.
Chatterbox uses its built-in voice; Qwen offers its nine documented speakers.
Their APIs do not provide KYRIN's speaking-speed setting. Chatterbox remains
fixed at 1.0. Qwen can use the system's optional FFmpeg `atempo` filter to
adjust the generated audio from 0.5 to 1.5 without changing pitch. This is
audio post-processing, not native model speed, and may add processing time or
artifacts. Without FFmpeg, the Qwen speed control stays fixed at 1.0. Their Python runtimes are available
as separate `tts-chatterbox` and `tts-qwen` extras. The upstream packages pin
incompatible Transformers versions. KYRIN therefore checks for separate
installed Python environments and runs each engine in a persistent child
process when its environment exists. Direct loading remains available when
only one compatible engine is installed in KYRIN's own environment. The UI
reports a missing runtime rather than claiming the selected weights can run.
A packaged release still needs to ship or provision these environments.

| Platform | Chatterbox runtime Python | Qwen runtime Python |
| --- | --- | --- |
| Linux | `~/.local/share/kyrin/runtimes/tts/chatterbox/bin/python` | `~/.local/share/kyrin/runtimes/tts/qwen3tts/bin/python` |
| Windows | `%LOCALAPPDATA%/KYRIN/runtimes/tts/chatterbox/Scripts/python.exe` | `%LOCALAPPDATA%/KYRIN/runtimes/tts/qwen3tts/Scripts/python.exe` |
| macOS | `~/Library/Application Support/KYRIN/runtimes/tts/chatterbox/bin/python` | `~/Library/Application Support/KYRIN/runtimes/tts/qwen3tts/bin/python` |

On Linux, `XDG_DATA_HOME` replaces `~/.local/share` when set. Each environment
must have KYRIN and its family's optional runtime installed. The app does not
download weights or install packages. A selected model folder is data only;
the isolated worker accepts only built-in engine names and never executes
scripts from the model folder. CPU/GPU support is checked in the corresponding
runtime. A worker keeps its loaded model warm across responses.

On Linux, the Qwen CPU worker sets a conservative per-process address-space
limit before loading model weights. If the system cannot provide at least 4 GiB
of that budget, the request fails instead of consuming the remaining RAM.
Explicit Qwen GPU selection requires CUDA and checks that the loaded model
reports a CUDA device. The runtime probe checks CUDA availability only; it
does not prove that a full model can fit in VRAM or produce audio. The owner
reported a previous CPU run that exhausted RAM. After the memory guard was
added, the owner reported a successful CPU preview; peak RAM use has not been
measured. A CUDA runtime probe alone is insufficient to verify synthesis.
On the owner's RTX 5060 Ti, FP16 generation caused a CUDA device-side assertion.
The Qwen adapter now uses BF16 on GPUs that report BF16 support and FP32 on
older GPUs. A bounded test with the installed 0.6B model and the exact preview
sentence passed on BF16 through the isolated worker. The owner subsequently
confirmed GPU playback and audible preview-speed changes in the Qt app. A
failed worker is discarded before the next request.

Engine contracts, adapters, and the worker implementation live in
`src/kyrin/tts/`. The `kyrin.app.tts_worker` module remains a compatibility
entry point for separately installed runtimes. Those environments contain
their own installed copy of KYRIN; after changing worker code in a source
checkout, reinstall KYRIN in each optional runtime with `--no-deps` before
testing the new behavior. Model weights do not need to be copied or reinstalled.

KYRIN uses the existing `SpeechSynthesizer` and background `ResponseSpeaker`
contract for each route. Changing a language's voice does not change the
command model or another language's voice. A route matches the exact response
language first and then its primary language (`fa-IR` uses `fa`). If no route
exists, non-English text uses the installed system voice rather than being
mispronounced by an English model. The default system voice remains available.

Desktop installations include the sherpa-onnx runtime. A source checkout
installed without the desktop extra can add the same runtime with:

```bash
python -m pip install '.[tts-sherpa]'
```

The older `tts-kitten` extra remains an alias. On this source checkout, place
each extracted package under `models/local/by-model/tts/<family>/<model>/` and
choose it from **Installed local models**. A packaged app without the catalog
uses its platform application-data model folder instead. **Browse** can select
a compatible absolute folder elsewhere. Do not point the app at a compressed
archive or a single ONNX file.

For Persian, one official compatible package is
[`vits-piper-fa_IR-gyro-medium`](https://k2-fsa.github.io/sherpa/onnx/tts/all/Persian/vits-piper-fa_IR-gyro-medium.html).
It contains an ONNX model, `tokens.txt`, and `espeak-ng-data/`; add language
`fa`, select the package folder, and select speaker ID `0`.
The [upstream TTS catalog](https://k2-fsa.github.io/sherpa/onnx/tts/all/)
lists other languages and voice samples. Kitten archives additionally contain
`voices.bin`; see the
[official Kitten example](https://k2-fsa.github.io/sherpa/onnx/tts/all/English/kitten-nano-en-v0_8-int8.html).
The [official Kokoro v1.1 package](https://k2-fsa.github.io/sherpa/onnx/tts/all/Chinese-English/kokoro-multi-lang-v1_1.html)
has `voices.bin` and lexicon files, which KYRIN uses when loading it.

Explicit GPU selection reports an error when CUDA execution is unavailable;
AUTO selects CUDA when advertised and otherwise uses CPU. A model can still
fail to start on specific hardware; preview errors are reported. No model
weights are bundled with KYRIN. Audible output from each new model must be
validated on the user's actual machine.
The Kokoro, Kitten, and Piper/VITS adapters use sherpa-onnx, which ships its own
ONNX Runtime native library. A CUDA-capable Python `onnxruntime` package alone
does not prove that the installed sherpa-onnx wheel can run on GPU. The main
KYRIN `.venv` remains CPU capable. On the owner's Ubuntu machine, a separate
CUDA 13 sherpa-onnx environment at
`local-data/kyrin/runtimes/tts/sherpa-gpu/` handles GPU requests for these
families. Its NVIDIA CUDA and cuDNN libraries are hard-linked from the existing
Qwen runtime, so the environment has independent paths without duplicating the
large binaries. The launcher uses the standard application-data symlink to find
that environment; other installations may provision it at their own XDG data
root. The official [sherpa-onnx CUDA wheel index](https://k2-fsa.github.io/sherpa/onnx/cuda.html)
provides platform- and Python-specific builds. A CUDA 13 build for Python 3.14
was used here. The active CPU runtime and model weights were not replaced.

An isolated generation test with the installed Kokoro v1.0 package completed on
the owner's RTX 5060 Ti. The worker process appeared in `nvidia-smi` using
about 658 MiB of GPU memory and generated a short 24 kHz waveform. A separate
preview call also completed playback through the default audio output. This
verifies the code path and actual GPU use. The owner later reported that the
Kokoro GPU playback problem was resolved and previously preferred Kokoro's
voice to Qwen's. If the GPU
environment is absent, explicit GPU selection reports an unavailable-runtime
error while CPU remains usable.

**Compatibility boundary:** The app can import complete packages from the
listed families without user coding. Arbitrary model weights, including a raw
Piper archive from another provider or an unsupported family such as Matcha,
still require a compatible package or a new built-in adapter. The model file
alone cannot tell KYRIN how to execute every synthesis architecture. Generic
Kokoro weights from Hugging Face also need conversion to the supported
sherpa-onnx package format; the official extracted sherpa-onnx Kokoro archive
works directly.

## Adapter boundary

`TtsModelAdapter` is the code-side contract for a package format. A trusted
adapter recognizes an extracted folder, validates device and speaker choices,
loads the runtime, and generates audio. `register_tts_adapter()` makes it
available to discovery, playback, and the Voice Output engine list. Existing
Kitten, Kokoro, and Piper/VITS packages use built-in sherpa-onnx adapters.
Model directories are treated as data: KYRIN does not import Python modules or
execute scripts found beside downloaded weights. Additional families need a
compatible adapter shipped with the application; a user selecting an unknown
folder sees an unsupported-format error and does not have to edit project code.

Fish Audio S2 Pro, CosyVoice 3, IndexTTS 2.5, F5-TTS, and Qwen3-TTS Base or
VoiceDesign are not implemented by this change. Some need a reference voice
or a runtime that does not support KYRIN's current Python version. Their
names are not presented as working engines until a complete offline path is
validated.
