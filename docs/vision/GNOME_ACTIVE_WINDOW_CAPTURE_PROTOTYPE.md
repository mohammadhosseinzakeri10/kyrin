# GNOME active-window capture: session-access prototype

<div dir="rtl" lang="fa">

**به‌روزرسانی F20:** Qt پیش از مجوز و تصویر، نسخه و قابلیت افزونهٔ بارشده را
با probe بدون تصویر می‌سنجد. مالکیت اتصال با آمادگی backend جداست؛ retry
سرویس دیررس محدود است. پاسخ تصویر legacy به‌صورت پیش‌فرض رد می‌شود و فقط
گزینهٔ صریح سازگاری آن را می‌پذیرد. [قرارداد و خطاها](../desktop/BACKEND_PROTOCOL.md).

</div>

<div dir="rtl" lang="fa">

**قرارداد هندسه — ۲۰۲۶/۱۰/۲۴، F13:** در GNOME 50، مستطیل خروجیِ
`screenshot_window_finish` قاب پنجره است، ولی PNG از `WindowActor.get_image(NULL)`
می‌آید. اختلاف ابعاد، تقارن سایه یا برابر بودن مقیاس تصویر و مانیتور را
اثبات نمی‌کند. اکنون تولیدکننده محدودهٔ منطقی `get_buffer_rect` را با موقعیت
و اندازهٔ actor تطبیق می‌دهد؛ نبود actor، عدم تطابق، خروج قاب از بافر یا
اعوجاج نسبت ابعاد بیش از گردکردن یک پیکسل موجب رد تصویر می‌شود.

`capture_rect` محدودهٔ کامل بافر در فضای منطقی دسکتاپ و `frame_rect`
محدودهٔ مجاز تعامل است. نسبت ابعاد PNG به بافر، `scale_x/scale_y` را
تعیین می‌کند؛ سایهٔ نامتقارن داخل همین مستطیل است و `padding` صفر می‌ماند.
بافر و مانیتور در طول ثبت و اعتبارسنجی دوباره بررسی می‌شوند. فراداده،
فضاهای `logical_desktop` و `source_png_pixels` و منشأ نسخه‌دار
`gnome-buffer-actor-v1` را اعلام می‌کند؛ Qt فرادادهٔ قدیمی یا ناشناخته
را رد می‌کند. افزونهٔ جدید باید نصب و در نشست بارگذاری شود.

Qt برش و بزرگ‌نمایی OCR را یک‌بار به پیکسل PNG اصلی برمی‌گرداند؛
مکان‌یاب عمومی و تلگرام همان جعبه‌ها را حمل می‌کنند و هر دو actuator با
`image_pixels=True` به مختصات منطقی دسکتاپ می‌روند. بررسی دوبارهٔ نقطه پیش
از فشردن، خروجی تبدیل نخست را دوباره تبدیل نمی‌کند. مسیر قدیمی فقط نگاشت
دقیق یک‌به‌یک را می‌پذیرد؛ اختلاف کوچک ابعاد یا سایهٔ متقارن حدس زده نمی‌شود.

آزمون قطعی `test_gnome_geometry_pipeline.py` تولید فراداده در GJS، تجزیهٔ
Qt، PNG، برش، بزرگ‌نمایی، مکان‌یاب و رویدادهای هر دو actuator را متصل می‌کند:
سایهٔ نامتقارن، چهار گوشه و مرکز، مقیاس‌های ۱، ۱٫۲۵، ۱٫۵ و ۲، مبدأ مثبت و
منفی، تفاوت مقیاس تصویر و مانیتور و جابه‌جایی پنجره پیش/پس از حرکت اشاره‌گر.
ثبت Shell، تشخیص متن و انتقال portal شبیه‌سازی شده‌اند؛ پردازش تصویر و
منطق مسیر واقعی‌اند. تطبیق actor شرط پذیرش است و پوشش همهٔ انواع آن اثبات
نشده است. آزمون زندهٔ mixed-DPI، Wayland و XWayland انجام نشده؛ گام بعد،
بارگذاری افزونه و سنجش نشانگرهای گوشه/مرکز در همین ماتریس است.

منابع رسمی نسخهٔ پشتیبانی‌شده:
[GNOME Shell 50](https://github.com/GNOME/gnome-shell/blob/50.0/src/shell-screenshot.c)،
[تصویر actor در Mutter 50](https://github.com/GNOME/mutter/blob/50.0/src/compositor/meta-window-actor.c)،
[محدودهٔ بافر](https://github.com/GNOME/mutter/blob/50.0/src/core/window.c).

</div>

## Why this exists

The ScreenCast Portal safely lets a user choose a window, but its stream ID
does not identify the installed application. GNOME's focused-window API can
return the image and application ID from the same window object. This is an
optional Ubuntu/GNOME adapter; core OCR and vision contracts do not depend on
GNOME or Qt.

## Confirmed read-only foundation

On 2026-10-09, the owner approved two live, in-memory captures. The first test
window yielded `window:8`, a temporary ID for an unregistered window. The
extension now rejects window-backed IDs. The second test window used KYRIN's
registered desktop identity and returned `local.kyrin.KYRIN.desktop`, its
process ID, and OCR words including `Open` and `Telegram`. These two results
verify the earlier one-image prototype on this GNOME 50.1 desktop. They do not
verify other apps, persistent access, or any action based on OCR text.

## Remembered access design

The Qt control application owns `org.kyrin.Desktop` on the user's session
D-Bus. `ScreenAccess` sends all image and permission requests on that same
connection. The GNOME extension checks that a permission request sender is the
current unique owner of the name and asks the user once in a GNOME Shell
dialog. A second owner check follows the decision. A successful grant is bound
to that unique connection name in memory. Another process cannot use the
active grant by sending its own request. For a remembered grant, the Qt app
stores a random 256-bit token in a 0600 local data file, and the extension
stores its hash. On later starts, the app requests access with that token;
the extension compares its hash and rebinds the grant to the new verified
D-Bus owner. The `Screen Access` switch deletes both local records and asks
the extension to revoke the active grant. Merely quitting KYRIN releases the
active connection but keeps the remembered choice. No image is saved.

The extension releases the active grant when the app's bus name changes owner
or it is disabled. Explicit `RevokeSession` also forgets the remembered grant.
Capture requests
still reject an unregistered active window, missing PID, focus change during
capture, failed screenshot, image over 16 MiB, concurrent capture, and the
eight-second capture timeout. Image bytes remain in memory. No capture runs
periodically. The Qt adapter is asynchronous so it does not block the UI.

`ValidateCaptureRegions(capture_id, regions)` compares decoded RGBA pixels
only in the target's evidence rectangles. Each rectangle is `(left, top, width,
height)`, half-open, in **original PNG pixels**, including shadow padding.
Qt restores cropped/resized OCR boxes to that coordinate space before target
resolution; helpers must not apply those transforms a second time. Generic
visible controls supply the complete label box. Telegram supplies the title
and the actual supporting time/preview, query, section or menu-heading boxes
used to locate it. Supporting boxes remain separate so unrelated content
between them can animate. Extra margin is zero because the evidence consists
of complete OCR boxes; this does not infer a widget's border from its text.

Every rectangle must have integer coordinates, positive dimensions and fit
entirely inside both same-sized images. Empty, partial and out-of-image sets
fail; helpers also require the exact target box in the evidence set. There is
no clipping, pixel tolerance or guessed similarity threshold. Changes to any
protected pixel (including alpha), or movement of the target out of its old
box, fail; changes outside the evidence set do not. PNG metadata, compression
and decoded row padding remain irrelevant. Pixel equality cannot distinguish
a replacement with identical visible evidence or verify an action's effect.

The extension binds regions to its retained capture ID/window token. Its
existing ten-second monotonic lifetime is checked before and after the fresh
capture. Focus changes during validation, changed frame/screenshot area,
changed image dimensions, capture replacement, revocation, timeout and invalid
PNGs fail. Window token, current focus, frame, pointer and freshness checks in
the helpers remain. `ValidateCapture` retains strict whole-window comparison
for callers without an evidence contract; it does not silently downgrade a
failed region validation. An older loaded extension lacking the new method
causes validation to fail closed until the updated extension is loaded.

Deterministic GJS tests use real PNG decoding with simulated screenshots and
an isolated D-Bus round trip for the region signature. Python tests cover
supporting evidence and helper transport. Live Shell validation is pending.
API references:
[PNG loader](https://gnome.pages.gitlab.gnome.org/gdk-pixbuf/gdk-pixbuf/ctor.PixbufLoader.new_with_type.html),
[pixel layout](https://gnome.pages.gitlab.gnome.org/gtk/gdk-pixbuf/class.Pixbuf.html),
[busctl array/structure arguments](https://www.freedesktop.org/software/systemd/man/latest/busctl.html#Parameter%20Formatting),
[GJS exported services](https://gjs.guide/guides/gio/dbus.html#exporting-an-object).

The old separate-process helper and its terminal diagnostic were removed:
their D-Bus sender could never match the control app's unique connection.
`ActiveWindowTextReader` remains a platform-neutral composition for future
adapters. The session adapter is not connected to OCR-triggered actions.

## Trust and current limits

Owning a well-known D-Bus name proves which **connection** sent a request; it
does not prove that the process is a trustworthy KYRIN binary. Another process
in the same user session could claim the name before KYRIN starts and ask the
user to approve its prompt. The Qt app refuses screen access if the name is
already owned. The remembered token prevents a process that merely claims
the bus name from silently using the owner's prior choice, but another process
running as the same user could read or replace the token or extension files.
This prototype is not a security boundary against a malicious process running
as the same user. A stronger
isolation requirement would need a sandbox and a trusted portal design.

The session path has passed focused Python tests and a GJS permission harness,
including foreign-caller denial, revocation, lost bus ownership, and a late
reply after revocation. A live Qt request initially returned `false` before any GNOME
prompt appeared. D-Bus monitoring showed that the request sender matched the
owner of `org.kyrin.Desktop`. A focused GJS check then showed that
`GLib.Variant.unpack()` left the owner's string wrapped in a child variant;
the extension now uses `deepUnpack()` for owner replies and owner-change
signals. An unauthorized direct D-Bus capture request returned no image.
After the owner restarted the desktop session, the corrected extension
accepted the Qt app's request and displayed the GNOME session-consent dialog.
In a separate approved one-image test, `ScreenAccess` received a 20,072-byte
PNG in memory with the registered ID `local.kyrin.KYRIN.desktop` and the test
window's PID. After `RevokeSession`, another capture request returned no image.
The Qt adapter, live GNOME grant, one-image path, and explicit revocation are
therefore validated on this desktop. Later read-only Qt OCR runs captured the
actual Telegram Desktop window; its Settings view yielded several expected
English labels. This does not validate contact matching, OCR-based decisions,
other applications, or stronger protection against a malicious process in the
same user account.
No image should be used to authorize a click or keystroke until the active
target is checked again at action time.

On 2026-10-14, after the owner restarted GNOME, the loaded extension exposed
`RequestPersistentSession` and the owner reported that remembered Screen Access
worked across the restart. The local token and grant hash were both mode 0600.
The owner subsequently turned Screen Access off inside KYRIN and confirmed
that the switch worked.
