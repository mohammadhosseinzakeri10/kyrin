# KYRIN — Project Context

> Engineering handoff for the current repository state.
> Updated: 2026-10-20.
>
> This document records confirmed implementation state, engineering decisions,
> current direction, experiments, and open questions. The repository remains
> the source of truth when this document and the code disagree.

> **Visible-chat speech and OCR grounding (2026-10-20):** The owner reported
> `openvisibly chat my mother` and `open visibly chat my mother` being rejected
> as `repeat_command`. The visible-chat grammar now accepts these two bounded
> STT variants. Existing Unicode case-folding already ignores letter case.
> For this visible-list action, OCR can also match an exact title when word
> spaces were lost in speech or OCR; all exact and compact rows are retained,
> so duplicate titles still require numbered selection. Chat-row anchors,
> stable rereads, identity checks and click verification remain required.
> This does not infer different names or enable general screen-wide clicking.
> Focused deterministic tests pass; later live validation is recorded below.

> **Visible-chat live failure and next foundation (2026-10-20):** The owner
> repeated `open visibly chat my mother` twice. Both transcripts became
> `open_chat: my mother`, then failed as `visible_chat_uncertain` in about
> 3.3 seconds after final speech. The command name and letter case were
> already understood; the failure is in OCR row classification or stability,
> not proven to be a spelling error. English chat forms now have one bounded
> command catalog, and literal OCR label matching is a shared function with
> opt-in joined-word handling. The visible-chat failure now carries a
> content-free classification status in `Action result`; the spoken message
> remains simple. The shared OCR matcher is also used for Telegram Settings
> navigation under its existing Settings-heading and uniqueness checks. No
> screen content is sent to the command model, and no
> broader app-control action is enabled by this foundation. The owner chose
> to defer another live visible-list test while this base is built.

> **Visible-list OCR diagnostic (2026-10-20):** The next owner run still
> returned `visible_chat_uncertain:unclassified_matches_3_size_1853x1048_`
> `at_89-251-92_350-275-74_69-747-96`. Thus OCR did see the spoken title
> in the left pane; one occurrence at x=350,y=275 is plausibly preview text,
> while x=89,y=251 and x=69,y=747 are plausible chat titles. The image alone
> does not prove which row anchor failed. The visible-list classifier now
> reports content-free reasons for missing title, active search field, low
> title confidence, missing same-row time label, missing preview line, and
> unstable rows. It keeps rejecting an uncertain row. Subsequent restarted
> live runs identified the failing anchors, as recorded below.

> **Visible-list false search detection (2026-10-20):** A restarted owner run
> reported `visible_chat_uncertain:search_field_active_matches_3_size_`
> `1853x1048_at_89-251-92_350-275-74_69-747-96`. No target-name OCR
> occurrence was in the search bar; the earlier rule had treated *any*
> confident upper-left text other than exact `Search` as an active query.
> It now requires the spoken target in the top search area or a recognized
> Search Results heading before refusing the visible-list route. Unrelated
> UI text near the top no longer blocks row classification. A synthetic test
> covers unrelated top text, a real query, and a results heading.

> **Visible-list duplicate selection validated (2026-10-20):** The next two
> live diagnostics showed three title-text matches but only two actual rows.
> The middle match at x=350 was preview text, so the title-column limit was
> narrowed. One of the two actual rows lacked an OCR time label; a bounded
> fallback now accepts a high-confidence title with its own preview only when
> another matching row has a same-line time anchor and the candidate is not
> positioned like the previous row's preview. Synthetic tests cover both the
> accepted row and rejected preview. After restarting, the owner reported
> that selecting the second visible `My Mother` chat now works. This is live
> user confirmation of the duplicate selection path, not proof of every
> Telegram layout or speech variant.

> **Low visible-list rows (2026-10-20):** The owner supplied a Telegram
> screenshot after `Open visible chat H` and also reported a failed
> `Spotify Downloader` visible-list command. Both rows were near the bottom
> of the window. Replaying the screenshot with the owner's selected Tesseract
> Best engine showed that its usual sparse-text pass missed `H` and read
> `Spotify` below the confidence gate. A magnified left-column pass with
> block segmentation identified both titles; `Spotify Downloader` also had
> a valid time and preview anchor, while `H` was clipped against the bottom
> and lacked trustworthy row anchors. The verifier retains the existing
> full-window pass and uses the focused pass only after uncertainty. A
> recognized clipped bottom row triggers at most one identity-bound scroll
> and a fresh stable reread before any click. Focused tests pass and the
> supplied screenshot reproduces the expected classifier statuses; live
> owner retest of these two commands remains pending.

> **Unreadable visible-chat previews (2026-10-20):** The owner confirmed that
> `Spotify Downloader` opens with the focused OCR pass, then showed a `matin`
> row with a stylized Latin title and Persian preview. The diagnostic found
> one title at x=66,y=872 with 94% confidence and a strong aligned date, but
> reported `preview_1`: the selected English OCR did not read the Persian
> preview. The classifier now permits a row without a readable preview only
> when the exact title and same-row right-column date are both high-confidence
> and no prior row date aligns with that same column above it. This keeps the
> two-read stability and post-click header checks. Focused synthetic tests pass;
> the owner has not yet retested `matin` with this correction.

> **Owner status corrections (2026-10-20):** The owner confirmed that the
> current dashboard behaves as intended; its particle renderer and preferences
> were committed locally as `953e4ed`, with no GitHub action. The owner also
> reported successful real Power Off and Restart voice flows, beyond the earlier
> inert preview. The exact diagnostic logs and behavior of Logout and Suspend
> were not supplied, so these reports should not be generalized to all power
> operations. Misrecognition of unusual chat names with the selected
> English-only Whisper model is considered a model/language limitation, not an
> outstanding parser defect. Users choose and install their OCR engine; KYRIN
> is not responsible for selecting the universally best model. Safe action
> targeting still depends on the selected engine returning adequate text,
> geometry, and confidence for the requested action.

> **Experimental document OCR device selection (2026-10-19):** The owner
> requested CPU/GPU/Auto for the separate text-only document models. Screen
> Access now saves the document model and device choice independently of the
> action OCR engine. The worker resolves Auto against CUDA availability,
> rejects explicit GPU when unavailable, moves model inputs to the selected
> device, and reports the actual device with its text. CPU alone retains its
> process address-space limit; both paths retain the four-minute timeout.
> Both isolated runtimes now have PyTorch 2.10 CUDA 13.0. On the owner's RTX
> 5060 Ti, a synthetic local image returned `device=gpu` with dots.mocr in
> 4.5 seconds, Surya in 16.1 seconds, and GLM-OCR in 4.2 seconds. Auto also
> selected GPU in a real dots.mocr read. Explicit CPU initially failed with
> `MemoryError` under the 18 GB address-space limit when CUDA remained visible;
> hiding CUDA in CPU-only workers fixed it, and a GLM CPU read completed in
> 9.9 seconds. These observations do not establish model accuracy or latency
> on arbitrary real desktop windows.

> **dots.mocr live GPU failure and correction (2026-10-20):** The owner tested
> all three document models in Screen Access. Surya first returned no text
> and then succeeded, GLM returned text, and dots.mocr failed with a generic
> screen-read error. Replaying the supplied 1222×820 control-center screenshot
> exposed a CUDA out-of-memory error in the dots vision tower's eager attention
> softmax. Switching GPU inference to the checkpoint's built-in SDPA attention
> read that image successfully at original resolution. A larger 1853×1048
> synthetic desktop image still exhausted GPU memory, so dots reads large
> images in overlapping horizontal bands at their original pixel scale; the
> same large image and the owner's screenshot then both returned text on GPU.
> Remaining GPU memory errors have a distinct UI message. Results are text
> only and do not change action OCR or desktop clicking. Live owner retest
> after the correction remains pending. The first screenshot in which Surya
> had reported no text returned 622 characters when replayed locally on GPU;
> that earlier empty output was not reproduced and should not be attributed to
> the dots CUDA memory error.

> **OCR choice in Screen Access (2026-10-19):** Installed Tesseract, Fast,
> Best, PaddleOCR v5 Persian, v6 Small, v6 Medium, and PaddleOCR-VL 1.6 are
> selectable when their local runtimes and weights are present. The three
> detector/recognizer pairs return confidence and coordinates; PaddleOCR-VL
> returns coordinates but no confidence, so confidence-gated actions stop.
> All four Paddle models ran offline on synthetic images. Surya, GLM-OCR, and
> dots.mocr now have separate text-only experimental backends; they do not
> participate in screen action targeting.
> The owner live-tested Surya on the KYRIN control window: a full-window read
> sometimes returned no text, while the standard Tesseract screen reader found
> text. The supplied screenshot reproduced this locally; a right-panel crop
> recovered text. Surya now retries that crop only after an empty first read.
> Each Screen Access text panel has its own Clear button. GLM-OCR and dots.mocr
> still need live desktop validation. The owner next observed dots.mocr still
> showing Reading on a KYRIN window. A direct local read of the supplied
> screenshot finished in 80.1 seconds and returned 682 characters using the
> installed CPU-only runtime. Screen Access now shows elapsed time while a
> document model runs and distinguishes its four-minute timeout from other
> errors. Actual live completion after the change remains to be confirmed.

> **Telegram Settings row correction (2026-10-18):** The owner confirmed
> `Go to Settings` opens the panel, then `Go to My Account` tried to reopen it
> and failed as `telegram_setting_not_found` after roughly 32 seconds. The
> owner's Settings screenshot shows `My Account` as its first row. Local OCR
> with the installed Tesseract runtime found the Settings title and that row;
> a model replacement is not justified by this sample. Settings OCR now reads
> the centered pane with coordinate translation. The executor does not reopen
> Settings when its title is visible and does not scroll for the fixed first
> row. The screenshot's actual top-level navigation rows are in the catalog;
> the absent `Default`, `Interface`, and `Skills` entries were removed.
> `Default interface scale` is a control and is not clicked by a navigation
> command. Explicit `Open settings <label>` and
> `Go to <label> in Telegram settings` can navigate a previously unlisted
> visible row only after a unique, stable OCR match beneath the Settings title.
> After a `Go to Settings` command, a 90-second dialogue context also accepts
> the short `Go to <label>` form for an unlisted row while Telegram remains
> foreground. The executor verifies that Settings is *currently* open before
> OCR matching and never reopens it for this contextual form. A different app
> command, Back/Cancel, or paused dialogue clears the context. This is a
> parsing hint, not a cached claim about the current screen.
> Focused deterministic tests pass; live owner retest remains pending.

> **Telegram nested Settings navigation (2026-10-18):** The owner's live
> transcript showed `Go to Chat Setting` heard as `go to chat seating` and
> routed to an OCR search for that literal phrase; after Cancel, the same
> phrase fell into chat search. The exact observed STT variant now maps to
> `chat_settings` regardless of recent Settings context. The owner supplied
> an Advanced screenshot and confirmed the Back command returns one level.
> A narrow OCR header read now distinguishes the root Settings page from a
> nested page. For a known top-level section requested from a nested page,
> the executor sends at most three Back inputs and verifies the root title
> before finding or clicking the destination. If verification fails it stops.
> The installed OCR runtime recognized the root and Advanced headings in the
> two supplied screenshots. Focused tests pass; the revised voice flow still
> needs live owner validation. Nested-page controls and cross-app navigation
> remain proposals, not implemented features.

> **Telegram Settings work in progress (2026-10-18):** Bounded English voice
> commands now map the owner's named sections to OCR-verified settings rows.
> The executor checks the Telegram window identity, stable row position and
> pointer geometry before clicking, and can scan a few pages. `Go to Back`
> and `Cancel` dispatch Escape with an unverified-result label. Deterministic
> tests cover parsing and safe click boundaries; this Settings path has not
> yet been owner-tested live. Control state changes, visual-only switches,
> nested pages and sensitive-change confirmation remain open. The owner chose
> a separate voice confirmation only for sensitive changes. Version and
> redacted UI screenshots have been requested to ground the controls.

> **Telegram explicit search (2026-10-18):** The user requested a separate
> way to enter search and speak a person's name. `Go to search` focuses the
> global box, while `Search for <name>` types a bounded name without pressing
> Enter or selecting a result. It uses the existing saved Telegram control
> grant and fresh focus checks. OCR of the query in the left input field is
> required for a confirmed result. Unit tests pass; live owner validation is
> pending. Named-chat opening remains a separate command.

> **Telegram Settings STT alias (2026-10-18):** The owner reported
> `Go to setting` transcribed as `go to seating`, which fell into generic
> application-name confirmation. Exact `seating` and `my seating` forms now
> map to Telegram Settings when Telegram is the observed foreground app,
> including when a stale app clarification exists. Focused deterministic
> tests pass; an owner microphone retest is pending.

> **Telegram Settings menu and latency (2026-10-18):** The owner then got
> `telegram_view: settings` for `go to seating`, but only the hamburger menu
> opened; action failed as `telegram_menu_uncertain` after roughly 14 seconds
> from final text. On the supplied screenshot, the installed OCR engine found
> no menu words in the whole window, but a menu crop found `Settings` at
> `(61, 432)` with 0.77 confidence and the other expected labels. Menu OCR now
> reads the left 30% and top 65% of the window, retaining full dimensions for
> guarded clicking. Pre-open scanning exits after one miss and post-open
> scanning is bounded to three reads. Right-pane title verification replaces
> the former left-pane check. Deterministic tests pass; live confirmation is open.

> **Gently command live retest (2026-10-16):** After the correction, the owner
> observed `Gently open Calculator` -> `open_app: calculator`, confirmed in
> 6431 ms onset-to-result (1602 ms final-to-result), and
> `Gently close calculator` -> `close_app_window: calculator`, confirmed in
> 2426 ms onset-to-result (214 ms final-to-result). Neither asked for extra
> app confirmation. This validates the `Gently` open and close paths live;
> replacing an already pending app question with a fresh command has only
> deterministic test coverage so far. See
> `docs/commands/LIVE_COMMAND_BASELINE_FA.md`.

> **Polite command live retest (2026-10-16):** After the correction, the owner
> observed `Kindly open calculator` -> `open_app: calculator`, confirmed in
> 6485 ms onset-to-result (1635 ms final-to-result), followed by
> `Kindly close calculator` -> `close_app_window: calculator`, confirmed in
> 2545 ms onset-to-result (209 ms final-to-result). This validates the
> `Kindly` close change on the live desktop. `Gently open` was subsequently
> retested live; the pending app-question replacement has not been. See
> `docs/commands/LIVE_COMMAND_BASELINE_FA.md`.

> **Fresh command after app confirmation (2026-10-15):** The owner observed
> `Gently open calculator` -> `confirm_app`, then `Kindly open calculator` ->
> no action. The operation evidence profile did not accept `Gently` as a
> prefix; while an app-name clarification was pending, a new model-assisted
> explicit command was not interpreted. The evidence profile now accepts
> `Gently`, and a new explicit operation replaces a pending app-name question
> while still requiring model proposal, source-operation verification, and
> target grounding. Deterministic tests pass; updated desktop microphone
> behavior is pending owner validation. See
> `docs/commands/LIVE_COMMAND_BASELINE_FA.md`.

> **Polite close live correction (2026-10-15):** A continuous
> `Kindly open calculator` succeeded in 4298 ms onset-to-result (1645 ms
> final-to-result). The owner then got no action for `Gently close calculator`
> and `repeat_command` twice for `Kindly close calculator`. Direct window
> grammar recognized `Please` but not these two prefixes, leaving them to
> the selected model; its internal result is not logged, so the precise model
> failure is unknown. The grammar now accepts `Kindly` and `Gently` before
> exact-name window commands. Permission checks remain downstream. Focused
> tests pass; owner live retest on the updated process is pending. See
> `docs/commands/LIVE_COMMAND_BASELINE_FA.md`.

> **Live latency follow-up split at `Kindly` (2026-10-15):** Three attempted
> repeats finalized `Kindly` or `Kintily.` as a standalone no-action segment,
> followed by `Open Calculator` twice and `Close Calculator` once. All three
> actions were confirmed; their own onset-to-result times were 1990, 702, and
> 731 ms. These times omit the first segment and do not retest the 7206 ms
> model-assisted utterance. The text log alone cannot attribute the split to
> speaker pause, speech endpoint detection, or STT behavior. No segmentation
> threshold or fragment-joining change is justified yet. The owner recalls a
> possible very short pause after `Kindly`, but its duration was not measured. See
> `docs/commands/LIVE_COMMAND_BASELINE_FA.md`.

> **Live model-assisted command pilot (2026-10-15):** The owner said
> `Kindly open Calculator`, which direct rules treat as `NotACommand` in the
> saved catalog. The active model-assisted path yielded `open_app: calculator`
> and `confirmed`. Speech onset to result was 7206 ms; final text to result
> was 1692 ms. A single sample cannot identify the source of the 5514 ms
> pre-final delay. Three negated attempts, two transcribed with `Currently`
> instead of `Kindly`, requested no action. See
> `docs/commands/LIVE_COMMAND_BASELINE_FA.md`. No behavior fix is indicated
> by these results; latency needs a warmed repeat before attribution.

> **Live command baseline, round one (2026-10-15):** The owner ran the eight
> current-machine cases in `docs/commands/LIVE_COMMAND_BASELINE_FA.md`, outside
> the chat flow. Open, minimize, restore, and close Calculator all reached the
> expected intent with `confirmed` action feedback. Their mean speech-onset
> to result was 2316 ms (four observations); mean final-text to result was
> 226 ms. Three negated-open utterances and one ordinary sentence produced no
> action, including one STT variant `Do not open, calculate her.`. `Open Terminal`
> requested an operation and `Cancel` ended it without action. These cases
> primarily exercise direct rules; model-assisted understanding needs a
> separate live case. No code correction was indicated by this first round.

> **Voice output control and power prompt interruption (2026-10-15):** The
> owner requested a global TTS switch. The Voice Output page now saves
> `tts_enabled` in settings schema 11; old settings default to enabled. The
> shared `ResponseSpeaker` suppresses voice while disabled and interrupts an
> active announcement when turned off. Visual prompts, STT, and command actions
> remain independent. Power-stage voice now replaces queued speech and stops
> active local-model playback when the stage changes. Focused deterministic
> tests pass; an owner listening retest of the new stage timing and switch is
> pending.

> **Shutdown and packaging follow-up (2026-10-15):** An in-process CPU TTS
> generation can hold the model lock. Desktop shutdown now waits at most two
> seconds for that lock and at most one further second for a still-busy speech
> thread, leaving its model intact until process exit. Normal isolated-worker
> shutdown remains explicit. A blocked-generation regression test passes; a
> real stalled CPU model has not been induced. Development model discovery now
> requires a verified source-checkout layout, while an installed wheel uses
> the application model library fallback. This path check is not a complete
> portable package or installed-environment validation.

> **Telegram Saved Messages live correction (2026-10-15):** The owner confirmed
> the Terminal-only picker worked, then heard `Open chat, save the messages`.
> KYRIN parsed `open_chat: save the messages`, but the Saved Messages shortcut
> accepted only `saved messages` and `saved massages`; generic search typed the
> phrase and safely stopped at `chat_search_uncertain`. The exact observed
> phrase is now a shortcut alias. Permission, focus, and OCR header checks
> remain required. In the restarted desktop microphone retest, the owner
> reported that Saved Messages opened. The diagnostic showed
> `open_chat: save the messages` with `Action result: confirmed` (1,500 ms
> from final transcript to result). The Terminal-only picker was also
> owner-validated.

> **TTS catalog consolidation (2026-10-13):** The owner clarified that all TTS
> families should share the project's `models/local/by-model/tts/` root, with
> one folder per family and model. Kokoro v1.0 was moved there, its archive to
> `models/archive/tts/kokoro/`, and the existing Qwen and Chatterbox catalog
> copies were verified byte-for-byte against their duplicate installed copies.
> The Voice Output page now discovers the catalog in this source checkout and
> falls back to the platform application-data root when the catalog is absent.
> The local active Qwen selection points to its catalog model; the duplicate
> installed TTS folders were removed. The owner's GPU device selection was
> preserved. Focused UI tests and model-package inspection passed; this sandbox
> could not probe CUDA availability for an audible post-migration test.

> **Kokoro voice picker (2026-10-13):** The Voice Output page now shows the
> documented speaker names for the English voices in the known sherpa-onnx
> Kokoro v1.0 and v1.1 packages. It saves the corresponding numeric speaker ID
> for the runtime. Unknown package names keep the numeric control because their
> voice mapping is unverified. Focused Qt and TTS tests pass; the owner has not
> yet checked the names or heard each selection in the desktop app.

> **Kokoro GPU preview diagnosis (2026-10-13):** The managed desktop launcher
> uses the project `.venv`. Its Python ONNX Runtime exposes only
> `CPUExecutionProvider`, and the installed sherpa-onnx native package has no
> CUDA provider library. Kokoro GPU preview could not run with that runtime,
> while CPU could still be selected. The preview previously hid the
> specific missing-GPU validation error behind `Local TTS playback failed`;
> it now reports the specific reason.

> **Kokoro GPU runtime (2026-10-13):** A separate Python 3.14 sherpa-onnx
> CUDA 13 environment now lives at `local-data/kyrin/runtimes/tts/sherpa-gpu/`.
> It uses hard-linked CUDA/cuDNN libraries from the existing Qwen runtime,
> leaving the main `.venv` and TTS model files unchanged. KYRIN now routes
> explicit sherpa-family GPU selections through an isolated worker and keeps
> CPU requests in the main runtime. A short Kokoro generation passed through
> this application path; its worker PID appeared in `nvidia-smi` using about
> 658 MiB of GPU memory. A separate preview call completed playback through
> the default audio output. This was the status before the owner's later
> report that the Kokoro GPU playback problem was resolved.

> **TTS recovery (2026-10-13):** The owner observed Qwen3-TTS apparently not
> using GPU, a CPU attempt exhausting host RAM, and an unavailable speed
> control. Explicit Qwen GPU selection now rejects missing CUDA and verifies
> the loaded model's reported device instead of silently accepting CPU. The
> isolated Linux Qwen CPU worker applies a conservative address-space limit
> before loading weights. Qwen speed 0.5–1.5 is now available through optional
> FFmpeg audio tempo processing; it is not a native model generation parameter.
> Focused deterministic TTS tests and a CUDA runtime probe passed. A full
> model generation on GPU and a CPU load have deliberately not been performed
> since the owner reported a host freeze; real audio quality and peak memory
> remain open for a controlled user-session test.

> **Qwen GPU diagnosis (2026-10-13):** The owner provided a screenshot of a
> CUDA device-side assertion during the saved-voice preview. The installed
> Qwen adapter selected FP16 for GPU. The owner's RTX 5060 Ti supports BF16.
> A bounded GPU run with the installed 0.6B checkpoint generated the exact
> preview sentence using BF16, and a second run passed through the installed
> isolated worker's `load` and `generate` protocol without saving or playing
> audio. The adapter now selects BF16 on capable CUDA devices and FP32 on
> older devices, avoiding FP16. A failed generation evicts its worker so a
> CUDA error cannot poison later previews. The owner later confirmed live
> Qwen GPU playback and a working CPU preview.

> **TTS preview speed correction (2026-10-13):** The owner confirmed GPU voice
> playback but reported that changing the visible speed did not change the
> preview. The preview button used the saved synthesizer configuration, and
> the local saved Qwen speed was still 1.0. The page now sends its current
> draft voice/device/speed to the response speaker for one preview without
> saving or reconfiguring the active voice. A bounded real Qwen GPU sample
> measured 5.74 s at speed 0.5, 2.88 s at 1.0, and 1.94 s at 1.5 using the
> same waveform. Automated UI/queue tests pass; the owner later confirmed
> audible speed differences through the application.

> **TTS owner validation and controls (2026-10-13):** The owner confirmed that
> Qwen GPU output and speaking-speed previews now work, and reported that a
> CPU preview also completed without problems. Peak CPU memory has not been
> measured. The owner noticed that the Refresh and Browse button labels on
> Voice Output were invisible. Those compact utility buttons now receive
> their labels at construction, fixed minimum widths, and explicit high
> contrast styling. Offscreen theme rendering showed both labels, and focused
> tests confirmed Refresh discovers a newly added model and Browse selects a
> model folder. The appearance in the restarted desktop application still
> needs the owner's visual check.

> **Local layout update (2026-10-12):** The four Ollama development models now
> live in separate complete stores under
> `models/local/by-model/command-understanding/ollama/`. The command-model
> selector discovers the parent directory and starts only the selected store.
> The local setting for `qwen3.5:4b` points there. The old combined Ollama
> store and duplicate development Vosk/Whisper folders were removed after
> comparison and startup checks. Installed STT folders now use readable names
> with unique suffixes; the selected model path was updated. Selected TTS and
> OCR app data
> remain under `local-data/kyrin/models/`; see
> `docs/development/PROJECT_LAYOUT.md`. Older notes below describe the state
> at the time they were written and may mention retired paths.

## Status Vocabulary

- **CONFIRMED** — implemented, tested, directly observed, or explicitly decided.
- **CURRENT DIRECTION** — the next agreed engineering direction; implementation
  may not have started yet.
- **TEMPORARY / EXPERIMENTAL** — local hardware or development observations that
  must not be treated as portable product behavior.
- **PROPOSAL / IDEA** — discussed but not committed.
- **OPEN** — unresolved and requiring a future engineering decision.

---

## 1. Project Overview

- **Name:** KYRIN.
- **Package name:** `kyrin`.
- **Project version:** `0.1.0`.
- **Product status:** early development.
- **Current major engineering area:** GNOME screen-access boundary for V1
  desktop vision, alongside the existing voice/audio pipeline.
- **Current completed foundation:** audio capture, core PCM data model,
  streaming mono INT16 sample-rate conversion, configurable audio framing,
  an offline VAD adapter, continuous speech-activity monitoring, replaceable
  STT contracts, and a bounded live VAD/STT pipeline.
- **Current next direction:** measure and improve the speech-to-command path
  before more chat automation. The owner reported that non-English speech,
  varying spellings of KYRIN, and `Open chat Save Message` were not reliably
  understood. The application now displays an in-memory decision trace,
  accepts configurable wake-name spellings, and supports `auto` language
  detection with the installed multilingual Whisper adapter. These are
  diagnostics and bounded improvements, not general multilingual command
  understanding or an installed translation engine. The permission-gated
  `Saved Messages` action still needs a live product-path test. Runtime
  packaging and broader model management remain future work.
  Settings, lifecycle control, Ubuntu session composition, a Qt control
  window, a single-instance guard, and user-scoped XDG registration exist.
  English development uses the locally
  installed Whisper `small` CPU/GPU adapter while Vosk remains replaceable; this
  is not a packaged default or a general accuracy claim. The terminal
  diagnostic stays dry-run by default. Explicitly allowlisted app launch and
  registered app-name matching have passed focused tests, and the owner
  validated a real microphone-to-Telegram launch. Model packaging,
  multilingual setup, a complete product UI, broader stability validation, and
  Windows/macOS/mobile adapters remain future work.
- **Conversational response boundary (2026-10-11):** The selected local command
  model can now return a short response to direct speech such as a greeting.
  This becomes a response event with no action intent. A model response to
  recognizable command text is rejected; executable model proposals still
  require independent source, target, and permission checks. The existing
  pending app-name confirmation accepts exact German `Ja` and `Nein` as well
  as its English and Persian words. These are local code and deterministic
  test results; a live microphone and spoken-response check remains open.
- **Mixed-script and multilingual opening (2026-10-11):** Owner diagnostics
  showed `Open Telegram` transcribed as Arabic, Urdu, Swedish, and Persian,
  including `اوپن تلگرام` and `اپن ٹیلیگرام`. Reviewed spellings of the open
  verb now use exact registered app-name matching, with ambiguous `Opend`
  asking for confirmation. For other languages, a model-proposed single app
  opening with a literal, exact, permitted target requires a second short
  confirmation; model-proposed actions in uncovered languages do not execute
  directly. A local model can classify that reply in its spoken language.
  Deterministic tests pass; actual model quality and microphone behavior still
  require a user-session trial. Other operations and localized confirmation
  prompts remain open work.
- **Registered app names and STT hints (2026-10-11):** The owner reported
  `Please open Visual Studio Code` transcribed as Turkish, Arabic, or only
  `Please open.` The installed Snap desktop entry is named `Visual Studio
  Code` and is already in the owner's allowed-app settings. The app-name
  resolver now derives short forms such as `VS Code` and `VSCode` from
  registered multiword names, preserving ambiguity when names collide.
  STT backends that advertise vocabulary-hint support receive up to 16
  bounded names/short forms from permitted installed apps; the Whisper
  adapter already passes such hints to local inference. Tests cover the
  mapping and hint wiring. The reported real audio has not been replayed,
  and lost or badly transcribed words cannot safely be reconstructed from
  a model guess.
- **Generic browser requests (2026-10-11):** `Open browser` was correctly
  transcribed but could not resolve when only specific browsers such as Chrome
  and Firefox were permitted. The XDG catalog now reads the registered
  `WebBrowser` category. The Ubuntu session offers only installed, explicitly
  allowed browsers as clarification candidates; it does not launch one until
  the user names it. With one candidate it asks for confirmation. Exact app
  names still follow the existing direct path. Focused unit and composition
  tests pass; live microphone validation remains open.
- **Mascot alignment (2026-10-11):** The owner observed that long status
  captions left the mascot at the left edge. The GNOME extension now gives
  the mascot a row matching the caption width and positions it at that row's
  center after each caption resize. The revised extension file was installed
  in the current user's GNOME extension directory. A fresh Shell session and
  visual confirmation of short and long captions remain pending.
- **Current speech and window-focus correction (2026-10-09):** The owner supplied
  diagnostic traces showing standalone wake-name spellings `Kairin`, `Kyreen`,
  `Kyrie`, and `Kairi`. The standalone name is now acknowledged with text-only
  readiness and cannot create an action; the observed variants are exact wake
  aliases. An unsupported phrase after the name still asks for repetition.
  The owner also requested that `Open Telegram` raise its existing window.
  The Ubuntu composition now optionally uses a GNOME Shell adapter to request
  activation of an existing registered app window, confirms foreground focus
  with a fresh observation, and launches only when the extension explicitly
  reports no window. Uncertain activation never triggers a second launch.
  Focused Python and GJS tests cover these paths. The updated extension file
  is installed for the current user, but the running GNOME session still
  exposes the old D-Bus methods after a disable/enable cycle; a fresh GNOME
  session and live user validation remain required.
  After that restart, the owner reported repeated `Open Telegram` finals with
  `activation_unverified` while the Telegram window was minimized; GNOME showed
  "Telegram is ready" instead of focusing it. One attempt did confirm. The
  interpreter and allowlist were working; the focus request was intermittent.
  GNOME's `Shell.App.activate_window` compares the passed timestamp with the
  last user interaction and may request attention instead of activating an
  existing window. The extension now uses the same `Main.activateWindow` path
  used by Ubuntu Dock, with a fresh display timestamp, for this allowlisted
  voice action. Deterministic extension and Python tests pass; the revised
  installed extension still needs a fresh GNOME session and live verification.
- **Application foundation:** immutable, versioned settings, an injectable
  JSON store, and a UI-independent lifecycle controller now exist under
  `src/kyrin/app/`. Ubuntu composition and an optional Qt control UI connect
  them to the live runtime. User-scoped login startup registration exists. A missing settings
  file yields no selected STT model and no action permission. See
  `docs/app/UBUNTU_APPLICATION_LIFECYCLE_DESIGN.md`.
- **Visual feedback in progress:** a backend-independent status controller and
  optional GNOME Shell 50 character adapter now exist in the repository. The
  character distinguishes processing, clarification, actual action execution,
  confirmed completion, accepted-but-unverified launch, and failure. Focused
  Python tests and extension packaging passed. After correcting a GNOME 50
  drag API incompatibility, the owner observed a visible, draggable character
  and GNOME reported the extension as `ACTIVE`. Dragging felt laggy, so the
  extension now coalesces pointer motion and updates position once before each
  redraw. A separate fresh GNOME Shell 50.1 session verified status delivery
  and newest-position application. The owner reported that this was much
  better but still lagged. A visual-translation experiment passed a separate
  coordinate check but felt much worse on the user's actual desktop, so it was
  rolled back to frame-coalesced position updates. The remaining live delay
  needs measurement before another change. The owner rejected the dark static
  preview and authorized a smaller electric blue/violet animated mascot with
  contextual captions and a hide control. The optional GNOME
  adapter now uses a compact vector character and short state-driven motion;
  the UI has a × button and a top-bar restore control. The owner confirmed
  dragging, × hide, and restore after restarting the desktop session. The visual
  caption contract is independent of STT and TTS adapters. Headless GNOME
  tests verified movement, captions, hide/reopen, and queued position changes.
  The owner reported that real dragging failed; GNOME logs identified a null
  pointer-event source passed to `Clutter.Actor.contains()`. The owner later
  confirmed dragging after a session restart, but × did not hide the mascot.
  Drag starts on the image-and-caption content now, leaving × as a separate
  click target. A follow-up made × always clickable, handled primary press
  directly, and added a hover hint; the owner validated hide/restore after
  restarting the session. The owner approved more distinct state reactions.
  The mascot now uses head, eye, body, arm, and leg SVG layers, with
  compositor-only poses for ready, listening, processing, clarification,
  actual execution, confirmed/unverified results, and failure. The revised
  package is installed for the current user. A separate headless GNOME Shell
  50.1 session loaded all eight states without an extension error. After a
  restart, the owner observed distinct listening, processing, and execution
  motion; correct symbols and captions; smooth movement; and working ×
  hide/restore in a no-action display run. The user-session log showed no
  extension error. A later local `Open Telegram` microphone run produced a
  confirmed Telegram foreground action; the owner independently saw Telegram
  activate and observed the character change states during the real command.
  A later non-command transcript was the owner's spoken reaction and caused no
  action. Broader timing and other desktop environments remain unverified.
  This is not packaged product UI.

The 2026-10-07 repository audit read the project files by component and found
two small gaps in the current vertical slice. A final non-command could leave
the mascot showing Processing; a worker failure could go without immediate
user feedback. The status controller now returns to Ready on a final
non-command, with a later clarification event taking precedence. Executor
exceptions are represented as UNKNOWN because an action might have occurred
before the exception. A fatal worker processing error also emits immediate
UNKNOWN feedback before the worker stops. Deterministic tests cover these
paths. The full static type check now passes after synchronizing test doubles
with the current contracts. No new live microphone/GNOME validation has been
run for these corrections.

KYRIN is an open-source modular AI Desktop Agent. The high-level product vision
is to understand voice, vision, and text and interact naturally with the
operating system.

On 2026-10-09 a separate, read-only visual text foundation was added under
`kyrin.vision`: a permission-aware one-shot Ubuntu ScreenCast window capture,
a backend-independent OCR contract, a Tesseract CPU adapter, and a composition
that never executes desktop actions. The owner authorized and selected a window
in a live portal test; one 1920×1080 PNG was returned in memory. A local
Tesseract 5.5 runtime and English data were then extracted under the ignored
`models/local/ocr/tesseract/` directory without a system install. A synthetic
`Open Telegram` image returned both words and their boxes; live screenshot OCR
then found both expected words in a portal capture of a temporary test window
that the owner confirmed selecting. OCR processing after capture took 0.146 s
in that one run; broader live accuracy and latency remain unverified.
The selected portal window is not yet bound to active-app identity. This work
does not provide verified browser/chat navigation or a model-management UI.
An optional GNOME 50 active-window capture prototype was added as a separate
extension. Its first version asked for user consent for every image. It
returned focused-window identity and image in one request and rejected a focus
change. The subsequent live validation is described below. See
`docs/vision/GNOME_ACTIVE_WINDOW_CAPTURE_PROTOTYPE.md`.
After the owner restarted, GNOME Shell 50.1 listed the extension as ACTIVE.
In an explicitly approved live one-shot test, the owner accepted the GNOME
prompt; the temporary `KYRIN OCR Test` window was captured in memory and OCR
found `Open` and `Telegram`. GNOME reported `window:8`, which is a temporary
window-backed ID rather than an installed-app ID. The extension and adapter
were then tightened to reject those IDs. A second, user-approved live test of
a window bearing KYRIN's registered desktop ID returned
`local.kyrin.KYRIN.desktop`, its test process ID, and OCR words including
`Open` and `Telegram`. This confirms the read-only capture+identity+OCR path
for that one registered window. It does not authenticate the D-Bus requester,
generalize to other apps, or authorize actions. The prototype extension was
disabled after the tests and GNOME reports it INACTIVE.
The owner then approved a session-scoped access design. The Qt app now claims
`org.kyrin.Desktop` and provides a `Screen Access` page with a non-persistent
on/off control. The revised GNOME extension checks the D-Bus sender against
the current owner of that name, prompts once per app session, and revokes on
explicit request, owner loss, or extension disable. The old separate-process
image helper and terminal diagnostic were removed because their D-Bus sender
cannot be the Qt app's connection. Python and GJS tests cover grant, foreign
sender denial, revocation, owner loss, and a late owner response after revoke.
The corrected extension was installed and enabled. An unauthorized direct
D-Bus capture request returned no image. The first live Qt grant request was
denied before the GNOME prompt appeared. D-Bus monitoring confirmed that the
request sender and `org.kyrin.Desktop` owner matched. A real GJS check found
that `GLib.Variant.unpack()` returned a wrapped child variant rather than the
owner string. The extension now uses `deepUnpack()` for the owner check and
the name-owner-change signal; the GJS harness models this distinction.
Focused tests passed, but an immediate retry in the same GNOME session still
returned the old denial. After the owner restarted the desktop session, the
corrected Qt request displayed the GNOME dialog and received a grant. A
separate approved live test captured one 20,072-byte PNG in memory from a
registered KYRIN test window, with `local.kyrin.KYRIN.desktop` and its PID.
After explicit revoke, a further capture request returned no image. This
validates the Qt/GNOME one-image path and revocation on this desktop; it is
not connected to OCR-triggered actions. A session-bus name is not strong
authentication of a binary against a malicious process running as the same
user; GNOME consent remains required.

The owner approved a staged connection from screen observation toward command
understanding. The first slice is read-only: `ScreenTextReader` receives an
on-demand image from the Qt-owned `ScreenAccess`, runs the replaceable `OcrEngine`
on a worker thread, and discards the result if the active desktop ID/PID has
changed or access was revoked. The `Screen Access` page displays bounded plain
text and clears it on revoke. The Ubuntu Qt composition discovers an optional
English Tesseract runtime from the user's XDG data directory. The previously
downloaded local runtime was copied there on this development machine without
installing system packages. Focused automated tests pass. In a live Qt run
on 2026-10-09, session access was granted and the combined reader returned
`local.kyrin.KYRIN.desktop`, the test process PID, and OCR words including
`Open` and `Telegram` from the registered test window. Access was revoked on
exit. A portal app-ID registration warning appeared but did not prevent this
test. This validates one local read-only path, not recognition quality across
apps or permission behavior on other desktops. OCR text is still not fed to
the command interpreter and cannot authorize an action.
Two further read-only Qt tests captured the owner's real Telegram Desktop
window with a stable desktop ID and PID; the GNOME session grant was revoked
after each run. The first mixed Persian/English view yielded 162 OCR words but
none of the small English label set checked by the probe. The owner clarified
that this view contained both languages, while the installed Tesseract data is
English only. A controlled Telegram Settings view yielded 394 OCR words,
including `Settings`, `Notifications`, `Privacy`, `Security`, `Language`,
`Folders`, and `Advanced`; 102 of 394 spans had confidence at least 0.8.
The probe printed counts and fixed generic labels, not chat names or images.
This establishes that English UI labels can be read in this window; it does
not establish reliable contact matching, Persian OCR, or click coordinates.
A third read-only Telegram run used the owner's chat list with the public
`Saved Messages` title visible. OCR found the exact adjacent English words;
252 spans were returned, 56 at confidence 0.8 or higher. The probe reported
only whether that title was present, not other chat names. This is one
controlled title match, not evidence of reliable arbitrary contact matching.
An exact, same-line OCR phrase matcher with duplicate preservation was added
as read-only groundwork and passes focused tests. A proposed first input
action is documented in `docs/actions/TELEGRAM_CHAT_NAVIGATION_DESIGN.md`.
The local Wayland session exposes RemoteDesktop Portal v2, but its keyboard
permission is desktop-wide rather than Telegram-window-scoped. The owner
approved a one-shot, keyboard-only diagnostic. The installed Telegram shortcut
file maps `self_chat` to `Ctrl+0` with no custom override. A system-Python
portal helper requested a non-persistent keyboard session, rechecked the
Telegram desktop ID and PID, sent only that fixed shortcut, and closed its
session. The subsequent read-only Qt OCR run found one `Saved Messages` phrase
in the same Telegram window; the owner independently confirmed that this chat
opened. A subsequent owner-approved read-only test located a single exact
`Saved Messages` phrase in the upper chat pane of a 1853×1048 Telegram image
at x=679, y=45 with confidence above 0.87. The Ubuntu application now has a
separate saved Telegram chat permission (settings schema 2, with schema 1
migrating to permission off), and the action gate enables `OPEN_CHAT` only
when this permission and the required observer, window-identity reader, and
Qt screen verifier are present. Its one implemented target is `Saved Messages`.
The portal helper rechecks focus before the keyboard shortcut and the Qt-owned
OCR reader checks a fresh matching window and upper-pane title afterward.
Focused automated tests pass. The full product microphone-to-chat path has
not yet been live tested, and arbitrary contact navigation remains open.

The owner then prioritized speech understanding before further chat actions.
The Speech Recognition page now keeps a bounded, session-only trace of final
STT text, command decisions, clarification or block reasons, and action
results. Current settings schema 3 adds optional user-editable wake-name
spellings, with schema 1/2 migration to no custom spellings. The Whisper
adapter can use `language=auto` with a multilingual model and forward the
detected language code from local verbose JSON; Vosk rejects `auto`. On this
development machine, the installed Whisper `small` model returned `en` and
`fa` for one previously recorded clip in each language. This confirms the
adapter path for those two clips, not accuracy or broad language coverage.
The demo command interpreter still recognizes a limited English/Persian
grammar. See `docs/stt/MULTILINGUAL_COMMAND_INPUT.md`.

---

## 2. Current Audio Architecture

The implemented components can be composed as follows:

```text
Microphone
    ↓
MicrophoneInput
    ↓
AudioCaptureQueue (dedicated capture thread, bounded queue)
    ↓
AudioData
    ↓
SampleRateConverter (mono INT16 sample-rate conversion)
    ↓
AudioFramer (configurable processing windows)
    ↓
VoiceActivityDetector / SileroVad (offline, 16 kHz mono INT16)
    ↓
SpeechActivityMonitor (continuous audio and stable activity transitions)
```

`ContinuousAudioPipeline` composes the components above for one stream.

The implemented live STT composition is:

```text
Microphone
    ↓
MicrophoneInput
    ↓
AudioCaptureQueue
    ├──→ AudioBacklog → STT worker → SpeechToTextSession
    └──→ SampleRateConverter → AudioFramer → VoiceActivityDetector
                                           ↓
                                  SpeechActivityMonitor

Both branches → live events → command decision layer (implemented, dry-run)
```

`SampleRateConverter` and `AudioFramer` are separate downstream components.
The capture-to-activity pipeline, replaceable STT contract, optional Vosk
adapter, and backend-independent live VAD/STT composition exist. A reusable
`LiveCommandRuntime` connects transcript decisions to the bounded action
worker. The Linux launcher is available only with explicit execution and app
bindings in the terminal diagnostic; a packaged application entry point does
not yet exist.
A downstream engine that accepts variable-size chunks may bypass `AudioFramer`.

### Architectural boundary

`MicrophoneInput` is only responsible for audio acquisition.

It must not contain:

- STT logic
- VAD logic
- intent understanding
- agent decision-making
- desktop automation
- unrelated application logic

Downstream audio processing must remain separate from microphone acquisition.

---

## 3. Implemented Core Components

### `AudioSampleFormat`

Location:

```text
src/kyrin/audio/audio_format.py
```

Implemented values:

```text
INT16
FLOAT32
```

Current byte sizes:

```text
INT16   -> 2 bytes per sample
FLOAT32 -> 4 bytes per sample
```

`AudioSampleFormat` is implemented as a `StrEnum`.

**Status:** CONFIRMED.

---

### `AudioFormat`

Location:

```text
src/kyrin/audio/audio_format.py
```

Current shape:

```python
@dataclass(frozen=True)
class AudioFormat:
    sample_rate: int
    channels: int
    sample_format: AudioSampleFormat
```

Responsibilities:

- describe how PCM bytes must be interpreted
- store sample rate
- store channel count
- store sample representation
- calculate `bytes_per_frame`
- reject invalid non-positive sample rates
- reject invalid non-positive channel counts

`AudioFormat` is immutable.

`frames_per_chunk` does not belong to `AudioFormat`; it is streaming
configuration rather than an intrinsic property of the audio representation.

**Status:** CONFIRMED.

---

## 4. PCM Terminology

### Sample

A sample is one numeric audio measurement for one channel.

### Sample rate

The number of PCM sample frames per second.

Example:

```text
16000 Hz
```

means:

```text
16000 sample frames per second
```

### PCM sample frame

A PCM sample frame contains one sample for every channel at one instant.

Examples:

```text
mono   -> 1 sample per PCM frame
stereo -> 2 samples per PCM frame
```

### Bytes per PCM frame

The current formula is:

```text
bytes_per_frame =
    channels × bytes_per_sample
```

Example:

```text
stereo INT16

2 channels × 2 bytes
= 4 bytes per PCM frame
```

### Chunk

A chunk is a group of PCM sample frames read or processed together.

A microphone chunk size is not automatically the same as a VAD or
processing window size.

### Processing window

A framing/VAD window can be a time-based block such as:

```text
10 ms
20 ms
30 ms
```

A processing window contains many PCM sample frames.

The term "frame" can be ambiguous in audio systems, so this project should
distinguish:

```text
PCM sample frame
processing/VAD window
```

when the distinction matters.

---

## 5. `AudioData`

Location:

```text
src/kyrin/audio/audio_data.py
```

Current shape:

```python
@dataclass(frozen=True)
class AudioData:
    data: bytes
    audio_format: AudioFormat
```

`AudioData` uses composition:

```text
AudioData has an AudioFormat
```

Responsibilities:

- carry immutable raw PCM bytes
- carry the exact format needed to interpret those bytes
- reject byte sequences that do not contain complete PCM sample frames

Current alignment invariant:

```text
len(data) % audio_format.bytes_per_frame == 0
```

This guarantees that an `AudioData` instance cannot end in the middle of a PCM
sample frame.

`AudioData` is source-independent. It is not tied specifically to microphone
capture.

**Status:** CONFIRMED.

---

## 6. `AudioInput`

Location:

```text
src/kyrin/audio/audio_input.py
```

Current contract:

```python
class AudioInput(Protocol):
    def capture(self) -> Iterator[AudioData]: ...
```

The protocol defines the behavior of an audio source without requiring callers
to depend on a concrete hardware implementation.

This supports structural typing and loose coupling between audio consumers and
audio sources.

**Status:** CONFIRMED.

---

## 7. `MicrophoneInput`

Location:

```text
src/kyrin/audio/microphone/input.py
```

Constructor configuration:

```text
device
audio_format
frames_per_chunk
```

Responsibilities:

- retain microphone configuration
- validate `frames_per_chunk`
- open `sounddevice.RawInputStream` inside `capture()`
- read microphone chunks
- convert the library-provided buffer to independent `bytes`
- construct `AudioData`
- yield `AudioData` continuously
- detect microphone overflow
- translate `sounddevice.PortAudioError` into project-level errors
- release the stream through context-manager semantics

Current invariant:

```text
frames_per_chunk > 0
```

Hardware is intentionally not acquired inside `__init__`.

The current flow inside `capture()` is conceptually:

```text
open RawInputStream
    ↓
read frames
    ↓
check overflow
    ↓
convert buffer to bytes
    ↓
construct AudioData
    ↓
yield
    ↓
repeat
```

**Status:** CONFIRMED.

---

## 8. Audio Error Hierarchy

Location:

```text
src/kyrin/audio/audio_errors.py
src/kyrin/audio/microphone/errors.py
```

Current hierarchy:

```text
AudioError
    ↓
MicrophoneError
    ↓
MicrophoneOverflowError
```

`AudioError` and capture-queue errors live in the shared audio package.
`MicrophoneError` and `MicrophoneOverflowError` live with the microphone source.
`MicrophoneError` acts as the project-level boundary for microphone-related
failures.

PortAudio-specific failures are translated rather than leaked directly as the
main application-facing exception type.

Exception chaining is preserved for translated `PortAudioError` failures.

**Status:** CONFIRMED.

---

## 9. Testing State

Current automated test areas include:

- package import
- `AudioFormat`
- `AudioSampleFormat`
- `AudioData`
- audio error hierarchy
- `MicrophoneInput`
- `SampleRateConverter`
- `AudioFramer`
- `AudioCaptureQueue`
- `ContinuousAudioPipeline`
- `SileroVad`
- `SpeechActivityMonitor`
- replaceable STT contract and transcript/device value types
- optional Vosk adapter behavior and lifecycle

Current behaviors covered include:

- `AudioFormat` value storage
- `AudioFormat` immutability
- value-based equality
- zero sample-rate rejection
- negative sample-rate rejection
- zero-channel rejection
- negative-channel rejection
- sample-format string values
- bytes-per-sample calculation
- bytes-per-frame calculation
- `AudioData` value storage
- `AudioData` immutability
- misaligned PCM data rejection
- microphone `AudioData` production
- microphone stream configuration
- overflow handling
- multiple chunk production
- PortAudio stream-open error translation
- PortAudio read error translation
- zero `frames_per_chunk` rejection
- negative `frames_per_chunk` rejection
- package import
- streaming resampling duration across input rates and chunk boundaries
- removal of frequencies above the output Nyquist limit
- output before the input stream ends
- identity conversion, empty input, and unsupported-format errors
- audio framing across arbitrary chunk boundaries without losing PCM data
- full windows during streaming and an unpadded remainder at natural end
- independent framing calls, format checking, and converter/framer composition
- bounded capture, source-failure propagation, and stop behavior
- continuous capture-to-activity composition
- offline Silero VAD inference and speech-activity transitions

Latest observed full quality gate:

```text
ruff check src tests scripts
→ All checks passed!

mypy src tests
→ Success: no issues found in 36 source files

pytest -q
→ 90 passed (full suite requires access to the system audio service)
```

**Status:** CONFIRMED.

---

## 10. Test Doubles

`tests/audio/microphone/test_input.py` uses fake `RawInputStream` implementations to
test microphone behavior without requiring real hardware.

Current fake behaviors cover:

- normal capture
- overflow
- multiple chunks
- stream-open failure
- read failure

Some fake state is currently stored using class variables.

This is accepted for the current test suite but may be refactored later for
stronger test isolation.

**Status:** known non-blocking technical debt.

---

## 11. Hardware Validation Scripts

Hardware-dependent checks are intentionally separated from deterministic unit
tests.

Current scripts:

```text
scripts/audio/microphone/check_audio_rates.py
scripts/audio/microphone/check_microphone_stream.py
scripts/audio/check_live_speech.py
```

### `check_audio_rates.py`

Used to manually test selected device/sample-rate combinations using
`sounddevice.check_input_settings()`.

The currently encoded device IDs are local development values and must not be
treated as portable application defaults.

### `check_microphone_stream.py`

Used for a minimal real `RawInputStream` capture experiment.

Current example configuration is local development configuration and is not a
portable product default.

**Status:** CONFIRMED development utilities.

---

## 12. Observed Hardware Environment

Local hardware experiments established that audio-device support depends on the
full combination of:

```text
device
sample rate
channels
sample format
```

A reported default sample rate must not be treated as proof that every complete
configuration is supported.

Observed development findings include:

- device 4 rejected one tested 32 kHz configuration
- device 4 successfully captured at 48 kHz, mono, INT16
- device 5 accepted selected 44.1 kHz and 48 kHz configurations

These findings are machine-specific.

**Status:** TEMPORARY / EXPERIMENTAL.

---

## 13. Package and Tooling

Project configuration is stored in:

```text
pyproject.toml
```

Current baseline:

```text
Python >= 3.14
setuptools src layout
```

Runtime dependencies:

```text
numpy >= 2.0
onnxruntime >= 1.30, < 2
soxr >= 1.1.0
sounddevice >= 0.5.6
```

Development tools:

```text
coverage >= 7.0
mypy >= 2.0
pytest >= 9.0
ruff >= 0.16
```

Ruff target:

```text
py314
```

Mypy configuration:

```text
python_version = 3.14
strict = true
```

Pytest test root:

```text
tests
```

Coverage source:

```text
kyrin
```

**Status:** CONFIRMED.

---

## 14. Current Repository Structure

Relevant current files:

```text
KYRIN/
├── README.md
├── LICENSE
├── pyproject.toml
├── AGENTS.md
├── PROJECT_CONTEXT.md
├── scripts/
│   └── audio/
│       └── microphone/
│           ├── check_audio_rates.py
│           └── check_microphone_stream.py
├── src/
│   └── kyrin/
│       ├── __init__.py
│       ├── audio/
│       │   ├── audio_data.py
│       │   ├── audio_errors.py
│       │   ├── audio_framer.py
│       │   ├── audio_format.py
│       │   ├── audio_input.py
│       │   ├── audio_capture_queue.py
│       │   ├── continuous_audio_pipeline.py
│       │   ├── sample_rate_converter.py
│       │   ├── activity/
│       │   │   ├── voice_activity_detector.py
│       │   │   ├── silero_vad.py
│       │   │   ├── speech_activity_monitor.py
│       │   │   └── models/
│       │   │       └── silero_vad.onnx
│       │   └── microphone/
│       │       ├── input.py
│       │       └── errors.py
│       └── stt/
│           ├── capabilities.py
│           ├── contracts.py
│           ├── device.py
│           ├── errors.py
│           └── transcript.py
└── tests/
    ├── test_package.py
    ├── audio/
    │   ├── test_audio_data.py
    │   ├── test_audio_framer.py
    │   ├── test_audio_format.py
    │   ├── test_sample_rate_converter.py
    │   ├── activity/
    │   │   ├── test_silero_vad.py
    │   │   └── test_speech_activity_monitor.py
    │   └── microphone/
    │       ├── test_input.py
    │       └── test_errors.py
    └── stt/
        └── test_contracts.py
```

The tree lists representative files. Shared audio contracts and processing
remain in `kyrin.audio`. Microphone-specific acquisition and errors live in
`kyrin.audio.microphone`; VAD, speech-activity monitoring, and the bundled
Silero model live in `kyrin.audio.activity`. This leaves room for a future
file-based source without tying processing to the microphone. STT contracts
are isolated in `kyrin.stt`; no backend library is imported there.

---

## 15. Major Confirmed Design Decisions

### Separate contract from implementation

```text
AudioInput
```

is the abstraction.

```text
MicrophoneInput
```

is the concrete microphone implementation.

**Reason:** loose coupling and testability.

---

### Acquire hardware during capture

`MicrophoneInput.__init__` stores configuration only.

The audio device is acquired inside:

```text
capture()
```

**Reason:** cleaner resource lifetime and easier testing.

---

### Use streaming generators

`capture()` returns:

```text
Iterator[AudioData]
```

and uses `yield`.

**Reason:** audio must be processed incrementally rather than accumulated in
memory.

---

### Convert external buffers to `bytes`

The temporary buffer received from `sounddevice` is converted to independent:

```text
bytes
```

before entering the project data model.

**Reason:** avoid coupling domain objects to temporary external-library memory.

---

### Represent audio format explicitly

Sample rate, channel count, and sample representation are grouped into:

```text
AudioFormat
```

instead of being scattered independently.

**Reason:** they form one logical description of PCM interpretation.

---

### Keep streaming configuration separate from audio format

```text
frames_per_chunk
```

remains outside `AudioFormat`.

**Reason:** chunk size controls streaming behavior, not how individual PCM bytes
are interpreted.

---

### Require complete PCM sample frames

`AudioData` rejects byte lengths that are not divisible by:

```text
audio_format.bytes_per_frame
```

**Reason:** downstream processing can rely on structurally valid PCM input.

---

### Keep hardware configuration portable

Machine-specific device IDs must not become hard-coded application defaults.

**Reason:** device numbering and capabilities differ between machines and
operating systems.

---

## 16. Implemented Sample-Rate Conversion

`SampleRateConverter` is located in `src/kyrin/audio/sample_rate_converter.py`.
It accepts an explicit `AudioFormat` and target sample rate, then converts an
iterable of `AudioData` chunks. Each `convert()` call has independent streaming
state. The converter yields nonempty output as it becomes available and flushes
the filter when the iterable ends. Output chunk sizes can differ from input
chunk sizes. No fixed target rate is built into the component.

The current supported input and output representation is mono INT16 PCM.
Changing the sample rate is implemented; changing channel count or sample
representation is not. Unsupported formats and midstream format changes raise
`ValueError`. Equal rates pass through without resampling. Empty input yields
no output.

NumPy interprets the PCM bytes as numeric samples; `soxr.ResampleStream` does
the stateful conversion with MQ quality and anti-alias filtering. A local trial
with `samplerate` lost output frames when the same one-second signal was fed in
small chunks; this was the reason to choose `soxr` for this implementation.
The installed `soxr` package declares LGPL-2.1-or-later licensing. Distribution
packaging and license obligations still need review before a release. This
environment verified Linux only; Windows and macOS packaging remain untested.

`MicrophoneInput` has not been modified or wired to the converter yet.
Downstream framing can consume the converter's `AudioData` iterator.

**Status:** CONFIRMED for the implemented mono INT16 path. Other conversion
dimensions remain OPEN until a consumer requires them.

---

## 17. Implemented Audio Framing

`AudioFramer` is located in `src/kyrin/audio/audio_framer.py`. It accepts an explicit
`AudioFormat` and a positive `frames_per_window` count. The caller chooses this
count to match a downstream engine; no duration or VAD-specific setting is
hard-coded. It works with any currently represented PCM channel count and
sample format because it only groups bytes along PCM frame boundaries.

`frame()` accepts an iterable of `AudioData` chunks and creates independent
buffer state for each call. It yields complete windows as soon as enough audio
arrives, even if the source continues indefinitely. At natural stream end, it
yields any remaining PCM data as a single shorter, unpadded `AudioData` item.
Consumers can identify that final item by its length and decide how to handle
it. The framer never invents silence or discards input data. Empty chunks are
ignored; midstream format changes raise `ValueError`.

The buffer holds at most one incomplete window between input chunks. Larger
incoming chunks are sliced directly into windows rather than first being copied
into the buffer. No new runtime dependency was needed. Framing is optional for
consumers that can use variable-size audio chunks.

**Status:** CONFIRMED for the implemented behavior. Required window sizes for
specific downstream engines remain OPEN.

---

## 18. VAD and Turn Detection

`VoiceActivityDetector` is a small streaming contract: required `input_format`,
`frames_per_window`, `detect(window) -> bool`, and `reset()`. Consumers can use
another engine without importing Silero. A detector instance belongs to one
audio stream. `reset()` clears engine state when a genuinely new stream starts;
pauses in a continuing conversation do not reset it.

`SileroVad` implements that contract with a bundled Silero VAD 6.2.3 ONNX
model. ONNX Runtime performs local CPU inference. No Torch installation or
runtime model download is needed. Input must be complete 512-sample windows
of mono 16 kHz INT16 PCM; the adapter normalizes samples to float32 and keeps
the model's recurrent state and 64-sample context between windows. Threshold
defaults to 0.5 and is configurable. The model and upstream MIT license are
packaged under `src/kyrin/audio/activity/models/`.

KYRIN sets `ORT_DISABLE_TELEMETRY=1` before importing ONNX Runtime through
this adapter. The official ONNX Runtime package may initialize telemetry at
import time, so calling its disable API only after import is insufficient for
the project's offline requirement. This setting affects the process; other
code must not import ONNX Runtime earlier if this guarantee is required.

`SpeechActivityMonitor` composes any `VoiceActivityDetector` and returns one
`SpeechActivityFrame` per input window, without reading ahead or withholding
audio. Each result contains the original audio, raw VAD decision, stable
`LISTENING`/`SPEAKING` state, and an optional `STARTED`/`PAUSED` transition.
The default confirmation intervals are 64 ms of speech and 384 ms of silence;
they are configurable in milliseconds and are provisional until validated on
real speech. The monitor never treats a pause as the end of the conversation.
Its `reset()` starts a new audio stream and resets detector state, not
conversation memory.

The final partial window emitted by `AudioFramer` is forwarded with an unknown
speech decision. It is not passed to a VAD that requires complete windows and
does not count as silence. Another window after that partial requires an
explicit stream reset. The monitor does not transcribe audio, decide whether
a command is complete, or execute actions.

The new command coordinator interprets streaming transcript updates and emits
replaceable candidates plus final resolutions. It does not execute actions.
A pause is an activity signal, not a mandatory command boundary.

The current high-level composition is:

```text
Audio capture ──→ VAD / SpeechActivityMonitor ──→ activity events
       └───────→ streaming STT ────────────────→ TranscriptUpdate
                                                   ↓
                                          CommandCoordinator
                                                   ↓
                                   candidate / resolution / response request
```

Silence or absence of speech must eventually be treated as a normal listening
state rather than as an exceptional failure.

STT selection and desktop application integration remain open.

---

## 19. Open Questions

The following engineering decisions are still open:

- What exact normalized audio format should downstream V1 processing use?
- Will downstream consumers require sample representation or channel conversion?
- What distribution steps will be required for the `soxr` license?
- What exact framing-window durations will downstream consumers require?
- Which reversible commands, if any, may execute from a provisional partial
  candidate, and how should a later correction be reconciled?
- Which STT engine will be used?
- What retry/recovery behavior should occur after microphone device failure?
- How will default microphone selection work across operating systems?

These questions must not be silently decided without investigation or an
explicit project decision.

---

## 20. Known Risks and Constraints

- Audio device IDs are machine-specific.
- Supported audio configurations vary by hardware and OS.
- Streaming chunk boundaries are not semantic speech boundaries.
- Streaming chunk boundaries are not necessarily future processing-window
  boundaries.
- Resampling cannot safely be implemented as naive sample deletion without
  considering aliasing.
- Real-time processing may require state to persist across chunks.
- Queues can introduce latency and backpressure problems if introduced without
  a clear ownership model.
- External audio-processing dependencies should not be added without first
  evaluating why they are required.

---

## 21. Development Workflow

The user is learning while building KYRIN.

Preferred workflow:

1. Explain the new concept from first principles.
2. Use a small example outside KYRIN when useful.
3. Give a small exercise when a concept is new.
4. Review the answer.
5. Connect the concept to KYRIN.
6. Design the component boundary.
7. Use TDD for behavioral changes.
8. Run focused tests.
9. Run the full quality gate.

When a complete file replacement is requested, provide the entire final file
rather than partial fragments.

---

## 22. Current Project State

This section preserves an earlier milestone snapshot. Later sections 43–57
record decisions and implementation that supersede its old next-step and test
counts; use the overview above and the repository for current status.

### Completed

```text
AudioSampleFormat
AudioFormat
AudioData
AudioInput
MicrophoneInput
SampleRateConverter (mono INT16 sample-rate conversion)
AudioFramer (configurable audio framing)
VoiceActivityDetector (replaceable VAD contract)
SileroVad (bundled offline ONNX model)
SpeechActivityMonitor (continuous, smoothed VAD observations)
AudioCaptureQueue (bounded capture worker and explicit overflow error)
ContinuousAudioPipeline (capture-to-activity composition)
SpeechToTextEngine / SpeechToTextSession (replaceable STT contracts)
TranscriptUpdate and CPU/GPU device preferences
VoskEngine / VoskSession (optional CPU-only experimental STT adapter)
AudioBacklog (duration-bounded pending STT audio and wait/ready notices)
LiveSpeechPipeline (one capture, independent VAD/STT workers)
CommandInterpreter / CommandCoordinator (dry-run command decisions)
DemoCommandInterpreter (limited example phrases, not a product NLP engine)
ActionPolicy / ActionGate (final-only, allowlisted requests and result tracking)
ActionExecutor / LinuxDesktopEntryExecutor (separate, limited OPEN_APP launcher)
ContextResolver / CommandContext (dialogue history versus fresh active-app state)
Audio error hierarchy
hardware diagnostic scripts
unit-test foundation
```

Latest focused quality checks for the command and action-gate changes:

```text
Ruff   -> passing
Mypy   -> passing
Pytest -> 61 focused action/command/STT/live-pipeline tests passing
```

The earlier full-suite result was 90 passing tests. A new full-suite attempt
in the current isolated environment did not complete collection because
PortAudio could not connect to PulseAudio. This does not validate or invalidate
the hardware-dependent tests; they need a normal audio environment.

### Current next step

Broaden the English command corpus and validate the owner-selected Vosk
`lgraph` default candidate on ordinary CPU hardware before bundling it. The
current replay includes errors in confirmed command names. Then design a
user-facing model manager and optional language installation. Keep live voice
action execution disabled until app state and feedback are handled honestly.

The standalone Vosk adapter works with a locally supplied model. The live
pipeline accepts any engine implementing the STT contract, including Vosk;
the owner's product direction chooses Vosk for English V1, but no runtime
default is wired yet. Acceptance still requires measured command accuracy,
partial-result latency, resource use, and offline packaging. The first semantic
command layer exists as a dry-run contract and coordinator; its demo interpreter
recognizes only a few example phrases and is not a production language engine.
Additional audio-format conversions should be implemented only when a
downstream requirement is known.

### Current blocker

No known blocker prevents evaluating offline STT engines. Short real
microphone runs produced partial and final transcripts through the live
pipeline; a repeated short Persian sentence matched the user's reference
closely, but this is not a representative accuracy benchmark. A direct ALSA
input device failed to stop cleanly; the corresponding PulseAudio source
stopped successfully. Long-running stability, precise end-to-end latency,
recovery after device failure, and packaging on other operating systems
remain to be validated.

---

## 23. Handoff Instructions for Future AI Assistants

1. Inspect the actual repository before making architectural claims.
2. Read this document before planning major project changes.
3. Treat repository code and observed test output as stronger evidence than
   stale documentation.
4. Preserve the `AudioInput` / `MicrophoneInput` separation.
5. Keep microphone acquisition separate from downstream processing.
6. Preserve `AudioFormat` as the PCM format value object unless a documented
   requirement justifies changing it.
7. Preserve `AudioData` frame-alignment guarantees.
8. Do not assume microphone chunk boundaries equal downstream processing
   windows.
9. Do not jump directly from microphone capture to STT without reconsidering
   format conversion, framing, VAD, and turn detection.
10. Do not add a new audio-processing dependency without explaining and
    evaluating it first.
11. Treat local hardware IDs and sample-rate observations as experimental, not
    portable defaults.
12. Update this document whenever a significant architectural or behavioral
    milestone makes it inaccurate.

---

## 24. Source and Confidence Notes

This document combines:

- the current verified repository state
- observed local test output from the current development session
- confirmed engineering decisions from the KYRIN development conversation
- explicitly stated current architectural direction

It intentionally distinguishes implemented behavior from future design.

When this document becomes inconsistent with the repository:

```text
inspect repository
    ↓
identify newer evidence
    ↓
verify with tests where possible
    ↓
update PROJECT_CONTEXT.md
```

Do not preserve stale documentation merely for historical consistency.

---

## 25. Continuous Capture and Processing Pipeline

`AudioInput` now includes `stop_capture()`, which may be called from another
thread. `MicrophoneInput.stop_capture()` sets a stop signal, briefly allows the
current read to finish, and aborts the active stream only if capture does not
end promptly. A stopped `MicrophoneInput` is one-use; create
a new instance for a restarted capture session. Its hardware stream remains
owned by the capture thread and is never opened in `__init__`.

`AudioCaptureQueue` runs `capture()` on a dedicated worker thread and transfers
chunks to one consumer through a bounded standard-library queue. Its default
capacity is eight source chunks, not eight VAD windows; the actual buffered
duration depends on the source's chunk size. When the queue fills, the worker
records `AudioQueueOverflowError` and the consumer receives that failure.
Capture or source errors also propagate to the consumer. The class is used as
a context manager: leaving it requests source stop and joins the worker. A
worker that cannot stop within the configured timeout produces
`AudioCaptureStopError`; this condition requires application-level handling.

`ContinuousAudioPipeline` composes capture queue, `SampleRateConverter`,
`AudioFramer`, and `SpeechActivityMonitor` for one active stream. The caller
must consume its `open()` iterator inside the context manager; exiting that
context stops capture even if the consumer exits early. The current conversion
path requires mono INT16 input and a mono INT16 detector format. Unsupported
formats fail explicitly. The pipeline does not transcribe speech, run actions,
or clear conversation memory. No new runtime dependency was introduced.

The application is not yet wired to instantiate this pipeline or supervise
restarts. Tests use deterministic fake audio sources and a mocked microphone
stream. Queue capacity, real microphone latency, and recovery behavior still
need validation on target systems. A bounded queue protects short processing
bursts but cannot fix sustained processing slower than audio arrival.

---

## 26. Replaceable Speech-to-Text Contract

The core `kyrin.stt` modules contain backend-independent contracts and value
types. An optional concrete adapter lives under `kyrin.stt.backends`. No model
weights, runtime download, or microphone logic have been added to STT.

`SpeechToTextEngine.capabilities` reports the configured model's supported
devices, known languages (if enumerable), partial-update support, and
automatic language-detection support. Declared GPU support does not guarantee
that a usable GPU exists on the current machine. Language coverage does not
guarantee accuracy, and an unknown language list never means all languages.

`SpeechToTextEngine.open_session(options)` creates one
`SpeechToTextSession` for one ordered audio stream. The session declares its
required `AudioFormat`, its actual CPU or GPU device, and whether it can emit
partial updates. It accepts `AudioData` chunks, returns newly available
`TranscriptUpdate` values, flushes pending results through `finish()` when the
stream truly ends, and releases session resources through `close()`. The engine
also has `close()` for its loaded model. Pauses within a continuing stream do
not call `finish()` and do not clear conversation memory.

Each transcript update carries a segment ID, text, `PARTIAL` or `FINAL`
status, and an optional language. A later update for the same segment may
replace partial text. `FINAL` seals that text segment, not the conversation.
No confidence score or timing field is required because candidate engines
have not yet been validated to provide those values consistently.

`SpeechToTextOptions` requests `AUTO`, `CPU`, or `GPU` and may include a language
hint. An adapter must honor an explicit device choice or raise
`DeviceUnavailableError`; the actual choice made for `AUTO` is reported by the
session. The contract does not prescribe a particular GPU API, model path, or
sample rate. Tests use fake partial/GPU and final-only/CPU engines to verify
that one consumer can use both through the same contract.

`ContinuousAudioPipeline` remains an activity-only API. `LiveSpeechPipeline`
adds a separate STT path, so engines receive their own requested sample rate
without being forced through Silero's fixed windows. STT inference runs on its
own worker. Engine selection, multilingual quality, latency, device
availability, offline model packaging, and integration with file input remain
OPEN.

---

## 27. Offline STT Evaluation Preparation

`docs/stt/STT_EVALUATION_FA.md` records the candidate shortlist, comparable
measurements, and observed limitations of the current development machine.
This is an evaluation plan, not an engine-selection decision or a claim of
measured recognition quality. The repository contains no STT model or labeled
speech benchmark yet. The local NVIDIA GPU is visible via PCI, but
`nvidia-smi` cannot communicate with its driver; GPU STT results cannot be
reported from this environment until that is resolved. No runtime dependency
or application behavior changed during this preparation.

The subsequent CPU-only smoke test is documented in
`docs/stt/STT_CPU_SMOKE_2026-10-03_FA.md`. It used 12 public Persian read-speech
clips and disposable models/dependencies under `/tmp`, without changing
KYRIN's runtime dependencies or code. Vosk small-fa-0.42 produced streaming
partials and a 3.0% corpus CER on that small subset; faster-whisper multilingual
base/int8 produced 32.5%; small/int8 produced a provisional 17.0%, pending
verification of its tokenizer after a network TLS error. These numbers cannot
establish multilingual or conversational suitability. The optional Vosk
adapter can now be used through `LiveSpeechPipeline`, but it is not the
production default or wired into a desktop application. A labeled multilingual
command corpus and meaningful live-command latency measurement remain
necessary before selection.

---

## 28. Experimental Vosk Adapter

`src/kyrin/stt/backends/vosk.py` implements the portable STT engine/session
contracts for a locally provided Vosk model. `pyproject.toml` exposes Vosk as
the optional `stt-vosk` dependency; the default project install is unchanged.
The adapter accepts mono INT16 PCM at the configured model sample rate, emits
revisable partial updates and final segment updates, and never ends a session
merely because speech pauses. It supports CPU only and one configured language
per model instance. A GPU request or a mismatched language hint fails
explicitly. It does not download a model or access microphone hardware.

The adapter's design and use are documented in `docs/stt/VOSK_ADAPTER_FA.md`.
Its deterministic tests use a fake Vosk API. A separate run with the actual
Persian model and a public WAV produced partials and a correct final transcript
while network connection attempts were blocked. Live microphone throughput,
multilingual switching, and production model selection remain unvalidated.

---

## 29. Live VAD/STT Composition and Backpressure

`LiveSpeechPipeline` opens one `AudioInput` source through `AudioCaptureQueue`.
A VAD worker sends each source chunk to `AudioBacklog` before independently
resampling and framing it for the existing `SpeechActivityMonitor`. An STT
worker consumes the same ordered source chunks from the backlog and resamples
them to the session's declared input format. Only confirmed activity
transitions are emitted to the caller; every VAD window is still examined.
Partial and final transcript updates are also emitted. A speech pause never
calls `session.finish()`; only natural source completion does. Exiting the
context early stops the source and closes the session.

The STT backlog includes audio currently under inference. Its default warning,
recovery, and hard limits are 1000, 250, and 5000 ms of source PCM. It emits
`BacklogNotice(WAIT)` once when the warning threshold is crossed and
`BacklogNotice(READY)` once after processing catches up. The UI must decide
how to display those notices; no UI is wired yet. A hard limit raises
`AudioQueueOverflowError` rather than silently dropping speech. Capture
itself retains its separate chunk-count limit, so unusually slow VAD or an
unresponsive event consumer may still trigger a capture overflow. These
thresholds are provisional and must be measured on real devices.

Deterministic tests cover one capture and ordered delivery to both branches,
independent sample rates, warning/recovery, explicit sustained-overflow
failure, early stop, and continued STT session across a speech pause. The
bounded diagnostic `scripts/audio/check_live_speech.py` was then run on a real
microphone. One 20-second PulseAudio run with a locally supplied Persian Vosk
model emitted streaming partials and three final segments while continuing
across pauses, without backlog or stop errors. A separate direct ALSA input
run received audio but failed to stop within the current timeout. The model's
own WAV test file produced partial and final text through the same pipeline.
Device IDs, model files under `/tmp`, and these observations are local and
temporary. No raw microphone recording or private transcript was committed.
One additional 35-second run of a short, repeated Persian sentence produced
two matching final texts close to the user's reference without backlog or
stop errors. General command accuracy, exact audio-to-text latency,
multilingual quality, and long-duration behavior remain unvalidated. See
`docs/audio/LIVE_SPEECH_PIPELINE_FA.md` for the commands and observations.

A controlled live test with three Persian desktop commands produced three
final transcripts without backlog or stop errors. Two matched their references
apart from punctuation/spacing. The first transcribed the spoken wake name
imperfectly, and a partial transcript briefly contained incorrect words before
correcting itself. This supports cautious partial-command handling and wake
name evaluation, not a production STT selection. Reference phrases and
results are in `docs/stt/STT_LIVE_COMMAND_SMOKE_2026-10-03_FA.md`.

---

## 30. Model-Independent Command Decisions

`src/kyrin/commands/` now contains a replaceable `CommandInterpreter`
contract, a `CommandCoordinator` for one ordered STT stream at a time, and a
limited offline `DemoCommandInterpreter`. The contract receives text, optional
language, dialogue context plus any fresh active-app observation, and an
outstanding clarification.
It returns a ready command, a question, an incomplete/unclear command, or
ordinary speech. It does not import Vosk or operate the desktop.

The first ready partial interpretation produces a replaceable
`CommandCandidateUpdate`; repeated identical partials produce no duplicate.
Later partials may replace or retract it. A final
transcript produces `CommandResolution` for the same `(stream_id, segment_id)`.
Candidates are advisory and never authorize execution by themselves. Later
partial changes can retract a candidate; final resolution supersedes it.
Repeated final updates for the same segment are ignored. VAD pauses do not
clear dialogue state. `start_new_stream()` increments the stream ID and resets
segment IDs after an STT restart while keeping an outstanding clarification.
The coordinator keeps the last app referenced in a final command separately
from an active-app observation. A previous action result or spoken proposal is
not a fresh foreground observation for a later command.

The limited demo recognizes only a few Persian and English app/chat phrases,
with or without a wake name. It is not the multilingual production engine.
Ambiguous chat commands ask which app; incomplete or unclear final text asks
for repetition; ordinary speech remains silent. Response events specify
text-only or text-and-voice delivery, but UI and TTS are not implemented.
The Linux app executor exists separately; no live desktop integration exists.
See
`docs/commands/COMMAND_UNDERSTANDING_FA.md` for behavior and limitations.
Focused command, STT, and live-pipeline tests passed (35 tests); Ruff and Mypy
passed. Full-suite collection was blocked by unavailable PulseAudio in the
isolated execution environment.

The bounded diagnostic `scripts/audio/check_live_speech.py` now has a
`commands` mode. It feeds live `TranscriptUpdate` events into the coordinator
and prints command candidates, final resolutions, and response requests. It
uses the limited demo interpreter and does not infer verified application
state or execute any action. A hardware-free integration test replays a
partial command that later becomes negated through `LiveSpeechPipeline` and
checks candidate retraction. A user-coordinated, 35-second microphone run
then confirmed four final decisions: a separately transcribed wake word did
not trigger an action; open Telegram was proposed; opening Ali's chat asked
which app and accepted "Telegram" as the answer; a negated open command did
not become an action. Under the rule used at that time, there were no
provisional candidates because each complete ready partial appeared only once
before its final update. The rule was subsequently changed to emit the first
ready partial as a retractable candidate. A second 25-second user-coordinated
microphone run produced a candidate for "open Telegram" about 0.72 seconds
before the final decision and no open candidate for "do not open Telegram".
The run did not observe a live candidate retraction; that behavior remains
covered by deterministic tests. These are local event timestamps, not exact
audio-to-action latency measurements. No action or voice response was executed.
See `docs/commands/COMMAND_LIVE_SMOKE_2026-10-03_FA.md` for exact test text,
observations, and limits. No action or voice response was executed.

---

## 31. Dry-Run Action Gate

`src/kyrin/actions/` now contains `ActionPolicy`, `ActionGate`, and structured
request/notice/result/feedback types. The gate consumes command events but
only a final `CommandResolution` may produce an `ActionRequest`. Partial
candidates and command response requests cannot authorize work. The policy
defaults to denying everything and has explicit allowed app identifiers for
`OPEN_APP` and `OPEN_CHAT`. An optional per-command-kind confirmation rule
returns a notice until an explicit trusted confirmation decision arrives.

The gate deduplicates resolutions by `(stream_id, segment_id)` within one
coordinator/gate lifetime. Pending confirmations and issued requests are
bounded by `max_pending`; reaching the limit returns a visible busy notice.
No shell command or OS call is derived from recognized speech here.

`ActionResult` must match an outstanding request. Only a successful result
that explicitly reports the observed active app updates `VerifiedContext`;
failure leaves prior context intact. `ActionFeedback` carries structured
success/failure and the requested text/voice channel for the localized
presenter. Unit tests use synthetic results, not actual desktop actions.
No executor is connected to the live voice diagnostic. No confirmation
interface, UI, or TTS is connected. See
`docs/actions/ACTION_GATE_FA.md` for the rules and limitations.

The microphone diagnostic's `commands` mode now feeds live command events to
the gate and prints allowed or blocked dry-run decisions. Its small diagnostic
allowlist covers `telegram` and `browser` for app opening and `telegram` for
chat opening. It records no synthetic success, so it does not invent verified
application context. A real three-phrase microphone run observed an authorized
dry-run request for "open Telegram", no action for "do not open Telegram",
and a clarification request for "open Ali's chat". No app launched in that run.

---

## 32. Limited Linux App Executor

`ActionExecutor` is a platform-neutral request/result protocol. Its first
implementation, `LinuxDesktopEntryExecutor`, handles only `OPEN_APP` on Linux.
Trusted configuration maps internal app IDs to absolute `.desktop` file paths;
the executor invokes `gio launch` with separate arguments and no shell. Other
commands or unconfigured apps return controlled errors. Windows, macOS, and
Android will need separate adapters behind the same contract.

`ActionOutcome` distinguishes `CONFIRMED`, `LAUNCH_ACCEPTED`, `UNKNOWN`, and
`FAILED`. A zero exit status from the Linux launcher means only
`LAUNCH_ACCEPTED`, not that a window opened or became active. The executor
never fabricates `observed_active_app`; the gate updates verified context only
from an independently confirmed active app. A new app launch that is accepted
or uncertain invalidates the previously verified active app. See
`docs/actions/OS_EXECUTOR_FA.md` for behavior and limitations.

Focused deterministic tests and static checks pass. A manual launch request
for the installed Telegram desktop entry returned `LAUNCH_ACCEPTED` twice;
the first visual check was inconclusive because Telegram was already open.
After closing Telegram, the user confirmed it opened again on the second
request. This is a human observation on one Linux desktop, not an automatic
foreground-app verification mechanism. No live voice command is yet connected
to this executor.

---

## 33. Chat-App Context Resolution

`CommandContext` separates the last app mentioned in final dialogue from a
fresh, optional `observed_active_app` supplied for the current transcript
update. `CommandCoordinator` retains the dialogue reference across silence
and STT stream restarts; partial text never changes it. The interpreter uses
an explicitly named app first. For an omitted chat app, `ContextResolver`
uses a supported fresh foreground observation if dialogue history does not
conflict. If the last referenced app is Telegram but the newly observed app
is WhatsApp, the demo interpreter asks which one the user means. With no
fresh observation, dialogue history alone cannot authorize an implicit app.

This is a language-neutral resolution boundary with limited Persian demo
phrases; it does not read the actual foreground app or search contacts.
The dry-run microphone tool can now supply foreground observations on final
transcripts when explicitly configured with exact GNOME desktop-ID bindings.
The GNOME observer was validated with live focus switching; the combined
microphone-to-context path still needs a coordinated live test. Other platforms
need their own adapters where possible. Otherwise the safe path is a
clarification question. No `OPEN_CHAT` desktop
executor exists yet. Focused tests cover conflict, explicit choice, missing
observation, partial correction, and context surviving an STT restart.

---

## 34. GNOME Active-App Observation Prototype

`kyrin.desktop.active_app.ActiveAppObserver` is a minimal cross-platform contract for a
fresh active-app observation. `GnomeShellActiveAppObserver` queries a tiny GNOME
Shell extension over the existing `org.gnome.Shell` session D-Bus connection.
The extension returns only the focused app's desktop ID, never window titles or
screen content. The Python adapter maps only configured external IDs to KYRIN
app IDs; an absent extension, missing focus, unknown app, malformed response,
or timeout returns `None`. It does not cache observations or execute actions.
No new Python dependency was added. The diagnostic under `scripts/desktop/`
prints raw desktop IDs as focus changes.

Seven focused deterministic tests, Ruff, and Mypy passed. A separate headless
GNOME Shell 50 session loaded the extension and returned an empty app ID when
no window was focused; the diagnostic displayed `unknown`. An attempt to focus
Calculator in that headless session also displayed `unknown`, so that run did
not validate nonempty app-ID reporting.
The first live Wayland session did not recognize the newly installed extension.
After the user restarted the system, GNOME Shell 50.1 recognized and enabled
it. In a 20-second test, the observed IDs alternated between Chrome and
Telegram as the user confirmed switching between those windows. The extension
is enabled in that user session. No command was executed. See
`docs/desktop/ACTIVE_APP_OBSERVATION.md`.

---

## 35. XDG Installed-App Catalog

`kyrin.desktop.app_catalog.AppCatalog` is a small platform-independent
discovery contract. `XdgDesktopAppCatalog` reads XDG `.desktop` entries with
the standard library, including the user's data directory before system data
directories. It derives exact desktop IDs, honors `Hidden=true`, and returns
base display names. The active-app diagnostic can now show a registered name
beside a freshly observed ID. On this device it found the local Telegram ID
and two Chrome IDs with the same display name. Display names are therefore
not trusted to infer a KYRIN command target. `AppIdentityResolver` applies
explicit exact-ID bindings, with an optional catalog-presence check; the GNOME
observer delegates to it without breaking its existing constructor. A
read-only live probe mapped the freshly observed `chatgpt.desktop` to `codex`
with a test binding and catalog validation. At that stage, no live command
integration or desktop action was added. No new runtime dependency was added.

---

## 36. Optional Active-App Context in Live Command Dry Run

`src/kyrin/desktop/command_bridge.py` supplies a fresh active-app observation
to `CommandCoordinator` only for final transcript updates. Partial updates
remain advisory and do not wait for the desktop. The microphone diagnostic's
`commands` mode accepts repeated, explicit `--active-app-binding`
`DESKTOP_ID=KYRIN_APP_ID` values and composes the GNOME observer with the XDG
catalog. Without bindings it preserves the old behavior. Missing focus,
unrecognized IDs, or an unavailable extension give `None`, so ambiguous chat
commands still ask for clarification. The action gate remains a dry run and
no executor is connected.

Deterministic bridge tests cover final-only observation and an unknown
observation after a previously known app. The CLI option was parsed in the
user session without opening the microphone. A read-only probe combined the
real GNOME observer with a synthetic final Persian chat transcript while
Codex was focused. It returned `None` for the Telegram binding and asked
which app to use; no action was executed. A coordinated real microphone test
is still pending because the local Persian Vosk model directory was not found
after the restart. This change does not establish STT accuracy or actual
desktop-action behavior.

---

## 37. Localized Response Text

`ResponseRequest` now carries a `ResponseKind` and structured chat details,
not a prewritten Persian sentence. `PendingClarification` retains the chat
target and candidate app IDs, so the demo interpreter and coordinator no
longer choose output wording. `ResponsePresenter` turns a command response,
`ActionNotice`, or `ActionFeedback` into `PresentedResponse` with text, channel,
locale, and stream/segment identity. The component has no microphone, OS,
UI, or TTS access and adds no dependency. The live-command diagnostic prints
the localized response text and still executes no actions or voice output.

Persian and English text are currently available; unsupported locales fall
back to the supported session preference, or English. This is presentation
coverage, not multilingual STT or command-understanding coverage.
`LAUNCH_ACCEPTED` text explicitly says that
completion is unconfirmed. `error_code` stays internal and is never copied
to user-facing text. Focused command/action/desktop-bridge/presenter tests
pass. A real active-app microphone test remains pending because the local
Persian Vosk model used earlier under `/tmp` was not found after restart.

---

## 38. Per-Command Response Language and Process Notices

Final transcript language now travels with `CommandResolution` and
`ResponseRequest`. `ActionGate` retains it in requests, notices, pending
confirmations, and eventual feedback, so late results do not adopt the
language of a later command. The presenter uses a supported event language,
then the session preference, then English. The actual output language remains
visible in `PresentedResponse.language`. Vosk's language tag is the configured
model language, not evidence of automatic language detection.

`SystemNotice` and focused adapters classify backlog wait/ready states and
known audio/STT failures without displaying raw exception text. The backlog
warning requests a pause with text and voice; recovery is text-only. A queue
overflow says that speech may have been lost. The live diagnostic prints
localized text, accepts an independent `--response-language`, and still does
not synthesize audio, show a product UI, or execute recognized commands.
It now loads the audio runtime after parsing CLI arguments, so a startup
failure can be reported as a localized microphone error.
Only Persian and English catalogs exist. Additional language catalogs and
offline TTS voices remain future work; no new dependency was added. See
`docs/responses/RESPONSE_LANGUAGE.md`.

---

## 39. Bounded Recovery of Live Speech Sessions

`SpeechSessionController` now supervises one bounded listening run. It uses a
factory to construct a fresh `LiveSpeechPipeline` and microphone source after
recoverable capture, queue-overflow, or STT failures. The shared STT engine
opens a fresh session for each attempt; Silero VAD is reset by the monitor at
each new stream. Default recovery is two retries with a one-second delay, and
the live diagnostic exposes both values as CLI options. The diagnostic's
duration applies to the full supervised run. The VAD-only diagnostic is not
under this controller.

A `SpeechSessionEnded` boundary tells the command consumer to retract partial
candidates and increment its stream ID while retaining dialogue reference
and pending clarification. A failed capture stop, failed STT-session close,
worker shutdown failure, or unavailable compute device is terminal; the
controller does not risk reusing an uncertain native resource. System notices
give localized text for recoverable errors and an impending retry. No real
command is executed or voice output produced.

Focused deterministic tests cover fresh attempts, retry limits, interruption
of backoff, active stop, and unsafe-close classification. A real microphone
recovery run is still pending: the temporary Persian Vosk model used in
earlier sessions is no longer present after restart, and the sandbox does not
expose the desktop audio server. No new dependency was added. See
`docs/audio/LIVE_SPEECH_PIPELINE_FA.md`.

---

## 40. Reproducible Offline STT Evaluation Tool

`kyrin.stt.evaluation` reads a labeled CSV manifest and local mono 16-bit PCM
WAV files, feeds audio through the existing sample-rate converter and any
`SpeechToTextEngine`, and computes normalized character error from final
transcripts. The default paced run reports first partial/final event times
relative to file replay; unpaced mode measures processing without simulated
capture timing. The Vosk CLI in `scripts/stt/evaluate_offline_stt.py` adds no
dependency and never downloads a model or audio. Focused tests use a fake
engine and generated PCM files; they do not establish recognition quality.

The temporary `/tmp/kyrin-stt-eval-20261003` corpus/model directory is absent
in the current environment. No STT model weights are tracked in Git. An
official `vosk-model-small-fa-0.42` ZIP was downloaded and kept in the ignored
local `models/archive/` directory. Its extracted files live in `models/local/`;
ZIP CRC passed and the bundled WAV/reference
were processed with paced 20 ms chunks. Vosk loaded and produced “من عرضه این
کار رو ندارم” against “من عرضه اين کارو ندارم”; the defined character metric
counted 2 edits in 22 normalized characters. The one-file result shows that
this local model runs, not that it is suitable for KYRIN commands or other
languages. A small six-command Persian corpus was then recorded with explicit
consent using one USB microphone and kept under Git-ignored
`datasets/stt/recordings/`. The speaker confirmed the `fa-05` reference. On
these six clips, Vosk exactly matched four; aggregate normalized CER was
12/133 (9.0%). It misheard “کایرین” as “طاهری” and the `fa-05` phrase
“چت علی را در واتساپ” as “ساعت علی را در صبح”. This is a local baseline, not a
representative quality claim. A first cross-engine file comparison has now
been run, but representative multilingual samples and live comparison remain
open. See `docs/stt/STT_EVALUATION_FA.md`.

The repository now tracks `models/README.md` and `models/.gitignore` so the
development model location and recorded ZIP checksum are discoverable while
the large weights remain outside Git. This is a development storage
convention, not a product default model or installed-app storage decision.

---

## 41. Experimental Whisper CPU Comparison

The user requested a Whisper comparison and emphasized that the eventual
product should also work on ordinary machines without a 16 GB GPU. No existing
Whisper weight file was found in the project or common local model caches.
`whisper.cpp` tag `v1.9.4` was built for CPU under ignored `build/tools/`;
CMake was installed only in the ignored project virtual environment. No
production dependency, STT contract or live pipeline was changed. Two
multilingual weights are retained under ignored `models/local/whisper.cpp/`:
full-precision `ggml-small.bin` (487,601,967 bytes) and quantized
`ggml-large-v3-turbo-q5_0.bin` (574,041,195 bytes). Paths and hashes are in
`models/README.md`. An aborted large-turbo download was removed.

On the same six consented recordings converted to common 16 kHz mono PCM,
normalized CER was 8/133 (6.0%) for Vosk, 18/133 (13.5%) for Whisper small,
and 25/133 (18.8%) for quantized Whisper turbo. The earlier Vosk test using
KYRIN's own resampler gave 12/133 (9.0%), reproduced twice; the resampler
path affected the `fa-05` transcript. Whisper CLI processed complete files
on CPU with four threads: about 2.4–2.6 seconds per clip for small, and
8.6–8.9 seconds for turbo-q5. These are local file-process measurements,
not live partial-text latency. Peak measured RSS for one clip was about
750 MiB and 793 MiB, respectively. Vosk's unpaced common-input processing
took about 0.13–0.23 seconds per clip with its model already loaded, but this
timing is not directly comparable with a separate Whisper process per clip.

The six-file, one-speaker experiment does not justify selecting or rejecting
Whisper as the product engine. `whisper.cpp` CLI was kept outside the streaming
`SpeechToTextEngine` contract because a whole-file transcription test cannot
demonstrate partial updates. GPU execution, broader language data, and live
command latency remain open. Full conditions and caveats are in
`docs/stt/WHISPER_CPP_COMPARISON_FA.md`.

## 42. Initial Whisper Rolling-Window CPU Replay

The user approved a multilingual corpus and a separate live-CPU diagnostic.
English command prompts and one optional exploratory German prompt were added
as separate templates; at that point, no new microphone recording had
occurred. The speaker
is fluent in Persian and English and has some German, so German speech from
this speaker cannot serve as a definitive quality result. Public multilingual
audio with references remains to be selected and recorded by source/license.

An isolated `scripts/stt/benchmark_whisper_replay.py` now replays an existing
consented WAV at recorded speed to a temporary loopback-only `whisper-server`
with one preloaded CPU model. It logs each overlapping window's transcript,
request time and lateness. No production dependency, STT contract, live
pipeline or command execution path changed. On `ggml-small.bin`, four threads,
the `fa-03` negative command (3.6 s) took 9.33 s overall at a 1 s window step
and 6.26 s at a 2 s step; first nonempty text arrived at 3.05 s and 4.24 s,
respectively, from file start. The `fa-02` positive command (2.5 s) took
6.07 s at a 2 s step, with first text at 4.04 s. At the 1 s step, processing
accumulated 3.70 s of dispatch lag. These are single-run, rolling-window
diagnostics, not actual microphone or native streaming STT measurements and
not grounds to select a product default. See
`docs/stt/WHISPER_LIVE_REPLAY_FA.md` and local ignored JSON results.

The user then explicitly authorized the first English recording, “Open
Telegram.” A short, near-silent attempt was rejected by the recorder. A
second 20 s capture yielded a 2.5 s crop (`en-02`, from 16.7–19.2 s); the
original capture was retained under ignored `datasets/stt/recordings/raw/`.
Whisper small returned the exact English reference on that crop. With a 2 s
rolling-window step and explicit `en`, first text arrived at 3.94 s and total
replay/processing took 5.89 s. With automatic language detection, first text
arrived at 5.79 s and total took 9.59 s. These are individual runs on one
English clip and cannot establish multilingual quality or a universal cost
for automatic language detection. No other new voice or public audio was
recorded/downloaded at that point. The English local manifest initially listed
only `en-02`.

The user also authorized recording the negative English command `en-03`.
A 2.7 s crop (22.2–24.9 s of the 30 s capture) was retained for scoring and
the original was preserved in the ignored recordings/raw directory. Whisper
small transcribed the whole crop exactly. With 1 s rolling windows, explicit
English yielded first nonempty text at 2.93 s and full reference at 4.89 s;
auto language yielded 4.79 s and 8.61 s, respectively. Both first nonempty
texts contained “Do not” in this one clip, but the worker accumulated 2.19 s
and 5.91 s maximum dispatch lag, respectively. The local English manifest now
lists `en-02` and `en-03`. No command was executed.

## 43. English Vosk Desktop Default Candidate

The owner selected English as the only initially installed language for V1
desktop and chose `vosk-model-en-us-0.22-lgraph` as the intended default.
Users should be able to add other compatible languages later; the model manager
and application settings do not exist yet. This is a product-direction decision,
not evidence that the model is accurate enough for KYRIN commands on ordinary
machines. The replaceable STT contract remains unchanged.

The official 130,557,655-byte ZIP was downloaded to ignored `models/archive/`,
checked by ZIP CRC and safe-path inspection, then extracted to ignored
`models/local/`. Its local SHA-256 and exact paths are recorded in
`models/README.md`. No product dependency or runtime default was added.

Two previously consented English commands were replayed through the existing
Vosk evaluator on CPU, both with KYRIN's 48-to-16 kHz conversion and with
previously prepared 16 kHz WAVs. `en-02`, “Open Telegram,” became “open filler
drop” in both paths; `en-03`, “Do not open Telegram,” became “do not open
telegram.” The two-file normalized CER was 8/33 (24.2%), which is not a
representative quality estimate. The paced run loaded the model in about
0.49 s and reached about 470 MiB peak RSS for the whole process. Detailed
outputs and timing are in ignored `datasets/stt/results/`, summarized in
`docs/stt/STT_EVALUATION_FA.md`. Further commands and speakers, target-machine
memory/latency checks, and actual microphone validation are required before
shipping this choice. No desktop command was executed in this evaluation.

The speaker then consented to three more English prompts. One near-silent
`en-01` attempt was rejected; the USB microphone input level was adjusted from
14% to 60% and the three prompts were recorded successfully. First-utterance
crops of `en-01`, `en-04`, and `en-05` and their original raw recordings remain
under ignored `datasets/stt/`. Vosk transcribed `en-01` as “corinne opened the
door,” `en-02` as “open filler drum,” `en-03` correctly, and `en-05` correctly.
The first `en-04` crop was transcribed “open alleys charge in telegram.” The
speaker then clarified that they actually said Telegram, not the template's
WhatsApp. The initial five-file scoring report was therefore invalidated and
marked `UNVERIFIED-REFERENCE`; it must not be cited as a model-error result.
Four clips with usable references were replayed and yielded CER 20/80 (25.0%),
still far too small and single-speaker to generalize. A later `en-04` crop
yielded “open alleys chart in what's up,” but its exact spoken reference is
unconfirmed and it is not scored. The model loaded in about 0.46 s and the
whole evaluation process peaked at about 491 MiB RSS on this machine. See
`docs/stt/STT_EVALUATION_FA.md` for the full results and limits.

A new `en-06` recording then explicitly captured “Open Ali's chat in
WhatsApp,” and the speaker confirmed the word WhatsApp. Vosk returned “open
alleys child in what's up”: the app name was rendered as ordinary words, but
the contact/chat phrase was wrong. A five-file replay using only confirmed
references (`en-01`, `en-02`, `en-03`, `en-05`, `en-06`) yielded normalized CER
29/107 (27.1%) on this one speaker. The model loaded in about 0.47 s and the
whole process peaked at about 493 MiB RSS on this machine. This is a small
diagnostic, not a production accuracy guarantee. No action was executed.

## 44. Spoken Application Name Matching Prototype

An optional `CatalogSpokenAppResolver` now reads a cached snapshot of
registered application labels and configured spoken aliases. Only explicit
platform-ID-to-KYRIN-ID bindings are eligible. The command interpreter can use
it for simple English/Persian open-app phrases. Exact matches can form a final
command; approximate matches require confirmation and ambiguous labels require
a choice. The existing final-only `ActionGate` and explicit executor mapping
remain separate. The microphone diagnostic exposes opt-in bindings/aliases and
still executes no desktop actions. The similarity parameters are provisional,
and no product settings UI or cross-platform catalog exists yet. See
`docs/desktop/SPOKEN_APP_MATCHING.md`.

## 45. Verified English Command Decision Replay

On 2026-10-05 the five user-confirmed English command WAVs were replayed
through the selected local Vosk candidate, then both the confirmed references
and resulting transcripts were separately passed through the demo interpreter,
catalog-assisted app-name resolver, and final-only ActionGate. STT output was
identical to the prior five-file run (CER 29/107). No wrong action was
authorized. Two basic Telegram requests failed because STT misheard their
targets; two other commands failed even with perfect reference text because
the demo parser does not cover compound navigation or that English chat form.
No OS executor or microphone was used. The reusable decision replay tool and
full limits are in `docs/commands/VERIFIED_ENGLISH_COMMAND_REPLAY_2026-10-05.md`.

## 46. Pending English Reference Recheck and Shared-Audio STT Comparison

The owner later questioned whether every word in the English WAVs matches the
previously accepted reference text. The five clips were checked for audio
format and signal, then converted to a shared 16 kHz PCM set. On those same
files, local Vosk, `whisper.cpp` small, and quantized large-v3-turbo were
compared without network or desktop actions. Both Whisper variants recognized
the short `Open Telegram` clip where Vosk did not; small was faster than turbo
in this file-based CPU setup. The old-reference error rates are provisional,
and neither Whisper candidate has a production streaming adapter. The speaker
has been asked to listen to `en-01`, `en-02`, and `en-06`; any uncertain words
must be corrected or rerecorded before scoring. Details and limits are in
`docs/stt/ENGLISH_AUDIO_REFERENCE_AUDIT_2026-10-05.md`.

## 47. English Whisper Small Live Adapter

The speaker re-listened to `en-01`, `en-02`, and `en-06` and confirmed their
displayed reference wording. The owner chose to stop expanding the comparative
corpus for now and proceed with the locally installed Whisper `small` weights
for English STT development, prioritizing correct command text over the fastest
provisional response. This supersedes the earlier English Vosk default direction
for current development; it does not remove Vosk or choose a packaged default.

`src/kyrin/stt/backends/whisper.py` now implements the existing STT engine and
session contracts with optional turn hints. `whisper_server.py` owns a preloaded
local, CPU-only `whisper.cpp` server bound to loopback, with no model download or
new Python dependency. The live pipeline passes VAD-confirmed start/pause
markers in audio order only to turn-aware sessions. Streaming sessions such as
Vosk retain their independent source-to-STT conversion path. Whisper previews
are partial; only a full-turn re-transcription after a confirmed pause is final.
Turns over 30 seconds retract previews with empty final text. Listening remains
continuous across pauses.

Focused STT/pipeline tests passed. A local `en-02.wav` run produced provisional
`Open Telephone.` and final `Open Telegram.` with the real server; a paced file
run through Silero VAD and `LiveSpeechPipeline` produced partial and final
`Open Telegram`. No microphone or desktop command was used in these validations.
Measured live microphone latency, performance on other hardware, GPU support,
multi-language switching, and packaging remain open. See
`docs/stt/WHISPER_LIVE_ADAPTER.md`.

## 48. First Whisper Microphone Dry Run

The owner read `Open Telegram.` and `Do not open Telegram.` into the selected
USB microphone during a 25-second local, no-save, no-action diagnostic. The
first turn finalized as `Open Telegram.` and was authorized only as a dry-run
request. The negative turn finalized as `to open telegram.` despite the owner
confirming they spoke `Do not open Telegram.` exactly. The interpreter produced
no command for that text, so no action was authorized. Each final arrived
about 3.5 seconds after its VAD pause; backlog wait appeared near 1024 ms and
then recovered. A separate recorded-speed replay of the previously confirmed
`en-03.wav` through the same new pipeline preserved `Do not open telegram.`.
The live failure remains unexplained because the microphone audio was not
saved. The owner then consented to one 15-second local, Git-ignored WAV of the
same negative sentence at `datasets/stt/recordings/raw/live-negation-2026-10-05.wav`.
VAD found one speech interval; recorded-speed replay through the full new
pipeline finalized correctly as `Do not open telegram.` The original failure
did not reproduce and its exact cause remains unknown. A focused scheduler
fix now excludes pre-roll from the first-preview timer. On one subsequent
recorded-speed `en-02.wav` run, the correct final arrived about 1.92 seconds
after VAD pause. This is not a live microphone latency guarantee. See the
live-adapter document for conditions and limits.

## 49. Offline Spoken Repeat Prompt and Playback Guard

The owner approved text and offline voice feedback for unclear commands.
`CommandCoordinator` already emitted a `REPEAT_COMMAND` request with
`TEXT_AND_VOICE` only after an incomplete or unrecognized **final** command
transcript; partial text and ordinary speech stay silent. The demo interpreter
now also classifies the observed `to open telegram` STT result as unclear,
without authorizing an open action. A clear `do not open telegram` still
authorizes nothing.

`ResponseSpeaker` is a separate, replaceable speech-output contract with a
bounded background queue. The Ubuntu adapter uses local Speech Dispatcher and
its `espeak-ng` module. The `commands` microphone diagnostic prints the
localized text and speaks responses requested as `TEXT_AND_VOICE`, unless
`--no-voice-responses` is supplied. It still never executes desktop actions.
`PlaybackGuardInput` preserves continuous microphone capture but substitutes
silence while a response is queued/playing and for a short tail, preventing
the diagnostic from feeding its own voice back to VAD/STT in that interval.
The guard also suppresses user speech during playback; barge-in is not yet
supported. Text remains available on speech failures. No network or new
Python dependency was introduced.

Focused unit tests cover final-only repetition, the dropped-negation result,
asynchronous speech dispatch, backend command construction, and audio guarding.
A local `spd-say` playback command returned successfully on the development
machine. Audible output and real microphone echo behavior still need owner
listening validation. See `docs/responses/OFFLINE_SPEECH_OUTPUT.md`.

## 50. Owner-selected TTS Trial and Ordered English Commands

In a local, Git-ignored listening trial, the owner preferred the English
Kitten v0.2 sample over Piper after adjusting their speaking rates. This is a
**temporary voice preference**, not a product dependency, packaged voice, or
new default. The owner deferred TTS integration and wants to revisit voice
quality later. Trial files are under `downloads/tts-trials/`; product code was
not changed for this comparison.

The owner approved ordered commands and explicitly chose partial completion:
when a later step is unsupported, perform an earlier supported step and tell
the user what remains undone. `CommandPlan` and `CommandPlanResolution` now
represent two or three ordered intents from one final utterance. The current
demo parser recognizes exact two-step English forms such as `Open Telegram and
open Alice chat`; it does not claim general compound-language understanding.
`ActionPlanRunner` applies `ActionGate` and an injected executor one step at a
time, with a distinct action key per step. It stops on a block, failure,
unknown result, or pending confirmation. Before a supported chat step it
requires a fresh foreground-app observation; `LAUNCH_ACCEPTED` or old context
cannot stand in for that observation. An
unsupported chat step gives a specific localized notice after an earlier app
step. The microphone diagnostic prints this plan and per-step dry-run gate
decisions, but still executes no desktop actions. Focused tests use a fake
executor. See `docs/commands/MULTI_STEP_COMMANDS.md`.

## 51. Controlled Ubuntu Live Open-App Dispatch

The owner approved a bounded microphone-to-application integration after
reviewing the existing dry-run command and action layers. The live diagnostic
still defaults to dry-run. With `--mode commands`, `--execute-actions`, and
explicit `--launch-app KYRIN_APP_ID=/absolute/path.desktop` bindings, a final
command decision may launch only a bound app through the existing
`LinuxDesktopEntryExecutor`. The action policy uses those same app IDs as its
allowlist. No dependency or core action contract changed.

Single-step finals pass through `ActionGate`, `ActionExecutor`, and
`record_result`; ordered plans pass through `ActionPlanRunner`. Partial
transcripts never reach execution. The diagnostic prints localized action
feedback, preserving the distinction between `LAUNCH_ACCEPTED` and confirmed
completion. Chat and all other desktop actions remain unsupported. Focused
tests cover final-only execution, correction from a partial open command to a
negated final, unknown text, allowlist denial, duplicate suppression, and
ordered-plan stopping behavior without touching desktop hardware. In an owner
validated microphone smoke test, Whisper finalized `Open Telegram.` and the
launcher returned `LAUNCH_ACCEPTED`; the owner confirmed the Telegram window
opened. This is a single local observation, not a general STT accuracy claim.
The initial 45-second run then failed while stopping microphone capture. A
short graceful-read wait with abort fallback was added; a later five-second VAD
run and eight-second Whisper run both ended normally with exit code zero. The
full voice-to-action run was repeated during the queued-dispatch work below. See
`docs/actions/LIVE_OPEN_APP_INTEGRATION.md`.

## 52. Bounded Ordered Action Worker

The owner approved moving live OS actions off the microphone event consumer
before making KYRIN a persistent listener. In explicit execution mode, final
single-step decisions and ordered plans enter a small bounded FIFO. One
`QueuedActionDispatcher` worker owns the existing `ActionGate` and Linux
executor, preserving their order and avoiding shared mutable policy state.
Partial transcripts and no-command finals are not enqueued. A full queue
returns a localized `BUSY` notice; on shutdown, commands that have not started
receive `CANCELLED` notices, and an active action gets bounded completion time.
Dry-run mode remains synchronous and never invokes an executor. No new
dependency or platform action was added. Focused tests cover blocking executor
behavior, order, capacity, cancellation, and an ordered plan. A 25-second live
Whisper-to-queued-action run finalized `Open Telegram.`, produced
`LAUNCH_ACCEPTED`, and exited with code zero. The owner confirmed Telegram
opened or became active. Automated window verification and broader latency
measurements remain open. See `docs/actions/LIVE_OPEN_APP_INTEGRATION.md`.

## 53. Fresh Foreground Confirmation After App Launch

An optional `ObservedAppExecutor` wraps the platform launcher only when an
exact GNOME active-app binding is configured. After a `LAUNCH_ACCEPTED` result,
it makes a small bounded set of fresh foreground observations. A match with
the requested internal app ID produces `CONFIRMED` and carries
`observed_active_app` through `ActionGate` into user feedback; otherwise the
accepted result is unchanged. Only feedback with a matching observed app says
the requested app is now active. This confirms foreground state at observation
time, not whether the launcher created a new window or caused focus to change.
No new dependency was added. Unit tests cover matching, delayed, missing, and
mismatched focus. A 30-second live Whisper command finalized `Open telegram.`,
reported `CONFIRMED`, and exited cleanly. The owner confirmed Telegram became
active. See `docs/actions/LIVE_OPEN_APP_INTEGRATION.md`.

## 54. Consecutive Live Commands and App Process Lifetime

A 45-second live microphone test recognized and dispatched four separate final
commands in one listening session: Telegram, browser, Telegram, browser. The
owner confirmed the same foreground sequence. The first two launches returned
`LAUNCH_ACCEPTED`; fresh observations confirmed the later two. Listening did
not stop after the first action. The owner also noticed Chrome closing at the
end of the diagnostic. A local reproduction showed Chrome running in the
diagnostic's process session and exiting when that session ended. Starting
`gio launch` in a separate process session kept Chrome open after the launching
command exited. The Linux executor now requests a new session for the launcher;
focused automated tests assert that invocation. This does not change action
result semantics or claim portability beyond the observed Ubuntu/GNOME setup.

## 55. Opt-In Continuous Listening Trial

The owner approved a controlled longer listening trial before a packaged
always-on application. The command microphone diagnostic now accepts
`--until-stopped`, mutually exclusive with the existing `--seconds` option.
Its default remains a 10-second dry run, and bounded runs still cap at 120
seconds. The opt-in mode keeps the same `SpeechSessionController`, command
coordinator, action queue, and engine alive until Ctrl+C or a terminal error.
Silence does not reset command context. Manual interruption requests controller
stop before the existing cleanup closes the action worker, optional speaker,
and STT engine. The mode does not save audio or enable actions on its own.
Focused tests cover argument boundaries and resource cleanup without opening a
microphone. A roughly three-minute dry-run microphone trial on this Ubuntu
machine kept listening across about 90 seconds of silence and later recognized
`Open browser.`; earlier it misheard `Open Boser.` and issued no action. The
owner thinks they repeated the final browser phrase, so the two final browser
segments are not evidence of an unintended duplicate. Several Telegram finals
were also produced. Backlog wait/ready notices occurred, but no overflow or
recovery failure was observed. Manual Ctrl+C exited with code zero, and both
the diagnostic Python process and the local Whisper server were gone afterward.
Two process snapshots showed roughly 94 MiB RSS for the diagnostic and
637–641 MiB RSS for the Whisper server; this short run cannot establish
long-term memory stability. No desktop action or audio recording occurred.
See `docs/actions/LIVE_OPEN_APP_INTEGRATION.md`.

## 56. Reusable Live Command Runtime

The owner approved moving continuous command orchestration out of the terminal
diagnostic. `LiveCommandRuntime` in `src/kyrin/runtime/command_runtime.py` now
consumes `SpeechSessionController` events, asks `CommandCoordinator` for
decisions, reads fresh app focus only for final transcripts, and routes final
commands through the existing bounded action worker. In dry-run mode it uses
the same action policy without launching applications. Session boundaries
invalidate provisional speech segments but do not clear dialogue context;
silence alone has no reset behavior. The runtime exposes `run()` and `stop()`
and sends events to injected presentation callbacks. The terminal diagnostic
still selects microphone, VAD/STT adapters, Linux bindings, response output,
and optional timer, and owns the STT engine and speaker cleanup. No new
dependency, default action permission, platform integration, or model choice
was introduced. Deterministic tests cover multiple finals across a stream
boundary, partial-positive/final-negated speech, worker execution, and the
existing manual stop path. A packaged background app and longer stability
validation remain future work.

## 57. Registered App Names from Explicit Launch Bindings

The owner prioritized correct execution and asked KYRIN to use system app
names and desktop context without slowing the live audio path. The Ubuntu
command diagnostic now identifies an exact `--launch-app` desktop-entry path
in the XDG registered-app catalog at startup. For such entries it automatically
binds the installed display name and the configured internal app ID to the
existing `CatalogSpokenAppResolver`. The interpreter can recognize that name
without a duplicate `--spoken-app-binding`; near matches still require user
confirmation and `ActionGate` still restricts actual execution to explicitly
allowed apps. Unregistered paths gain no inferred name, and conflicting
explicit bindings fail at startup. The resolver uses a startup snapshot, so
no catalog scan is added to each partial transcript. Fresh foreground state
continues to be read only for final transcripts when explicitly configured.
Deterministic tests use temporary desktop entries and a fake executor. Names
that overlap command syntax, such as a name beginning with "Chat", remain an
open interpreter ambiguity. No system settings are changed or UI internals
inspected by this step.

## 58. Exact App-Name Versus Chat-Command Ambiguity

The owner prioritized command correctness before other incomplete work. A
registered app such as "Chat One" previously matched the chat-command grammar
before the spoken app name was considered. The demo interpreter now detects a
unique plausible registered app name that also matches a chat form and emits an
app-or-chat clarification on a final transcript. The app opens only after an
explicit "app" reply; "chat" follows the existing fresh-context rules. A
generic "yes" repeats the question, while a negated final never acts. Such an
ambiguity inside a compound command rejects the whole plan to avoid executing
an uncertain fragment. This is a safety rule for the limited demo interpreter,
not general natural-language disambiguation. Focused tests use a fake catalog
and do not launch desktop apps. No STT/TTS backend or new dependency changed.

## 59. First Ubuntu Application Settings Slice

The owner approved building the Ubuntu application in ordered slices and
specified automatic start after user login, an in-app listening switch, and
visible CPU/GPU/AUTO choices for both STT and TTS. An unavailable GPU choice
must explain the reason and keep the last valid active setting rather than
disappearing or silently falling back. The current Vosk/Whisper adapters still
support CPU only, and TTS has no compute-device or speed contract yet.

`AppSettings`, `SttSelection`, and `AllowedApp` now describe immutable saved
preferences. The default requests login start and listening, but selects no
STT model, enables no desktop action, and grants no app binding. The future
application must enter setup without microphone capture in that state.
`JsonSettingsStore` uses an injected absolute path and version-1 JSON; the
Linux path helper points to the user's XDG config location. Missing files
return defaults. Invalid, duplicate-key, or unknown-version files raise a
settings error and are not overwritten. Saving writes a private temporary
file in the same directory and atomically replaces the old file. Tests use
temporary directories and cover round trips, preservation on bad input or a
failed replacement, permission defaults, and path selection. This slice does
not create real user settings, autostart entries, a running application, or a
model manager. No dependency was added.

## 60. UI-Independent Application Lifecycle

The next approved slice added `ApplicationController` in
`src/kyrin/app/controller.py`. It receives saved settings and a factory for a
managed runtime session, rather than choosing STT, microphone, desktop, or UI
implementations itself. Listening disabled yields PAUSED; a missing STT model
yields SETUP_REQUIRED without constructing audio. A configured session runs on
one worker thread. Stop requests do not wait on microphone shutdown in the
calling thread, and a second live session is rejected. Factory, runtime, and
cleanup errors remain visible through a status snapshot. RUNNING means the
runtime has begun, not that microphone capture has already been observed.
The factory's context manager remains responsible for closing the model,
speaker, and action resources. Tests cover pause/setup, stop during startup,
restart, duplicate prevention, slow stop, errors, and a real
`LiveCommandRuntime` with a fake event source. This slice changes neither the
terminal diagnostic nor the user's audio devices, settings, startup entries,
or model files. A concrete factory and product UI remain future work.

## 61. Ubuntu Live Session Composition

The owner approved the next implementation slice. `UbuntuSessionFactory` in
`src/kyrin/app/platforms/ubuntu.py` now connects saved app settings to the
existing live runtime. A microphone resolver records a stable host-API/name
selection and resolves the current PortAudio index before startup and on each
retry. Missing or ambiguous selections fail visibly. Vosk and Whisper remain
replaceable through injected STT openers; their standard adapters are CPU-only
and reject explicit GPU rather than falling back silently. The factory
preserves the existing VAD, speech-session recovery, command coordinator,
action gate, optional desktop observer, response presenter, optional visual
adapter, and optional injected speech synthesizer. Installed app names and
launch paths are limited to explicit allowed-app desktop-entry bindings;
actual action execution remains disabled by default. Focused fake-adapter
tests cover dry run, allowlisting, setup failures, and resource cleanup. No
physical microphone, real desktop launch, user settings file, login startup,
new dependency, or model download was used in this slice. The Ubuntu control
window and model/TTS settings remain future work.

## 62. First Qt Control Window

The owner explicitly selected PySide6. The project now offers its smaller
`PySide6_Essentials` distribution as an optional `desktop` extra and a
`kyrin-desktop` entry point. A small
right-to-left Qt window controls the existing `ApplicationController` and
persists microphone/STT choices through `JsonSettingsStore`; it does not move
audio work onto the GUI thread. Final transcript and presented response
events cross a Qt signal to the UI; their shared event type is independent of
Ubuntu and Qt. Explicit GPU remains visible and fails
without changing the last saved choice because the current STT adapters are
CPU-only. Applying a model change requests the old session to stop before
restarting. The window minimizes on close and has an explicit Quit control.
Offscreen tests with fake sessions cover GPU rejection, listening persistence,
stop-before-restart, and malformed settings preservation. `PySide6_Essentials`
6.11.2 was installed into `.venv` after the sandboxed download failed, and the
tests were rerun there. No live
microphone, real user settings file, login startup, or desktop launcher was
changed. Model management, TTS controls, packaging and single-instance login
startup remain open work.

## 63. English control center and static cosmic dashboard

The owner selected the dark fifth cosmic concept for the application and
requested English control text plus a path for adding UI languages later. A
multi-page Qt Widgets control center now separates Dashboard, Audio Input,
Speech Recognition, and Preferences. The built-in UI strings are English;
interface locale selection and complete JSON language-pack import are separate
from the STT language. The selected concept art is packaged as a static,
aspect-preserved dashboard image. The owner explicitly dropped real-time 3D
after reviewing its graphics and installation costs. The temporary Qt Quick 3D
scene and `PySide6_Addons` dependency were removed. The microphone/STT/runtime
controller interfaces were not changed. The app still lacks a portable
installer, TTS configuration, login startup, and a single-instance launcher.

The control-center follow-up made UI language loading recoverable: invalid
preferences or a missing selected pack now open English, show an error, and
leave the original file untouched. Catalog strings are cached rather than read
on every status update. Runtime language changes refresh the action status and
microphone label, while unsaved speech settings remain in the form. UI content
uses plain-text labels so transcripts and imported strings are not treated as
rich text. Qt tests inject a temporary UI config directory. A full test run
passed with 308 tests, and an isolated offscreen startup reached the event loop.
No physical desktop presentation or microphone validation was performed in
this follow-up.

## 64. One Qt control instance per user session

The next desktop-lifecycle slice adds a `QLockFile` held for the control
process lifetime and a local Qt socket in the user-session runtime directory.
Opening `kyrin-desktop` again sends an activation request to the existing
window, instead of constructing a second microphone runtime. A lock owner may
remove a socket abandoned by a crashed process; a second process may not take
over a live socket. The activation raises a minimized window. Tests cover
second-instance activation and abandoned-socket recovery without audio.
This slice does not install a desktop menu entry or register login startup;
the saved `start_at_login` preference still has no operating-system effect.

## 65. User-scoped Ubuntu launcher and login startup

The owner approved the next lifecycle step. `XdgDesktopRegistration` now
generates managed XDG desktop entries for the application menu and per-user
autostart directory. The Qt Preferences page exposes an explicit login-startup
control. Disabling it removes only KYRIN's autostart file. Unknown same-named
files are not overwritten, and a failed settings save attempts to restore the
previous registration. Unit tests use temporary XDG directories; both desktop
entries pass Ubuntu's `desktop-file-validate`. On this host, the owner-approved
registration was installed for the current user and points to
`/mnt/ai_projects/KYRIN/.venv/bin/kyrin-desktop`. The current settings have no
selected STT model, so a future login opens setup without microphone capture.
Real next-login behavior is not yet observed; the development-environment
launcher is not portable if the project directory moves. A stable packaged
installation and model-management UI remain future work.

## 66. Dashboard copy over the cosmic artwork

The owner clarified that the first dashboard should use the selected cosmic
image across the entire content panel, with the welcome title and two supporting
lines placed on the image. The previous separate right-hand copy panel was
removed. The black hole remains visible on the left; a translucent right-side
shade and a title shadow keep text readable. The existing UI language keys
still supply the text. The dashboard is a static image and does not add a
continuous rendering loop. Offscreen previews were inspected at the normal
window size and the current minimum size; live display feedback remains with
the owner.

## 67. Owner-selected original black-hole K logo

The owner chose the second of four black-hole logo concepts and explicitly
preferred its original generated image over a later simplified revision. The
original transparent PNG was copied unchanged into the Qt assets as
`kyrin-logo.png` at that time. The control window displays the active logo
beside the KYRIN name; the Qt application uses it as its window icon, and
managed XDG desktop entries include its packaged absolute path. The user's
existing menu and autostart entries were refreshed without changing their
enabled state. A built wheel contains
the PNG and the desktop entries passed `desktop-file-validate`. An offscreen
window preview was inspected. A future packaged release may need
multi-resolution icon files.

The owner later requested a more realistic rendering of the same emblem across
the application. The original PNG remains as `kyrin-logo-original.png`, while
the newly rendered transparent PNG now occupies `kyrin-logo.png`. The K
silhouette and black-hole center remain recognizable. The Qt window icon,
sidebar logo, and existing XDG menu and autostart entries all reference that
unchanged active path; their live appearance after application restart remains
for the owner to inspect.

The owner then reported that the applications menu showed a generic gear and
the running application's tooltip said `Python 3`. Inspection found that the
desktop entry already resolves to the selected PNG, but the Qt process did not
declare its matching desktop-file ID. Qt now sets that ID and its display name
to `KYRIN` before creating the window. The owner restarted the application and
confirmed that its menu/dock identity and icon now appear correctly.

The owner later selected the luminous Kailarin black-hole K from the brand
exploration as the application and GitHub-profile logo. A circle-safe export of
that same artwork is saved at `assets/brand/kailarin-v3-profile-safe.jpg`.
The application's shared `kyrin-logo.png` was replaced with a 512 px PNG
export of that image, so its window, sidebar, and desktop-launcher references
continue to use the same path. The vector studies in `assets/brand/` were not
selected. The browser sign-in was completed, and the profile image was uploaded
to the owner's GitHub account `mohammadhosseinzakeri10`. GitHub confirmed the
update and displayed the new image in the profile settings; propagation across
the site may take a few minutes. The application asset passed a focused Qt
load check and desktop registration tests; a live application restart has not
been observed yet.

## 68. Desktop action permissions in the Qt control center

The owner authorized completing five follow-up steps after a repository audit.
The existing Ubuntu control-center work was saved in local Git commit `6eb64f1`
without pushing to GitHub. The Qt window now has a Desktop Actions page with
searchable visible XDG launchers. The user can select explicit app bindings and
enable action execution; a session is stopped before changed settings are saved
and restarted. Saved hidden or removed entries stay visible for review.
Permission checks remain in the existing action gate, not in the page.

The Qt entry point now reuses the XDG catalog for both the picker and runtime.
It connects the existing GNOME active-app observer and visual-status sink only
when their optional Shell endpoints are available. The owner has previously
verified the character and a Telegram launch separately. The new end-to-end
control-center path has passed automated tests; its live voice test remains to
be confirmed. UI language packs imported before these new labels remain usable
with English fallbacks for the added strings; new imports require all labels.

## 69. Local Whisper GPU execution and actual-device reporting

The owner prioritized completing GPU STT on capable hardware while preserving
CPU and AUTO choices. The current `whisper.cpp` adapter can now start separate
CPU and CUDA-enabled server executables for the same model weights. CPU starts
with `--no-gpu`. Explicit GPU fails if the CUDA runtime is missing or does not
confirm a CUDA backend; it cannot silently fall back to CPU. AUTO first tries a
configured GPU runtime and falls back to CPU if GPU startup fails. Vosk remains
CPU-only. The session's actual compute device is emitted to the Qt control
center, separately from its selected preference. Paths are configured through
`KYRIN_WHISPER_SERVER` and `KYRIN_WHISPER_GPU_SERVER` or executable names on
`PATH`.

On this Ubuntu development machine, an isolated CUDA 13.1 toolkit and pinned
`whisper.cpp` v1.9.4 GPU build were placed under Git-ignored `build/tools/`.
The toolkit was not installed into the operating system. The existing
multilingual Whisper `small` weights worked on the local RTX 5060 Ti. Three
short recorded English clips had a warm mean request time of about 1.95 s on
CPU and 0.032 s on GPU; this small sample is not a general performance or
quality promise. A real GPU engine session returned the expected text and a
CPU-only binary placed in the GPU slot was rejected. A live microphone dry run
reported an actual GPU session and recognized `Open Telegram` without storing
audio or executing a desktop action. The two final segments matched the owner's
later clarification that they said the sentence twice. The desktop entry point
now discovers CPU and GPU server executables beside its installed script as
well as from explicit environment variables or `PATH`. Git-ignored links in
the local `.venv/bin/` point to the two builds; the app's discovery path opened
the GPU engine with the existing model successfully. This is local development
setup, not a portable runtime package. The detailed scope and remaining
release work are in `docs/stt/WHISPER_GPU_EXECUTION.md`.

## 70. Engine-aware speech model library in the control center

The owner requested separate CPU and GPU model views and import controls,
alongside a default view of all models. They clarified that a model usable on
both devices should be stored once and listed in both views. The control center
now includes those three views. It imports local Vosk directories and
`whisper.cpp` GGML files into a per-user XDG data library in a background
thread, using a private staging directory before publishing the model. The
library derives device compatibility from the backend: Vosk is CPU-only and
Whisper supports CPU or GPU with the appropriate runtime. Import location does
not itself assert compatibility. Reimporting identical content and language
uses the existing stored copy. The current external model path remains visible
and usable. Selecting from All requests AUTO; selecting from a device-specific
view requests that device and fills the existing Speech Recognition form for
explicit saving. The library does not download models or install GPU software.
Format checks are intentionally lightweight; actual model loading and hardware
availability are verified when the selected runtime starts. See
`docs/app/MODEL_LIBRARY.md`.

The owner found that both existing Whisper files were rejected by the new
importer. Investigation reproduced the problem: the on-disk GGML magic is a
little-endian integer, while the first implementation compared its bytes to
the display-order text `ggml`. The importer now reads the numeric magic in
little-endian order. Both local Whisper files passed validation and a full
temporary import, appearing in both CPU and GPU views. No user model files or
settings were moved during this diagnosis.

## 71. Desktop Actions picker usability

The owner reported that clicking an app row did not toggle its checkbox and
that selecting many apps required individual clicks. The Qt picker now treats
row clicks and checkbox clicks as one toggle each. It adds Select all shown and
Clear shown controls scoped to the current search results, plus a selected
count. With no search filter, Select all shown selects all listed installed
apps. Bulk selection never turns on action execution; the separate permission
checkbox and Save changes remain required. Qt mouse-click tests cover both
click targets and filtered bulk selection without modifying real user
permissions.

## 72. Read-only active-window observation foundation

The owner approved the first step toward desktop-aware browser and chat work:
an on-demand observation of the focused window before adding new actions.
`ScreenObserver` is a platform-neutral, read-only contract. An Ubuntu adapter
uses the existing GNOME extension's new desktop-ID/PID method and an isolated
AT-SPI helper to return bounded visible labels. It never clicks or runs a
command. A failed or ambiguous identity match returns unknown. The extension
update is installed for the current user but may require the next desktop
login/restart to expose its new method. Focused tests pass; product integration
and live end-to-end validation remain open. AT-SPI coverage varies by app;
Chrome did not expose a top-level window in the current diagnostic. See
`docs/desktop/SCREEN_OBSERVATION.md`. Telegram also exposed no top-level
AT-SPI window in this session. The screenshot portal is version 2 and local
Tesseract is absent, so OCR fallback is not yet implemented.

## 73. Explicit existing-window controls

After a restart, the owner confirmed that `Open Telegram` now brings an
already-running, minimized Telegram window forward. They approved separate
commands to restore, minimize, and close an existing application window.
`CLOSE_APP_WINDOW` means a normal window close request, not process termination;
full application quit remains a distinct future behavior. Maximize, return to
normal size, fullscreen, and exit fullscreen were added before a planned GNOME
session restart, using the same window-control permission. The interpreter,
action gate, persisted settings, control-center permissions, platform-neutral
controller, and GNOME adapter now support these window commands. New window
permissions default to off for existing settings. When an app has multiple
windows, GNOME selects the focused window only if it belongs to that app;
otherwise KYRIN asks the user to focus the desired one. Verification uses an
opaque stable window token so a focus change cannot accidentally verify a
different window. The updated extension source still needs to be installed
for the user before the next GNOME login. The prior version remains loaded in
the current session, and real desktop behavior is not yet validated. See
`docs/desktop/ACTIVE_APP_OBSERVATION.md`.

## 74. Two-step system power requests

The owner approved shutdown, reboot, logout, and suspend requests with a
warning about possible unsaved work and two confirmations. Either confirmation
may be spoken or clicked. A separate opt-in setting defaults off. The power
flow is independent of microphone session lifetime so the on-screen buttons
work when listening is unavailable. Spoken input is accepted from final STT
transcripts only. A bounded GNOME session-inhibitor query informs the warning,
but cannot establish that every editor buffer is saved. The adapter uses
GNOME's normal session methods and does not bypass native prompts or blockers.
Focused deterministic tests pass; no live system-power action has been run.
See `docs/actions/SYSTEM_POWER_ACTIONS.md`.

## 75. Semantic command reference cases and proposal contract

The owner approved first defining reference behavior and a replaceable
command-understanding boundary before choosing a multilingual NLU or local
translation model. `datasets/commands/semantic_cases.jsonl` now contains
owner-verified, owner-reported, and designed cases for English, Persian, and
German. The cases specify desired decisions and structured meanings, including
negation, ambiguous application names, app-versus-system restart, chat context,
and ordered steps. They are not audio recordings or measured model results.

`src/kyrin/commands/understanding.py` defines an engine-neutral, proposal-only
input/output contract. It retains the original text, attributes a source
language, permits optional STT alternatives, and reports proposed operations,
unresolved spoken targets, polarity, and categorical uncertainty. A ready
proposal must be singular, affirmative, and unambiguous. This contract is
not wired into `LiveCommandRuntime`; the existing `CommandInterpreter`, action
gate, and separate system-power confirmation behavior are unchanged. Before
integration, a target/dialogue resolver must map proposals to the existing
action domain and preserve the safety boundary. See
`docs/commands/SEMANTIC_UNDERSTANDING_CONTRACT.md`.

## 76. Local command model storage for comparison

The owner selected four offline command-understanding candidates for a
comparison: `qwen3.5:4b`, `qwen3.5:9b`, `gemma4:e4b`, and `gemma4:12b`.
They were copied from the machine's default Ollama store into the Git-ignored
`models/local/command-understanding/ollama/` store. Every referenced blob
passed a SHA-256 check, all four manifests resolved, and each model answered
a text-only request through a separate loopback Ollama server. After this
validation, only these four tags were removed from the default Ollama store;
the four unrelated tags there remained. The project store has four manifests,
19 referenced blobs, and no unreferenced or partial files.

This is a local development asset, not application model installation. The
KYRIN UI and live command runtime do not yet use these models. An initial
two-case dry-run showed all four could load. A later prompt with its JSON
schema included was run over 26 text cases; all four still showed errors,
including unsafe executable proposals. The corpus is small and includes
designed cases; three non-English Qwen 9B responses were empty, and one
browser-search reference may conflict with the owner's partial-execution
preference. These results do not establish a final model ranking. See
`models/README.md` and
`docs/commands/LOCAL_MODEL_COMPARISON.md` for restart and benchmark details.

## 77. Speech-language correction and command-model safety review

A full repository audit on 2026-10-09 found 468 passing tests, intact local
model data, and an incorrect `en` language label on the installed Persian
Vosk model. Its user-local library metadata was corrected to `fa` without
changing model weights. The existing active Whisper setting remains `en` on
GPU with listening disabled; it was not silently changed while desktop
actions and system-power permissions are enabled. New Whisper imports in the
Qt Model Library default to `auto`. A standard Vosk folder name now warns on
an obviously mismatched language code before copying. Reimporting identical
Whisper weights under another language preference reuses one copy and tells
the user to edit the active recognition language explicitly. Typing errors in
the Telegram portal diagnostic were corrected. After these code changes,
the full suite passed 475 tests, mypy found no issues in 119 source files,
and Ruff checks passed.

The semantic corpus was expanded with designed negative and app-versus-system
cases. Three disputed references are retained but excluded from ranking until
the partial-execution result and chat-target alias rules are defined. The
benchmark now validates output shape and scope more strictly, records each
model's full digest, and separately counts unsafe proposals involving system
power. A 31-case run and an eight-case power-scope run are documented in
`docs/commands/LOCAL_MODEL_COMPARISON.md`. None of the four models passed the
additional safety set. In particular, `gemma4:12b` interpreted some requests
to restart an application as requests to restart the computer. No candidate
was chosen as a live default, and no command model was connected to actions.

The existing `SystemPowerFlow` now treats a bare `Restart` as ambiguous and
requires explicit computer scope for the initial restart request. A public
`recognized_power_request` check on the original text is the required
independent guard for future model proposals; system actions still need the
existing separate opt-in permission and two confirmations. English and
Persian explicit phrases are currently reviewed; other languages need a
verified recognizer before voice power requests are supported.

An additional ten-case rerun with a stronger app-versus-computer model prompt
still yielded unsafe system proposals from Qwen 9B and Gemma 12B; Qwen 4B
abstained more often and produced one invalid response. Prompting alone did
not solve power scope. The model comparison remains a development diagnostic,
not a production-quality ranking or approval for live action integration.

## 78. Proposal target resolution and active Whisper language

A pure `SemanticTargetResolver` now sits beside the proposal contract. It
resolves app phrases against the installed, explicitly allowed catalog only;
approximate or ambiguous names require clarification. Chat app context uses
fresh foreground observation or a preceding resolved app-opening step in the
same proposed plan. It returns no executable `CommandIntent`, performs no
desktop action, and rejects model-proposed system-power steps from this path.
The live `DemoCommandInterpreter` remains in use. Focused deterministic tests
cover exact/fuzzy/unknown/duplicate names, chat context, multi-step proposals,
negation, ambiguity, and system-power isolation.

At the owner's request, the currently selected user-local multilingual Whisper
model was changed from `en` to `auto` language detection. The model file, GPU
device preference, listening-disabled state, and all action permissions were
preserved. This is a local application setting, not a repository default or
proof of multilingual command understanding: the live demo interpreter still
recognizes only its bounded English/Persian grammar. A new app session is
required to load the saved preference.

## 79. Read-only multilingual decision replay

The active Whisper `auto` setting was exercised on four already consented
English/Persian WAV clips through the local GPU adapter, without a microphone
or desktop action. All four detected the expected language. The Persian
negative clip yielded wording different from its reference, reinforcing that
detected language alone does not validate intent.

An untrusted-JSON decoder now maps local command-model responses into the
engine-neutral proposal contract, rejecting contradictory and malformed
outputs. The benchmark calls this same decoder. A separate replay diagnostic
applies the decoder and proposal-only target resolver to saved model outputs,
using a fixed allowlisted app catalog and an independent source-text check for
system-power eligibility. It neither invokes the action gate nor executes
commands. The 31-case replay had no unsafe resolved proposals, but the
separate eight-case scope replay found one: `gemma4:12b` proposed opening
Telegram for a Persian request to restart Telegram. This wrong operation
passed target lookup. Four actual Whisper transcripts were also compared
against all four local models; the two open requests resolved correctly, while
two models had one invalid/empty response each on negative requests. These
small sets do not justify choosing a live model. The isolated Ollama server
was stopped after evaluation. German is represented only by text examples,
not a verified recording. See `docs/commands/LOCAL_MODEL_COMPARISON.md`.

## 80. Independent source-operation verification in proposal replay

The next read-only command-safety boundary compares each proposed operation
and its order with independent evidence in the original text, before app-name
resolution. The initial replaceable rule profile covers explicit English and
Persian phrasing only. Negation, unsupported actions, uncertain alternatives,
and uncovered languages clarify; system-power operations remain in their
separate source-text recognizer and confirmation flow. Nothing in this boundary
is connected to live desktop execution.

Replaying the previously saved 31-case text set and eight-case app/system
scope set removed the one earlier unsafe *resolved* proposal: the Persian
request to restart Telegram can no longer be accepted as opening it. The four
saved Whisper transcripts still yielded two correct resolved open requests
per model. This is a small, partly designed corpus, not production accuracy.
Importantly, the operation check does not yet prove that the proposed app or
chat target appeared in the source. A focused test demonstrates that a wrong
but allowlisted target can still resolve. Source-to-target grounding and
broader language validation are required before live model integration.

## 81. Source-to-target grounding in proposal replay

The proposal-only replay now checks that each resolved app target and chat name
is grounded in the original utterance. A wrong but allowlisted application
can no longer pass merely because the proposed operation was correct. The
source app must uniquely match the registered alias catalog; the chat name
must match the source words after limited Unicode normalization. Explicit
chat-app wording, multi-step alignment, and alternative transcripts are also
checked. Ambiguous wording clarifies. This is independent of the local command
model, but still depends on the STT transcript being faithful to actual speech.

Replays of the same saved 31 text cases, eight scope cases, and four Whisper
transcripts retained the previously correct proposal counts. Focused tests
confirm that `open_app: browser` for "Open Telegram" now clarifies. No model
has been connected to the live command path. Language coverage remains a
conservative English/Persian subset, and the existing demo interpreter is
unchanged. See `docs/commands/SEMANTIC_UNDERSTANDING_CONTRACT.md` and
`docs/commands/LOCAL_MODEL_COMPARISON.md`.

## 82. Paired spoken-reference command audit

A read-only audit now joins four previously consented WAV clips to their
user-verified spoken references, saved Whisper `auto` transcripts, and saved
model proposal decisions. The tracked link file contains no audio; WAV files,
transcripts, and generated reports remain Git-ignored. The audit rejects
reference, language, or expected-label drift before scoring. It distinguishes
a correct action, unsafe action, missed action, and non-action or uncertain
result against what was **spoken**, rather than treating the STT text as truth.

On these four one-speaker clips, each of the four models retained two correct
positive proposals. Qwen 4B and Gemma 12B returned two correct non-actions;
Qwen 9B and Gemma E4B returned one correct non-action and one invalid or
uncertain result each. No unsafe action was observed in this tiny set. A
synthetic regression case proves that if STT changes "Open Telegram" into
"Open browser", source-to-target checks can match the mistaken transcript,
while the spoken-reference audit still records the browser proposal as unsafe.
No live command, microphone, or model was run in this stage. The remaining
risk requires broader labeled speech and a separate runtime design decision;
this audit alone cannot recover words STT failed to recognize.

## 83. Safety-command recordings captured and speaker-verified

A four-item English/Persian prompt template was added for a focused speech
safety set: close Telegram, open browser, open browser in Persian, and do not
open browser in Persian. The owner authorized microphone capture. The first
attempt missed the start cue and was rejected as nearly silent. After the USB
input level was set to 60%, four 20-second recordings were saved locally under
Git-ignored `datasets/stt/recordings/`; the manifest is also ignored. The raw
recordings are preserved. Single-utterance segments were extracted into the
ignored `recordings/segments/` directory. The owner confirmed saying each of
the four template sentences and intentionally repeating them. One complete
utterance per prompt is selected in the local manifest. Local Whisper `small`
on GPU returned exact normalized English text for `Close Telegram` and `Open
browser`; Persian results were `مرورگی را باز کن` and `مارورگره باز نکن` for
the affirmative and negative browser requests. The four-clip, one-speaker
character error rate was 5/59 (8.5%). The negative verb remained negative;
the proposal-only rule pack rejects it as non-executable. The misspelled
affirmative browser name produces a fuzzy candidate but not an exact app
match, so the proposal-only boundary would clarify. A separate read-only call
to the current live `DemoCommandInterpreter` returned actionable close/open
intents for the two English transcripts, clarification for the Persian
affirmative, and `NotACommand` for the Persian negative. This was an
interpreter call only, not a live end-to-end command or executor run. The local report is at
`datasets/stt/results/whisper-small-gpu-safety-2026-10-10.json` and is
Git-ignored. No command was executed. More speakers and languages are needed
before any broader accuracy or safety claim.

## 84. Four-model safety-command speech audit

The four newly verified safety recordings were passed through the local
Whisper `small` GPU adapter. Each resulting transcript, not the clean spoken
reference, was sent to the same four isolated Ollama command models used in
earlier comparisons. Saved proposals were replayed through the strict decoder,
source-operation check, exact app resolver, and source-target grounder, then
audited against the owner's verified spoken words. This is a read-only
development comparison; no command executor or app action was invoked.

All four models produced correct resolved proposals for `Close Telegram` and
`Open browser`. All missed spoken `مرورگر را باز کن`: Qwen 4B/9B requested
clarification, while Gemma E4B/12B proposed the browser but the source-target
grounder rejected the misspelled STT target `مرورگی` as non-exact. For spoken
`مرورگر را باز نکن`, Whisper retained the negation. Qwen 9B and both Gemma
models produced `no_action`; Qwen 4B returned an invalid model response that
failed closed. No unsafe resolved proposal appeared. A combined audit of the
original four clips and these four clips found four correct actions and one
missed action per model, with two or three correct no-actions depending on the
model. Eight one-speaker clips are not sufficient to select a model or claim
general safety. The isolated local Ollama server was stopped after the run.
The recorded links are tracked in `datasets/commands/verified_speech_links.jsonl`;
WAV files and model/audit reports remain Git-ignored.

## 85. Existing spoken app clarification completed for the observed Persian misspelling

The current live `DemoCommandInterpreter` already offered a single fuzzy,
registered app as an explicit `CONFIRM_APP` question. A deterministic run with
Whisper's observed `مرورگی را باز کن` confirmed that no action request was
issued before the next final transcript `بله`; `نه` declined the suggestion.
The question is sent through the existing text-and-voice response channel.
Two narrow corrections were made: the generic `browser` display label is
rendered as `مرورگر` in a Persian confirmation question, and a later explicit
negative open command now cancels the pending suggestion. Previously a
negative final had no action but left the old suggestion pending, so a still
later `بله` could have authorized the older open request. Focused tests use
the actual saved Persian STT spellings for the positive and negative turns,
check the action gate, and confirm no stale request remains. The full test
suite passed (543 tests). No new command model was integrated and no live
microphone or desktop action was run for this correction.

## 86. Live clarification attempt and recorded-audio replay

A dry-run microphone check of section 85 did not reach the app-name confirmation.
The diagnostic initially used its CPU default and fell behind the live audio,
causing an explicit capture/backlog failure. The diagnostic now accepts an
explicit `--compute-device gpu` for the existing Whisper backend; focused
parser and engine-injection tests passed. This is a development-tool option,
not a change to product settings or the selected STT model.

With GPU inference, a short Persian utterance under `--language auto` was
misclassified as Greek. A subsequent `--language fa` run produced the final
text `مرور گیر را باسکن`; an intentionally slow repeat was split into several
short VAD turns and yielded word fragments. No confirmation question, voice
reply, app action, or desktop execution occurred in those live runs. No audio
was saved during them. These observations concern this speaker and session;
they do not establish a general Whisper accuracy rate or a VAD defect.

To isolate the path, a previously authorized, locally ignored recording of
spoken `مرورگر را باز کن` was replayed at real-time chunk pace through the
current `LiveSpeechPipeline`, Silero VAD, and Whisper `small` GPU with Persian
selected. One speech start, one pause, and the final `مرورگی را باز کن` were
observed. Deterministic command tests show that this text asks for explicit
browser confirmation, and `بله` or `نه` then authorizes or declines the
suggestion. No command was executed during replay. Live microphone validation
of the complete question-and-answer exchange is still open. The next focused
check should observe the live STT final before testing that exchange; avoid
repeating app execution until the question actually appears.

In the next owner-approved live dry run, the USB microphone at 48 kHz and
Whisper `small` GPU with `--language fa` received complete speech turns.
The first final was `مورورگیر را باسکو`; two later finals were
`مرورگیار روباسکن` and `مورورگیر را باسکن`. The demo interpreter classified
each as `NotACommand`, so there was no clarification question or action.
The microphone was stopped cleanly. These observations point to unstable
recognition of both the app name and the operation in this session; they do
not justify silently correcting an uncertain operation into an executable
open command. A product decision is still needed on how command-like but
unrecognized speech should request repetition or clarification without
turning ordinary speech or a missed negation into an action.

The USB source was then found at 36% input volume, compared with 60% during
the earlier successful recording. With the owner's prior authorization for
this input setting, a second dry run temporarily used 60% and restored 36%
afterward. The two final transcripts were `مورور جره باز کن` and
`مرور جار را باز کن.` Both received the existing Persian repeat-command
response and no action; the first lacked the expected `را` pattern, while the
second app-name spelling fell below the registered-name proposal threshold.
The action verb was clearer at 60%, but two samples do not prove volume alone
caused the difference. No clarification confirmation or browser launch was
tested. A safer next design would generate non-executable app suggestions for
credible command-shaped text, retain explicit verbal confirmation, and keep
uncertain or negative operations from becoming actions. That behavior needs
owner approval and focused safety cases before implementation.

## 87. Candidate-only recovery for observed spoken app names

The owner approved a narrow recovery step after the live findings in section
86. `AppNameResolver.resolve()` retains its original stricter suggestion
threshold for normal lookups. A separate `suggest()` operation now tolerates
weaker, longer names and spacing differences, but returns candidates only;
it never marks them exact. The demo interpreter uses this only after a clear
Persian `باز کن` phrase, including a missing or colloquial case marker, and
asks for explicit confirmation before any action. Observed live forms such as
`مرور جار را باز کن` and `مورور جره باز کن` now lead to the browser question.
An uncertain verb such as `مورورگیر را باسکو` can request repetition but
cannot become an open action. An explicit negative command cancels a pending
question, so a later `بله` cannot approve it. The model-neutral semantic
proposal/grounding boundary remains separate and no language model was
connected to the live runtime.

Focused tests cover these paths and stale catalog-name behavior. A wider
commands/desktop/runtime/app run had 300 passing tests and two local socket
failures under the sandbox; those two passed on rerun with local socket access.
The affected source passes Ruff and Mypy. The new behavior has not yet been
validated in a fresh live microphone question-and-answer run.

## 88. Follow-up live microphone check of candidate-only recovery

The owner approved a live dry run of section 87. The first diagnostic launch
used a stale PortAudio device index 23 and stopped without capturing speech;
the USB source had moved to index 22. With the current device and a temporary
60% input volume, Whisper `small` GPU with Persian selected produced one
non-command-like final and then `مروریا را باسکن` for the target phrase.
Because the operation `باز کن` was not recognized, no browser suggestion or
action was issued. Audio was not saved and the microphone was stopped. The
USB volume was restored to the 30% value observed immediately before this
test. A live `بله`/`نه` exchange still has not been validated.

The new text also exposed a response gap: the uncertain-verb repeat path
required a plausible app-name candidate, but `مروریا` fell below even the
question-only name threshold. The path now recognizes a command-shaped
Persian `name را/رو operation` utterance whose operation resembles `باز کن`
as unrecognized, and requests repetition without opening an app or retaining
a pending confirmation. Negated `باز نکن` is handled earlier and cannot enter
this path. Focused tests use both observed uncertain-verb spellings and confirm
that a later `بله` has no action. Commands/desktop/runtime tests passed (187);
the affected code passes Ruff and Mypy. This change does not improve the
underlying Whisper transcript or establish broad Persian speech accuracy.

## 89. USB microphone input-level comparison

The owner approved a bounded three-level check and confirmed reading the same
Persian phrase `مرورگر را باز کن` once at 30%, 60%, and 100% USB input volume.
Each 15-second mono 48 kHz WAV was recorded locally under Git-ignored
`datasets/stt/recordings/gain-comparison-2026-10-10/`. No desktop command was
executed. The source was 27% immediately before the check and was restored to
27% afterward. An ephemeral capture script in `/tmp` was used; no product
microphone behavior or default gain was changed.

Silero VAD identified one speech interval in each file. The cropped speech
RMS values were -13.3, -16.0, and -16.6 dBFS respectively; the 30% clip had
19 samples near the digital limit, while the 60% and 100% clips had none.
These differing amplitudes are not a controlled measurement of microphone
gain alone: the three utterances were spoken separately and may differ in
distance or loudness. Whisper `small` GPU with Persian selected missed the
exact reference at all three levels, both on the VAD crops and on the full
15-second files. The full-file character edit distances were 7, 6, and 4
respectively out of a 16-character normalized reference; this tiny apparent
ordering is insufficient to recommend 100% as a default. The existing
`large-v3-turbo-q5_0` GPU model was also tried on the three crops and returned
mixed Latin-script phonetic text, not a better Persian transcription. The
ignored local report is `datasets/stt/results/mic-gain-comparison-2026-10-10.json`.

The captured speech was not near silence, and 100% did not by itself solve
the command error. Input volume remains a per-device setting. The next
technical investigation should concentrate on Persian short-command STT
behavior and turn context rather than hard-coding an input gain or silently
relaxing the action gate. This check does not identify the best speech model
or establish a general accuracy rate.

## 90. Optional STT vocabulary hints: offline feasibility and contract

The owner approved a staged context-aware STT investigation after the gain
comparison. The pinned local whisper.cpp server accepts a per-request `prompt`.
On 11 existing Persian recordings with user-provided reference text, a fixed
four-term vocabulary prompt reduced summed normalized character edit distance
from 44 to 18; 10 samples improved and one became slightly worse. Both tested
negative commands preserved their negation. Timings on a warmed GPU server
were almost identical, but this is not a general latency benchmark. The
detailed output is in the Git-ignored local result file
`datasets/stt/results/context-prompt-2026-10-10.json`.

A bounded, optional `vocabulary_hints` field now exists in the backend-neutral
`SpeechToTextOptions` contract. Whisper forwards it as request context; Vosk
explicitly rejects unsupported nonempty hints. The Ubuntu product runtime
does not supply hints by default. Focused tests and a two-file real Whisper
session check (one positive, one negative) passed without microphone access
or desktop action. This is a feasibility result, not approval to infer actions
from approximate text or evidence of general multilingual accuracy. See
`docs/stt/CONTEXT_VOCABULARY_HINTS.md`.

## 95. Narrow spoken-Persian command recovery

The live Ubuntu composition now registers `مرورگر` as a spoken alias only
when the configured browser application is installed and explicitly bound.
The demonstration interpreter accepts both `را` and colloquial `رو` before
the explicit `باز کن` operation, but still requires an exact registered app
name for direct action. An approximate name remains a confirmation question;
an uncertain verb such as `باسکن` still requests repetition without action.
A fresh incomplete or unrecognized command clears an older pending app
confirmation, so a later `بله` cannot authorize that stale suggestion.
Focused composition, command, and grounding tests pass. This does not repair
Whisper's transcript itself or establish multilingual speech accuracy; no
microphone or desktop action was run for this change.

The owner then confirmed two fresh live test utterances, positive
`مرورگر را باز کن` followed by negative `مرورگر را باز نکن`, during a
35-second STT-only microphone run with the four-term hint. Their final
transcripts were `مورورگر، بوسکن.` and `مورورگر را باز نکن.`. The first
remained ambiguous; the second retained negation. No audio was stored or
desktop command executed. Because the hint did not solve the positive live
case, automatic hint generation/activation in the product remains deferred.

## 91. Direct/live STT path and language-mode comparison

At the owner's request, a no-action WAV replay comparator was added under
`kyrin.stt.path_comparison` with a CLI at
`scripts/stt/compare_live_path.py`. It opens a turn-aware STT session directly
over the full file, then replays the same file through the existing paced
`LiveSpeechPipeline` and Silero VAD. The audio and reports stay in ignored
`datasets/stt/` paths. Focused tests cover VAD rejecting audible file data,
showing that this case is distinguished from a direct STT failure. See
`docs/stt/LIVE_PATH_COMPARISON.md` for commands, exact outputs, and limitations.

Four speaker-verified safety clips and four additional verified commands were
replayed on the existing Whisper `small` and `large-v3-turbo-q5_0` GPU models.
With automatic language detection, `small` attributed 5/8 languages correctly
and `turbo-q5` 3/8. In the four safety clips, short English `Close Telegram`
became Arabic-script text on both models; short Persian `مرورگر را باز کن`
became Greek-script text on `small` and Icelandic-like Latin text on `turbo-q5`.
The live path had one speech start and pause per clip and no backlog notice.
Explicit `en` gave correct normalized English text on both models; explicit
`fa` gave usable but misspelled Persian from `small` and still poor phonetic
Latin text from `turbo-q5`. No desktop action was run. The corpus is too small
to select a product default or language-routing policy.

On this workstation, the warmed GPU returned the four safety-clip finals no
later than about 0.10 seconds (`small`) or 0.24 seconds (`turbo-q5`) after file
end; several finals arrived before trailing silence ended. Sampled server GPU
allocation during one Persian replay reached about 1004 and 1040 MiB,
respectively, excluding the rest of KYRIN. CPU `small` lagged about 10.4–11.4
seconds after file end. CPU `turbo-q5` hit the current eight-second inference
request timeout; a separate direct server probe with a longer timeout returned
an English command after 8.23 seconds of inference. No model, user setting,
inference timeout, or action policy was changed by this diagnostic.

## 92. Short-command language candidate diagnostic

The follow-up no-action diagnostic `scripts/stt/compare_language_candidates.py`
replayed the same eight owner-verified WAVs through each installed Whisper
GPU model in auto, fixed English, and fixed Persian modes. It scored only
command *proposals* and kept verified labels out of language selection.
`small` produced 3/5 correct positive proposals with auto and 4/5 under an
offline hypothetical choice of the higher reported English/Persian
probability; neither route proposed an unsafe action on the three negatives.
The still-problematic Persian browser request favored English, and fixed
Persian still misspelled the app name. On `turbo-q5`, the server omitted
Persian from its top probability list on four recordings, so a restricted
winner was unavailable there. No live routing, model selection, user setting,
microphone access, or desktop action changed. Full method and limitations:
`docs/stt/LANGUAGE_ROUTING_DIAGNOSTIC.md`.

## 93. Speaker-aware safety evaluation preparation

The owner approved the next evaluation step without changing the live STT or
action route. The eight existing verified links now identify one pseudonymous
speaker. A no-action summary tool validates each prior report against those
verified references, independently recomputes proposal classifications, and
reports counts by speaker, language, and decoding condition. Its first local
report confirms that both tested models still have only one speaker; negative
no-action outcomes remain labeled as abstentions rather than proof that
negation was understood. The recording utility supports a separate ignored
path for another consenting speaker without replacing existing recordings or
silently treating prompts as verified speech. At that point new recordings
and a second speaker remained pending. See
`docs/stt/MULTI_SPEAKER_SAFETY_EVALUATION.md`.

The owner then confirmed that a second consenting speaker could read English
and Persian. Eight prompts were captured locally; seven complete utterances
were speaker-confirmed and admitted under a separate pseudonymous manifest.
The intended eighth, the Persian Telegram negation, was excluded: the first
take may have a cut-off opening, and the retry was spoken by the first
speaker. The original files remain local and ignored. Both installed Whisper
GPU models replayed the same 15 verified clips with no desktop action.
For the second speaker's five positive commands, `small` automatic decoding
proposed three correct actions and `turbo-q5` proposed two. The two second-
speaker negatives produced no action proposal, but Persian negation was not
reliably readable. The hypothetical restricted English/Persian probability
choice worsened `small` on this speaker to two correct positives among four
classifiable positives. The simple restricted selector is therefore not
activated. Exact counts, provenance, and missing-case limitation are in
`docs/stt/MULTI_SPEAKER_SAFETY_EVALUATION.md`.

## 94. Fixed vocabulary hints across the existing two-speaker corpus

The owner clarified that the second speaker is no longer available; new
speaker recordings are not a prerequisite for the next technical work. A
paired no-action replay used the 15 already verified clips and the installed
Whisper `small` GPU model. The same four Persian vocabulary hints were sent
to every clip in auto, fixed-English, and fixed-Persian modes; no reference
label selected a hint. Under automatic decoding, correct positive proposals
fell from 6/10 without hints to 4/10 with hints. Fixed-Persian decoding
improved from 1/4 to 2/4 correct Persian positives, but both positives from
speaker 2 remained missed. Fixed-English decoding fell from 6/6 to 4/6
correct English positives. No unsafe proposal appeared on the five negatives
in either auto condition, but unreadable negatives count as abstentions.
Despite better Persian character scores, the global hint list degraded
command behavior, so it was not enabled in KYRIN. See
`docs/stt/CONTEXT_VOCABULARY_HINTS.md`.

## 95. Optional local command-model selection in the Ubuntu app

The owner requested that the locally stored command-understanding models be
available in the real KYRIN application with Auto, CPU, and GPU choices. A
versioned optional setting, a Command Understanding page, local Ollama model
discovery, an isolated loopback Ollama session, and a model-assisted interpreter
now connect the selected model to final live transcripts. The default remains
the existing fast-rule interpreter until the owner selects a model. Simple
commands continue through fast rules; unresolved text may query the model.
Proposals must pass independent source-operation and target checks, installed
app resolution, and the existing action gate; model output cannot authorize an
action by itself. The four ignored local model tags are discovered without
copying weights. Focused settings, UI, interpreter, and composition tests pass.
A text-only local CPU smoke test with `qwen3.5:4b` returned `open_app` for
`Please open Telegram` after a prompt correction and `not_command` for
`Do not open Telegram`; it did not execute either command. The non-hardware,
non-socket suite passed 565 tests. The owner has not yet validated the new
route with the microphone or a desktop action; GPU inference was not verified
in this turn. English/Persian source checks limit command execution for other
languages. See `docs/app/COMMAND_MODEL_LIVE_INTEGRATION.md` for setup and
remaining validation limits.

## 96. Built-in Persian and system interface language

The owner approved completing interface-language selection without changing
the speech-language setting. The existing Preferences selector now offers
English, a complete built-in Persian catalog, the operating-system language,
and imported packs. A system locale selects the best installed language or
falls back to English. Script and region tags are accepted. Imported packs may
translate a subset of known keys; missing keys use English, and placeholder
names are validated before a pack is installed. Visible fixed labels in the
control-center branding, power buttons, and confirmation controls now use the
UI catalog. The selected locale drives Qt left-to-right or right-to-left
layout. UI language preferences remain separate from STT and voice settings.
See `docs/app/UI_LANGUAGE_SETTINGS.md`. Speech responses and system-action
prompt wording remain a separate localization concern.

## 97. Registered camel-case application names in spoken commands

The owner reported that `Open OpenRGB` asked for confirmation instead of
opening the permitted app. Diagnostics showed the actual final transcript was
`Open Open RGB` with language `tr`. The application binding already identified
the installed `OpenRGB` desktop entry, and exact `Open OpenRGB` text already
worked. Registered names now also provide a spelling split at Latin case
boundaries, so `Open RGB` resolves exactly to `OpenRGB`. If two permitted apps
share that spoken spelling, the existing choice prompt remains in force.
Focused tests and a deterministic check with the installed app registration
pass; live microphone validation after restarting KYRIN remains open. The
separate reported `Open Terminal` failure has no diagnostic transcript; the
owner suspects their pronunciation in that attempt. Its exact text resolves
to the permitted `Terminal` desktop entry in a deterministic check, so no
terminal-specific alias or behavior change was added.

## 98. Local model greeting reply rejected by a structured-output placeholder

The owner observed `Heard (en): Hello Kyrene.` followed by `No action
requested` and no user-facing reply. A read-only, action-free probe of the
selected local `qwen3.5:4b` model showed that it proposed `route=respond` with
a valid short greeting reply, but also filled the required `steps` array with
one item whose `operation`, `target`, and `app` were all empty strings. The
decoder rejected that template before the reply could reach the presenter.
It now treats an entirely empty item template as no steps, and accepts a
reply misplaced inside an otherwise action-free item, only on the
conversational route. Populated steps and action-route placeholders still
fail. A focused decoder test and an isolated end-to-end local-model
probe produced a `CONVERSATION` response with no action intent. Live
microphone and voice-output validation in the restarted app remains open.

## 99. Observed KYRIN wake spellings and greeting response

The owner chose to recognize observed spellings `Kyren`, `Kyrene`, `Kirin`,
`Kairina`, `Kiring`, and `Curring`, in addition to the existing built-in wake
names. `Creator` remains excluded because it can represent ordinary speech.
The reviewed names now live in one shared list used by the fast interpreter,
source-operation evidence, and explicit power-request recognition (whose two
separate confirmations remain mandatory). A bare wake name continues to
produce only the readiness cue; greeting plus name goes through the selected
local command model and cannot create an action. The greeting prompt now asks
for a short, warm response without claiming unsupported capabilities. Local
model probes of `Hello Kyren` and `Hello Kyrene` produced conversational
responses and no command intent. The owner selected text and mascot reaction
for now; product TTS integration stays deferred. A separate `conversation`
visual state shows the model's reply beneath a brief one-shot arm gesture,
without displaying an action-success mark. The updated GNOME extension files
were copied into this user's installed extension, preserving unrelated
installed differences; a new GNOME session is needed to load them. Live
microphone and visual behavior still require owner validation after restarting
the application and GNOME session.

## 100. Application-choice dialogue and Terminal observation

Bare permitted app names now lead to a numbered operation choice. Approximate
names are suggestions only; they require app confirmation before the operation
choice. Closing from the menu has a separate confirmation. GNOME window
presence is queried only on final speech and only for mapped permitted apps;
unknown status offers only open/bring forward. The adapter is optional and the
contract is platform-neutral. The installed user-scoped GNOME extension was
updated with the read-only `HasAppWindow` method, which needs a new GNOME
session before live use. Focused automated tests pass.

A live Terminal request was accepted by `gio launch` and the GNOME activation
method, while `GetActiveApp` kept reporting ChatGPT. The owner first reported
that Terminal came forward, then clarified that they saw their existing
ChatGPT-related terminal window; this does not establish that KYRIN brought
the requested Ptyxis window forward. The Terminal launch/activation issue
remains open. The user's separate workaround of terminating and restarting
ChatGPT is not part of KYRIN's Terminal action and was not executed here.

The owner wants Terminal to offer context-sensitive choices for existing or
new windows, tabs, all windows, preferences, and safe closing. This is a new
design request, not implemented by the generic app-choice menu. The local
Ptyxis desktop entry advertises `new-window`, `new-tab`, and `preferences`;
multiwindow enumeration and safe quit need further design and validation.

## 101. Ptyxis-specific Terminal choices and review of the prior dialogue change

The previous app-choice work was reviewed before extending it. Its numbered
selection, bound-app resolution, and optional window-presence adapter are
needed by the Terminal flow; no broad removal was justified. Two real defects
were found and fixed: non-chat actions displayed an "opening chat" mascot
caption, and a model-classified affirmative reply could bypass the
Terminal-specific choice after a suggested app name. Model-proposed opening
and closing now pass the same Terminal review as fast-rule commands.

The current GNOME/Ptyxis path counts only windows associated with the exact
bound `org.gnome.Ptyxis.desktop` entry. `Open Terminal` launches when the
count is zero, offers bring-forward/new-window/new-tab/Preferences for one,
and offers GNOME overview/new-window/Preferences for several. GNOME overview
shows all desktop windows, not only Ptyxis. Unknown count offers only a
conservative open/bring-forward choice. New window, tab, and Preferences run
fixed Ptyxis arguments; an accepted request is not reported as verified
success. Direct `Close Terminal` asks for a separate confirmation. Bulk Quit
and dock Unpin are intentionally absent because they need distinct safety
and desktop integration. The user-scoped active-app extension was updated
with window count and overview methods; a new GNOME session is required.
Focused automated tests pass; live verification after session restart remains
open. The owner clarified that a prior apparent Terminal activation was a
pre-existing ChatGPT-related terminal, so it is not counted as success.
The GNOME presence adapter is now kept during login even if its Shell
extension loads later, avoiding a stale startup availability decision. A
new-tab request rechecks the one-window condition at execution time.

## 102. Terminal-only numbered window picker

The owner reported that the earlier `ShowAllWindows` Terminal option displayed
Telegram, VS Code, ChatGPT, and other unrelated windows. The proposed
replacement was approved. The Terminal menu now requests a GNOME picker for
only the exact bound Ptyxis desktop ID. The picker shows equally sized live
previews with numbers, allows click or a spoken number, and checks the
displayed stable window token before activating it. A disappeared window is
rejected instead of replaced by another one. Cancel and Escape dismiss it.
The platform-neutral command and permission layers retain their boundaries;
the live preview implementation is GNOME-specific. Focused deterministic
tests and packaging checks cover the new path. Live confirmation after a new
GNOME session remains open; the installed extension must include both its
`extension.js` and `windowPicker.js` files.

## 103. Permission-scoped open-window picker

The owner approved a general open-window preview and selection by click,
spoken number, or app name after validating the Terminal picker. The GNOME
adapter now reuses that visual surface for windows of applications with
explicit window-control permission. No other windows are displayed. Python's
command layer receives no image or window title. The Shell stores temporary
app-ID and stable-window-token pairs, rejects vanished windows, and accepts
an app name only when exactly one of its windows was shown. The Terminal-only
menu remains intact. Focused Python and GJS tests and GNOME packaging pass.
The two source files were copied into the current user's extension directory.
The owner later reported that the general open-window picker worked correctly
on their desktop. This is a real-use check of the picker, not a comprehensive
multilingual or cross-platform validation. Other desktop environments need
their own adapter.

## 104. Meaning-based requests for the open-window picker

The owner rejected relying on a list of complete trigger sentences for the
general picker. The command contract now has a targetless
`show_all_windows` semantic operation. The selected local command model can
propose it for paraphrases across languages; only the established action gate
can authorize the chooser. A small English/Persian concept-slot path handles
clear display + collective + open-window/running-app requests quickly,
independent of word order. It is a fast path, not a closed utterance list.
Explicit negation and requests about installed apps, browser tabs, or files
are rejected. Bare “pages” remains ambiguous. The model cannot directly
select a window through this operation: selection still needs the numbered
snapshot or an exact registered app name. Focused tests pass. A local
`qwen3.5:4b` probe correctly proposed the operation for “Bring up every window
I have open” and a Persian open-app-pages request, but produced invalid JSON
for “List the currently running apps”; the concept-slot fast path now covers
that case. Model quality for arbitrary languages and live microphone behavior
remain unverified.

## 105. Desktop-wide two-step system power confirmation

The owner validated the general open-window picker on their desktop and then
reported that system-power confirmation was inconvenient because the controls
were inside the main KYRIN window. The approved change shows a separate,
non-modal Qt confirmation window without bringing the settings window forward.
It appears during the blocker check and stays visible through both stages.
Closing it cancels the request. The existing `SystemPowerFlow` remains the
authority for request IDs, permissions, timeout, cancellation, and the two
confirmations. The final spoken challenges are shorter and action-specific:
`Power off`, `Restart computer`, `Log out`, and `Suspend computer`. A vague
second answer such as `Okay` or `Yes` never submits a system action; it keeps
the request and shows a repeat instruction. It cannot select a different
action. The Qt application now shares one offline Speech Dispatcher response
speaker with the listening session, so the sensitive prompts can be spoken
and microphone capture is guarded during playback. This is an initial voice
using the existing local backend, not the previously preferred Kitten voice.
Focused deterministic tests pass. The owner validated a safe preview on their
GNOME/Wayland desktop: the dialog appeared over the current application, and
both confirmation stages showed text and played audio. The preview's backend
was fake, so it could not request a real system action. At first the operating
system sent audio to a digital sink; selecting the TSCO headset as default
made speech audible. Actual KYRIN voice input plus GUI confirmation remains
to be validated end to end. The dialog now also shows a voice-output error
in place if speech playback fails. No automated test calls a real shutdown,
restart, logout, or suspend action.

## 106. Local TTS selection in the control center

The owner decided that KYRIN must not download STT, command, or TTS models from
inside the application. Users can obtain compatible models themselves and
select installed local files. The owner approved a Voice Output management
page. The current implementation persists a selected backend, local Kitten
folder, voice, speaking speed, and AUTO/CPU/GPU preference in settings schema
7. It supports Speech Dispatcher/eSpeak NG and optional sherpa-onnx Kitten;
other engines require a separate adapter. The default remains the existing
system voice. Explicit GPU choice is rejected when its CUDA provider is
missing. Kitten currently covers English speech; other languages use the
system voice. The app lists complete local Kitten packages in the user TTS
data folder and can browse to a folder elsewhere. No model is downloaded or
packaged. This is a code-level integration validated with deterministic tests;
audible Kitten playback on the owner's computer has not yet been validated.
See `docs/responses/TTS_MODEL_MANAGEMENT.md` for setup and limits.

## 107. Multilingual TTS routing and Piper/VITS packages

The owner rejected the English-only Kitten boundary as inconsistent with the
goal of user-selectable offline voices. Settings schema 8 now preserves the
existing default voice and adds independent language-specific routes. The Qt
Voice Output page can add a language code, choose and preview its local voice,
and remove that route. The same `SpeechSynthesizer` contract now loads Kitten
or a compatible sherpa-onnx Piper/VITS archive. The official
`vits-piper-fa_IR-gyro-medium` package provides a concrete Persian route.
An unconfigured language falls back to the system voice; English model output
is not used to pronounce unrelated languages. Model downloads remain outside
the app. Deterministic routing, settings migration, package inspection, and
UI tests pass; real Persian-model playback on the owner's machine is still
unverified because the optional runtime/model have not been installed there.
Unknown TTS families need an adapter; the app must never imply that any ONNX
file can be executed by selecting its folder.

## 108. Automatic TTS family selection from local packages

The owner wants the user to obtain a voice package, select its extracted folder,
and adjust language, speaker, speed, and device in the app without coding or
installing a separate engine. Voice Output now recognizes supported package
families when a local folder is selected and chooses their engine automatically.
The built-in family catalog is shared by settings validation, model discovery,
and the UI. It includes Kitten, Piper/VITS, and sherpa-onnx Kokoro packages;
the desktop installation includes the shared sherpa-onnx runtime. The current
development environment also has sherpa-onnx 1.13.8 installed. Model weights
remain user-provided. Deterministic tests cover the new package and selection
path. Actual playback with a downloaded model remains to be validated on the
owner's computer. Unknown formats still require engineering support and must report
an explicit incompatibility instead of being accepted silently.

## 109. TTS adapter boundary and direct model selection

The owner wants downloaded TTS packages to be selected in the app without
editing code or installing a runtime separately. A model package remains data;
unknown weights cannot be executed safely without a compatible engine. The
TTS runtime now exposes a typed adapter contract for package inspection,
validation, device selection, loading, and synthesis. Built-in Kitten,
Kokoro, and Piper/VITS adapters keep their existing behavior. The default
system-voice state no longer disables the local-model picker, so selecting a
supported folder detects its engine immediately. A saved adapter identifier
can survive a temporarily unavailable adapter; validation reports the missing
adapter explicitly. Unsupported packages are rejected rather than executed.
Deterministic tests cover a registered test adapter and the default-state UI
selection; audible playback of additional families has not been validated.

## 110. Offline high-naturalness TTS adapter expansion

The owner approved extending local TTS support beyond the original sherpa
families. This turn added adapters for complete Chatterbox Multilingual V2/V3
packages with a built-in reference voice and Qwen3-TTS 0.6B/1.7B CustomVoice
packages. Both load local paths only and route response language to the engine;
unsupported languages and unsupported speed settings are rejected. The Qt
voice page detects these packages and exposes the available built-in speakers.
Deterministic integration tests use fake model runtimes. Real model weights and
upstream Python runtimes have not been installed or audibly tested. The two
upstream packages pin incompatible Transformers versions. Separate worker
execution was added later (section 111); packaging their environments for a
shipped desktop installation is still open. Fish S2 Pro, CosyVoice 3, IndexTTS 2.5,
and F5-TTS remain open work; some require a reference recording and/or a
different Python version. Do not describe these as implemented.

## 111. Separate execution for incompatible optional TTS runtimes

The owner chose to download model weights later and asked KYRIN to continue
engine integration without downloading them now. Chatterbox and Qwen3-TTS
can now run in persistent, separate Python worker processes when their
optional runtimes are installed at documented user-data locations. The
existing adapter contract, language routes, and voice/device settings remain
the application-facing boundary. A bounded line protocol returns float32
audio; the worker loads only built-in adapters and model folders are never
treated as executable plugins. A model-free subprocess test exercised probe,
load, and repeated synthesis. Real engine dependencies and weights are absent
on this machine, so neither engine has passed an audible end-to-end test.
Packaging/provisioning the worker environments and the remaining TTS families
are still open; do not present the two environments as installed by the UI.

Later owner validation superseded the installation and playback limitations
recorded in sections 106–111: Qwen3-TTS CustomVoice played on GPU and CPU,
and its preview speed changed audibly. The owner also reported that the
Kokoro GPU playback issue was resolved. These are owner-observed results on
the current Ubuntu machine, not evidence that all optional TTS families or
fresh installations are provisioned. Peak Qwen CPU RAM use remains unmeasured.

## 112. Text-only conversation memory and short command fragments

The owner approved a real local memory of multiple finalized spoken turns,
without storing audio, and requires KYRIN data on the AI-Projects drive on
the current Ubuntu machine. `ConversationHistory` separates persistence from
speech and command backends. Its SQLite implementation lives at the XDG data
path (linked to `local-data/kyrin/memory/` here), keeps up to 2,000 active turns, and
offers bounded recent reads and explicit clearing from Preferences. Only
final raw transcript text is saved. Up to six recent shortened turns reach
the local model as non-authoritative context; current-utterance operation and
target checks still govern actions. A separate four-second in-memory fragment
buffer can join a bare English operation with a nearby target, and is cleared
on STT reconnect. Deterministic tests cover persistence, bounds, clearing,
fragment expiry and negation, and runtime wiring. At that point, live microphone
latency had not been measured; topic-ranked retrieval remains unimplemented.

The short fragment buffer was subsequently extended to the existing
English window actions (including minimize, restore, maximize, and fullscreen)
and corresponding Persian suffix actions. It still accepts only explicit
operation fragments followed by a nearby target, never a delayed confirmation
or an unrelated new command. Action policy and window verification remain
unchanged.

The owner subsequently confirmed that joining short spoken command fragments
works in real use. A later audit found that Ubuntu session composition tests
had not isolated `XDG_DATA_HOME`, so fake transcripts could reach the owner's
SQLite history. Those tests now use a fresh temporary XDG data directory per
test, with a regression assertion for the stored path and turns. A read-only
inspection of the existing database found 81 turns in 55 sessions; 78 turns
across 54 sessions matched literal test utterances. This is strong evidence of
test contamination but cannot establish provenance for individual records,
because a real utterance could match the same text. The database was not
modified or purged. Future tests cannot add to that user history through this
composition path.

After the owner approved remediation, the 81 existing turns were marked
archived rather than classified or deleted. A separate private SQLite snapshot
was saved on the AI-Projects drive before the change. Recent command-model
context now starts empty and receives only new active turns. The schema retains
the old text and supports restoring archived rows; no per-turn provenance was
invented.

A synthetic SQLite benchmark on the same AI-Projects data drive measured 300
appends at median 0.845 ms/p95 1.354 ms and 300 six-turn reads at median
0.011 ms/p95 0.012 ms. This does not measure full speech-to-action latency;
the synchronous history write was retained because no material storage delay
was observed in this bounded test.

For desktop-wide system-power confirmation, a new safe live microphone
preview used the actual Qt dialog and spoken prompts with an inert backend.
The owner spoke `Power off`, `Yes`, then `Power off`, and confirmed seeing the
dialog and hearing both stages. The backend only recorded
`SAFE_BACKEND_ONLY: power_off`; no operating-system power request was made.
Automated Qt integration coverage now exercises the same voice progression.

## 113. Archived-memory review, safe power preview, and observed latency

Preferences now opens a paged review of archived transcripts only on user
request. The owner may restore one selected row after a separate confirmation;
archived turns do not enter model context until restored, and old text never
authorizes an action. The 81 preserved rows and the private snapshot were not
deleted or bulk-restored.

Desktop Actions now exposes a safe power-confirmation preview through the
installed control center. It uses the same two-stage dialog and listening
flow, but an inert backend, including when real system-power permission is
off. Tests verified that the real backend receives no request. On 2026-10-14,
after restarting the installed control center, the owner confirmed the new
button's `SAFE PREVIEW` window, both audible prompts and voice stages, and
the final message that no operating-system request was sent.

Speech Recognition diagnostics now show observed time from VAD-confirmed
speech start to action feedback, and from final STT text to feedback. A
repeatable safe probe uses current saved STT and command-model settings with
an inert executor and temporary conversation database. One owner-spoken
`Open Telegram` trial produced 1,100.28 ms from VAD-confirmed speech start to
final text and 0.32 ms from final text to inert result. It was one warm run;
the command may have used the rule-based interpretation path and does not
characterize all commands or model cold starts. No app was opened in the probe.

## 114. Saved Messages speech-path check and observed STT alias

A first installed-app microphone trial of `Open chat Saved Messages` did not
open the chat. The command interpreter produced `open_chat` with Telegram in
context, but Whisper transcribed the target as `Saved Massages`. The Telegram
executor rejected it as `unsupported_chat` before requesting keyboard input.
Other fragments in that trial did not authorize an action. An exact alias for
this observed target spelling is now accepted only by the bounded Telegram
Saved Messages executor. Permission, focused desktop ID/PID, temporary
keyboard access, and fresh OCR header verification remain required. Focused
tests cover the alias with both confirmed and unverified headers. After
restarting the installed app, the owner repeated the spoken request; the
interpreter produced `open_chat: saved massages`, the action result was
`confirmed`, and the owner saw the chat open. Two earlier short fragments in
the same session produced no action. This validates one live product path on
the current Ubuntu desktop, not arbitrary chat names or other languages.
The observed final-text-to-result interval was 16,849 ms, including temporary
input permission and screen verification; stage costs were not separated.
Inspection then found an unconditional ten-second sleep after the keyboard
portal grant. The helper now polls for two matching Telegram focus observations
up to the same ten-second deadline and can proceed earlier when focus is
already correct. Deterministic tests cover prompt focus, delayed focus,
unstable focus, and timeout. At that point, installed-app timing after the
change had not yet been measured.

The owner then repeated the complete spoken request without restarting KYRIN;
the freshly launched keyboard helper used the new polling code. The transcript
was `Open Chat Saved Messages`, the action result was `confirmed`, and the
owner reported the chat opened. Final-text-to-result time was 6,187 ms, versus
16,849 ms in the previous run. This is an observed improvement in two trials,
not a full latency distribution or a breakdown of portal and OCR time.

## 115. Remembered screen and keyboard access

The owner requested that Screen Access remain enabled across KYRIN restarts
until switched off in the app, and that opening Saved Messages not repeatedly
ask for GNOME keyboard consent. The implementation now stores a random local
screen capability and its hash for the GNOME extension, and binds each active
capture session to KYRIN's verified D-Bus connection. Quitting releases only
the active session. Turning Screen Access off removes both local records and
requests immediate revocation. The Telegram keyboard helper now asks the
RemoteDesktop portal for a remembered grant, stores the opaque restore token,
and rotates it after each successful `Start`; each input session is still
closed after the fixed shortcut. Removing Telegram chat permission clears
KYRIN's saved keyboard token. Focus ID/PID and fresh OCR checks remain.

Focused deterministic tests validate grant, restore, rotation, and revocation
logic. The changed GNOME extension must be installed and the desktop session
restarted before the app path can be checked live. Portal backend support for
actually restoring the token on this machine, behavior across a logout, and
the full installed-app workflow had not yet been verified at that point.
After restarting the desktop session, the owner reported checking both
permissions in the installed app and found them working without the repeated
approval problem. A read-only check found the loaded extension exposing
`RequestPersistentSession`; the screen token, screen grant hash, and Telegram
keyboard restore token were present in the AI-Projects-backed local data, each
with mode 0600. The owner later turned Screen Access off inside the app and
confirmed that this worked. Telegram keyboard permission revocation after
turning its app permission off has automated coverage but has not been
confirmed by the owner in a live test. The observations do not measure portal
restoration latency.

A same-user malicious
process can still read local user files or replace a user-installed extension;
these remembered grants are not a boundary against such a process.

## 116. Telegram chat permission revocation and bounded search navigation

The owner turned off `Allow Telegram chats` in the installed app and saved the
setting. A read-only check showed `allowed_chat_apps` empty and the remembered
Telegram keyboard token gone. In a live microphone check, a recognized
`open_chat: save the messages` request ended with reason `unsupported`; no
chat opened. This verifies the app action gate while the permission is off.

The next chat-navigation slice is being implemented in the worktree. It keeps
the fixed Saved Messages shortcut and adds a conservative search path for
other names: type a bounded name without Enter, require the same exact OCR
result in the left pane twice, request one session-only pointer grant, check
the focused Telegram ID/PID and window/pointer geometry before clicking that
result, then verify the exact chat title in a fresh image. The owner approved
the pointer grant for Telegram with a system consent prompt. The installed
OCR data remains English-only, so unrecognized or ambiguous names must stop
without a click. This new slice has deterministic tests but still needs a
GNOME extension reload and live owner validation before being called complete.

After a desktop restart, the owner observed a confirmed `Saved Messages`
opening. Other chat attempts were frequently split into `Open chat` followed
by a name such as `Hunter VP`, or STT replaced the intended name with `call
your email`. The generic search entered the transcribed text but returned
`chat_search_uncertain` before any result click; this does not establish an OCR
or pointer defect. The short in-memory fragment buffer now accepts `Open chat`
and `Go to chat` followed by a nearby name, with the existing four-second,
negation, new-command, and stream-reset limits. The uncertainty response now
shows the name actually searched. Focused deterministic tests pass; the new
fragment behavior and arbitrary chat selection still need a live check.

The owner listed many Telegram titles written in Persian. The installed local
Tesseract data currently contains only `eng.traineddata`, and the Qt screen
reader requests `OcrOptions("eng")`, so these titles are outside the currently
verified OCR path. The owner also reported failure to open v2rayN, but the
provided diagnostic lines did not include a V2RayN open intent. Read-only
inspection found `v2rayn.desktop` and `/usr/bin/v2rayn`, both bound and allowed
in KYRIN settings. The local resolver accepts exact `Open V2RayN` and asks
for confirmation on `Open V2Rain`; the observed `Visual Network Configuration`
and `Download Manager` are different transcriptions and cannot safely be
silently mapped to v2rayN. The actual live failure stage remains unconfirmed.

The next OCR change was started after this report. The local Ubuntu Persian
Tesseract data package was downloaded to `local-data/downloads/ocr/tesseract/`
and `fas.traineddata` placed beside the existing `eng.traineddata` in
`local-data/kyrin/models/ocr/tesseract/`; the downloaded package SHA-256
matched Ubuntu's package metadata. The OCR contract now accepts bounded
multi-language codes, and the Telegram verifier selects `fas+eng` only for
Persian-script chat targets. Persian OCR uses Tesseract page segmentation mode
3 and phrase matching accepts right-to-left word geometry. A synthetic
Persian image recognized `آموزش هوش مصنوعی` with three confidence scores above
0.91 and produced one exact phrase match. The owner has not yet checked a
private Telegram chat in the live application, so real chat-name accuracy and
input behavior remain unconfirmed.

The OCR architecture already had an `OcrEngine` contract but the Qt app always
selected the discovered Tesseract runtime in code. A saved `OcrSelection` and
Screen Access package picker now let the owner switch among compatible local
Tesseract runtime folders without editing code. The selection is versioned in
settings schema 9; schema 8 and earlier use the existing default. New reads,
including Telegram verification, use the selected engine after saving, while
an in-flight old read is discarded. Only the Tesseract adapter is installed
today, so different OCR engine families still need their own adapters before
the app can list them. This change does not download a model or establish live
accuracy for Persian Telegram titles.

Later OCR integration added a separate CPU PaddleOCR runtime under the ignored
`local-data/kyrin/runtimes/ocr/paddle/` directory. Three already-downloaded
detector/recognizer pairs from `models/local/ocr/candidates/paddleocr/` are
selectable in Screen Access when their local files and runtime are present:
v5 Persian, v6 Small, and v6 Medium. The adapter returns genuine line boxes
through the existing `OcrEngine` contract and keeps Paddle imports out of the
main Qt process. Each pair recognized the synthetic `Open Telegram` image in an
offline local smoke test; these observations do not establish Telegram action
accuracy or a performance benchmark. Other downloaded vision-language models
still need verified screen coordinates and confidence before they can be used
for action targeting.

PaddleOCR-VL 1.6 was subsequently run offline from its downloaded safetensors
checkpoint in a second isolated CPU runtime. Its spotting output recognized
`Open Telegram` with a real polygon on a synthetic image. The Screen Access
selector can use it for reading. It does not report a confidence score; the
current Telegram and settings action checks require one and therefore stop
without clicking when this engine is selected. Surya, GLM-OCR, and dots.mocr
were later added to a separate text-only experimental section of Screen Access.
They run from project-local isolated CPU runtimes, use the existing screen
permission, and do not supply positions to the click/action path. Each read
`Open Telegram` from a synthetic image in an offline local smoke test. The
dots.mocr custom vision configuration needed `eager` attention explicitly;
changing only the top-level attention setting still called Flash Attention.
This establishes basic execution, not comparative accuracy, live desktop
performance, or suitability for Telegram targeting.

The owner's desktop layout review found that controls on several Qt pages
were compressed at the control window's minimum size: the Desktop Actions app
list could show only one row, Speech Recognition reduced its clear button to
four pixels, and Preferences reduced a button to ten pixels. Settings pages
with longer content now scroll vertically while their app/model lists and
diagnostic fields retain readable minimum heights. The Dashboard and Audio
Input pages fit without scrolling. Plain-text output fields and spin boxes
now use the dark theme, and longer guidance labels wrap. Offscreen visual
checks covered the top and bottom of all nine pages in Persian; deterministic
geometry tests cover English and Persian at the minimum window size and a
30-app Desktop Actions list. Live desktop feedback remains open.

## 117. Spark-X2.5 Q8 local startup and exploratory STT correction audit

The owner downloaded the official Spark-X2.5-4B Q8_0 GGUF to
`models/local/by-model/command-understanding/spark-x2.5-4b/`. The official
llama.cpp Ubuntu CPU release b11617 was placed under the ignored
`local-data/kyrin/runtimes/command-understanding/` tree; its archive SHA-256
matched the GitHub release asset digest. The 4,375,021,152-byte model loaded
on CPU and generated `Open Telegram` from a short `Open Telegrm` smoke prompt.
GPU access was unavailable from the sandbox. No live KYRIN model selection,
action path, or setting changed.

An offline, no-action comparison then reused the saved Whisper `small` automatic
transcripts from 15 speaker-verified recordings (two speakers, 10 positive and
five negative commands). The transcript, never the verified spoken reference,
was supplied to Spark; the reference was used only for scoring. A conservative
spelling prompt changed none of the 15 texts. An exploratory prompt restricted
to names already present changed six texts, mostly capitalization, but the
dry-run rule interpreter still recognized only five of 10 positive intents,
the same as without correction. Neither variant produced an intent from the
five negative cases. Crucially, the exploratory prompt shortened
`مرورگر رو باسکن` to `مرورگر`, deleting the command words and increasing its
character distance from the verified speech. The five no-intent negative
results include unreadable transcripts and are not evidence that the model
understood negation. The second prompt was revised after inspecting the same
cases, so its result is exploratory, not held-out performance. The two detailed
reports are in ignored `datasets/stt/results/spark-q8-*-2026-10-14.json` files.
This experiment does not support adding an unrestricted correction layer to
the live command path. A future candidate needs independent evidence and a
validator that rejects changes to operation or negation words before any live
integration.

## 118. Spark versus selected Qwen 4B command-understanding diagnostic

The next offline comparison used the selected local `qwen3.5:4b` GGUF and
Spark-X2.5-4B Q8_0 with the same llama.cpp b11617 CPU runtime, six threads,
4,096-token context, zero temperature, JSON schema, and shared benchmark
instructions. Native chat templates differed by model. The prompt was refined
once on the separate `en-open-telegram` pilot to state that action routes must
not carry nonempty uncertainty. No desktop executor, live setting, or
microphone was involved. The scored set contained the 15 previously verified
speech clips' saved Whisper `small` automatic transcripts plus nine designed
negation, ambiguity, and app-versus-system scope cases. It is a small
development diagnostic, not representative accuracy evidence or a test of
the exact live Ollama adapter prompt.

Whisper's saved language names were initially passed to the models directly.
The live `WhisperCppServer.transcribe_auto` normalizes these to ISO codes, so
the 15 speech cases were rerun for both models with that same mapping; the
initial full-name-language report remains exploratory. In the corrected
speech comparison, Spark returned valid proposal JSON for 13/15 and exactly
matched reference route and steps for 2/15, both clear English Telegram opens.
Qwen returned valid JSON for 13/15 and exactly matched 5/15. Among the 10
positive speech references, these are 2/10 and 5/10 correct action proposals.
None of the five negative speech cases produced a valid execute proposal;
unreadable negatives still count as abstentions, not proven understanding.

Across all 24 cases (using the nine unchanged designed-case results), Spark
had 18 valid outputs, four exact route-and-step matches, and one valid unsafe
proposal. For `Do not open Telegram; open the browser instead`, it proposed
opening the browser *and closing Telegram*, although no close was requested.
Its source-operation verifier rejected the extra operation. Several other
Spark outputs were invalid, including a system-restart step with an app target
for `Restart Telegram`; the decoder rejected those before any action. Qwen
had 21 valid outputs, eight exact matches, and no valid unsafe proposal in
this set; three invalid responses also failed closed. The fixed-catalog,
source-grounded replay yielded one correct resolved proposal for Spark and
four for Qwen on the 15 speech cases, with zero unsafe resolved proposals for
either. That boundary deliberately abstains on unsupported languages and
negated clauses, so these counts are not end-to-end live success rates.

The median wall time per isolated CPU invocation was about 12.4 seconds for
Spark and 10.5 seconds for Qwen; each invocation reloaded its model, so these
are not warmed serving latencies. Detailed ignored reports and prompts are
under `datasets/commands/results/spark-vs-qwen4b-*-2026-10-14.*`. The
experiment does not support replacing the selected Qwen 4B model with Spark
or enabling Spark for live actions. The independent source, target, and
permission checks remain necessary for any future candidate.

## 119. Portable installed-app vocabulary for post-STT recovery

The owner clarified a product requirement for the proposed post-STT word
recovery: app names must be discovered dynamically from each user's registered
applications and relevant saved settings. A vocabulary copied from this
development machine or limited to Telegram and browsers would not satisfy the
cross-platform product goal. Recognition of a registered app name and
authorization to operate that app are separate decisions. The correction stage
may consider all registered names as candidates, while the existing bindings,
action policy, and confirmation checks continue to govern actions. The original
STT text must remain available; uncertain name matches are suggestions, not
silent changes to command operations or negation.

The repository already has a platform-neutral `AppCatalog` contract and
`InstalledApp` metadata. The current `CatalogSpokenAppResolver`, however,
indexes only explicitly bound applications. Ubuntu populates it through XDG
desktop entries and supplies reviewed Telegram/browser aliases in code.
`AllowedApp.desktop_id` is Ubuntu-specific, and no other OS catalog adapter is
present yet. A future platform adapter must supply its own registered-app
catalog and binding mechanism without changing the portable matching policy.
Per-user spoken aliases, if introduced, belong in settings keyed to stable app
identity, with validation for collisions and stale registrations. The earlier
fixed STT vocabulary-hint experiment did not justify pushing the full catalog
into the recognizer prompt; the proposed use is downstream candidate matching.

## 120. Dynamic registered-app name matching and user aliases implemented

The owner approved implementation with cross-user and cross-platform design as
the primary constraint. The platform-neutral `CatalogSpokenAppResolver` now
indexes every `InstalledApp` returned by its injected `AppCatalog`, including
unbound apps. It still returns only explicitly bound apps to command callers.
An exact name collision with an unbound app abstains; a sufficiently near
unbound app also blocks fuzzy suggestions. This avoids "correcting" speech to
a different permitted application merely because the intended installed app
was not allowlisted. Approximate permitted candidates retain the existing
explicit clarification flow. Raw STT text, operation checks, action policy,
and executor authorization are unchanged.

`AppSpokenAliases` stores bounded per-user alternate names keyed by catalog
platform ID, independently of action permission. Settings schema 10 reads
versions 1-9 with empty aliases and strictly validates new entries. Ubuntu
session composition supplies these aliases to the portable resolver. The Qt
Desktop Actions page lets users select a listed application and edit its
spoken names even when the application is unchecked for control. Stale aliases
remain keyed by platform ID and are ignored while that ID is absent.
`InstalledApp.alternate_names` also carries localized labels supplied by a
platform catalog; XDG reads registered `Name[...]` values without a manual
machine vocabulary.
The small reviewed Telegram/browser aliases remain for existing behavior;
registered names and user aliases provide dynamic vocabulary for other apps.
No model weight, new dependency, or universal transcript rewrite was added.

The implementation is live in the existing Ubuntu product path. Windows,
macOS, and mobile runtime adapters remain future work, as they were before
this change; the matching code requires only the `AppCatalog` protocol and
has a non-XDG test catalog. Focused settings, resolver, Ubuntu composition,
and Qt tests passed. Full-suite behavior and live microphone performance need
separate verification if claimed later.

## 121. Installed Ubuntu app refreshed and real-catalog dry run

On 2026-10-15, the owner approved the next activation step. The managed menu
and autostart launchers both pointed to this checkout's
`.venv/bin/kyrin-desktop`; the virtual environment used an editable install
with its import path at this checkout's `src/`. No reinstall was needed. The
running desktop process was stopped and relaunched in the same graphical user
session. The replacement process stayed running and created its single-instance
control socket. Its log contained a nonfatal host-portal app-ID registration
warning. The saved settings loaded with action execution enabled, 65 allowed
bindings, zero custom spoken aliases, and listening disabled. This step did
not change permissions, settings, or start the microphone.

A no-action dry run against the machine's current XDG catalog found 145
registered apps, 65 bound app IDs, and 80 unbound registrations. Exact
`Telegram`, `تلگرام`, `Visual Studio Code`, and `Firefox` resolved to their
configured IDs. Approximate `Visual Studio Cod` produced only a suggestion.
An exact sample unbound app name returned no command candidate. This confirms
the editable installation and actual catalog integration for these examples;
it does not replace a coordinated live microphone test or measure recognition
quality across users and operating systems.

The existing 15 verified Whisper-auto transcript cases were also replayed
through the bounded interpreter with the current user catalog and settings,
without microphone or actions. Four of ten reference action cases produced
an action intent, three produced a response request, and none of five
reference no-action cases produced an intent. The user's settings have no
generic `browser` binding, so clear `Open browser` examples ask the user to
choose from permitted browsers. These counts are exploratory and reflect
the current settings and saved STT outputs, not new STT accuracy or live
microphone performance.

## 122. Close-Claude clarification loop diagnosed and fixed

The owner reported live English transcripts in which `Close.` was followed by
`Cloud`, then several `Yes.` replies left the request at `confirm_app`. The
fragment buffer can combine the first two transcripts within its four-second
window. Replaying them with the registered Claude app showed that the rules
correctly move from app-identity clarification to a separate close-action
confirmation on the first `Yes.`, and produce `close_app_window` on the
second. The model-assisted wrapper had instead sent that first reply back to
the confirmation model because it treated every `NeedsClarification` as the
same pending question. If that model was unavailable, it restored the old
`confirm_app` state indefinitely. Its question also incorrectly said `Open`
for a pending close request.

`ModelAssistedInterpreter` now preserves a rules-produced transition to a
different pending clarification, accepts completed or declined rule outcomes
directly, and does not classify an explicit new operation as a yes/no reply to
an older app question. Its app-identity question is operation-neutral.
Regression tests cover `Close.` / `Cloud` / `Yes.` / `Yes.` and a new
`Close the code` command during an older clarification. The command, desktop,
and app test groups passed (511 tests, excluding the two host-socket tests
that cannot run in the sandbox); lint and type checks on changed files passed.
The editable desktop app was restarted with the fix and its host process was
confirmed running. No live microphone retest has yet confirmed the spoken
flow. Short or misrecognized STT outputs such as `Close.`, `Load.`, and
`Open Kailin.` remain a separate recognition/fragmentation issue.

## 123. One confirmation for an approximate close target

The owner tested the fixed clarification flow with OnlyOffice and found the
two separate yes/no turns unnecessarily repetitive: `Close only Office` asked
first whether OnlyOffice was the intended app and then whether to close it.
The chosen behavior is one explicit, action-bearing confirmation. For a
single approximate target, KYRIN now asks whether to close the named app; a
single yes confirms both the app candidate and close action. A no declines it.
For several candidates, KYRIN asks which app to close, and the selection
completes that close request. Exact close requests and the separate Terminal
and numbered-window confirmation paths retain their existing rules. The
allowlist and action gate still check the final intent before execution.
Command, desktop, app, and response tests passed after this change. The
editable desktop process was restarted in the graphical session with the new
code. Live microphone behavior still requires the owner's retest.

## 124. Silent recognition clarifications and provisional PipeWire barge-in

The owner asked that an unclear or misspelled speech result not trigger a
spoken announcement, because reading the on-screen response is faster than
waiting for TTS. `REPEAT_COMMAND` and `PendingAppClarification` responses now
use `TEXT_ONLY`; action confirmation unrelated to name correction retains its
previous channel. The presenter still shows the localized question.

The owner also asked to speak while KYRIN's voice is playing and reported
separate loudspeaker and microphone hardware. The existing `PlaybackGuardInput`
silenced all microphone chunks during TTS and therefore prevented barge-in.
PipeWire's bundled echo-cancel module is available on this Ubuntu host. A
temporary Ubuntu-session adapter now creates a virtual WebRTC echo-cancelled
source in monitor mode when the default microphone is selected. A separate
`PipeWireEchoInput` reads its 16 kHz mono PCM. The app bypasses the playback
guard only while this source is active; if module setup is unavailable or a
nondefault microphone is explicitly selected, it retains the guard. No global
audio defaults are changed and no new package is downloaded. The module and
capture process are stopped with the listening session.

The temporary source was created and one 20 ms chunk was read on the owner's
machine without storing the audio. Focused unit tests and command/response/app
tests passed (559 tests). The editable desktop process was restarted with the
new code; saved listening remains disabled and the selected microphone is the
default. This proves wiring and capture availability, not acoustic echo
suppression or recognition quality while a person talks over TTS. The latter
requires a live user test. Other operating systems need their own echo-cancel
adapters or can retain the conservative playback guard.

## 125. Power prompts no longer block spoken confirmation

The owner observed that power-off and restart confirmations still required
waiting for the spoken prompt to finish. The separate system-power flow had a
`voice_ready` check based solely on the response speaker's active state, even
when the Ubuntu listening session used the new PipeWire echo-cancelled source.
The desktop application presents system-power prompts in text/dialog form and
speaks them through the response speaker. While the echo-cancelled source is active, the
flow accepts final spoken replies during KYRIN voice playback; without
that source, the existing playback guard and voice-ready check remain. Spoken
`Continue` is accepted at the first stage alongside `Yes`, matching the button
label and updated prompt. The second stage still requires the exact displayed
action phrase or matching button. No change was made to the two-stage safety
requirement or the underlying GNOME power backend. Focused tests cover the
echo-cancelled active-speaker path and spoken `Continue`.
The initial change mistakenly removed the system-power TTS announcement. It
was restored after the owner reported silent prompts. The live power dialog
and simultaneous microphone response still need the owner's retest;
automated tests did not issue a real operating-system power request.
One prior desktop process had been terminated outside the normal shutdown
path and left its temporary PipeWire module and recorder running. Those exact
orphaned processes were removed without touching the current listening
session. The AEC adapter now detects and removes only stale KYRIN-named
sources whose embedded desktop PID is no longer a running KYRIN process when
the next listening session starts; ownership and executable identity are
checked before terminating associated processes.

## 126. Live preview exposed an ambiguous checking screen and repeated speech

During an owner-run live safe preview, the dialog appeared to advance without
speech and the prompt repeated several times. An immediate conservative guard
was tried, but a follow-up report showed only `[BLANK_AUDIO]` in the STT
diagnostic and the dialog's button still read `Continue`. This means the
visible transition was the automatic `CHECKING` → `FIRST` progression after
the inert backend returned, not a confirmed `FIRST` → `SECOND` voice reply.
The temporary power-only guard was removed so PipeWire barge-in remains
available. The dialog now explicitly labels checking as "no confirmation yet"
and the confirmation stages as 1 of 2 and 2 of 2.

Unclear power replies now update the dialog without submitting another spoken
reminder; this prevents a possible TTS/recognition feedback loop. The second
owner-run preview no longer reported repeated speech, but its stage report was
initially ambiguous. Focused tests cover the stage labels, active-speaker
reply path, and text-only reminders. A further owner-run safe preview is needed
to verify acoustic barge-in with the distinct stage labels. Neither run sent
an operating-system power request.

## 127. Discard late power-stage speech

The owner confirmed that the clearly labelled safe preview did not advance on
its own. They then observed a voice timing issue: the first spoken prompt
played, the next confirmation screen was initially silent, and its audio was
heard only after they had answered that screen. The selected offline TTS is
`kokoro` on GPU. The earlier prompt had finished before they said `Continue`,
so its playback was not holding the queue. A plausible cause is model speech
generation finishing after the stage had changed; this remains an inference,
not an instrumented timing measurement.

`ResponseSpeaker` now accepts an optional stage-validity callback and skips a
queued prompt if its stage is obsolete. `ConfiguredSpeechSynthesizer` checks
the same callback again after model generation, immediately before audio
playback. `SystemPowerFlow` exposes whether a confirmation prompt is still
current. The desktop power announcement wires these checks for the two active
confirmation stages. This prevents
audio that finishes preparing after a stage change from speaking on the next
screen; it does not claim zero TTS preparation latency. A later change now
stops active local-model playback when a new power stage replaces the prompt.
Focused tests cover both skip points.

In the follow-up, the owner heard only a shortened final-stage announcement
through the phrase `Power off`, even while remaining silent. This matched an
intentional shortening of `speech_text`, not proven audio truncation. The
spoken final-stage message now includes the button and cancel options shown
in the dialog. The full audio still needs an owner listening retest.

## 128. Omnilingual ASR v2 local integration

The owner downloaded six Meta Omnilingual ASR v2 checkpoints under
`models/local/by-model/stt/omnilingual-asr/`, with one folder and tokenizer copy
per model. KYRIN now lists these folders individually in the STT model library
and offers `Omnilingual ASR` in Speech Recognition. The selected checkpoint is
loaded in place through a Python 3.12 worker because the main application uses
Python 3.14 and upstream `omnilingual-asr` currently requires `<3.14`. The
worker uses local fairseq2 asset cards and sends final transcripts to the
existing turn-aware STT boundary; it does not download checkpoint duplicates.
The isolated runtime and its caches are under `local-data/`, with upstream
package version 0.2.0 and compatible Torch, torchaudio, NumPy, and PyArrow
versions. Setup and limitations are in `docs/stt/OMNILINGUAL_ASR_FA.md`.

On this machine, `omniASR_CTC_300M_v2` loaded from the project folder and
transcribed two existing English recordings on CPU. One returned an incorrect
Ethiopic-script transcript; the other returned Latin-script text with CER
0.263 on that single reference. These are smoke results, not an accuracy
benchmark. The other five checkpoints and GPU inference have not been run.
An offscreen Qt check listed all six local models, 84 focused tests passed,
and the desktop process was restarted with the new engine code. The owner
has not yet confirmed the visible selector or tried live microphone input.

## 129. Local Omnilingual versus Whisper speech benchmark

The owner approved implementing the next speech-to-command measurement step.
The generic STT evaluator now reports word error rate as well as character
error rate, supports the local Whisper adapter, and can write a new JSON
report. A sequential comparison tool runs each model/language pair in an
isolated subprocess, checks available CPU RAM or GPU VRAM before loading,
and records per-file text, elapsed time, model load time, and peak child RSS.
For GPU, it samples total card memory use and records the delta from the
pre-run baseline. A separate diagnostic scores only speaker-verified command
references with the bounded demo interpreter; it never reaches ActionGate or
an OS executor. The WAV replay comparison tool also accepts Omnilingual.

On the current development workstation, 12 existing, locally consented,
single-speaker WAV files (four English, eight Persian) were scored on CPU.
Whisper small had CER 0 on the four English files and 0.151 on the eight
Persian files. Omnilingual CTC 300M scored 0.576 English and 0.078 Persian;
CTC 1B scored 0.593 English and 0.108 Persian; LLM 300M scored 0.034
English and 0.030 Persian. The CPU memory admission rule skipped CTC 3B,
LLM 1B, and LLM 3B; their model integrity or accuracy has not been inferred
from that skip. A GPU run of LLM 300M produced the same transcripts and
scoring for this small corpus, with mean unpaced per-file processing around
0.29 s English and 0.26 s Persian, excluding model load and recorded-speed
capture. The later GPU-monitored repeat measured about 0.25 s English and
0.27 s Persian per file. The CPU Persian mean for that model was 8.59 s per file. The
speaker-verified command subset yielded three correct positive English
proposals for Whisper small and two correct positive Persian proposals for
LLM 300M, with the tested negative utterances producing no action proposal.
No desktop action was executed. One Persian negation with LLM 300M and one
English close command with Whisper also retained exact reference text through
the paced VAD/STT replay path. A repeated GPU run observed roughly 3.6 GiB
more total card memory used at peak than before each LLM 300M subprocess;
this is a sampled device-wide delta, not exact per-process VRAM. This is a
small development comparison, not a
population accuracy estimate or a live microphone validation. Full method,
reports, limitations, and commands are in
`docs/stt/LOCAL_MODEL_COMPARISON_FA.md`.

On 2026-10-15 the owner separately authorized four ordinary-speech microphone
recordings and confirmed the exact wording of all four 20-second repeats.
Four earlier short captures with utterances at file edges were excluded from
scoring. The ignored `manifest.neutral.csv` points to one complete crop from
each repeat. Whisper small on CPU scored 0.019 CER / 0.10 WER for the two
English clips and 0.040 CER / 0.20 WER for the two Persian clips. Omnilingual
LLM 300M on GPU scored 0.019 / 0.10 English and 0 / 0 Persian. The bounded
interpreter proposed no action for all four neutral clips from either model.
These are single-speaker diagnostics, not a false-action rate estimate.
Paced VAD/STT WAV replay retained the same output as direct STT for neutral
English `neutral-en-02` with Whisper and Persian `neutral-fa-01` with
Omnilingual. For Persian `neutral-fa-02`, direct Omnilingual STT was exact,
but VAD split the utterance into two starts and the live-path transcript
misrecognized the Telegram word; the bounded interpreter still proposed no
action. The VAD-positive runs were roughly 1.06–1.89 s and 2.53–4.99 s in
the crop, leaving about 640 ms of non-speech. The generic 384 ms pause
threshold ended the first turn at 2.24 s. Replaying the same WAV with an
800 ms threshold kept one turn and yielded the exact reference text. Two
verified Persian safety commands, one affirmative and one negated, also
remained exact with 800 ms. Ubuntu composition now passes 800 ms to
`LiveSpeechPipeline` for an Omnilingual selection only; other backends retain
384 ms. The tradeoff is up to roughly 416 ms later finalization after silence
and possible merging of separate utterances less than 800 ms apart. Actual
microphone use inside the running desktop app and multiple-speaker behavior
remain untested.
Appending one second of silence to the problematic WAV confirmed that the
800 ms setting still produces one start and one pause in a continuing stream,
with an exact live-path transcript; it is not relying on end-of-file flush.

## 130. Duplicate Google Chrome registrations caused repeat_command

The owner reported three live `open google chrome` transcripts in English,
each followed by `No action requested` and `repeat_command`. STT had produced
the correct words. The current XDG catalog contains both
`google-chrome.desktop` and `com.google.Chrome.desktop`, each labeled
`Google Chrome` and each launching `/usr/bin/google-chrome-stable`. Only the
first registration is in the owner's allowed bindings. The spoken-name
resolver intentionally abstained on a duplicate registered label when one
registration was unbound; the bounded rule interpreter therefore returned
`UnrecognizedCommand`, which the coordinator presented as `repeat_command`.
The selected command model was not the cause: an exact rules result precedes
model interpretation.

The owner explicitly chose the existing allowed `google-chrome.desktop` as
the target for `Open Google Chrome`. The portable resolver now treats a single
user-assigned spoken name equal to that entry's own display name as a choice
among duplicate registrations. It does not let a name assigned to a different
app override an existing catalog name; multiple user assignments stay
ambiguous. The owner's ignored local settings now record `Google Chrome` as
an alias on `google-chrome.desktop`, preserving all other settings. A dry run
with the real catalog and saved settings produced `OPEN_APP` targeting
`google-chrome` without executing the action. Focused resolver, settings, and
Ubuntu composition tests cover the fix. The running desktop process must
restart before it reads the changed code and settings; a live voice retest
has not yet been observed.

## 131. Telegram named-chat search and transcript capitalization

In a first live `Open Chat My Mother` trial on 2026-10-16, the installed app
heard the intended phrase and produced `open_chat: my mother`, but reported
`chat_search_uncertain` after 3,803 ms from final text to result. The owner saw
the target typed in Telegram search and no matching row. A read-only portal
capture with local Tesseract found one high-confidence phrase match at x=67,
y=45, inside the search field; it did not find a result-row match. The owner
reported that manually typing the visible spelling `My Mother` produced the
chat result. This isolates the observed failure to the search stage rather
than command recognition or OCR letter-case comparison. No uncertain row was
clicked.

The command path already used Unicode `casefold()` to compare recognized
speech and OCR without case sensitivity, but its rule interpreter discarded
the final transcript's capitalization when constructing `OPEN_CHAT`. A shared
normalization utility now keeps case-insensitive comparison while recovering
the source spelling for a chat target before sending it to an external app.
The model-assisted path applies the same recovery after source grounding.
Regression tests cover mixed-case chat names, OCR matches, split utterances,
and multi-step commands. In the next live trial, KYRIN interpreted
`open_chat: My Mother` and typed the correct spelling. The owner confirmed the
first local chat row was visible, but KYRIN still stopped with
`chat_search_uncertain` after 3,674 ms from final text to result. A read-only
portal capture found the query at y=45, that chat row at y=92, and four more
exact-name matches at y=182, 244, 368, and 492 in Global Search Results.
The previous verifier excluded y=92 and treated lower repeated names as an
ambiguity. No row was clicked.

The owner then specified a two-stage choice: choose the local chat or Global
Search Results first; if Global Search Results is chosen, present numbered
rows for a second choice. The OCR parser now separates the first local row
from lower repeated exact-name matches and exposes both categories through the
Qt screen verifier. A session-scoped Telegram selection flow now asks for the
local chat or global results, then accepts a 1-based global result number from
top to bottom. Invalid answers repeat the current question; cancellation and
expiry discard the pending selection. The action re-reads all choice boxes and
the focused Telegram identity before clicking a selected row. Tests cover the
dialogue, stable rows, and changed results. The parser still recognizes only
global rows with exact-name OCR matches, and no live named-chat opening after
this change has yet been observed.

The first live repeat after adding dialogue still returned
`chat_search_uncertain` after 7,146 ms from final text without showing the
choice question. A separate owner-approved, non-persistent portal capture of
the same search returned a 1920×1080 image with exact-name matches at y=45,
92, 182, 244, 368, and 492; the parser classified one local chat and four
global rows. This points to a difference in KYRIN's persistent capture/read
path, not a failure of the pure parser on that captured image. A content-free
choice-read status is now emitted in the action diagnostic so the next live
run can distinguish capture, identity, OCR, and classification failure.

The next two owner runs still showed no choice prompt:
`chat_search_uncertain:unclassified_matches_1` with `My Mother`, then
`chat_search_uncertain:classified_own_0_global_0` with `my mother`. These
statuses show that the in-app OCR did not classify a result row in either run;
they do not establish whether rows were absent from the captured frame or
missed by OCR. The settle loop no longer treats two empty classifications as
a stable search result. A content-free diagnostic now includes image size and
the positions of exact target matches for the next live run. The corrected
wait and diagnostic pass deterministic tests; live validation is pending.

A fresh owner-authorized read-only portal capture while KYRIN's query was
visible found only the phrase in the search field at x=67, y=45, with no
matching result row. The owner reports that clearing the field and typing the
same name manually produced the chat row. Telegram Desktop's `Ctrl+F` search
can be scoped to the open conversation; the previous helper invoked it
without leaving that context or clearing an existing query. Search input now
presses `Esc`, then `Ctrl+F`, selects the existing field content, and types the
target. The pointer helper's lower bound now permits the observed first local
row at y=92 in a 1080-pixel image while excluding the query at y=45. These
are proposed corrections backed by deterministic tests, awaiting live owner
validation; the capture does not prove which search mode was active.

The owner identified the scope difference directly: with a chat open on the
right, KYRIN searched inside that chat; with no chat open, Telegram displayed
matching chat results. The latter run still returned
`chat_search_uncertain:unstable_unclassified_matches_4_size_1853x1048_at_67-42_69-92_155-244_71-492`.
A later selected-window portal capture at 1920×1080 found the query, local row,
and four exact-name global matches; pure classification returned one local and
four global choices. The in-app four-match read therefore remains an OCR or
classification discrepancy, not an absence of all results. Search input now
sends two `Esc` keys before `Ctrl+F` (to close an existing search and leave an
open chat), checks Telegram focus, then selects prior query text. Query-title
classification accepts a lower OCR confidence than result rows; diagnostics
now include match confidences. A live retest of these changes is pending.

The owner confirmed that the two-Escape search path displayed results even
with a chat initially open, but still did not ask for a choice. The diagnostic
was `unstable_unclassified_matches_4_size_1853x1048_at_67-42-5_69-92-96_155-244-96_71-492-0`.
Thus the typed query itself had only 5% OCR confidence while the first local
row and one global row had 96%; the old query threshold discarded the whole
classification. The parser now requires an exact, unique query phrase in the
search-field geometry without imposing a confidence floor on that known typed
text. Result rows still require 75% confidence and two stable full reads
before a choice prompt or click. A live owner retest is pending.

That retest still produced no prompt. The diagnostic
`unstable_unclassified_matches_3_size_1853x1048_at_69-92-96_155-244-96_71-492-0`
showed that OCR omitted the query entirely while reading the local row and
one global row at 96%. Classification now allows a missing query only when
a unique, high-confidence local row appears in the expected left-pane band.
The automatic single-result click still requires an exact query-field match;
all choice clicks still require fresh stable rows, focused identity, portal
geometry checks, and header verification. A live retest is pending.

The next owner retest opened `My Mother` successfully with `Action result:
confirmed` after 7,375 ms from final text, without a choice prompt. The
owner clarified a revised product rule: a single existing chat with the
requested name should open directly even if global search results also match;
ask for a numbered choice only when two or more selectable chats have that
name. The current implementation now prioritizes local chat rows over global
results, uses a recognized `Search Results` section heading to separate
multiple local rows from lower results, and prompts with 1-based numbers for
multiple local matches. Global rows alone do not start this selection flow;
an unmatched local chat remains unverified and is not opened automatically.
The prior local/global two-stage prompt is
superseded. Deterministic tests cover one local plus globals, two locals,
numbered selection, and changed-row rejection. A real duplicate-name chat
has not been available for live validation.

In the owner's next run, diagnostics showed `Reason or clarification:
conversation`, but the avatar stayed on `Opening My Mother's Chat` without
showing the question. Code inspection found that the choice request was
emitted during action execution; the visual controller suppresses ordinary
conversation requests while `_executing` is true. The selection callback now
explicitly transitions the visual state to `QUESTION` and clears the executing
flag. A timer expires an unanswered choice after 45 seconds and publishes
failure feedback; stopping or ending the runtime cancels a pending choice. The owner
has not yet live-tested this fix. The latest rule also limits selection to
multiple local rows, so a single `My Mother` chat should open without a
question even when global results repeat its name.

## 132. Remembered Telegram pointer consent

The owner reported that opening a named Telegram chat works but prompts for
pointer access on every click. The keyboard portal grant was already
remembered, while pointer clicks always used `persist_mode=0`. Desktop
Actions now has a separate, default-off `remember_telegram_pointer` checkbox
in settings schema 12. When checked, the click helper requests pointer
`persist_mode=2`, stores an opaque single-use restore token, and rotates it
after each successful session. Disabling the checkbox or Telegram chat
permission deletes that token. The per-action Telegram identity, result-box,
pointer-position, and chat-header checks remain. Deterministic settings,
UI, and portal tests pass; owner validation of the system's actual pointer
restore behavior remains pending. Portal persistence can be withdrawn or
refused by the desktop, in which case the system consent dialog may reappear.

## 133. Numbered Telegram chat selection fails after the spoken answer

In two subsequent owner runs, `Open Chat My Mother` produced a conversation
question, but both `One` and `Number 1` ended in `chat_search_uncertain` after
about 12–16 seconds from final answer. Thus the display handoff is now
working; failure occurs during the fresh OCR reread before the selected row
can be clicked. The owner reports that the question offered three numbered
`My Mother` matches; the exact local/global division was not recorded.

The selection implementation compared every global result box between the
initial question and final click, even though only local rows are selectable.
It now checks stable local rows only, so refreshes in the unrelated global
section cannot invalidate a local selection. The completion feedback now
distinguishes a failed fresh read from changed local rows without reporting
message contents. Deterministic tests cover a global-row refresh before and
after the question.

In the next owner trial, answering `Number One` reached an operating-system
permission dialog before the chat click. Code inspection identifies this as
the `org.freedesktop.portal.RemoteDesktop` pointer-device grant requested by
the Telegram click helper. The owner's `remember_telegram_pointer` setting is
enabled, and the owner-only pointer restore-token file was updated at the time
of the trial. This is strong evidence that the dialog was the portal grant;
the exact wording and whether the chat finished opening were not observed.

## 134. Advance Telegram RemoteDesktop setup

The owner confirmed that the mid-command dialog was named Remote Desktop and
asked for a one-time setup action inside KYRIN instead of a consent request
while choosing a chat. The portal's official API supports persistent grants
and single-use restore tokens, but says a revoked or un-restorable token can
cause a system prompt again. The initial pointer-only remembered grant was
therefore superseded by a Desktop Actions setup button that requests keyboard
and pointer together, saves one `telegram-control` restore token, and rotates
it for each Telegram input action. The existing default-off
`remember_telegram_pointer` settings field gates this combined control setup;
its UI label now names both devices. A missing saved setting or token stops
chat actions with `telegram_control_setup_required` before the action-time
portal request. Disabling the setting or Telegram chats removes the token.
The button launches the portal helper asynchronously so the Qt window stays
responsive. Focus and visual verification still apply to each action.
Deterministic tests cover setup, token rotation, no grant during action when
setup is absent, and UI wiring. The owner then restarted KYRIN, completed the
in-app control setup, and reported that chat selection worked without the
previous permission interruption. The owner did not provide a final
`Action result` line, so this confirms the observed user flow rather than a
recorded action outcome. Future OS revocation can still require a new grant.

## 135. Telegram duplicate-row correction and global-only choices

The owner tested two local chats named `My Mother`. Saying `Number 2` initially
opened the first chat while KYRIN reported `confirmed`. A read-only portal OCR
capture showed local chat titles at y=92 and y=154, plus another occurrence
of `My Mother` in the first row's preview at x=350, y=116. The parser counted
that preview as the second local choice. It also missed the global section
heading because OCR read only `results` at y=203. The parser now limits local
titles to Telegram's title column, recognizes a high-confidence left-pane
`results` heading when the full heading is absent, and extends adjacent local
rows when the heading is missed. A second read-only capture classified local
rows `(92, 154)` and global rows `(244, 306, 430, 554)`. The owner restarted
KYRIN and reported that `Number Two` opened the intended second chat. No final
diagnostic line was supplied for that successful retest.

When no local chat matches, a visibly identified global-results section can
now start a numbered selection. The prompt explicitly says these are global
search results; even a single global result requires a spoken number. Before
clicking, KYRIN rereads and compares the global row boxes. If the section
heading is not observed or rows change, it does not click. Existing local
priority remains: one local match opens directly, while multiple local
matches use local numbering and ignore global refreshes. Deterministic tests
cover the new parser geometry, global-only question, selected click, and
changed-row rejection. A live global-only case has not yet been tested.

## 136. Natural spoken Telegram choices and STT test scope

The owner reported that the current speech recognizer transcribes `matin` as
`Martin` and does not reliably preserve the coined name `kyrin`. The current
navigation acceptance tests should therefore use names with clear English
pronunciation, while custom-name and multilingual STT improvements remain a
separate future work item. These transcription errors do not establish which
words occurred in the recognizer's training data. The global-only live path
remains unconfirmed: `Admin` opened successfully, but a read-only check found
that it also had a local row above the global section.

Telegram's pending selection now accepts cardinal and ordinal replies such as
`number two`, `two`, `the second`, `the second one`, `second option`, `2nd`,
`option number two`, and `choose the second`. Standard Persian number and
ordinal forms are also accepted. Words for one through ten and first through
tenth are supported; numeric replies still require a valid displayed index.
The entire answer must fit the small selection grammar: negated, ambiguous,
multi-choice, and out-of-range replies repeat the question without completing
the action. Local and verified global choices share the parser and still
require the executor's fresh row and window checks. The spoken prompt now
mentions ordinal replies. Deterministic selection and executor tests cover
equivalent forms, correct row selection, and rejected answers; these new
ordinal phrases have not yet been validated live through the microphone.

## 137. Offscreen and archived Telegram chat discovery

The owner pointed out that the intended chat may be far down the initial chat
list or in Archive, and that `Open My Mother chat` should work alongside
`Open chat My Mother`. Inspection showed the named-chat action already exits
an open conversation and types the target into Telegram's own search. It does
not crawl the initial list; therefore a chat being initially offscreen is not
by itself a known limitation. The verifier does inspect only the currently
visible search-result rows and cannot yet page through more matches. Archive
coverage has not been confirmed with a live named-chat run. An upstream
Telegram Desktop issue indicates that archive and search can interact, but is
not sufficient evidence for this user's installed version or for KYRIN's OCR
classification. The owner chose `My Mother` for a future archive test; at
the time of the first follow-up run, the selected chat was still ordinary.

The single-command rule interpreter and the model source-target grounder now
accept `Open My Mother chat`; the rule path also accepts the possessive form.
The final transcript's name spelling is preserved for Telegram search. This
is command phrasing support, not a fix for STT changing a name to another
word. Focused deterministic command tests pass. The owner then restarted
KYRIN and spoke `Open my mother chat`; KYRIN reported `open_chat: my mother`,
requested a numbered match, and confirmed opening after `First`. The owner
confirmed that this was an ordinary chat and planned to archive one of the
same-name chats for a separate test.

After archiving one of the two `My Mother` chats, the owner observed in
Telegram's search that the ordinary row was first and the archived row
second, both above `Global Search Results`. Thus the current search surface
exposes this archived chat without separate Archive navigation. A KYRIN
`Open my mother chat` attempt reached the selection dialogue but ended with
`Action result: failed (chat_selection_cancelled)`. The owner also said the
chat opened, so that statement and the diagnostic do not establish a
confirmed archived-row selection; a focused `Number Two` retest followed.

In that focused retest, the owner answered `Number Two` and confirmed that
the archived chat opened. The final `Action result` line was not supplied,
so this is owner-confirmed visual behavior rather than a recorded outcome.

## 138. Bounded desktop scroll and Telegram result paging

On 2026-10-18 the owner confirmed the previous named-chat selection correction
works and requested scrolling inside an open Telegram conversation, in addition
to the left chat list. Explicit area commands now distinguish `Scroll chat
down/up` (right conversation pane) from `Scroll chat list down/up` (left list),
and `More` repeats the area. The general desktop-scroll token and smooth-axis
input remain in use. Focus and pointer checks are unchanged. This has
deterministic tests but still needs a live owner movement check.
The short `Scroll down/up` retains its prior left-list behavior; a user
preference question about changing that default remains open.
The owner then tested the new in-conversation scroll and reported it worked
well. This is live owner-confirmed movement, without a recorded action line.

**IMPLEMENTED, LIVE VALIDATION PENDING (2026-10-18):** The owner requested
voice navigation within Telegram to Archive, Contacts, Settings, My Profile,
and Calls, plus `Create new group` and `Create new channel`. The bounded English
rule path now recognizes these phrases only while Telegram is observed as the
active app. The gate requires the existing Telegram chat permission; the
executor requires screen access, saved Telegram input consent, and matching
foreground desktop ID/PID. Archive and Contacts use Telegram Desktop's
documented default Ctrl+9 and Ctrl+J shortcuts. The remaining destinations
open the main menu, require two stable OCR reads of the exact menu label,
then click the bounded box. A fresh OCR read checks the destination heading;
uncertain heading detection reports dispatch rather than confirmation.
Creation commands stop at the initial wizard and do not create a group or
channel. Deterministic tests pass; the owner's installed Telegram layout and
custom shortcuts still need live validation.

The owner's first live Archive and Contacts trial resolved both exact voice
commands to `telegram_view`, and the owner reported the pages opened. The
diagnostics nevertheless returned `unknown (executor_exception)`. The cause
was an invalid `ActionResult`: the unverified-heading path combined
`LAUNCH_ACCEPTED` with an `error_code`, which the result contract rejects.
That path now returns a valid accepted outcome without an error code, with a
focused regression test. The owner then confirmed in a restarted live trial
that `Go to archive` opens Archive and `Go to contacts` opens Contacts. The
exact post-fix `Action result` lines were not supplied, so the owner's visual
confirmation establishes navigation but not OCR heading confirmation.

The next owner trial found that menu destinations from Archive required
repeating the command: the first top-left click returned to the ordinary chat
list, the next exposed the main menu, and only then could the destination be
selected. `Go to my profile` and `Go to calls` initially failed with
`telegram_menu_uncertain`; repeated commands eventually reported
`launch_accepted`. The STT phrase `go to setting` entered a generic Settings
app suggestion instead of Telegram navigation. The menu flow now checks for
a stable, anchored menu item before clicking and can make up to two bounded
top-left clicks to leave Archive and open the menu in one command. The rules
also accept singular `setting`, singular `contact`, `my calls`, and a trailing
`telegram` qualifier while Telegram is active. Live retest remains pending.

In the next owner trial, `Go to my profile` and `Go to setting` resolved to
`telegram_view` and reported `launch_accepted`. Spoken `Go to my calls` was
repeatedly transcribed as `go to my carls`, which the rule path did not
recognize. A narrowly scoped alias now maps the observed `my carls` spelling
to Telegram Calls only while Telegram is the observed active app. This is an
STT output correction; Calls navigation still needs a live retest.
The owner subsequently reported that Calls now works after the observed STT
spelling alias was added. Exact post-fix diagnostics were not supplied.
The owner then asked to proceed with New Group and New Channel; the current
implementation opens their creation screens but does not submit a group or
channel. Live testing of those two entry points is pending.

On 2026-10-16 the named-chat selection guard was tightened after code review.
One visible personal result is no longer auto-opened when the Global Search
Results boundary is unverified: another same-name personal result might be
offscreen. The user instead gets a numbered choice and can say `next` for
bounded result paging. Paging keeps the personal/global category, including
global pages whose section heading has scrolled away. A later personal page
without a visible verified section boundary is rejected as ambiguous.
Numbered clicks whose
titles are shared now report `launch_accepted` after a matching header rather
than claiming the exact chosen chat identity was confirmed. Focused tests pass;
these changes have not yet had a fresh owner microphone test. This is a
conservative safeguard, not exhaustive discovery beyond the existing page and
scroll limits.
Spoken `Cancel` during an active result-page read or selected-row completion
now reaches that operation. A cancellation before the click prevents it; if
the OS click has already occurred, the actual action result is reported rather
than suppressed. Deterministic tests cover both timing cases. Live owner
validation is pending.

The owner requested both generic voice scrolling and bounded navigation of
offscreen Telegram search results, in that order. A separate default-off
`allow_desktop_scroll` setting (settings schema 13) and `desktop-scroll`
RemoteDesktop pointer restore token now gate generic scroll commands. In
Desktop Actions, the user selects apps, saves the scroll setting, and runs
the dedicated setup button. `Scroll up/down` and short Persian equivalents
resolve only against a freshly observed active selected app. A new executor
checks the focused desktop ID/PID, then a system-Python helper checks focus,
window geometry, and pointer position before sending three discrete vertical
axis events near the window center, or inside Telegram's left chat list. It
reports an accepted dispatch, not a verified change of content. The generic grant is separate from the existing
Telegram chat-control grant; disabling the setting deletes its token.

The Telegram named-chat action now uses the same bounded pointer-axis helper
with its existing `telegram-control` token, aiming inside the left results
pane. If no exact selectable row is visible after search, it tries up to
four scrolls within an 18-second scan deadline, rereading stable OCR choices
after each. While a numbered choice is pending, `next`/`more results`/`بعدی`
scrolls to another visible page, with at most five pages. A changed digest
of visible left-pane OCR text is required for the next-page prompt. The
digest is transient and not logged. A selected number still undergoes the
existing fresh row, focus, and header checks. Duplicate names are numbered
within each visible page rather than accumulated across pages. Live portal
and microphone tests of Telegram result paging remain pending.

The first owner microphone test of generic scrolling recognized `Scroll down`
three times and showed the Remote Desktop dialog on the first action only.
All three returned `confirmed` but the owner saw no movement. The original
generic target was the center of the Telegram window, which can hit the open
conversation instead of the chat list. The target now aims into the left
list, and the result is `launch_accepted` because no visual movement check
exists. The observed `More, Scroll Down` phrasing is also accepted. These
This initial correction was subsequently tested live as described below.

The owner restarted KYRIN and confirmed four consecutive `Scroll down`
commands moved Telegram's left chat list, each returning `launch_accepted` in
about 1.5–1.6 seconds from speech onset. The owner reported that the three
discrete wheel steps felt like an abrupt jump. Generic scrolling now sends
twelve small `NotifyPointerAxis` events over roughly 440 ms, with focus checks
throughout; Telegram search paging retains its discrete input. Deterministic
tests pass. The owner then restarted and reported two smooth scroll commands
that moved the list, each returning `launch_accepted`. The owner requested
slightly slower movement, so the pause between pulses increased from 25 to
40 ms. This timing adjustment needs a final live feel check. No new Remote
Desktop dialog was reported, but the owner did not explicitly answer that
part of the question.

The owner then clarified that standalone `More` should repeat the previous
scroll direction (up after up, down after down), while explicit `scroll ...
more/less` should adjust the distance. The coordinator now carries the recent
scroll direction and amount for at most 30 seconds and only in the same
foreground app. Plain down/up use three units, explicit more uses four,
explicit less uses two. The spoken `More Scrolls Down` variant is recognized
as an ordinary down action. Deterministic tests pass; microphone validation
of these new phrases is pending.

The owner microphone retest confirmed `More` repeated an upward scroll and
`Scroll down more` dispatched. Three attempts reached the interpreter as
`More Skool Up`, `Scroll down list`, and `Scroll up Liz`, so they did not act.
The direct grammar now accepts those bounded scroll-shaped ASR variants;
`Oh` remains non-actionable because it is ambiguous. The owner reported the
motion itself felt good. The new spelling aliases need a live retest.

The owner subsequently requested that generic scrolling work in every
focused desktop app, independently of the app-selection and window-control
permissions. The earlier composition allowed speech and policy checks for
all selected installed apps, but built the scroll executor's desktop-ID map
only from `allowed_window_apps`; scroll could therefore fail even with its
own permission enabled. Generic scroll now uses the GNOME extension's fresh
focused-window desktop ID as a scroll-only command target. The action rereads
the focused desktop ID/PID and the portal helper checks them again before
pointer movement. The saved scroll permission and one-time RemoteDesktop
grant remain required. `More` still needs the same focused desktop ID within
30 seconds. The UI permits saving scroll without selecting any app and labels
the setting for the focused app. Opening apps, chat navigation, and window
controls keep their separate allowlists. Deterministic command, gate,
composition, executor, and UI tests pass. The owner then reported a live
`Scroll up` in ChatGPT and a successful `Scroll down` after removing the
per-app permission in KYRIN. The owner agreed that generic scroll should
remain available without individual app permission. Exact `Action result`
lines were not supplied, so this is owner-confirmed visible movement rather
than a recorded action outcome. A window with no identity from the GNOME
endpoint cannot be scrolled by this voice path.

## 139. Voice listening modes

The owner requested voice activation at startup, voice standby, and a spoken
complete microphone shutoff. A configured KYRIN installation whose saved
`listening_enabled` setting is true now starts its existing local STT/microphone
session in standby. In standby, ordinary transcripts and activity are not sent
to the command interpreter or normal live UI; an exact `Start listening`
activates commands. Exact `Stop listening` returns to standby without closing
the audio session. `Turn off microphone completely` (also the variant with
`the`) closes the session via the application controller and persists
`listening_enabled=false`. The separate GUI button does the same. An explicitly
saved off setting stays fully off at next startup and requires the GUI button
to reenable capture. Persian equivalents are implemented in the same bounded
phrase matcher.

This first version reuses the selected local STT engine while in standby and
filters its output; it is not a separate low-power keyword spotting model.
The fixed shutoff phrase is a control phrase, not an authentication secret.
Deterministic runtime, controller, and Qt tests pass. In the first owner
restart test, spoken `Start listening` did not activate the initial standby
session despite repeated attempts. The owner used the GUI Start button; after
that, spoken `Stop listening`, `Start listening`, and `Turn off microphone
completely` worked. This establishes those later controls, but does not
establish reliable first wake at startup.

The controller had marked its session RUNNING before the STT session and
microphone capture opened, so the UI could display standby before audio was
actually available. The pipeline now emits `AudioCaptureReady` after its first
captured chunk, and the UI displays a microphone-starting state until that
event, resetting the indication after a speech-session restart. The GUI Start
button is disabled until capture is ready. Unit tests and the full suite pass;
at that point, the first spoken wake still needed a retest after the UI showed
standby. If it failed again, the next step would have been to inspect the first
STT transcript/segmentation without assuming readiness was the sole cause.

On 2026-10-20, the owner reported a successful live test of the first spoken
`Start listening` after launching KYRIN. The earlier first-wake issue is no
longer considered open. No diagnostic transcript was supplied for this retest.

The owner later found that saying `Turn microphone off` after `Stop listening`
did not shut down capture, while resuming first and using the full phrase did.
The runtime already checks exact control phrases while in standby; this
shorter spoken wording was absent from its bounded phrase set. It now accepts
`Turn microphone off` and close word-order/articles variants in both active
and standby modes. A focused runtime test covers `Start listening` → `Stop
listening` → `Turn microphone off` without a second start. Live microphone
validation of the new wording remains pending.

## 3D dashboard experiments and 2D decision

On 2026-10-20, the owner chose to keep the existing 2D point animation as an
option for lower-powered systems and add an interactive 3D option for the same
logo and point-based text. The first 3D attempt merely layered copies of the
2D artwork. The owner explicitly rejected that as superficial and requested
an actual model with visible sides and back and unrestricted mouse rotation.
The next procedural scene generated a sphere, torus, and curved round arms,
but the owner found that its frontal silhouette was a different logo. A
later prototype mapped the same color samples used by the approved 2D
scene onto curved front and back surfaces, with point-sampled side walls and
a spherical dark core. It preserved the frontal silhouette but still looked
like joined sheets to the owner. A final procedural solid-blade experiment
also failed to match the desired logo. A single image could not determine
the hidden shape to the required standard.
After evaluating multiple prototypes, the owner decided to omit 3D from the
current version and keep only the approved 2D particle scene. The production
choices are now `cpu` and `gpu`, both 2D. All 3D rendering, geometry,
interaction, and preference UI code was removed. A saved `gpu3d` preference
is read as `gpu`, preserving the selected locale and animation setting. The
2D GPU path remains supported by the existing `PySide6_Essentials` package.
Performance on other drivers and weaker systems remains unmeasured.

On 2026-10-20, the owner asked to increase the 2D particle count by about
one half. The packaged emblem samples grew from 29,999 to 44,999 by adding
color-matched positions between nearby existing samples. Point-sampled text
also gained intermediate glyph samples. A 1000×600 GPU preview had 46,755
total points, about 1.5 times its prior count of 31,287. The 2D CPU and GPU
renderers still share the same particle data and animation cycle. On this
machine, five 1000×600 offscreen CPU grabs averaged about 41 ms with the old
emblem sample count and 61 ms with the new one; these are rendering snapshots,
not a measured animation frame rate or a cross-device benchmark.

The owner then chose renderer-specific density: CPU keeps the first 29,999
approved emblem samples, while GPU uses 59,999. The additional 30,000 samples
are derived from color-matched nearby points in the same artwork. After the
owner reported little visible change, measurements showed that about 80% of
the earlier additional samples were within 2/1000 of a base point (roughly
1 pixel at a 500-pixel emblem size), while GPU dots were 3 pixels wide.
The additional samples were redistributed toward gaps between similar colors;
the median distance to a base point is now 3.5/1000, and the GPU emblem dot
size is 2.5 pixels. This makes density more visible while retaining the
approved silhouette. The CPU
path loads only its base particle objects; selecting GPU loads the full set,
and returning to CPU releases the extra objects. GPU initialization failure
also restores the CPU count. The denser text point sampling remains in both
renderers. The earlier 44,999-sample state was an intermediate experiment,
not a separate user-selectable mode.

On 2026-10-20, the owner requested two GPU-only density choices. At that stage the
2D options are CPU (29,999 emblem points), GPU Light (29,999), and GPU Heavy
(119,999). The previous saved `gpu` choice maps to Light. The first 59,999
packaged samples remain in their earlier order; another 60,000 reproducible
samples fill nearby gaps, weighted toward the luminous logo. The additional
samples are stored separately and loaded only for Heavy. The heavy GPU
draw uses lower per-point opacity so overlap does not wash the blue and purple
artwork into bright white, while text keeps its original opacity and point
sampling. A 1000×600 Wayland/OpenGL preview rendered 31,755 total points in
Light and 121,755 in Heavy, including point-based text. CPU mode and the
animation pause behavior were unchanged.

The owner then observed that the 120k heavy option mostly made existing
points brighter while leaving visible gaps. They requested 30k/60k/150k GPU
Light/Medium/Heavy choices and a shared starting cloud for logo and text
particles. Heavy now adds 90,000 points sampled directly from colored pixels
of `kyrin-logo-original.png`; candidates are accepted in passes that fill
larger gaps before smaller ones. Medium uses the pre-existing 59,999 samples.
Text remains point-rendered, and its start positions and timing now match the
emblem's uniform scene-wide scatter, so white text points and colored emblem
points start mixed before moving to their separate final shapes. In a
1000×600 Wayland/OpenGL preview, Medium drew 61,755 total points and Heavy
drew 151,755, including 1,756 text points. The CPU option remains 29,999
emblem points.

The owner then corrected the artwork source: the intended reference is the
1254×1254 cosmic image they attached, with fine stars and extended blue and
purple energy halos, not the transparent `kyrin-logo-original.png` used by
the earlier heavy-point generator. The attached image is preserved as
`src/kyrin/app/qt/assets/dashboard_reference.png`. All renderer modes now
sample their moving points directly from this one reference. CPU and GPU Light
each keep exactly 29,999 points, GPU Medium uses 59,999, and GPU Heavy uses a
768×768 grid (589,824). GPU points keep the reference's sampled RGB instead
of the earlier coarse palette. The earlier synthetic halo and central-hole
shapes were removed so they cannot change the approved silhouette. Text is
still drawn as moving points in both CPU and GPU modes. The obsolete JSON
particle sets and their generator were removed. A 1000×600 Wayland/OpenGL
preview showed the approved cosmic silhouette with fine details in Heavy;
the CPU preview showed the same image source at its fixed lower density.

The owner found CPU, GPU Light, and GPU Medium too dim and soft, while GPU
Heavy looked better but could be brighter. The cause was smooth downsampling
of the 1254×1254 reference to 174×174 or 245×245 before point selection,
which diluted thin light trails and stars. GPU point radius also shrank as
the square root of density, leaving roughly the same screen coverage in
Light and Medium; the fragment shader's broad fade further reduced brightness.
The low-density modes now blend each grid cell's averaged color with its
brightest source pixel, preserving isolated bright stars. CPU still uses
29,999 particles with slightly wider pens. GPU uses a tighter point-edge fade
and improved coverage, especially in Medium. Heavy keeps its 768×768 grid
and applies a mild color gamma of 0.96. A 1000×600 screenshot diagnostic of
source-bright regions measured output mean brightness of about 192 CPU,
163 GPU Light, 167 GPU Medium, and 176 GPU Heavy after the change. On the
owner's machine, five offscreen CPU grabs averaged about 38 ms; initial CPU
sample preparation took about 326 ms. These are snapshots, not cross-device
frame-rate measurements.

The owner still found the three limited modes hazy, and requested that minor
background details be removed there while keeping CPU at 29,999 points. CPU
and GPU Light now sample 29,999, and GPU Medium 59,999, from brightness bands
of the approved reference: 60% of points in bright features, 25% in midtone
features, and 15% in faint visible features. Pixels below peak RGB 12 are
omitted in these modes. This preserves the main blue/purple trails and ring
without spending their point budgets on dark background pixels. GPU Heavy now
uses exactly 800,000 samples from an 895×895 grid of the full reference. A
1000×600 Wayland/OpenGL preview showed a more legible logo in the limited modes
and preserved the full artwork in Heavy. Text and emblem GPU data now use
one vertex buffer with text points placed before emblem points. This keeps
the text addressable at the front of the buffer even with 800,000 emblem
vertices. Direct OpenGL framebuffer previews after switching GPU modes showed
the point-based text and emblem together.

The owner approved GPU Heavy at 800,000 points but preferred the earlier
locally committed dashboard for CPU, GPU Light, and GPU Medium. Those three
modes now load the original 59,999-sample `dashboard_particles.json` from
commit `953e4ed`: CPU and GPU Light use its first 29,999 points, Medium all
59,999. They also restore the original quantized palette, point sizing,
blue/purple background halos, dark center, and text scatter/timing. Heavy
continues to use the approved `dashboard_reference.png` at exactly 800,000
points, with its previous color sampling, shader edge, and mixed text cloud.
Visual Qt/OpenGL previews on the owner's machine showed both variants in the
same dashboard after switching modes.

The owner noticed a square/checkerboard texture when viewing GPU Heavy up
close and requested a fix scoped only to Heavy, while keeping the emblem
crisp. The 895×895 sampling grid now uses deterministic within-cell jitter
for positions; sampled RGB and the 800,000 count remain unchanged. Heavy
points have a 1.5-pixel minimum size and reduce alpha as they converge, so
the formed image blends away regular pixel rows without dimming the dispersed
particles. Text keeps full opacity. CPU, GPU Light, and GPU Medium retain
their committed sampling and rendering. A 1000×600 local OpenGL preview
showed reduced regularity with similar mean/max-channel luminance in the
emblem region (about 109 before and 113 after); the fine cyan/magenta
filaments and stars remained visible.

The owner then observed that CPU, GPU Light, and GPU Medium still appeared
to form the emblem before the welcome text, with the two groups scattered in
different parts of the dashboard. Their text points now start uniformly
across the full scene with the same delay range and formation duration as
the emblem points. The CPU right-side shade fades in with formation so it
does not hide scattered emblem colors. GPU Heavy's particle data and render
settings remain unchanged.

The owner then requested resource cleanup when switching between GPU and CPU
and a genuine static-image mode when dashboard animation is disabled. The
dashboard now composes the approved reference image with the current
translated welcome copy into one cached raster image, invalidated on resize
or translation. Disabled animation stops its timer, releases all point data,
and destroys any GPU widget resources. Point data is loaded lazily when an
animated renderer becomes visible. GPU-to-CPU transitions explicitly destroy
vertex buffers, vertex arrays, and shader programs while the OpenGL context
is current; Qt's deferred widget deletion follows. GPU-to-GPU transitions
reuse the widget and replace its point buffer with the selected mode's data.

The owner reported that visible Telegram chat opening still fails when an
English speech recognizer hears `martin` for the visible `matin` chat, renders
a Persian name such as «ابوالفضل عبادی» in Latin phonetic words, or hears only
the Latin portion of a mixed Latin/Persian title. The command interpreter
continues to preserve the heard target; a separate, bounded OCR grounding
step now proposes titles actually observed in the left chat list. It compares
case-folded forms, close Latin spellings, and a conservative Persian-to-Latin
phonetic approximation. Suggested rows must pass the existing title-row
anchors, and the app asks for a numbered choice before clicking any corrected
title. It re-reads the rows and verifies the opened header against the OCR
title. A Latin request may trigger a focused `fas+eng` read if the English
read cannot find a row. This is deterministic visual grounding rather than
sending screenshots to the command-understanding model. Live Telegram tests
for these new examples are still pending; OCR quality, transliteration, and
the installed language data remain limiting factors.

The next live `openvisibly chat martin` still failed with
`visible_chat_uncertain:title_not_read_matches_0`, despite the earlier
`matin` screenshot having produced a high-confidence title and date in the
full-window OCR pass. Inspection found that the new OCR-grounding step ran
only after the focused retry unless the spoken title already matched exactly.
It now evaluates validated OCR-title suggestions on the initial full-window
read as well. A regression test replays the earlier stylized `matin` row,
date, and unreadable Persian preview and confirms that `martin` yields a
numbered `matin` suggestion without needing the focused pass. If future live
reads still fail, the action diagnostic now includes content-free counts of
candidate OCR titles and close matches or the row-anchor rejection reason.
Owner validation of this latest correction remains pending.
