# AGENTS.md — Desktop Control Agent (Click Capability)

Read this file fully before writing any code. These rules apply to every task in this project.

## 1. Goal

Build a reusable, general-purpose "click on a UI element" capability in Python that works for ANY application and ANY screen, not only the one currently being tested.

## 2. Environment

- OS: Ubuntu 26.04 (GNOME).
- The display server (X11 or Wayland) is UNKNOWN. Ubuntu 26.04 is most likely Wayland.
- FIRST TASK, before any design: detect it.
  - Run `echo $XDG_SESSION_TYPE` and `echo $WAYLAND_DISPLAY`, and report the result to me.
  - Write a small `env_check.py` that reports: session type, desktop environment, whether AT-SPI is reachable, and which screenshot and input backends work.
- Do NOT assume X11 tools work. On Wayland, `xdotool`, `pyautogui`, and `scrot`-style tools are unreliable or blocked.
- Screenshot and input backends must be chosen by detection at runtime, behind a small interface, in this order of preference:
  - Wayland: XDG desktop portals (Screenshot / RemoteDesktop), `ydotool`, or libei-based input.
  - X11: `xdotool` or `python-xlib` for input; `mss` or `scrot` for screenshots.
- If no working backend is found, STOP and tell me. Do not invent a workaround.

## 3. Hard rules (never violate)

1. NEVER hardcode pixel coordinates, button positions, window sizes, or app-specific selectors in the click logic.
2. NEVER write code that only passes the current test or the current app.
3. Do not special-case any single application (no `if app == "..."`). If you feel the need to, STOP and tell me instead.
4. Do not change the architecture below without asking me first.
5. Never claim success without verification (see section 5).
6. If something fails, report the real error. Do not silently swallow exceptions or fake a result.

## 4. Required architecture (separate layers)

### Layer 1: Locator

`locate(description: str) -> LocateResult(x, y, confidence, strategy)`

Try strategies in this order, falling back to the next on failure or low confidence:

1. AT-SPI accessibility tree (`pyatspi`): match by name, role, and text.
2. OCR on a screenshot: text-based match.
3. Vision model on a screenshot: ask "where is <description>?" and parse the answer.

Rules for the Locator:
- It returns coordinates. It never clicks.
- Coordinates must always come from live data (the tree, the screenshot), never from constants.
- Handle multiple monitors and display scaling (HiDPI). Convert coordinates correctly between screenshot space and screen space.

### Layer 2: Actuator

`click(x, y) -> None`

- Performs the click only. It knows nothing about apps, buttons, or descriptions.
- Uses the backend selected by the environment check.

### Public API

`click_element(description: str) -> bool`

Flow: locate, check confidence, click, verify.
- Default confidence threshold: 0.6 (configurable, not hardcoded in the logic).
- Maximum attempts: 3 strategies, 1 click each. No infinite retry loops.

## 5. Verification

After each click:
1. Take a new screenshot.
2. Confirm that something changed (compare against the screenshot taken before the click).
3. If nothing changed, retry with the next locator strategy.
4. If all strategies fail, return `False` and log a clear failure reason.

## 6. Project structure

```
agent/
  env_check.py
  locator/
    atspi_locator.py
    ocr_locator.py
    vision_locator.py
    __init__.py        # locate() orchestrates the fallback chain
  actuator/
    base.py            # click(x, y) interface
    wayland.py
    x11.py
  api.py               # click_element()
tests/
  test_locator.py
```

Do not add files outside this structure without asking.

## 7. Logging

- Log every `locate` attempt: strategy used, description, result, confidence, time taken.
- Log every click and its verification result.
- On failure, save the before and after screenshots to a `debug/` folder.

## 8. Testing

- Test on at least 3 different applications (for example: a terminal, a browser, a file manager or settings window).
- Test on at least 2 different screen resolutions or scaling factors.
- A test that passes only on one app or one resolution does not count.
- Tests must not contain hardcoded coordinates either.

## 9. Workflow

Work in small steps and wait for my approval between steps.

- Step 0: environment check (`env_check.py`). Report results. Wait.
- Step 1: Locator layer only, with tests. Show the code. Wait.
- Step 2: Actuator layer. Wait.
- Step 3: `click_element()` with verification. Wait.

### Approval gates (mandatory for every step and every component)

Never jump from a step straight into code. Each step goes through these gates, and you must STOP and wait for my explicit approval at gates A and B:

**Gate A: Explain before acting.**
Before touching any part of the project, tell me:
- What this part does and why it is needed.
- What you are about to do, in plain words.
- Which files you will create or change.
- Your assumptions, and any question you have. Do not guess; ask.
Then STOP and wait for my approval.

**Gate B: Present the options.**
For each part that needs an implementation decision, list ALL realistic implementation approaches (not only your favorite). For each approach give:
- How it works, in two or three sentences.
- Pros and cons (reliability, speed, complexity, dependencies, Wayland/X11 support).
- Your recommendation and the reason.
Keep it to the approaches that really apply (usually 2 to 4). Do not pad the list with unrealistic ones.
Then STOP and wait until I choose one. Do not implement anything before I choose.

**Gate C: Implement only what was approved.**
Implement exactly the chosen approach. If you discover a problem that needs a different approach, STOP and go back to Gate B.

**Gate D: Report after implementing.**
After each step, give me a short report:
- What was done and which files changed.
- How I can run and test it myself, with the exact commands.
- What is still not done or not verified.
- Known risks or limitations.
Then wait for my go-ahead before the next step.

**Definition of done.**
At Gate A, state the acceptance criteria for the step ("this step is done when ..."). Do not call a step finished until those criteria are met and shown.

## 10. Explanation style

I am learning while building. For each step:
- First explain the concept in simple words, with a small flow diagram (ASCII) showing the data flow.
- Then explain the code line by line, including simple variable lines.
- Then give me a short exercise.
- Only after that move on to the real implementation.

## 11. Safety (this agent controls a real desktop)

- Provide a `dry_run` mode: it runs locate() and shows what it WOULD click, without clicking. Use it by default during development.
- Provide an emergency stop: a global hotkey or a flag file that immediately halts the agent.
- Never click on destructive or irreversible actions (delete, send, pay, submit, uninstall, shutdown) without asking me for confirmation first.
- Never type or click into password fields, and never log or save screenshots that may contain secrets without telling me.

## 12. Scope and dependencies

- Touch only the files that belong to the current step. No refactors or "improvements" outside the approved scope.
- Before installing any package, running `sudo`, or changing system settings, tell me exactly what and why, and wait for approval.
- Pin new dependencies in `requirements.txt` and tell me about each one.
- Make a git commit after each approved step, with a clear message, so I can roll back.
