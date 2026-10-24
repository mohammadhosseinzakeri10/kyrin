# On-demand image text recognition

KYRIN now has a separate capture interface (`ScreenCapture`), OCR engine
interface (`OcrEngine`), and `WindowTextReader` composition. None can click,
type, navigate, or approve an action. An OCR result contains recognized word
text, image coordinates, confidence when available, language, engine, and
actual compute device. Text visible in an image is untrusted observation, not
an executable instruction or a stable UI selector.

<div dir="rtl" lang="fa">

فهرست برچسب‌های قابل مشاهده و مکان‌یاب از نرمال‌سازی و سازندهٔ عبارت مشترک
در `text_targets.py` استفاده می‌کنند. ترتیب خواندن خروجی OCR حفظ می‌شود؛
عبارت فارسی، انگلیسی و ترکیبی، چه در یک span و چه در چند span، با همان
قواعد هم‌سطری، فاصله و هم‌پوشانی محدود بررسی می‌شود. متن چندخطی یک برچسب
تک‌خطی نمی‌سازد. حداقل confidence همهٔ spanهای عبارت حفظ می‌شود؛ وجود حتی
یک مقدار ناموجود، confidence کل عبارت را نامعلوم می‌کند. پالایش پس از
ساخت عبارت انجام می‌شود تا کلمهٔ کم‌اطمینان حذف و همسایه‌هایش به هم وصل
نشوند. تکرارهای OCR با همین نرمال‌سازی از فهرست انتخاب یکتا حذف می‌شوند.
انتخاب زبان هدف و آستانهٔ فعلی ۰٫۶۵ تغییر نکرده‌اند؛ این آستانه ادعای
کالیبراسیون مشترک میان موتورهای OCR نیست. آزمون زندهٔ این تغییر انجام نشده است.

</div>

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

This one-shot portal path is a first image acquisition adapter. Its
user-selected window is not bound to KYRIN's active-app identity, and its
pixels must not authorize an automated click. The separate GNOME active-window
adapter described below does bind an image to desktop ID and PID. General
browser/chat navigation still needs verified targets and dedicated actions.
Other operating systems need their own permission-aware `ScreenCapture`
adapters.

The optional GNOME active-window capture adapter is described in
`docs/vision/GNOME_ACTIVE_WINDOW_CAPTURE_PROTOTYPE.md`. It is installed for the
current user and has passed live Qt capture/revocation checks. Its fresh
identity checks also support the narrowly scoped Telegram `Saved Messages`
verification path; they do not enable general screen-driven actions.

## Recognition and models

`OcrEngine` accepts image bytes and `OcrOptions`, then reports `OcrResult`.
The first adapter runs the offline Tesseract CLI with a user-supplied absolute
`tessdata` directory. It discovers installed `.traineddata` language codes,
reports CPU capability only, and rejects a requested GPU rather than silently
switching devices. It does not download models or modify system packages.
The PaddleOCR adapter implements the same contract using a separate, local
Python runtime. The capture path and action code do not import PaddleOCR.

Tesseract is not installed as a system package on the development machine. A
local, ignored test runtime and English model are described in
`models/README.md`; a synthetic `Open Telegram` image returned both words with
word boxes. In a separate live ScreenCast test, the owner selected the
temporary `KYRIN OCR Test` window and confirmed that choice. Tesseract found
both expected words from the captured image. OCR took 0.146 seconds after
capture in that one run. This is a health check, not an accuracy or latency
benchmark across applications or screen conditions.

A local OCR package selector is now saved in application settings. The Screen
Access page offers the installed Tesseract adapter, downloaded Fast and Best
English/Persian language packs, and the ready PaddleOCR v5 Persian, v6 Small,
and v6 Medium model pairs from the source-checkout catalog. PaddleOCR-VL 1.6
is also available for screen reading when its separate runtime is installed.
It returns text spotting polygons converted to real boxes, but no confidence
score. Telegram and other action checks that require confidence therefore stop
without clicking when this model is selected. A folder picker
supports a compatible, already extracted Tesseract runtime or language
directory. The selected Tesseract packs reuse the installed executable;
PaddleOCR uses isolated Python runtimes under the ignored local app data.
On the owner's machine, `runtimes/ocr/paddle/` and
`runtimes/ocr/paddle-vl/` each contain PaddlePaddle 3.2.2, PaddleOCR 3.7.0,
and PaddleX 3.7.2; the VL runtime also has PaddleX's `ocr` extras. These
optional packages are not imported by KYRIN's main Python environment.
The saved choice is applied to new reads without changing the screen capture or
Telegram verification code; a read already in flight is discarded when the
engine changes. The Paddle worker loads local detection and recognition files
in a CPU subprocess and returns real line boxes; it does not silently download
missing model components. Other downloaded vision-language model families need
runtime integration and verified text coordinates before they can safely drive
screen actions. The app does not download OCR models.
In local offline smoke checks, all three Paddle detector/recognizer pairs
returned `Open Telegram` and nonempty boxes. The v5 Persian pair also read a
synthetic `سلام مادر` image with a confidence score. PaddleOCR-VL 1.6 returned
`Open Telegram` and a box with unknown confidence. These checks do not establish
accuracy or responsiveness on full desktop windows.

Surya OCR 2, GLM-OCR, and dots.mocr have a **separate read-only document
comparison** path. Since 2026-10-24, discovery requires an independently reviewed
provenance/hash manifest, and execution requires a working Linux bubblewrap
profile. No document checkpoint is approved yet, so installed files alone do
not enable this path. Auto currently uses protected CPU; explicit GPU is
unavailable. See [the protection contract](DOCUMENT_MODEL_PROTECTION.md).
The GPU and model observations below describe earlier experiments, not current
approval or successful containment. This section captures the active
window only after the existing screen grant, runs offline inference in a
bounded subprocess, and displays text without coordinates. It never feeds
Telegram verification or clicking. Surya and GLM share the local
`document-vlm5` runtime; dots.mocr uses `document-dots` because its compatible
Transformers version differs. The dots vision configuration must explicitly
select eager attention; a process-local import shim makes the checkpoint's
unconditional flash-attention import safe and raises if that code path is used.
The CPU subprocess has an address-space limit; GPU runs omit that virtual
address-space limit because CUDA reserves large address ranges. Both paths have
a four-minute timeout. Results
are discarded if screen access is revoked or the active window changes. No
captured image is saved. All three read `Open Telegram` in separate offline
synthetic-image smoke tests. This is not an accuracy or full-screen latency
benchmark, and the document models have no verified click coordinates.
On the owner's 2026-10-19 KYRIN screenshot, dots.mocr in the CPU
PyTorch runtime returned 682 characters after 80.1 seconds. The UI now shows
elapsed time during a document read and reports a distinct four-minute timeout.
This documents CPU latency rather than treating a long run as a frozen UI.
The model and Auto/CPU/GPU device selection are saved separately from action
OCR. Before the protection profile above, Auto used CUDA when the isolated
runtime reported it available, otherwise CPU. An explicit GPU request fails clearly if CUDA is unavailable and never
silently falls back. The text result reports the device actually used. GPU
support requires a CUDA-enabled PyTorch installation in each model's isolated
runtime; selecting GPU alone does not install one.
The owner's RTX 5060 Ti completed synthetic GPU reads with dots.mocr (4.5
seconds), Surya (16.1 seconds), and GLM-OCR (4.2 seconds); all reported
`device=gpu`. Auto selected GPU on this machine. Explicit CPU hides CUDA from
its subprocess to avoid CUDA library mappings exhausting the CPU worker's
virtual address-space limit; a GLM CPU read then completed in 9.9 seconds.
On a real Screen Access screenshot, dots.mocr's eager vision attention ran out
of CUDA memory because it materialized a large attention matrix. GPU inference
now uses the checkpoint's SDPA attention path. Larger desktop images are read
as overlapping horizontal bands at native pixel scale to bound peak vision
memory without shrinking text. The owner's 1222×820 screenshot and a synthetic
1853×1048 desktop frame both returned text after these changes. If other GPU
work still exhausts memory, Screen Access reports that condition separately
from generic OCR failure and suggests CPU or freeing GPU memory.
The document model selector is independent of the saved Local OCR model above
it. Clicking its read button captures the window that is active at that moment;
when the control center is in front, that is KYRIN itself. Each read-only text
panel has its own Clear button, which removes displayed text and resets the
panel's status without changing the selected model or screen permission. A
blank document-model result now names the backend and captured application so
it can be distinguished from a capture or permission failure. On 2026-10-19,
the owner reported a blank Surya result while the standard screen OCR read
text. The supplied full-window screenshot reproduced this: Surya returned no
text for the full frame but read the central panel after a left-navigation
crop. Surya now retries once on the right 85% of sufficiently wide, tall
windows only when its first result is empty. This is a bounded text-only
recovery path; it does not change action targeting or other document models.
Multilingual model acquisition and a measured CPU/GPU benchmark remain
separate product work. Model file size does
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

Action-driven reads now carry a shared absolute operation deadline through Qt,
OCR and fallback. Timeout cancels the request and prevents a late callback from
starting another pass. Built-in OCR processes are stopped and reaped; a native
in-process plugin retains busy ownership until it actually finishes, including
after an engine switch. See [Desktop operation lifetime](../actions/DESKTOP_OPERATION_LIFECYCLE.md)
for cancellation, cleanup allowances, and live-validation limits.

The Ubuntu Qt composition discovers the default optional Tesseract
runtime at the user's XDG data location,
`kyrin/models/ocr/tesseract/`, alongside the STT model library. The discovery
step does not install or download it. `ScreenTextReader` accepts the `OcrEngine`
contract, so another OCR adapter can replace Tesseract without changing the
capture or page logic. An absent runtime leaves the read button unavailable.
The general Screen Access read remains English. When a Telegram chat target
contains Persian script and `fas.traineddata` is installed beside
`eng.traineddata`, the chat verifier requests `fas+eng` only for that capture.
It uses Tesseract page segmentation mode 3 for Persian and preserves mode 11
for English-only reads. A missing Persian model stops the chat match without
clicking. Both the language data and the optional runtime stay in the local
project data on the owner's AI-Projects drive. This does not translate a
misheard chat name or guarantee OCR accuracy on the owner's Telegram theme.
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
The later, narrowly scoped `Saved Messages` action uses a fresh identified
capture to verify its header; general screen-dependent actions remain open.

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

<div dir="rtl" lang="fa">

**F19، ۲۰۲۶/۱۰/۲۴:** اقامت و پذیرش مدل در ترکیب Ubuntu اکنون از
[سیاست مشترک منابع](../app/MODEL_RESOURCE_POLICY.md) پیروی می‌کند؛
تنظیم صریح دستگاه و قراردادهای مجوز حفظ شده‌اند. آزمون زنده و baseline
سرعت/حافظهٔ این سیاست هنوز انجام نشده‌اند.

</div>

<div dir="rtl" lang="fa">

**بخش محدود F22، ۲۰۲۶/۱۰/۲۴:** ساخت snapshot از تصویر و نتیجهٔ OCR در
`IdentifiedWindowText.from_capture` مشترک است؛ مسیر مستقل و Qt اندازهٔ PNG،
مستطیل‌ها و هندسه را از همان capture منتقل می‌کنند. Qt ابتدا مختصات OCR را
به تصویر اصلی برمی‌گرداند؛ سازنده فقط منشأ برش/بزرگ‌نمایی را ثبت می‌کند و
مختصات را تغییر نمی‌دهد. ابعاد ناموجود یا خارج از محدوده همچنان نامعلوم
می‌مانند و مجوز ساخت هدف ایجاد نمی‌کنند. سازندهٔ مستقیم و فیلدهای اختیاری
برای فراخواننده‌های موجود حفظ شده‌اند. این استخراج فقط مسئولیت ساخت observation
را پوشش می‌دهد؛ شکستن سایر توابع بزرگ، استخراج validator/handler/lifecycle،
نام‌گذاری عمومی و قالب‌بندی فایل‌های دیگرِ F22 باقی مانده‌اند؛ از جمله
`DemoCommandInterpreter.interpret`، `UbuntuSessionFactory.__call__`،
`CommandCoordinator.observe` و `ModelAssistedInterpreter.interpret`.

دو حالت رگرسیون پیش از اصلاح با نبود اندازه شکست خوردند؛ پس از اصلاح
۲۲۴ آزمون مرتبط موفق شدند. بررسی نوعِ سه فایل Python تغییرکرده، lint و
قالب‌بندی دامنه موفق‌اند. بررسی‌گر کامل با `PYTHONPATH=src` و محیط موقت،
خارج از sandbox محدود، هر ۲۱۷۶ آزمون را موفق اجرا کرد؛ نحو و lint نیز موفق‌اند،
اما ۴۲۵ خطای نوع در ۵۷ فایل مانع موفقیت کلی است. گزارش‌ها در
`local-data/quality-f22-unrestricted/` نگه داشته شده‌اند. اجرای داخل sandbox
۱۸۵ شکست و سه آزمون ردشده داشت؛ زنجیرهٔ هندسه با برداشتن محدودیت محیط
موفق شد. قرارداد آزمون برای عبور از این شکست‌ها تغییر نکرد.
آزمون زندهٔ GNOME و OCR واقعی برای این تغییر انجام نشده است.

</div>
