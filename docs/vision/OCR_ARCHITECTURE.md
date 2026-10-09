# On-demand image text recognition

KYRIN now has a separate capture interface (`ScreenCapture`), OCR engine
interface (`OcrEngine`), and `WindowTextReader` composition. None can click,
type, navigate, or approve an action. An OCR result contains recognized word
text, image coordinates, confidence when available, language, engine, and
actual compute device. Text visible in an image is untrusted observation, not
an executable instruction or a stable UI selector.

## Ubuntu acquisition

`UbuntuPortalScreenCapture` invokes a short-lived system-Python helper because
the Ubuntu GObject and GStreamer bindings are supplied by the operating system,
not the project virtual environment. It asks the
[ScreenCast Portal](https://flatpak.github.io/xdg-desktop-portal/docs/doc-org.freedesktop.portal.ScreenCast.html)
for one **window** source. The system picker controls the user's choice. This
implementation requests no persistent permission or automatic restore token.
It also rejects a returned stream unless the portal identifies its source as
a window, so a monitor stream cannot be mistaken for a window capture.
The helper receives a PipeWire stream, encodes one frame as PNG in memory, and
closes the session. No image is written to disk. A user cancellation, portal
failure, or oversized/invalid output becomes an unavailable capture.

This one-shot path is a first image acquisition adapter. The selected portal
window is not yet bound to KYRIN's active-app identity, and the returned pixels
must not be used to authorize an automated click. Browser/chat navigation needs
a separate target verification and action design. Other operating systems need
their own permission-aware `ScreenCapture` adapters.

The optional GNOME active-window capture adapter is described in
`docs/vision/GNOME_ACTIVE_WINDOW_CAPTURE_PROTOTYPE.md`. It is installed for the
current user and has passed one live Qt capture/revocation check. It is not
connected to automatic actions.

## Recognition and models

`OcrEngine` accepts image bytes and `OcrOptions`, then reports `OcrResult`.
The first adapter runs the offline Tesseract CLI with a user-supplied absolute
`tessdata` directory. It discovers installed `.traineddata` language codes,
reports CPU capability only, and rejects a requested GPU rather than silently
switching devices. It does not download models or modify system packages.
Adding a PaddleOCR or another engine requires an adapter for this contract;
the capture path and action code do not need to import that engine.

Tesseract is not installed as a system package on the development machine. A
local, ignored test runtime and English model are described in
`models/README.md`; a synthetic `Open Telegram` image returned both words with
word boxes. In a separate live ScreenCast test, the owner selected the
temporary `KYRIN OCR Test` window and confirmed that choice. Tesseract found
both expected words from the captured image. OCR took 0.146 seconds after
capture in that one run. This is a health check, not an accuracy or latency
benchmark across applications or screen conditions.

A model-management UI, an OCR-engine selector in saved settings, multilingual
model downloads, and a
measured CPU/GPU benchmark remain separate product work. Model file size does
not establish RAM or VRAM requirements; those must be measured with the chosen
runtime and image size.

## Read-only Qt observation

The optional `Screen Access` page can request one image after its session
permission has been granted. `ScreenAccess` calls the GNOME extension on the
Qt thread; `ScreenTextReader` passes only that image to an OCR worker thread.
The result is an `IdentifiedWindowText` snapshot carrying recognized text, the
desktop ID, and the PID of the captured window. A fresh identity read after
OCR must still match both values or the snapshot is discarded. Revoking screen
access discards any late result. Only one read is in flight, and image bytes
are never written to disk. The page displays up to 2,000 characters as plain
text and clears them when access is revoked.

The Ubuntu Qt composition currently discovers an optional English Tesseract
runtime at the user's XDG data location,
`kyrin/models/ocr/tesseract/`, alongside the STT model library. The discovery
step does not install or download it. `ScreenTextReader` accepts the `OcrEngine`
contract, so another OCR adapter can replace Tesseract without changing the
capture or page logic. An absent runtime leaves the read button unavailable.
This read-only path does not send OCR text to the command interpreter, click
anything, or treat image text as an instruction. Action targeting needs a
separate design and a fresh identity/target check at execution time.

In a live Qt test on 2026-10-09, the session grant succeeded and
`ScreenTextReader` returned the registered KYRIN test window's desktop ID and
PID plus the expected `Open` and `Telegram` words. Access was revoked when the
test ended. The portal logged an app-ID registration warning, without blocking
this run. This verifies one end-to-end read-only observation on the development
desktop; it does not measure recognition quality on other apps or authorize a
screen-dependent action.

Two further read-only runs used the actual Telegram Desktop window. A view
containing both Persian and English produced OCR text but no match among the
small English labels checked; the installed OCR data is English only. A
controlled Settings view returned `Settings`, `Notifications`, `Privacy`,
`Security`, `Language`, `Folders`, and `Advanced`, with 102 of 394 spans at
confidence 0.8 or higher. The probe exposed only counts and fixed generic
labels, and the grant was revoked after each run. This supports English UI
text acquisition in Telegram but does not validate contact-name matching or
selection. Screen-dependent actions still require a separate design.
A third read-only run found the exact adjacent words `Saved Messages` in the
owner's Telegram chat list. It did not open the chat or print other titles.
This one controlled match does not validate arbitrary or non-English names.

Once a local Tesseract executable and language data are available, an explicit
read-only diagnostic is available:

```bash
PYTHONPATH=src .venv/bin/python scripts/vision/check_window_ocr.py \
  --executable /absolute/path/to/tesseract \
  --tessdata-dir /absolute/path/to/tessdata --language eng
```

The default output reports only engine, device, and word count. Add
`--show-text` only when it is acceptable for visible on-screen text to appear
in terminal output. The diagnostic requests a window through the system
picker every time and never launches an application.
