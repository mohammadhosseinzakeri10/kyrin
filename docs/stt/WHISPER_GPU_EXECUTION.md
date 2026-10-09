# Local Whisper GPU execution

## Scope

KYRIN can open the existing `whisper.cpp` Whisper adapter on CPU or on an
NVIDIA CUDA runtime. The model weights are the same for both devices. Vosk
remains CPU-only. This is a local Ubuntu development capability, not a bundled
GPU installer or a claim of support for every GPU and operating system.

The STT selection is applied when a speech session opens:

- **CPU** starts the configured CPU server with `--no-gpu`.
- **GPU** requires a separately configured CUDA-enabled server. Startup must
  report that its CUDA backend initialized; otherwise the session fails with a
  visible device error. It never silently runs on CPU.
- **AUTO** tries the configured GPU server first, then the CPU server if GPU
  startup fails. The control center reports the device the session actually
  opened, rather than only the saved preference.

The current launcher discovers `whisper-server` and `whisper-server-gpu` on
`PATH`, or uses the absolute paths in `KYRIN_WHISPER_SERVER` and
`KYRIN_WHISPER_GPU_SERVER`. Selecting a model and a language remains separate
from selecting a device. The UI keeps an unavailable GPU choice visible and
explains why it cannot be applied. No per-user settings or system CUDA packages
are changed by the runtime.

## Local development build and validation

On 2026-10-08, a separate CUDA build of pinned `whisper.cpp` v1.9.4 was made
under the ignored `build/tools/whisper.cpp-v1.9.4/build-gpu/` directory. The
CUDA 13.1 compiler and libraries were extracted under ignored
`build/tools/cuda-13.1-root/`; they were not installed system-wide. This build
targets the test machine's NVIDIA RTX 5060 Ti. It is not a portable release
binary. The GPU server and its CUDA libraries must be packaged or installed
appropriately on each target system.

The same local multilingual `ggml-small.bin` model was used for CPU and GPU.
On this machine, three short existing English clips were transcribed twice on
each device. The warm mean request time was about 1.95 seconds on CPU and
0.032 seconds on GPU. The GPU model occupied about 829 MiB of additional
reported video memory during the test. These are measurements of a tiny local
sample, not a general latency, accuracy, or memory guarantee. Text was
semantically equivalent in those clips, with minor casing differences. The
local comparison report is ignored by Git at
`datasets/stt/results/whisper-small-cpu-gpu-2026-10-08.json`.

A real `WhisperEngine` GPU session reported `gpu` and transcribed an existing
clip as `Open Telegram.`. Passing a CPU-only server in the GPU slot produced a
`DeviceUnavailableError`, confirming that a CPU process cannot masquerade as
GPU. A live microphone dry run then reported `ACTUAL_STT_DEVICE gpu`, received
`Open Telegram` as final text, and resolved it to an `OPEN_APP` request. The
dry run did not save microphone audio or execute an application. Two final
segments were heard in that run. The owner subsequently clarified that they
said `Open Telegram` twice, so the two results are expected and do not show a
duplicate-command defect.

The Qt launcher now also discovers both runtime executables beside its own
installed script. In this development environment, Git-ignored links in
`.venv/bin/` point to the separate CPU and GPU builds. Opening the GPU engine
through the same discovery path as the desktop app succeeded. This local setup
does not yet package either runtime for other machines.

The CUDA-backend confirmation uses the startup line emitted by the pinned
`whisper.cpp` runtime. A future runtime version with different logging may
need a revised confirmation check before it can be used safely as the GPU
executable. Tests use fake processes and do not require GPU hardware.

## Remaining release work

- Package and discover the platform-specific runtime and CUDA libraries.
- Validate the GPU build on each supported hardware and operating-system
  target. CPU remains the fallback when AUTO is selected.
- Add model management in the app; current model paths are development assets.
- Measure longer and multilingual live sessions before promising performance
  or recognition quality to users.
