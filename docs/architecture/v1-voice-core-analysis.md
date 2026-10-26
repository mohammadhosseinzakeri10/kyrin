# V1 Voice Core — Problem Analysis & Requirements

This document describes the V1 target, not a claim that every capability below
already exists. See `PROJECT_CONTEXT.md` for implemented state. The earlier
manual, one-attempt recognition flow was superseded by the decision to listen
continuously without a mandatory wake word or microphone button.

## 1. Purpose

The V1 Voice Core provides the initial reliable voice input layer of KYRIN.

Its responsibility is to capture audio continuously from the system microphone,
pass it to a replaceable offline Speech-to-Text (STT) provider as it arrives,
and return provider-independent partial and final text for downstream command
processing.

The Voice Core is limited to voice input only. It does not perform desktop automation, visual analysis, memory management, or autonomous task execution.

## 2. Goals

The V1 Voice Core aims to:

- Listen continuously while the application is running, without a mandatory
  wake word or microphone button for each command.
- Convert incoming speech into partial and final text while listening continues.
- Present recognized text to the user as appropriate.
- Handle microphone and speech-recognition failures safely.
- Allow application-controlled recovery after recoverable failures.
- Produce provider-independent transcription results.

## 3. Scope

Included in V1:

- Microphone initialization.
- Continuous audio capture and controlled shutdown.
- Bounded transfer from capture to processing with explicit overflow handling.
- Streaming Speech-to-Text processing using an offline provider.
- Recognition result handling.
- User-visible transcription output.
- Recoverable error handling.
- Restart after a recoverable capture or recognition failure.

The Speech-to-Text provider must be replaceable without changing higher-level Voice Core behavior.

## 4. Non-Goals

The following features are intentionally excluded from V1:

- Desktop application control.
- Mouse and keyboard automation.
- Window management.
- Vision or OCR.
- Webcam or gesture recognition.
- Long-term memory.
- Teach Mode.
- Multi-step task planning.
- Autonomous decision-making.
- Multimodal reasoning.
- Skill execution.
- Cross-platform desktop abstraction.

## 5. User Flow

### Successful Flow

User speaks at any time
  ↓
Continuous microphone capture and audio processing
  ↓
Streaming STT Provider
  ↓
Partial and final transcription results
  ↓
Voice Core and higher-level command understanding
  ↓
User

### Recoverable Failure Flow

Audio source or provider
  ↓
Voice Core
  ↓
Controlled Error
  ↓
Application reports the failure and safely resets the affected stream
  ↓
Listening can restart under application control

The Voice Core does not interpret commands or decide which action should be executed.

## 6. Inputs

The Voice Core accepts:

- Audio input from the system microphone.
- Application-level start, stop, and recovery control.

It does not directly accept application-level commands such as "Open Telegram". Command interpretation belongs to a higher-level command or agent layer.

## 7. Outputs

The Voice Core produces:

- Partial and final transcription results as speech is processed.
- A controlled error result.
- User-visible feedback for successful and failed streaming sessions.

Outputs remain independent of the underlying STT provider.

## 8. Failure Scenarios

### F-1 — Microphone Unavailable

- The application must not crash.
- A controlled microphone error must be returned.
- The application must be able to retry capture later.

### F-2 — No Usable Speech

- Silence is a normal listening state, not an error or a reason to clear
  conversation context.

### F-3 — Recognition Failure

- The provider error must be converted into a Voice Core error.
- Application stability must be preserved.
- The application must be able to restart the affected stream.

### F-4 — Provider Unavailable

- A controlled provider-unavailable result must be returned.
- Provider-specific details must not leak into higher-level logic.
- The application must be able to retry provider initialization.

### F-5 — Recognition Timeout

- The stalled provider operation must fail safely.
- A controlled timeout result must be returned.
- The application must remain able to listen or restart the affected provider.

### F-6 — Capture Queue Overflow

- Audio loss must be reported explicitly; incomplete audio must not silently
  become a valid command.
- The affected stream can be stopped and restarted safely.

## 9. Architectural Constraints

### C-1 — Provider Independence

The Voice Core must not depend directly on a specific STT provider.

### C-2 — Separation of Concerns

Audio capture, speech recognition, result handling, and higher-level command processing must remain separate responsibilities.

### C-3 — Provider-Independent Errors

Higher-level components must not need to understand provider-specific exceptions or implementation details.

### C-4 — No Action Execution

The Voice Core must not open applications, control input devices, manipulate files, or execute desktop actions.

### C-5 — Replaceable STT Implementation

The underlying STT implementation must be replaceable without requiring changes to higher-level Voice Core behavior.

### C-6 — Controlled Failure States

Expected runtime failures must be represented as controlled states rather than uncaught exceptions propagating through the application.

## 10. Acceptance Criteria

### AC-1 — Microphone Initialization

Given an available supported microphone, the Voice Core starts continuous
capture under application control.

### AC-2 — Audio Capture

Given a functioning microphone, the Voice Core forwards audio in order while
the user speaks or pauses.

### AC-3 — Speech Recognition

Given valid incoming speech, the Voice Core produces provider-independent
partial and final transcription results.

### AC-4 — User Feedback

A successful transcription is presented to the user.

### AC-5 — Failure Handling

Microphone, capture, recognition, provider, and timeout failures do not crash the application and produce controlled failure states.

### AC-6 — Continuous Listening

After a pause or completed command, listening continues without a new wake word
or button press. After a recoverable failure, application control can restart
the affected stream without restarting the application.

### AC-7 — Repeated Operation

The Voice Core remains stable across repeated commands and recoverable failures
during normal operation.

### AC-8 — Provider Independence

Replacing the underlying STT implementation does not require changes to higher-level Voice Core behavior.

## 11. Definition of Done

V1 Voice Core is complete when:

- AC-1 through AC-8 are satisfied.
- Continuous listening remains stable across commands and pauses.
- Recoverable failures do not crash the application.
- The STT implementation is replaceable behind a stable abstraction.
- Required automated and integration tests pass.
- Architecture documentation is complete.
- Linting and type-checking pass.

## 12. Success Definition

V1 succeeds when KYRIN can reliably listen and transcribe speech continuously
and offline while maintaining clear architectural separation between audio
capture, speech recognition, and downstream command processing.
