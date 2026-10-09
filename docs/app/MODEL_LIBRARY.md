# Speech model library

The control center has a **Model Library** page with three views: **All models**
(the default), **CPU models**, and **GPU models**. The CPU and GPU views have
separate **Add model** buttons. Selecting a model from All requests Automatic
processing; selecting from CPU or GPU requests that device. **Use selected
model** fills the Speech Recognition form, and **Save changes** applies it.

Models are classified by the STT engine they belong to, not by the import
button or folder name. The current Vosk adapter is CPU-only. The current
`whisper.cpp` adapter can use the same GGML model weights with either its CPU
or CUDA server. Consequently, a Whisper model added through either import
button is stored once and appears in both filtered views. A GPU view entry may
still say that the GPU runtime is unavailable on this computer. An explicit
GPU choice is never silently executed on CPU.

The page asks for an engine and a language code before import. It accepts an
extracted Vosk model directory with its required acoustic and configuration
files, or a `whisper.cpp` `.bin` file with the GGML magic value in its on-disk
little-endian form. Import copies the
model in a background thread to the user's data directory:

```text
$XDG_DATA_HOME/kyrin/models/stt/<model-id>/
~/.local/share/kyrin/models/stt/<model-id>/  (when XDG_DATA_HOME is unset)
```

The import uses a private temporary directory and publishes the model only
after copying and writing its metadata. A repeated import of the same model
and language is deduplicated by content. The original user-selected file is
not moved or deleted. Models outside this library that are already selected
in KYRIN remain visible as the current external model; the existing settings
format and manual path field still work.
An interrupted import leaves no published model; KYRIN removes its own
incomplete staging directories at the next app start.

The lightweight import checks identify the expected file layout. They do not
prove that every downloaded model is valid, nor that the selected machine has
enough memory or a working GPU. The chosen backend makes the final runtime
check when a session starts and reports the device actually opened. This slice
does not download models, install GPU drivers, manage TTS models, or package
the model weights with KYRIN.

The first importer revision compared the Whisper file's first four bytes to
the text `ggml` in display order. Actual `whisper.cpp` model files store the
numeric GGML magic in little-endian order, so both existing local Whisper
models were incorrectly rejected. The check now reads the numeric value;
both local model files passed validation and a temporary full import without
changing the user's model library.
