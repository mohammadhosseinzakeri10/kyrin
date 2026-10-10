# Optional STT vocabulary hints

KYRIN can pass a small tuple of likely spoken names through the backend-neutral
`SpeechToTextOptions.vocabulary_hints` field. Hints are decoder context, not
commands, translations, or authorization. The command interpreter and action
gate still inspect only the final transcript. A backend advertises support
through `SpeechToTextCapabilities.supports_vocabulary_hints`; the current Vosk
adapter rejects a nonempty hint request explicitly. The pinned whisper.cpp
server accepts a per-request `prompt` field, so one session's hints do not
persist into another session. This path is opt-in; the Ubuntu runtime does not
yet generate or send hints automatically.

On 2026-10-10, the local Whisper `small` GPU server transcribed 11 existing,
user-referenced Persian recordings with and without the same four-term hint:
`مرورگر، تلگرام، واتساپ، کایرین`. The sum of normalized character edit
distances was 44 without hints and 18 with hints. Ten files improved and one
(`fa-04`) worsened slightly. Both tested negative commands retained `باز نکن`.
The 11 request times totaled 0.557 s without hints and 0.562 s with hints on
this warmed local server; these times exclude model loading and audio capture.
The detailed local report is Git-ignored at
`datasets/stt/results/context-prompt-2026-10-10.json`. No microphone or
desktop action was used in this experiment. A direct `WhisperEngine` session
test with hints returned the expected positive and negative final transcripts.

This corpus is small, largely from one speaker, and includes repeated instances
of the same browser phrase. It does not establish general accuracy, behavior
on other languages, or an acceptable false-action rate. Automatic hint
generation from installed application names and a live safety check should be
designed and validated before enabling hints by default. Hints must only come
from bounded, relevant vocabulary; recognition remains untrusted input.

A subsequent owner-confirmed live microphone check used the same four terms
through the diagnostic's explicit `--vocabulary-hint` flags. After the start
message, the owner said `مرورگر را باز کن` and then `مرورگر را باز نکن`.
Whisper's final transcripts were `مورورگر، بوسکن.` and
`مورورگر را باز نکن.` respectively. Audio was not saved and no action was
executed. The first command remained ambiguous despite the hint. Earlier
startup fragments in that timed run were not treated as test sentences.
Automatic product activation therefore remains deferred; the current
experiment does not demonstrate reliable live command recognition.
