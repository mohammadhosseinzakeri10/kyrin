# Omnilingual ASR local execution

English reference. The Persian original,
OMNILINGUAL_ASR_FA.md (source repository only), is preserved unchanged.

- **Status:** experimental local engine. Timeouts, the 30 s turn limit and model
  names checked in `src/kyrin/stt/backends/omnilingual.py` and
  `omnilingual_worker.py`. Quality on real speech is not established; the one
  local check below only confirms the wiring.

Six version-2 models are kept under `models/local/by-model/stt/omnilingual-asr/`
(a Git-ignored local path). Each model has its own folder containing the `.pt`
weight and `omniASR_tokenizer_written_v2.model`. KYRIN finds these folders in the
speech-model library and does not copy the weights again to add them to the app.

## Execution architecture

The main application runs on Python 3.14, but the official `omnilingual-asr`
package requires an older Python. The KYRIN adapter therefore starts a separate
Python 3.12 process from `local-data/kyrin/runtimes/stt/omnilingual-asr/`. That
process opens the same downloaded weights and tokenizer with local `fairseq2`
asset cards and converts each turn's speech to text over JSON messages. It is
closed when the session stops.

`CTC` and `LLM` share one Engine option named `Omnilingual ASR`; the six model
names appear separately in the model library. The language choices `en`, `fa`,
`de` and `fr` map to the official model identifiers; for other languages a full
id such as `eng_Latn` can be entered. `auto` removes language conditioning, which
can reduce quality on `LLM` models; `CTC` models ignore language conditioning
according to the producer's documentation.

Each turn is processed after speech ends; interim text is not produced, to avoid
repeated runs of a large model. A turn is at most 30 seconds of 16 kHz mono INT16
audio. An explicit GPU request runs only if CUDA exists; automatic selection picks
CUDA when available.

To avoid unbounded waiting, the child's readiness reply has 300 s
(`STARTUP_TIMEOUT_S`) and each recognition request 120 s
(`INFERENCE_TIMEOUT_S`). If the process does not answer, KYRIN stops its own
process and shows the error. Stopping listening also interrupts a running request
so releasing the model does not wait for the computation to finish. Admission and
residency follow [Model resource policy](../app/MODEL_RESOURCE_POLICY.md).

## Rebuilding the environment on the current development machine

All tools and temporary caches stay on the project drive (see
local data storage (`LOCAL_DATA_STORAGE.md`, source repository only)). From the repository root:

```bash
export UV_PYTHON_INSTALL_DIR="$PWD/local-data/kyrin/tools/python"
export UV_CACHE_DIR="$PWD/local-data/cache/uv"
export PIP_CACHE_DIR="$PWD/local-data/cache/pip"

python3.14 -m venv local-data/kyrin/tools/uv
local-data/kyrin/tools/uv/bin/python -m pip install uv==0.13.1
local-data/kyrin/tools/uv/bin/uv python install 3.12.15
local-data/kyrin/tools/uv/bin/uv venv --python 3.12 \
  local-data/kyrin/runtimes/stt/omnilingual-asr
local-data/kyrin/tools/uv/bin/uv pip install \
  --python local-data/kyrin/runtimes/stt/omnilingual-asr/bin/python \
  'omnilingual-asr==0.2.0' 'torch==2.8.0' 'torchaudio==2.8.0' \
  'numpy==1.26.4' 'pyarrow==20.0.0'
local-data/kyrin/tools/uv/bin/uv pip check \
  --python local-data/kyrin/runtimes/stt/omnilingual-asr/bin/python
```

The new dependency is installed only in the separate environment;
`pyproject.toml` of the main app is unchanged. Restart the desktop app after
installing so the new Engine option appears.

## Evaluation without a microphone

The shared evaluation tool can run a CSV with columns `id,path,language,reference`
against this engine:

```bash
PYTHONPATH=src .venv/bin/python scripts/stt/evaluate_offline_stt.py \
  --backend omnilingual \
  --model-path models/local/by-model/stt/omnilingual-asr/omniASR_CTC_300M_v2 \
  --model-language en --device cpu --unpaced \
  --manifest /path/to/english-manifest.csv
```

In a local check a 3.2-second file was processed with `CTC 300M` on CPU and the
model returned text; accuracy on that sample was low, so working wiring alone is
not a quality confirmation. Loading and running the other five models and the GPU
remain to be measured separately. A later comparison on the shared Persian and
English set ran several models on CPU and `LLM 300M` on GPU; the exact models run
or excluded for memory reasons, with method and results, are in a historical
Persian measurement report (local model comparison (`LOCAL_MODEL_COMPARISON_FA.md`, source repository only)).
The paragraph above describes only the initial wiring check.
