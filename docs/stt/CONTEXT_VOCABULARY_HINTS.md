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

## Paired two-speaker command-safety replay, 2026-10-10

The later 15 verified clips (eight from the original speaker, seven from a
second speaker) were replayed on the same installed Whisper `small` GPU model
with and without the **same fixed four hints for every clip**:
`مرورگر، تلگرام، واتساپ، کایرین`. The comparison CLI now accepts repeated
`--vocabulary-hint` values and records them in its report. Verified spoken
references were used only for scoring, never to choose hints. The paired
reports are Git-ignored under
`datasets/stt/results/language-candidates-small-{hints-,}two-speakers-2026-10-10.json`.
No microphone or desktop action was used for the replay.

| Decoding condition | No hints | Four fixed hints | Interpretation |
| --- | ---: | ---: | --- |
| Automatic, correct positive proposals across both speakers | 6/10 | 4/10 | Two previously correct English requests from speaker 2 were missed. |
| Fixed Persian, correct Persian positive proposals | 1/4 | 2/4 | The gain occurred only on speaker 1; speaker 2 stayed at 0/2. |
| Fixed English, correct English positive proposals | 6/6 | 4/6 | Persian hints degraded two speaker-2 English requests. |
| Automatic, unsafe proposals on the five negated requests | 0/5 | 0/5 | Small safety sample; abstention does not prove negation comprehension. |

The fixed-Persian sum of normalized character edits improved from 23 to 14
over seven Persian clips. In automatic mode, Persian edits improved from 64
to 51, while English edits worsened from 13 to 22. Character error alone
would hide the loss of executable English commands. The second speaker's
Persian `مرورگر را باز کن` remained `مورورگر رو باسکن` with hints and still
produced no intended action. Its negative counterpart remained poorly
recognized and produced no action; this is a safe abstention, not evidence of
correct semantic understanding.

This result argues against applying a Persian hint list globally or treating
language attribution on very short speech as a reliable switch for hints.
The existing opt-in contract remains available for controlled experiments;
KYRIN's live default, model selection, and action policy remain unchanged.
