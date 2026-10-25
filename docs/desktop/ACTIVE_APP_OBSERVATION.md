# Active App Observation on GNOME

<div dir="rtl" lang="fa">

**به‌روزرسانی F20:** آمادگی از نسخه و قابلیت کد بارشده سنجیده می‌شود؛ مبدل
نشست GNOME برای سرویس دیررس حفظ می‌شود و probe محدود دارد. نبود سرویس دیگر
به‌تنهایی موجب انتخاب دائمی launcher هنگام شروع نیست؛ فعال‌سازی نامطمئن
همچنان اجرای دوم نمی‌فرستد. [قرارداد فعلی](BACKEND_PROTOCOL.md).

</div>

## Problem and scope

For a command such as “open Ali's chat,” conversation history alone cannot establish which app the user is currently using. The `kyrin.desktop.active_app.ActiveAppObserver` contract provides a fresh observation. `None` means the active app is unknown; command understanding should ask the user when that distinction matters.

This integration targets GNOME Shell 50 only. The extension reports the desktop ID of the focused app. Its `GetActiveWindow` method also reports the focused window PID for the separate, read-only [screen observation](SCREEN_OBSERVATION.md) adapter. It does not read window titles, text, images, or files. `GnomeShellActiveAppObserver` maps reported desktop IDs to KYRIN's internal app IDs through an explicit mapping. An unrecognized app, no focused app, an unavailable extension, or a D-Bus error produces `None`. Results are not cached; each request makes a new observation.

For an explicitly allowed `OPEN_APP` action, `GnomeExistingAppActivator` can ask the same extension to raise an existing window. The extension checks whether the exact registered desktop ID has a window and uses GNOME's `Main.activateWindow` with a fresh display timestamp only in that case. This follows the window path used by Ubuntu Dock and handles a minimized window or another workspace. The result `requested` is not proof of focus: `ActivateOrLaunchExecutor` reads the foreground app again before reporting `CONFIRMED`. An explicit `no_window` falls back to the existing `.desktop` launcher; a missing or uncertain reply never triggers a second launch. The action gate still decides which app KYRIN may control. When the loaded extension is absent or incompatible, GNOME activation fails closed with a backend diagnostic until a later compatible probe succeeds. Other desktop environments can implement the same `ExistingAppActivator` contract.

## Existing-window commands

### Open-window picker

On GNOME, requests to see all currently open desktop windows open a numbered
preview of **currently open windows of applications selected for window
control in KYRIN Actions**. It does not expose windows outside that permission
list. Clear English/Persian wording is handled by a small concept-slot fast
path: a display request, a collective scope, and desktop windows or running
apps. This does not compare complete sentences. Other phrasings can be
proposed by the selected local command-understanding model as the targetless
`show_all_windows` operation. The model proposal still passes the permission
gate, and explicit negation or references to installed apps, browser tabs, or
files cannot trigger the picker. Unqualified “pages” stays ambiguous because
it could mean browser pages rather than desktop windows. Without a selected
command model, wording beyond the reviewed fast path may need rephrasing.
The user can click a preview, say its number, or say an exact registered
application name. A name works only when one window of that application was
shown; multiple windows require a number. “Cancel” or Escape closes the
preview. This uses the existing per-app window-control permission, and
`OpenWindowPickerExecutor` sends only those registered desktop IDs to GNOME.
The command layer never reads a title or screenshot. GNOME Shell holds a
temporary window-ID snapshot in memory and checks the same window still
belongs to the same app before activating it. While the picker is visible,
“close number two”, “exit 2”, “quit two”, or the Persian equivalent asks for a
separate yes/no confirmation. The number can be a digit or a spoken word, and
“number” is optional. Plain “two” still activates the window. Closing requires
both window-control and close permission for the selected application. GNOME
rechecks the saved window identity and sends a normal close request; it never
forces a process to quit. An app may ask separately about unsaved work. The
list is limited to the first 99 windows, ordered by application
name and stable window sequence. The existing Terminal-only picker remains
available for the Terminal menu and accepts the same numbered close request.

The preview itself may reveal on-screen content. GNOME's live clone is not
saved to disk. An action reply of `requested` means activation was requested,
not that the foreground result was verified. A user-session test is still
needed after the updated extension has loaded; deterministic GJS and Python
tests alone cannot establish live visual behavior.

`RESTORE_APP`, `MINIMIZE_APP`, `MAXIMIZE_APP`, `UNMAXIMIZE_APP`, `FULLSCREEN_APP`, `UNFULLSCREEN_APP`, and `CLOSE_APP_WINDOW` have separate settings permissions from `OPEN_APP`. Existing settings migrate with both new permissions disabled. The GNOME extension accepts only an exact registered desktop ID. When an app has multiple windows, it targets the focused window only if that window belongs to the named app; otherwise it asks the user to focus the desired window and repeat the command. This rule also applies to raising an existing app with `OPEN_APP`. Restore never launches a missing app. Unmaximize means returning to normal size and also exits fullscreen if needed. Close sends a normal window close request and never kills a process; the app may keep running in its tray or ask about unsaved work. Full application quit is a separate future action.

`GnomeAppWindowController` receives an opaque window token and checks the state of that exact window before returning success. A sent request alone is not a confirmed result. The extension returns only state flags and the token, never a window title or content. On an unsupported session or when the updated extension has not loaded yet, the window commands are unavailable. This GNOME-specific adapter sits behind `AppWindowController`, so other platforms can implement the same contract without changing command understanding. The control center exposes separate opt-in checkboxes for non-closing window controls and close, scoped to the selected applications.

<div dir="rtl">

**قرارداد جاری بستن پنجره، ۲۰۲۶/۱۰/۲۵:** طبق تصمیم جدید مالک، رضایت بستن از
مجوز ذخیره‌شده یا اعتماد کلی در `PermissionPolicy` می‌آید. در ترکیب اصلی هیچ
دکمهٔ Approve یا تأیید گفتاریِ جداگانهٔ عمل لازم نیست. رفع ابهام نام یا انتخاب
میان پنجره‌ها همچنان مستقل و لازم است. [قرارداد مشترک](../actions/PERSISTENT_PERMISSIONS_FA.md).

`PrepareWindowClose` یک مقصد را با برنامه/PID/token/نسل و مهلت ثابت ده‌ثانیه‌ای
مشاهده می‌کند؛ picker ورودی انحصاری را آزاد می‌کند. `CloseAuthorizedWindow`
همان نسل را یک‌بار مصرف و در همان نوبت حلقهٔ Shell، هویت، قابلیت بستن، تمرکز
و snapshot را دوباره بررسی می‌کند. تعویض پنجره یا PID، تغییر تمرکز حتی با
بازگشت، تغییر انتخاب، نسل نامنطبق و انقضا مانع اجرا هستند. لغو Python نیز پیش
از ارسال بررسی می‌شود. روش‌های قدیمی `ConfirmWindowClose` و
`CloseConfirmedWindow` برای سازگاری باقی‌اند و در مسیر اصلی فراخوانی نمی‌شوند.

فقط close معمولی ارسال می‌شود؛ kill، پاسخ به dialog ذخیره‌سازی و تکرار خودکار
وجود ندارد. نتیجه پس از بازخوانی همان پنجره گزارش می‌شود. backend باید قابلیت
`CloseAuthorizedWindow` و ساخت
`active-app@kyrin.local-2026-10-25-persistent-permissions` را گزارش کند.
پیش از آماده‌سازی، این قابلیت و `GetAppWindowState` بررسی می‌شوند؛ افزونهٔ قدیمی
با خطای قابلیت متوقف می‌شود و دیالوگ جایگزین ندارد. روش نصب و نتایج آزمون در
[گزارش مستقل](../development/PERSISTENT_PERMISSIONS_2026-10-25_FA.md) آمده‌اند.
مالک موفقیت بستن Chrome با تأیید بومی نسخهٔ قبلی را تأیید کرده است؛ این شاهد
به معنی آزمودن نسخهٔ تازهٔ بدون دیالوگ روی Chrome نیست.

**سابقهٔ تشخیص مرحلهٔ شکست پیش از مجوز ماندگار، ۲۰۲۶/۱۰/۲۵:** در پیگیری گزارش زندهٔ مالک، نتیجهٔ
عمومی `window_unverified` برای بستن GNOME کافی نبود. اکنون adapter علت‌های
ثابتِ `window_close_rejected:<reason>`، `window_close_commit_unknown:<reason>`
و `window_close_unverified:<reason>` را از هم جدا می‌کند. اولی ردشدن صریح
backend مانند `stale` است؛ دومی پاسخ مفقود/نامعتبر یا خطای انتقال هنگام
فراخوانی بستن؛ سومی دریافت `requested` بدون تأیید ناپدیدشدن پنجره است.
`window_present` یعنی در آخرین بازخوانی همان پنجره دیده شد؛ به معنی تشخیص
پرسش ذخیره‌سازی نیست. متن خطا، عنوان و محتوای پنجره کپی نمی‌شوند. رابط پیام
هر مرحله را توضیح می‌دهد. بررسی تمرکز و یک‌بارمصرف‌بودن تأیید حفظ شده‌اند. در پیگیری بعدی،
`stale` از مالک رسید و گرفتن تمرکز توسط خودِ dialog قدیمی Qt در نشست
جداگانه بازتولید شد. تأیید بومی Shell یک `Meta.Window` جدید نمی‌سازد؛
بنابراین به استثناکردن تغییر تمرکز از اعتبارسنجی نیازی نیست. افزونهٔ بارشده
در قرارداد پیشین باید قابلیت `ConfirmWindowClose` و ساخت
`active-app@kyrin.local-2026-10-25-close-confirmation` را گزارش کند.
مشاهدهٔ مهلت در Python نیز با جمع مستقیم مقایسه می‌شود تا خطای گردکردن
تفاضل دو عدد اعشاری، مهلت دقیق ده‌ثانیه‌ای را نامعتبر نکند.

</div>

## Components

```text
GNOME Shell → small extension → app desktop ID over D-Bus
                                     ↓
                       GnomeShellActiveAppObserver
                                     ↓
                      telegram / whatsapp / None
                                     ↓
                CommandCoordinator (optional dry run)
```

The extension lives under `integrations/gnome-shell/` and runs in the GNOME session. The Python adapter lives under `kyrin.desktop.platforms`, while the shared contract lives under `kyrin.desktop`. The adapter uses Ubuntu's `busctl` and adds no Python dependency. An optional bridge now supplies fresh observations to final decisions in the microphone diagnostic's `commands` mode. No desktop command is executed.

## Installed app discovery

`kyrin.desktop.app_catalog.AppCatalog` describes the separate task of finding applications registered on a device. `XdgDesktopAppCatalog` reads Linux `.desktop` entries from the [XDG data directories](https://specifications.freedesktop.org/basedir/0.8/) using Python's standard library. It derives exact desktop IDs according to the [Desktop Entry Specification](https://specifications.freedesktop.org/desktop-entry/latest/file-naming.html), prefers user entries over system entries, and honors `Hidden=true`. An entry with `NoDisplay=true` can still describe an installed app. The short diagnostic displays a catalog name beside an observed ID when an exact ID match exists.

The catalog is for discovery and labels, not proof of focus or app identity. Several entries can share a display name; this machine has two Chrome entries called “Google Chrome.” `AppIdentityResolver` applies explicit exact-ID bindings, optionally requiring that the observed ID still appears in the catalog. `GnomeShellActiveAppObserver` delegates mapping to this resolver. A name match alone must not authorize a command. Other operating systems can provide their own catalog implementation behind the same contract. This XDG reader is deliberately limited to the ID and base `Name` fields; it is not a full desktop menu implementation.

## Optional command dry run

The `scripts/audio/check_live_speech.py` diagnostic accepts repeated `--active-app-binding DESKTOP_ID=KYRIN_APP_ID` arguments in `commands` mode. It reads the active app only for a **final** transcript, verifies the exact desktop ID against the XDG catalog, and passes the mapped KYRIN ID to `CommandCoordinator`. Partial transcripts never block on a desktop observation. An absent extension, unknown ID, or unregistered app produces `None`, so an ambiguous chat command asks which app the user means. Without bindings, the diagnostic preserves its previous no-observation behavior. Its action gate still prints requests without executing them.

Use `scripts/desktop/check_active_app.py` to discover the desktop ID on the target machine. The binding is a diagnostic input, not a hard-coded project default or automatic identity guess. For example, after replacing the placeholder with an exact ID:

```bash
.venv/bin/python scripts/audio/check_live_speech.py --mode commands \
  --model-path /path/to/local/model --language fa --seconds 35 \
  --active-app-binding 'TELEGRAM_DESKTOP_ID=telegram'
```

## Manual validation

Build the test package with GNOME's own tool, then install and enable it for the current user:

```bash
mkdir -p local-data/permissions-checks/extension-build
gnome-extensions pack --force --extra-source windowPicker.js \
  --extra-source closeConfirmation.js \
  --out-dir local-data/permissions-checks/extension-build \
  integrations/gnome-shell/active-app@kyrin.local
gnome-extensions install --force \
  local-data/permissions-checks/extension-build/active-app@kyrin.local.shell-extension.zip
gnome-extensions enable active-app@kyrin.local
```

If the current session does not recognize the new extension, logging out and back in may be necessary. KYRIN must not log the user out automatically. Once the extension is enabled, this diagnostic prints changes in the observed app ID for 20 seconds:

```bash
.venv/bin/python scripts/desktop/check_active_app.py --seconds 20
```

Switch between several apps during that interval. The output should show the app that actually has focus, followed by its registered name when available; when no app ID can be determined, the diagnostic prints `unknown`. This test does not execute commands.

After updating an already loaded extension, a new GNOME session may be needed before `ActivateExistingApp` appears on D-Bus. A deterministic GJS test covers the extension method without touching the user's desktop. A separate live check must confirm that an already open Telegram window actually moves to the foreground on this GNOME installation.

### Validation results on 2026-10-05

- The extension package contained only `metadata.json` and `extension.js`.
- A separate headless session loaded the extension with `gnome-shell-test-tool --headless --extension`. With no focused window, the D-Bus method returned an empty app ID, which the diagnostic displayed as `unknown`.
- An attempt to focus Calculator in that headless session still produced `unknown`: the session did not provide an observable focused window. This run therefore did not verify that a real app ID can be reported.
- The extension was installed for a user-session test, but the current GNOME Shell session did not recognize it when `gnome-extensions enable` was called. The two installed files were removed after the test; no extension remained enabled in the main session.
- At that point, switching between Telegram and Chrome had not yet been validated in a live session. That check required a fresh login or a test session with an observable focused window.

### Live session result after restart on 2026-10-05

After a system restart, GNOME Shell 50.1 recognized and enabled the extension. A D-Bus request returned `chatgpt.desktop` for the focused Codex window. During a 20-second run, the diagnostic alternated between `google-chrome.desktop` and a Telegram desktop ID with an installation-specific suffix as the user confirmed switching between Chrome and Telegram several times. The Telegram ID exactly matched a `.desktop` entry in the user's XDG application directory. The local XDG catalog also found both Chrome entries and the Telegram entry. A later one-second run of the updated diagnostic displayed `chatgpt.desktop (ChatGPT)`. A read-only end-to-end probe mapped that observed ID to `codex` through an explicit test binding and catalog verification. This verifies foreground ID reporting, catalog labeling, and exact-ID resolution in this GNOME session; it does not validate command execution or future GNOME versions.

## Limitations

This approach is specific to GNOME and needs to be retested after a GNOME version change. Some windows may not map to a recognizable installed desktop ID. In that case, the observation must remain unknown. Other Linux desktop environments need separate adapters implementing the same contract; asking the user is the safe fallback when observation is unavailable.
