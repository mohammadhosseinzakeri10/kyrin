# Third-party notices

KYRIN's own source is MIT licensed. The following notice identifies bundled
third-party material; it does not replace dependency licenses or provide a
complete legal inventory of every optional installation.

## Bundled Silero VAD

- File: `src/kyrin/audio/activity/models/silero_vad.onnx`
- Origin: ONNX opset 16 model from the official `silero-vad==6.2.3` wheel.
- Upstream: https://github.com/snakers4/silero-vad
- Copyright: 2020-present Silero Team.
- License: MIT; full text retained in
  [LICENSE.silero](src/kyrin/audio/activity/models/LICENSE.silero).
- SHA-256:
  `1a153a22f4509e292a94e67d6f9b85e8deb25b4988682b7e174c65279d8788e3`.

This small activity-detection model is the exception to the repository's
policy of excluding separately downloaded model weights.

## Installed dependencies and optional models

Python dependencies are declared in `pyproject.toml`; the check environment
is pinned in `requirements/`. Installed dependency distributions retain their
own license notices. PySide6/Qt in particular is provided under its upstream
license options; KYRIN's MIT license does not relicense it.

Whisper, Vosk, Omnilingual, Ollama, TTS and OCR runtime/model packages are not
bundled in this source release. Compatibility code does not grant a license
to redistribute their runtimes or weights. Check each chosen package's exact
license, model card and redistribution terms before creating a bundle.

## Project artwork

KYRIN/Kailarin artwork and dashboard assets are included as project branding.
The development history records AI-assisted artwork and owner-selected
references. No separate third-party trademark endorsement or exclusive
trademark right is claimed. The source license does not imply endorsement of
modified versions by the maintainer.
