# KYRIN — Agent Instructions

## 1. Language and Communication

- Communicate with the user primarily in Persian (Farsi).
- Explanations, architectural discussions, code reviews, debugging guidance,
  and teaching should be provided in Persian unless the user explicitly
  requests English.
- Keep technical identifiers in English.
- Do not translate class names, function names, variable names, file names,
  paths, APIs, library names, or code.
- When introducing a technical concept, use the English technical term
  alongside the Persian explanation when useful.

## 2. Project Context

- Read PROJECT_CONTEXT.md before making architectural or implementation
  decisions related to the current project state.
- Treat PROJECT_CONTEXT.md as conversation-derived engineering context,
  not as a substitute for inspecting the actual repository.
- If the repository and PROJECT_CONTEXT.md disagree, inspect the actual
  code and investigate the discrepancy rather than silently choosing one.
- Preserve the distinction between confirmed decisions, current direction,
  temporary experiments, proposals, and open questions.

## 3. Development Approach

- The user is learning software architecture and wants to understand the
  implementation rather than blindly copy generated code.
- Explain important design decisions before making substantial changes.
- Prefer small, understandable implementation steps over large generated
  changes.
- When introducing unfamiliar code, explain what it does and why it exists.
- Do not unnecessarily rewrite working code.
- Preserve existing architecture unless there is a clear reason to change it.

## 4. Repository Inspection

Before making significant changes:

1. Inspect the relevant files.
2. Understand the existing architecture.
3. Check related interfaces, implementations, tests, and configuration.
4. Identify dependencies and existing conventions.
5. Then propose or implement the smallest appropriate change.

Do not assume that a file, class, function, dependency, or architectural
decision exists merely because it is mentioned in documentation.

## 5. Architecture

- Preserve clear separation between interfaces/contracts and concrete
  implementations.
- Prefer dependency injection where it improves testability and separation
  of concerns.
- Keep components focused on a single responsibility.
- Avoid introducing unnecessary abstraction.
- Do not move responsibilities between components without explaining the
  architectural reason.

## 6. Audio Architecture

For the current V1 audio-input work:

- Keep AudioInput and MicrophoneInput conceptually separate.
- MicrophoneInput is responsible for microphone/audio acquisition.
- Do not place STT, intent understanding, agent decision-making, or unrelated
  application logic inside MicrophoneInput.
- Keep audio configuration explicit and configurable.
- Do not acquire microphone hardware inside __init__ unless the architecture
  is deliberately changed and the reason is explained.
- Preserve the boundary between raw audio acquisition and downstream
  processing.

## 7. Code Quality

- Use clear Python type annotations.
- Prefer readable code over unnecessarily clever code.
- Use descriptive names.
- Handle specific exceptions rather than using broad except clauses.
- Avoid hard-coding machine-specific device identifiers or environment
  assumptions when configuration can be used instead.
- Follow the existing project formatting and dependency conventions.

## 8. Testing

- When changing behavior, inspect and update relevant tests.
- Prefer small, focused tests.
- For hardware-dependent functionality, distinguish hardware validation from
  deterministic unit tests.
- Do not claim that functionality is tested if it has not actually been
  tested.

## 9. Dependencies and External Services

- Do not add a new dependency without first explaining why it is needed.
- Prefer existing project dependencies when they are sufficient.
- Do not introduce external APIs, cloud services, or model providers unless
  the user has decided that they are part of the design or explicitly asks
  to evaluate them.

## 10. Changes and Git

- Keep changes focused on the requested task.
- Do not modify unrelated files.
- Do not delete or overwrite important project files without explaining the
  reason first.
- Before making a large change, summarize what will change.
- Preserve a clean and understandable Git history.

## 11. Documentation

- Update relevant documentation when an architectural or behavioral change
  makes existing documentation inaccurate.
- Keep PROJECT_CONTEXT.md focused on project context and engineering history.
- Keep AGENTS.md focused on instructions and working rules.

## 12. Uncertainty

- Do not invent missing requirements.
- Clearly distinguish:
  - confirmed facts
  - current direction
  - temporary experiments
  - proposals
  - open questions
  - assumptions
- If an important decision is not defined, say so and ask or investigate
  rather than silently deciding.

## 13. User Learning Mode

The user wants to learn while building KYRIN.

When appropriate:

1. Explain the concept.
2. Connect it to KYRIN.
3. Show the relevant code.
4. Explain the code step by step.
5. Let the user implement small parts when practical.
6. Review the implementation.
7. Test and debug together.

Do not optimize solely for speed at the expense of the user's understanding.