# Local speech models

This directory keeps development model assets in a predictable place. Model
weights and archives are intentionally excluded from Git because they are large
and may have separate distribution terms.

Current local Persian Vosk model:

```text
models/local/vosk-model-small-fa-0.42/
```

The original ZIP is retained at:

```text
models/archive/vosk-model-small-fa-0.42.zip
```

Source: https://alphacephei.com/vosk/models
Archive SHA-256 recorded on 2026-10-05:
`977cb5faa538f3a835ccfd35f5f6d8284b5c450b89c700b9bd4736b66536ad46`.

From the repository root, check that the model can be loaded with:

```bash
.venv/bin/python scripts/stt/evaluate_offline_stt.py \
  --manifest models/local/vosk-model-small-fa-0.42/test/corpus.csv \
  --model-path models/local/vosk-model-small-fa-0.42 \
  --model-language fa
```

The bundled WAV and `test.txt` provide only a one-file health check. The
generated `corpus.csv` and `baseline.json` under the ignored model directory
are local artifacts, not a representative KYRIN command benchmark.

`VoskEngine` still accepts an explicit model path. This local layout is a
development convention, not a runtime dependency or the future installed-app
storage policy. If these local files are removed, restore the ZIP from the
source above and verify its recorded checksum before extraction.

## Local Whisper comparison models

Two multilingual `whisper.cpp` candidates were downloaded on 2026-10-05 for
offline comparison. The owner subsequently chose `small` for the next English
live-STT development step. These remain local assets, not a packaged default:

| Model | Stable local path | Bytes | SHA-1 from the upstream model list |
| --- | --- | ---: | --- |
| small | `models/local/whisper.cpp/ggml-small.bin` | 487,601,967 | `55356645c2b361a969dfd0ef2c5a50d530afd8d5` |
| large-v3-turbo-q5_0 | `models/local/whisper.cpp/ggml-large-v3-turbo-q5_0.bin` | 574,041,195 | `e050f7970618a659205450ad97eb95a18d69c9ee` |

Both downloaded files matched the listed SHA-1. Their locally recorded SHA-256
values are, respectively:

```text
ggml-small.bin                 1be3a9b2063867b937e64e2ec7483364a79917e157fa98c5d94b5c1fffea987b
ggml-large-v3-turbo-q5_0.bin  394221709cd5ad1f40c46e6031ca61bce88931e6e088c188294c6d5a55ffa7e2
```

Source: <https://huggingface.co/ggerganov/whisper.cpp/tree/main>. See the
[upstream model list](https://github.com/ggml-org/whisper.cpp/blob/master/models/README.md)
for model sizes and published SHA-1 values. The local test runtime is
`whisper.cpp` tag `v1.9.4` (commit `927cfce34f31707e17f2bff35c349632fb9e2c3a`),
built for CPU under ignored `build/tools/whisper.cpp-v1.9.4/build-cpu/`.
Its build tool, CMake, was installed only in this project's ignored `.venv`.
Nothing was added to the product's `pyproject.toml` dependencies.

A separate local CUDA server build now exists under ignored
`build/tools/whisper.cpp-v1.9.4/build-gpu/`. It uses the same model files as
the CPU build; the GPU binary and its extracted CUDA toolkit are development
assets, not a packaged default. See
[`WHISPER_GPU_EXECUTION.md`](../docs/stt/WHISPER_GPU_EXECUTION.md) for device
selection, local results, and release limits.

The Git-ignored model paths above remain discoverable after a reboot. The
ignored build directory can be rebuilt from the pinned upstream tag if it is
removed. Local comparison results are under `datasets/stt/results/`; see
`docs/stt/WHISPER_CPP_COMPARISON_FA.md` for the test conditions and limits.

## English Vosk V1 desktop candidate

The owner chose `vosk-model-en-us-0.22-lgraph` as the intended English default
for the first desktop release, subject to command-quality and ordinary-hardware
validation. It is installed **locally for development and evaluation**, not
bundled in an application package or selected automatically by the runtime.

```text
models/local/vosk-model-en-us-0.22-lgraph/
models/archive/vosk-model-en-us-0.22-lgraph.zip
```

Source: <https://alphacephei.com/vosk/models> (Apache 2.0 according to the
official model list). The downloaded ZIP is 130,557,655 bytes. Its ZIP CRC
passed, and its entries had one expected root with no absolute paths, parent
traversal, or symlinks. Locally recorded SHA-256 on 2026-10-05:

```text
d9838b4aaa82a75c4a17f5aca300eaca129aaab2a7cbf951bafbb500eb9c4334
```

This is a local integrity fingerprint, not a checksum published by Vosk.
The first two-command English result and its limitations are in
`docs/stt/STT_EVALUATION_FA.md`. The local WAV files, manifests, and JSON reports
remain under ignored `datasets/stt/`; they are not shipped with KYRIN.

## Local OCR development runtime

On 2026-10-09, Ubuntu `tesseract-ocr` 5.5.0, `libtesseract5` 5.5.0,
`libleptonica6` 1.86.0, and the English language package were downloaded as
`.deb` files and extracted only under the Git-ignored directory below. No
system package was installed or upgraded. Each downloaded package's SHA-256
matched the value in the local signed Ubuntu package index.

```text
models/local/ocr/tesseract/packages/
models/local/ocr/tesseract/runtime/
models/local/ocr/tesseract/tesseract-local
```

The local wrapper sets the library path only for its own Tesseract process.
The English data path is
`models/local/ocr/tesseract/runtime/usr/share/tesseract-ocr/5/tessdata/`.
This test runtime works on the current Ubuntu machine; it is not a portable
application bundle. A synthetic image containing `Open Telegram` returned both
words and their coordinates. A live portal capture of the user-selected
`KYRIN OCR Test` window also returned both expected words. See
`docs/vision/OCR_ARCHITECTURE.md` for the
on-demand screen capture and OCR boundaries.

The read-only Qt observation page looks for an installed user copy at
`$XDG_DATA_HOME/kyrin/models/ocr/tesseract/` (or
`~/.local/share/kyrin/models/ocr/tesseract/` when XDG_DATA_HOME is unset).
For this development machine, the existing wrapper and extracted runtime were
copied there on 2026-10-09; package archives were not copied. The application
does not depend on the repository's ignored development path and does not
download an OCR engine at startup. OCR model import and selection in the app
remain future work.
