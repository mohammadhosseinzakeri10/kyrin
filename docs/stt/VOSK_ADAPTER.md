# Vosk STT adapter (experimental)

English reference. The Persian original, VOSK_ADAPTER_FA.md (source repository only),
is preserved unchanged. See also [DR-0001](../decisions/DR-0001-english-primary-v1-and-replaceable-stt.md).

- **Status:** implemented and exercised experimentally through
  `LiveSpeechPipeline` with a microphone; not connected as the product's final
  multilingual engine. Checked against `src/kyrin/stt/backends/vosk.py` and
  `pyproject.toml` (`stt-vosk = ["vosk>=0.3.45,<0.4"]`).

## Place in the architecture

```text
AudioData with a defined format
    |
VoskSession.accept_audio
    |
TranscriptUpdate: interim or final segment text
    |
command understanding
```

`VoskEngine` loads exactly one model installed at a local path. `VoskSession`
feeds an ordered audio stream to that model and converts its JSON output into
the shared KYRIN `TranscriptUpdate`, so STT consumers do not depend on Vosk class
names or output. Microphone capture, voice-activity detection and the decision to
execute a command are not inside this adapter.

## Configuration and behavior

- The dependency is declared in the `stt-vosk` extra and is not part of a normal
  KYRIN install; experimental use in a virtual environment needs `.[stt-vosk]`.
- The **already downloaded model** folder and its language are given when
  `VoskEngine` is built. No model is downloaded automatically or shipped with the
  package.
- The default input format is 16 kHz mono 16-bit signed samples. The sample rate
  is configurable for other models; the audio source must convert to that format
  before entering the session.
- CPU only. An explicit GPU request is rejected with `DeviceUnavailableError`;
  `AUTO` resolves to CPU.
- The Vosk model does not auto-detect language. The reported language is the one
  configured with the model path; the adapter cannot verify the label from the
  model files. Requesting a different language is an error.
- Interim text may change for the same `segment_id`; final text closes the
  segment. If Vosk gives an empty final after an interim text, an empty final
  text is sent to retract the earlier guess.
- Ordinary silence does not end the session. `finish()` is called only at the real
  end of the audio stream and does not clear conversation memory. After work ends
  the session is closed first, then the engine.

## Test boundaries and next work

Unit tests use a fake Vosk and cover data format, segment id, interim and final
text, device/language errors and lifecycle. A separate test with a real Persian
model and a public audio file ran without a network connection at recognition
time. A short microphone test through `LiveSpeechPipeline` showed interim and
final text while the user spoke; one short Persian sentence repeated twice gave
identical final output close to the reference. This limited sample does **not**
confirm general command accuracy, language switching, GPU, long-run stability or
other operating systems.

Next steps: measure accuracy and latency with real speech, check stability on
other devices and systems, and define a separate safety policy before executing
any command from interim text. Sources: [Vosk documentation](https://alphacephei.com/vosk/)
and [official model list](https://alphacephei.com/vosk/models).
