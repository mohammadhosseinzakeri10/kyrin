<div dir="rtl" lang="fa">

# بازبینی جامع Kyrin: معماری، قابلیت اطمینان و تعامل با رابط کاربری

تاریخ: ۲۰۲۶/۱۰/۲۳ — مبنای بررسی: commit `63df3390427adb49b9f4340eee37edd860d0f3d3`؛ در آغاز بررسی، درخت کاری Git پاک بود. این گزارش جایگزین گزارش پیشین همین فایل می‌شود و اصلاحات دو commit اخیر را در نظر می‌گیرد. هیچ کد، تنظیم، تست یا فایل دیگری تغییر نکرده است.

## ۱. نتیجهٔ اصلی

**پیشنهاد اصلی، اصلاح قرارداد عمل و چرخهٔ مشاهده تا تأیید نتیجه است؛ تعویض OCR به‌تنهایی مشکل کلیک را حل نمی‌کند.** برای نسخهٔ فعلی، سه عامل باید پیش از انتخاب مدل بزرگ‌تر بررسی شوند:

۱. مقایسهٔ بایت‌های PNG به‌جای پیکسل‌های تصویر می‌تواند حتی پنجرهٔ ثابت را «تغییرکرده» تشخیص دهد؛ GNOME زمان ساخت تصویر را داخل PNG می‌نویسد.
۲. سیاست جدید، تقریباً تمام نام‌های دلخواه و همهٔ درخواست‌های روشن/خاموش را پیش از OCR مسدود می‌کند؛ از جمله `Apply All Devices`.
۳. ارسال کلیک هنوز به معنی تحقق نتیجه نیست؛ ابزار عمومی بررسی پس از کلیک ندارد.

**[CONFIRMED]** این پروژه صرفاً یک اسکریپت صوتی یا نمونهٔ بدون تست نیست: قراردادهای جدا، تزریق وابستگی، صف محدود عمل، مجوزها، مشاهدهٔ GNOME، چند backend صوت/متن و تاریخچهٔ محلی دارد. در مقابل، قراردادهای lifecycle، لغو، تازگی هدف و نتیجه در همهٔ مسیرها یکسان نیستند. بازنویسی کامل توجیه ندارد؛ تکامل به یک هماهنگ‌کنندهٔ رویدادمحور با ابزارهای دارای پیش‌شرط و پس‌شرط، مناسب‌ترین مسیر است. شواهد ساختار: [ubuntu.py](/mnt/ai_projects/KYRIN/src/kyrin/app/platforms/ubuntu.py:271)، [command_runtime.py](/mnt/ai_projects/KYRIN/src/kyrin/runtime/command_runtime.py:102)، [gate.py](/mnt/ai_projects/KYRIN/src/kyrin/actions/gate.py:57).

### روش، دامنه و محدودیت شواهد

- `[CONFIRMED]`: مستقیماً در کد دیده شده یا با منطق واقعی و وابستگی‌های ساختگی بازتولید شده است. به معنی آزمون موفق روی دسکتاپ واقعی نیست.
- `[LIKELY]`: استنتاج قوی؛ شواهد و شرط وقوع مشخص شده‌اند.
- `[SPECULATION]`: فرضیهٔ نیازمند آزمایش؛ روش بررسی نوشته شده است.
- «پیشنهاد» و «معیار پذیرش» توصیف آینده‌اند. شدت‌ها اولویت مهندسی این محصول‌اند؛ امتیاز رسمی امنیتی نیستند.

**[CONFIRMED] دامنه:** ۴۵۹ فایل نسخه‌دار فهرست و برای ممیزی محتوایی/ایستا خوانده شدند: ۱۹۳ فایل Python در `src`، تعداد ۱۳۳ فایل تست Python، تعداد ۲۱ اسکریپت Python، تعداد ۶۲ سند Markdown و پنج فایل JavaScript. فایل‌های Python با AST تجزیه شدند؛ مسیرهای اصلی ورود، ترکیب وابستگی‌ها، صوت، فهم فرمان، سیاست، کلیک، Telegram، خروجی و حافظه عمیق‌تر بررسی شدند. همهٔ خطوط تمام تست‌ها و مستندات به‌صورت دستی بازبینی نشده‌اند؛ وزن مدل، کد کتابخانه‌های ثالث و داده‌های شخصی خارج از دامنه‌اند. [نقشهٔ پروژه](/mnt/ai_projects/KYRIN/docs/development/PROJECT_LAYOUT.md:1) و [PROJECT_CONTEXT.md](/mnt/ai_projects/KYRIN/PROJECT_CONTEXT.md:1) در کنار کد بررسی شدند؛ مستندات تاریخی به‌تنهایی اثبات رفتار فعلی نیستند.

**[CONFIRMED] اعتبارسنجی این بررسی:**

| بررسی | نتیجه و حدود |
|---|---|
| parsing تمام ۳۴۸ فایل Python | بدون خطای نحوی با Python پروژه؛ این پروژه Python 3.14 می‌خواهد و نحو جدید `except A, B:` در آن معتبر است. |
| `ruff check --no-cache --statistics src tests scripts` | خروج موفق؛ بدون diagnostic. |
| `ruff format --check --no-cache --output-format concise src tests scripts` | ناموفق از نظر قالب‌بندی: ۷۷ فایل نیازمند قالب‌بندی، ۲۷۱ فایل مطابق قالب. هیچ فایل اصلاح نشد. |
| آزمون‌های منتخب | `71 passed, 2 deselected`؛ هندسه، تطبیق متن، انتقال هندسه، کلیک عمومی، برنامهٔ عمل، صف و runtime. |
| محافظ آزمون | نوشتن فایل، ساخت/حذف مسیر، subprocess واقعی و اتصال شبکه در فرایند آزمون مسدود شد؛ bytecode، cache و بارگذاری خودکار pluginهای pytest غیرفعال بودند. |
| اجرای اولیهٔ آزمون منتخب | یک fixture نیازمند فایل موقت با محافظ برخورد کرد؛ این خطای محصول نبود. آن آزمون و آزمون تاریخچهٔ نیازمند دیتابیس موقت کنار گذاشته شدند؛ اجرای نهایی بدون خطا بود. |
| بازتولیدهای مستقل در حافظه | PNG هم‌پیکسل با metadata متفاوت؛ رد برچسب‌ها با policy؛ پذیرفتن جهت مخالف scroll؛ inference روی partial؛ ادامهٔ برنامهٔ درحال‌اجرا پس از لغو صف؛ تفاوت عبارت فارسی در locator و inventory. |
| اجرا نشده | کل pytest، mypy، آزمون زندهٔ میکروفون/کلیک/portal، دسترسی به محتوای صفحه، اجرای مدل واقعی و benchmark انتهابه‌انتها. |

**[CONFIRMED] محیط قابل مشاهده:** Ubuntu 26.04.1، GNOME Shell 50.1، `XDG_SESSION_TYPE=wayland`، `WAYLAND_DISPLAY=wayland-0` و `XDG_CURRENT_DESKTOP=ubuntu:GNOME`. پرس‌وجوی `nvidia-smi` در محیط این بررسی نتوانست با driver ارتباط بگیرد؛ این نتیجه برای اعلام خرابی GPU میزبان یا تعیین VRAM کافی نیست. مقدار VRAM، scale و چیدمان واقعی مانیتورها، مدل انتخاب‌شده و نسخهٔ extension واقعاً بارشده تأیید نشده‌اند. اطلاعات تاریخی سخت‌افزار در [PROJECT_CONTEXT.md](/mnt/ai_projects/KYRIN/PROJECT_CONTEXT.md:322) جای اندازه‌گیری جاری را نمی‌گیرد.

**فرض‌های صریح:** هدف، دسکتاپ محلی مالک با مدل‌های محلی است؛ شبکهٔ ابری و ورود به حساب جدید پیشنهاد پیش‌فرض نیستند. حفظ رفتارهای امنِ رد عمل در ابهام، بر افزایش پوشش به قیمت کلیک نامطمئن اولویت دارد. هیچ نصب، دانلود، اتصال حساب، اجرای sudo، درخواست مجوز جدید یا تعامل واقعی با دسکتاپ انجام نشد.

## ۲. پروژه اکنون چه می‌کند و چگونه کار می‌کند؟

### ساختار و نقاط ورود

| بخش | مسئولیت مشاهده‌شده |
|---|---|
| ورودی دسکتاپ | `kyrin-desktop -> kyrin.app.qt.main:main`، پنجرهٔ PySide6، نمونهٔ واحد، settings، سرویس مشاهده و workerها؛ [pyproject.toml](/mnt/ai_projects/KYRIN/pyproject.toml:54)، [main.py](/mnt/ai_projects/KYRIN/src/kyrin/app/qt/main.py:163). |
| ترکیب وابستگی‌ها | `UbuntuSessionFactory` مدل، مجوز، interpreter، gate، executor، صوت و حافظه را می‌سازد؛ [ubuntu.py](/mnt/ai_projects/KYRIN/src/kyrin/app/platforms/ubuntu.py:271). |
| صوت | `AudioInput` مستقل از `MicrophoneInput`؛ دریافت، تبدیل نرخ، framing، Silero VAD، backlog و STT؛ [live_speech_pipeline.py](/mnt/ai_projects/KYRIN/src/kyrin/audio/live_speech_pipeline.py:35). |
| فایل صوتی | ffmpeg فایل را بدون ساخت نسخهٔ PCM روی دیسک به مسیر ترتیبی VAD/STT می‌دهد؛ همان مجوزهای عمل مصرف می‌شوند؛ [file_input.py](/mnt/ai_projects/KYRIN/src/kyrin/audio/file_input.py:35)، [file_speech_pipeline.py](/mnt/ai_projects/KYRIN/src/kyrin/audio/file_speech_pipeline.py:30). |
| فهم فرمان | قواعد فارسی/انگلیسی، سپس مدل محلی Ollama و بررسی مستقل operation/target؛ clarification، fragment و plan؛ [demo_interpreter.py](/mnt/ai_projects/KYRIN/src/kyrin/commands/demo_interpreter.py:213)، [model_interpreter.py](/mnt/ai_projects/KYRIN/src/kyrin/commands/model_interpreter.py:246). |
| عمل | gate با مجوز صریح، صف FIFO و executorهای برنامه/پنجره/Telegram/scroll/control؛ [gate.py](/mnt/ai_projects/KYRIN/src/kyrin/actions/gate.py:25)، [queued_dispatch.py](/mnt/ai_projects/KYRIN/src/kyrin/actions/queued_dispatch.py:59). |
| مشاهده و ورودی Linux | GNOME extension، D-Bus، AT-SPI، OCR و RemoteDesktop portal؛ قرارداد مشترک `CaptureGeometry` اکنون وجود دارد؛ [capture_geometry.py](/mnt/ai_projects/KYRIN/src/kyrin/vision/capture_geometry.py:19). |
| پاسخ و حافظه | متن، نشانگر GNOME، صف TTS و SQLite برای متن نهایی؛ [speech.py](/mnt/ai_projects/KYRIN/src/kyrin/responses/speech.py:83)، [history.py](/mnt/ai_projects/KYRIN/src/kyrin/memory/history.py:45). |

همهٔ ردیف‌های جدول بالا **[CONFIRMED]** هستند. وابستگی‌های اصلی `numpy / onnxruntime / soxr / sounddevice` و extraهای اختیاری Qt، STT و TTS در [pyproject.toml](/mnt/ai_projects/KYRIN/pyproject.toml:18) آمده‌اند. ابزارهای سیستم مانند `busctl`، GNOME extension، portal و runtime مدل‌ها نیز لازم‌اند؛ نصب pip به‌تنهایی همهٔ قابلیت‌ها را آماده نمی‌کند.

### جریان داده و کنترل

<div dir="ltr">

```text
Microphone -> capture queue -> resample / frames -> VAD -> audio backlog
                                                          |
                                                          v
                                                    STT worker
                                                          |
Local audio file -> ffmpeg -> ordered VAD / STT -----------+
                                                          |
                                                  partial / final events
                                                          |
                       LiveCommandRuntime -> CommandCoordinator
                                                          |
                         fast rules -> optional local model -> validators
                                                          |
                                              final Command / Plan
                                                          |
                                       bounded action queue -> ActionGate
                                                          |
                         app / window / Telegram / desktop executors
                                                          |
                                   OS input -> result / some verification
                                                          |
                                               text / GNOME status / TTS

Focused window -> capture geometry / AT-SPI / OCR -> target evidence
Final transcript -> bounded SQLite history -> recent text context
Power confirmation flow and Telegram selection have additional workers.
```

</div>

**[CONFIRMED] نکتهٔ جریان:** capture/VAD/STT و اجرای عمل worker دارند، اما تفسیر فرمان و فراخوانی مدل در مصرف‌کنندهٔ رویدادها همگام‌اند. نمودار به معنی مستقل بودن تمام مراحل نیست؛ پیامد آن در F07 آمده است.

**[CONFIRMED] تفاوت با شرح اولیه:** در نسخهٔ فعلی مسیر آزاد «گفتار -> دستور shell دلخواه» پیدا نشد. Ptyxis با flagهای ثابت، tab/window/preferences را کنترل می‌کند؛ شواهدی از اجرای متن STT با `shell=True`، `eval` یا `bash -c` در این مسیر وجود ندارد. همچنین حافظهٔ متنی و کلیک عمومی از قبل وجود دارند. وب‌کم، تشخیص چهره/گوینده و حلقهٔ خودمختار عمومی در مسیر اجرایی بررسی‌شده پیاده نشده‌اند. [ptyxis.py](/mnt/ai_projects/KYRIN/src/kyrin/actions/platforms/ptyxis.py:12)، [linux.py](/mnt/ai_projects/KYRIN/src/kyrin/actions/platforms/linux.py:35)، [ubuntu.py](/mnt/ai_projects/KYRIN/src/kyrin/app/platforms/ubuntu.py:495).

### وضعیت اصلاحات پس از گزارش قبلی

شناسه‌های R در این جدول به گزارش پیشین اشاره دارند؛ شناسه‌های F در ادامه، یافته‌های این گزارش‌اند.

| موضوع قدیمی | وضعیت فعلی مشاهده‌شده |
|---|---|
| R01: شناسهٔ گزینه می‌توانست با هدف گفتار متفاوت باشد | **[CONFIRMED] اصلاح شده:** تطابق `_words(option.label) == _words(target)` الزامی است؛ [model_interpreter.py](/mnt/ai_projects/KYRIN/src/kyrin/commands/model_interpreter.py:449). خطای قدیمی نباید دوباره فعال گزارش شود. |
| R02: پذیرش scroll برای نفی/گفتار غیرامری | **[CONFIRMED] محدود شده:** `_source_is_instruction` افزوده شده؛ ولی جهت operation هنوز مستقل بررسی نمی‌شود؛ F09. |
| R03/R04: نبود geometry مشترک | **[CONFIRMED] اصلاح ساختاری:** scale، padding، viewport، token، capture ID و timestamp مشترک شده‌اند و به Telegram می‌رسند؛ [test_capture_geometry_flow.py](/mnt/ai_projects/KYRIN/tests/actions/test_capture_geometry_flow.py:25). محدودیت producer و legacy باقی است؛ F13. |
| R05: نبود هویت پنجره/تازگی | **[CONFIRMED] بهبود:** helperهای OCR اکنون token، سن capture و محتوا را بررسی می‌کنند. این حفاظت برای همهٔ مسیرهای AT-SPI و فاصلهٔ فهم فرمان تا capture کامل نیست؛ F14. |
| R11: لغو فرمان‌های در صف/نتیجهٔ دیررس مدل | **[CONFIRMED] بهبود:** generation زمان submit بررسی و صف باطل می‌شود؛ [command_runtime.py](/mnt/ai_projects/KYRIN/src/kyrin/runtime/command_runtime.py:294). برنامهٔ شروع‌شده و helper درحال‌اجرا هنوز لغو سراسری ندارند؛ F05. |
| R12: لغو فرمان‌های فایل در EOF | **[CONFIRMED] اصلاح شده:** منبع متناهی برای ظرفیت صبر می‌کند و در EOF طبیعی تا سقف ۶۰ ثانیه drain می‌شود؛ [command_runtime.py](/mnt/ai_projects/KYRIN/src/kyrin/runtime/command_runtime.py:314). این تضمین زمان نامحدود نیست. |
| R13: فیلتر پیامدهای حساس | **[CONFIRMED] محافظه‌کارانه‌تر شده:** Unicode/punctuation نرمال و unknown risk رد می‌شود؛ ولی مسیر تأیید برای ادامه وجود ندارد و پوشش محصول کاهش یافته؛ F02. |

## ۳. یافته‌های اصلی با اولویت کلیک

### F01 — High — «یکسان بودن PNG» معیار معتبر تازگی محتوای هدف نیست

**[CONFIRMED] محل:** [extension.js](/mnt/ai_projects/KYRIN/integrations/gnome-shell/window-capture-prototype@kyrin.local/extension.js:425)، به‌ویژه مقایسهٔ طول و همهٔ بایت‌ها در خط ۴۶۵. helper عمومی از [desktop_control_helper.py](/mnt/ai_projects/KYRIN/src/kyrin/actions/platforms/desktop_control_helper.py:179) و Telegram از [telegram_portal_helper.py](/mnt/ai_projects/KYRIN/src/kyrin/actions/platforms/telegram_portal_helper.py:366) آن را شرط کلیک می‌کنند.

**[CONFIRMED] شاهد خارجی:** منبع رسمی GNOME در شاخهٔ 50 در `write_screenshot_thread`، کلید `tEXt::Creation Time` را با زمان تصویر ذخیره می‌کند؛ زمان هر capture تازه ساخته می‌شود. بنابراین مقایسهٔ فایل فشرده با مقایسهٔ تصویر یکسان نیست. [منبع GNOME 50، خطوط ۲۵۹ تا ۲۸۴](https://github.com/GNOME/gnome-shell/blob/gnome-50/src/shell-screenshot.c#L259).

**بازتولید بدون دسکتاپ:** دو PNG معتبر در حافظه با یک پیکسل قرمز یکسان و دو مقدار متفاوت `Creation Time` ساخته شدند. QImage برابری پیکسل‌ها را تأیید کرد؛ شرط برابری بایت‌ها false شد.

**[LIKELY] اثر عملی:** روی GNOME نصب‌شده، عبور capture و validation از مرز یک ثانیه می‌تواند پنجرهٔ کاملاً ثابت را رد کند؛ خود PNG زندهٔ این نشست خوانده نشد. حتی با حذف metadata، caret، spinner، ویدئو، تغییر ساعت یا پیام جدید در بخش نامرتبط، کل تصویر را متفاوت می‌کند. این شکست به غلط شبیه جابه‌جایی هدف گزارش می‌شود. هزینهٔ capture/PNG دوم هم به latency افزوده می‌شود.

**اصلاح پیشنهادی:** مقایسه بر decoded pixels یا fingerprint ناحیهٔ مرتبط باشد؛ metadata نادیده گرفته شود. هویت پنجره و ساختار هدف حفظ و درست پیش از عمل، label/role/state/bbox هدف دوباره resolve شود. ROI و نواحی پویا جدا شوند؛ حذف بی‌قید validation نیز راه‌حل نیست. **معیار پذیرش:** metadata متفاوت و انیمیشن نامرتبط کلیک هدف ثابت را رد نکنند؛ جابه‌جایی یا جایگزینی خود هدف همچنان مانع عمل شود.

### F02 — High — بیشتر فرمان‌های کلیک و همهٔ toggleها اکنون پیش از OCR رد می‌شوند

**[CONFIRMED] محل:** [desktop_control.py](/mnt/ai_projects/KYRIN/src/kyrin/actions/platforms/desktop_control.py:39). فقط شش label انگلیسی `advanced/settings/search/help/preferences/about` با `state=None` مجازند؛ هر مقدار دیگر `visible_control_risk_unknown` می‌دهد و executor در خط ۸۸ پیش از identity/OCR برمی‌گردد.

**بازتولید واقعی تابع policy:**

| درخواست هدف | نتیجه |
|---|---|
| `Apply All Devices` | `visible_control_risk_unknown` |
| `Select All` / `Mode` | `visible_control_risk_unknown` |
| `Notifications` با `state=True` | `visible_control_risk_unknown` |
| «تنظیمات» | `visible_control_risk_unknown` |
| `Settings` با `state=None` | عبور از policy؛ موفقیت کلیک هنوز تضمین نیست. |

**اهمیت:** یک رد امنِ عمدی، regression پوشش محصول ایجاد کرده است؛ نباید آن را OCR miss تشخیص داد. روشن/خاموش‌کردن در parser و helper وجود دارد، اما در مسیر عمومی فعلی دسترس‌پذیر نیست. شرح کلیک OpenRGB در مستندات قدیمی‌تر رفتار این checkout را تضمین نمی‌کند.

**اصلاح پیشنهادی:** policy بر نوع عمل، control و پیامد متکی شود؛ خطر نامعلوم به جریان تأیید مشخص با هدف/پیامد/انقضا برسد، سپس target دوباره resolve شود. برای navigation شناخته‌شده alias چندزبانه و قابلیت ابزار تعریف شود. همهٔ نام‌های unknown را آزاد نکنید و فقط denylist را بلندتر نکنید. **معیار پذیرش:** label کم‌خطرِ تأییدشده قابل اجرا باشد؛ Delete/Send/Pay و toggle ناشناخته بدون تصمیم روشن اجرا نشوند؛ UI علت «مجوز/خطر» را از «متن پیدا نشد» جدا نشان دهد.

### F03 — High — dispatch کلیک، تحقق عمل را ثابت نمی‌کند

**[CONFIRMED] محل:** helper عمومی پس از press/release، `CLICK_DISPATCHED` می‌دهد؛ [desktop_control_helper.py](/mnt/ai_projects/KYRIN/src/kyrin/actions/platforms/desktop_control_helper.py:288). executor آن را به‌درستی `LAUNCH_ACCEPTED` می‌نامد، اما مشاهدهٔ پس از کلیک ندارد؛ [desktop_control.py](/mnt/ai_projects/KYRIN/src/kyrin/actions/platforms/desktop_control.py:232).

**[CONFIRMED]** برای toggle فقط «از قبل در حالت مطلوب است» بررسی می‌شود؛ پس از تغییر، حالت حاصل خوانده نمی‌شود. Telegram در مسیر search header را بررسی می‌کند ولی در visible-row فقط dispatch گزارش می‌دهد؛ [telegram.py](/mnt/ai_projects/KYRIN/src/kyrin/actions/platforms/telegram.py:856). کنترل پنجره در مقابل، verification با token و polling دارد؛ [gnome_window_control.py](/mnt/ai_projects/KYRIN/src/kyrin/desktop/platforms/gnome_window_control.py:118). پس ادعای «هیچ verificationی در پروژه نیست» صحیح نیست.

**[CONFIRMED]** `ActionPlanRunner` با `FAILED/UNKNOWN` متوقف می‌شود، اما `LAUNCH_ACCEPTED` می‌تواند مرحلهٔ بعد را آزاد کند؛ فقط برای `OPEN_CHAT` بررسی وابستگی ویژه وجود دارد. [plan_runner.py](/mnt/ai_projects/KYRIN/src/kyrin/actions/plan_runner.py:41).

**اصلاح پیشنهادی:** پس‌شرط معنایی ابزار تعریف شود: dialog مورد انتظار، node جدید، checked state یا هویت chat. مرحلهٔ وابسته تا تحقق آن شروع نشود. `DISPATCHED_UNVERIFIED` وضعیت مستقل و قابل بازیابی باشد. **معیار پذیرش:** «کلیک ارسال شد» با «گزینه فعال شد» در event، حافظه و پیام کاربر یکسان نشود.

### F04 — High — AT-SPI وجود دارد، اما به OCR وابسته و عمدتاً به مختصات تقلیل یافته است

**[CONFIRMED] محل:** [desktop_control_inventory.py](/mnt/ai_projects/KYRIN/src/kyrin/actions/platforms/desktop_control_inventory.py:61)، [desktop_control.py](/mnt/ai_projects/KYRIN/src/kyrin/actions/platforms/desktop_control.py:105)، [desktop_accessibility_inventory.py](/mnt/ai_projects/KYRIN/src/kyrin/actions/platforms/desktop_accessibility_inventory.py:23)، [desktop_control_helper.py](/mnt/ai_projects/KYRIN/src/kyrin/actions/platforms/desktop_control_helper.py:63).

inventory ابتدا accessibility را می‌خواند و در نام یکتای منطبق، OCR را کنار می‌گذارد؛ این نکتهٔ مثبت موجود است. ولی ورود به همان inventory و executor، `verifier.ready()` می‌خواهد که به screen grant و موجود/آزاد بودن OCR reader وابسته است. فرمان مستقیم معمولاً ابتدا OCR و سپس fallback accessibility دارد.

**[CONFIRMED]** جست‌وجو در subtree کل برنامهٔ هم‌PID انجام می‌شود؛ state عمدتاً `ENABLED` و مرکز rect داخل frame بررسی می‌شود. stateهای `SHOWING/VISIBLE/SENSITIVE/DEFUNCT`، ancestor پنجرهٔ دقیق و action interface کامل بررسی نمی‌شوند. `do_action` وجود ندارد؛ node به مرکز rect تبدیل و با portal کلیک می‌شود. Radio button در click roles هست، ولی در state roles نیست.

**[LIKELY]** node پنهان یا پنجرهٔ دیگرِ هم‌PID می‌تواند ambiguity یا انتخاب نامناسب بسازد؛ OCR busy یا نبود زبان OCR می‌تواند عملی را متوقف کند که accessibility به‌تنهایی قادر به اجرای آن است.

**اصلاح پیشنهادی:** locator/actuator معنایی AT-SPI را مستقل کنید؛ node را با window، role، ancestry و state معتبر resolve کنید؛ actionهای موجود را enumerate و action مناسب را invoke کنید؛ selection/text/value نیز interface خود را داشته باشند. سپس state خوانده شود. **معیار پذیرش:** کنترل استاندارد با OCR خاموش و بدون screenshot قابل استفاده باشد؛ node پنهان/defunct انتخاب نشود. semantics رسمی: [Action.do_action](https://gnome.pages.gitlab.gnome.org/at-spi2-core/libatspi/method.Action.do_action.html)، [StateType](https://gnome.pages.gitlab.gnome.org/at-spi2-core/libatspi/enum.StateType.html).

### F05 — High — توقف یا لغو صف، برنامهٔ شروع‌شده و helper فعال را متوقف نمی‌کند

**[CONFIRMED] محل:** [queued_dispatch.py](/mnt/ai_projects/KYRIN/src/kyrin/actions/queued_dispatch.py:128)، [plan_runner.py](/mnt/ai_projects/KYRIN/src/kyrin/actions/plan_runner.py:41)، [command_runtime.py](/mnt/ai_projects/KYRIN/src/kyrin/runtime/command_runtime.py:180). generation برای کارهای شروع‌نشده مفید است، اما `_process(command)` cancellation دریافت نمی‌کند؛ حلقهٔ plan نیز میان مراحل آن را بررسی نمی‌کند.

**بازتولید با executor ساختگی:** برنامه‌ای دو مرحله‌ای در مرحلهٔ اول متوقف شد؛ `invalidate_pending()` فراخوانی شد؛ پس از آزادشدن مرحلهٔ اول، هر دو مرحلهٔ `[0,1]` اجرا شدند. عملیات واقعی انجام نشد.

**[CONFIRMED]** کلیک عمومی `subprocess.run(timeout=45)` و Telegram تا ۶۵ ثانیه منتظر helper می‌مانند؛ helper cancellation مشترک ندارد. close صف برای نشست زنده ۲۰ ثانیه صبر می‌کند. حذف restore token برای revocation، نشست portal ازقبل‌فعال را در این کد نمی‌بندد. [desktop_control.py](/mnt/ai_projects/KYRIN/src/kyrin/actions/platforms/desktop_control.py:149)، [telegram.py](/mnt/ai_projects/KYRIN/src/kyrin/actions/platforms/telegram.py:595)، [window.py](/mnt/ai_projects/KYRIN/src/kyrin/app/qt/window.py:1050).

**[LIKELY] اثر:** پس از Pause/Stop یا خاموش‌شدن permission، عمل شروع‌شده ممکن است هنوز input بفرستد. این یک خطر lifecycle است؛ ادعای اجرای عمل مخرب روی دسکتاپ در این بررسی نیست.

**اصلاح پیشنهادی:** cancellation و deadline مشترک تا هر مرحله و helper حمل شوند؛ مجری درست پیش از input epoch مجوز را بررسی کند؛ مالک subprocess بتواند آن را متوقف کند و portal را ببندد. لغو، عمل قبلاً انجام‌شده را rollback نمی‌کند؛ نتیجهٔ آن باید مشاهده یا UNKNOWN گزارش شود. **معیار پذیرش:** پس از لغو، مرحلهٔ بعد و input هنوز ارسال‌نشده اجرا نشوند.

### F06 — High — مالک واحد برای تمام ورودی‌های دسکتاپ وجود ندارد

**[CONFIRMED] محل:** صف عمل یک worker دارد، ولی انتخاب شمارهٔ Telegram و paging، thread مستقل می‌سازند؛ [telegram_selection.py](/mnt/ai_projects/KYRIN/src/kyrin/actions/telegram_selection.py:332)، [telegram_selection.py](/mnt/ai_projects/KYRIN/src/kyrin/actions/telegram_selection.py:386). خود Telegram lock داخلی دارد؛ [telegram.py](/mnt/ai_projects/KYRIN/src/kyrin/actions/platforms/telegram.py:184). executorهای generic control و scroll در wrapperهای بیرونی از همان lock عبور نمی‌کنند؛ [ubuntu.py](/mnt/ai_projects/KYRIN/src/kyrin/app/platforms/ubuntu.py:775).

**[LIKELY]** completion انتخاب Telegram با scroll/click عمومی یا تغییر focus توسط ابزار دیگر می‌تواند هم‌پوشان شود. محافظ‌های focus بسیاری از موارد را رد می‌کنند، اما ترتیب واحدِ عملیات مرکب را تضمین نمی‌کنند. **روش تأیید:** barrier آزمون، completion فعال Telegram و فرمان generic هم‌زمان، ثبت ترتیب input ساختگی.

**اصلاح پیشنهادی:** یک DesktopInputBroker/actor مالک کلیهٔ keyboard/pointer و نشست portal باشد؛ عملیات مرکب input به‌صورت واحد قابل لغو اجرا شود. خواندن observation می‌تواند مستقل باشد؛ ورودی OS باید serialize شود. reuse نشست portal در همان مرز و با revocation واقعی انجام شود.

### F07 — High — مدل روی partial نیز فراخوانی می‌شود و مصرف‌کنندهٔ رویداد را مسدود می‌کند

**[CONFIRMED] محل:** [coordinator.py](/mnt/ai_projects/KYRIN/src/kyrin/commands/coordinator.py:171) پیش از شاخهٔ `PARTIAL`، interpreter را صدا می‌زند؛ [model_interpreter.py](/mnt/ai_projects/KYRIN/src/kyrin/commands/model_interpreter.py:320) guard برای `context.is_final_transcript` ندارد؛ مدل می‌تواند بعد از شکست قواعد اجرا شود.

**بازتولید:** یک partial با متن نامتعارف به coordinator واقعی و مدل ساختگی داده شد؛ شمار inference مدل یک شد. partial همچنان اجازهٔ عمل نمی‌دهد؛ نقص، هزینه و انسداد است.

**[CONFIRMED]** timeout مدل ۶۰ ثانیه و در CPU برابر ۱۲۰ ثانیه است؛ مسیر کشف کنترل گاهی دو inference دارد. [ollama_engine.py](/mnt/ai_projects/KYRIN/src/kyrin/commands/ollama_engine.py:365)، [model_interpreter.py](/mnt/ai_projects/KYRIN/src/kyrin/commands/model_interpreter.py:382). فراخوانی همگام در runtime است؛ [command_runtime.py](/mnt/ai_projects/KYRIN/src/kyrin/runtime/command_runtime.py:281).

**[LIKELY]** final و «توقف شنیدن» پشت inference منتظر می‌مانند؛ با event queue محدود ۲۵۶تایی و backlog پنج‌ثانیه‌ای، کندی طولانی می‌تواند به فشار صف و از دست رفتن پیوستگی نشست برسد. overflow مشخصی در این بررسی زنده دیده نشد.

**اصلاح پیشنهادی:** partial فقط مسیر ارزان و بدون I/O داشته باشد؛ فهم final در worker قابل لغو با backpressure انجام شود؛ stop/control مسیر اولویت‌دار مستقل داشته باشد. **معیار پذیرش:** صفر inference مدل برای partial؛ توقف دستی مستقل از timeout مدل؛ نتیجهٔ دیررس پس از تغییر epoch اجرا نشود.

### F08 — High — timeout درخواست، پایان واقعی کار OCR یا deadline کل عملیات نیست

**[CONFIRMED] محل:** [chat_verifier.py](/mnt/ai_projects/KYRIN/src/kyrin/app/qt/chat_verifier.py:192). caller پس از ۱۸ ثانیه Event را set می‌کند، اما worker و pending را لغو نمی‌کند. Paddle هر بار process/model تازه با timeout ۶۰ یا ۹۰ ثانیه می‌سازد؛ [paddle.py](/mnt/ai_projects/KYRIN/src/kyrin/vision/ocr/backends/paddle.py:95). callback می‌تواند پس از پایان انتظار caller، fallback OCR بعدی را آغاز کند؛ [chat_verifier.py](/mnt/ai_projects/KYRIN/src/kyrin/app/qt/chat_verifier.py:430).

**[CONFIRMED]** حلقهٔ settle ده‌ثانیه‌ای Telegram یک call داخلی هجده‌ثانیه‌ای دارد و در حالت خاص برای تأیید دوم ادامه می‌دهد؛ پس «۱۰ ثانیه» سقف کل نیست. [telegram.py](/mnt/ai_projects/KYRIN/src/kyrin/actions/platforms/telegram.py:982). capture حداکثر ۱۰ ثانیه معتبر است، اما آماده‌سازی مجدد portal می‌تواند بیشتر طول بکشد.

**[LIKELY]** کاربر شکست می‌بیند ولی OCR هنوز busy است؛ فرمان بعدی رد می‌شود و مصرف CPU ادامه می‌یابد. **اصلاح پیشنهادی:** deadline مطلق مشترک، remaining budget برای هر call، ابطال fallback پس از timeout، و worker پایدارِ قابل توقف برای backend سنگین. ابتدا input grant آماده و سپس target تازه گرفته شود. cold start، queue و inference جدا اندازه‌گیری شوند.

### F09 — High — بررسی جدید scroll، جهت درخواست را با پیشنهاد مدل تطبیق نمی‌دهد

**[CONFIRMED] محل:** [model_interpreter.py](/mnt/ai_projects/KYRIN/src/kyrin/commands/model_interpreter.py:416). `_source_is_instruction(scroll=True)` وجود یک درخواست scroll بالا یا پایین را می‌سنجد؛ intent از operation پیشنهادی مدل ساخته می‌شود، بدون اثبات برابری جهت.

**بازتولید با قواعد واقعی و مدل ساختگی:** متن `Could you scroll up on this page please` در قواعد مستقیم `NotACommand` شد؛ مدل `SCROLL_DOWN` پیشنهاد کرد؛ interpreter با `review_model_action` واقعی، `ReadyCommand(SCROLL_DOWN)` برگرداند. دو عبارت طبیعی دیگر نیز همان نتیجه را داشتند.

**اصلاح پیشنهادی:** استخراج مستقل جهت/ناحیه/مقدار و مقایسه با proposal؛ ابهام یا تناقض به clarification برسد. همان اصل برای state کنترل‌ها و تمام شاخه‌های زودبازگشت برقرار باشد. **معیار پذیرش:** خروجی معکوس مدل هرگز به input تبدیل نشود؛ آزمون منفیِ مدل عمداً اشتباه اضافه شود.

### F10 — High — Telegram هنوز به layout و نقاط ثابت وابسته است؛ تایپ نیز focus تراکنشی ندارد

**[CONFIRMED] محل:** cropهای درصدی/پیکسلی در [screen_text_reader.py](/mnt/ai_projects/KYRIN/src/kyrin/app/qt/screen_text_reader.py:38)، قواعد عنوان/تاریخ/preview در [telegram_verification.py](/mnt/ai_projects/KYRIN/src/kyrin/actions/telegram_verification.py:73)، و hamburger ثابت `(14,26,28,32)` در [telegram_portal_helper.py](/mnt/ai_projects/KYRIN/src/kyrin/actions/platforms/telegram_portal_helper.py:586). افزودن geometry مشترک، ثابت‌بودن محل hamburger را رفع نکرده است.

**[LIKELY]** sidebar قابل تغییر، زبان RTL، UI scale داخل Telegram، عنوان بلند یا theme متفاوت می‌توانند crop و فرض سطر را نامعتبر کنند. وجود چندمانیتور به‌خودی‌خود اثبات خرابی نیست.

**[CONFIRMED]** بعد از focus search و Ctrl+A، رشته حرف‌به‌حرف تایپ می‌شود؛ در حلقهٔ هر حرف، identity/فیلد متنی دوباره بررسی نمی‌شود؛ [telegram_portal_helper.py](/mnt/ai_projects/KYRIN/src/kyrin/actions/platforms/telegram_portal_helper.py:281). **[LIKELY]** تغییر focus در این بازه می‌تواند ادامهٔ نام chat را در مقصد دیگری وارد کند؛ حداکثر طول ۶۴ و کاراکترهای مجاز، مانع این نوع اشتباه نیستند.

**اصلاح پیشنهادی:** navigation شناخته‌شده با shortcut تأییدشده یا semantic selector؛ عناصر تصویری با locator از دادهٔ زنده؛ عملیات تایپ با field identity، cancellable batch و بررسی focus/state بین بخش‌ها. **معیار پذیرش:** resize/sidebar/RTL و تغییر focus وسط تایپ موجب ورودی در پنجرهٔ نامرتبط نشوند.

### F11 — High — تأیید بستن پنجره‌های دارای کار ذخیره‌نشده یکسان نیست

**[CONFIRMED] محل:** [demo_interpreter.py](/mnt/ai_projects/KYRIN/src/kyrin/commands/demo_interpreter.py:1081). بستن Terminal تأیید ویژه دارد، اما exact close برای دیگر برنامه‌های مجاز می‌تواند مستقیم Ready شود. composition، `confirmation_required_for` را برای gate تنظیم نمی‌کند؛ [ubuntu.py](/mnt/ai_projects/KYRIN/src/kyrin/app/platforms/ubuntu.py:406).

**[CONFIRMED]** کنترل GNOME درخواست معمول window close و سپس مشاهدهٔ بسته‌شدن را انجام می‌دهد؛ اجبار عمومی برای kill در این مسیر دیده نشد. **[LIKELY]** برنامهٔ مقصد ممکن است dialog ذخیره‌سازی نشان دهد، ولی همهٔ برنامه‌ها چنین تضمینی ندارند؛ KYRIN نیز state ذخیره‌نشدهٔ همهٔ برنامه‌ها را نمی‌داند.

**اصلاح پیشنهادی:** بستن دارای پیامد از allowlist کلی برنامه جدا شود؛ حالت نامعلومِ unsaved با تأیید هدف/پنجره و انقضای روشن مدیریت شود. power flow موجود با دو تأیید مستقل حفظ شود. **معیار پذیرش:** پنجرهٔ اشتباه یا درخواست قدیمیِ تأییدشده قابل مصرف نباشد.

## ۴. یافته‌های تکمیلی و کیفیت مهندسی

### F12 — Medium — قرارداد عبارت OCR و فهرست گزینه‌ها با زبان/segmentation یکسان کار نمی‌کند

**[CONFIRMED] محل:** [visible_control.py](/mnt/ai_projects/KYRIN/src/kyrin/actions/visible_control.py:37) گروه‌بندی حداکثر چهار span، حرکت چپ‌به‌راست، اختلاف top حداکثر ۸ و gap حداکثر ۲۰ پیکسل دارد. locator دقیق در [text_targets.py](/mnt/ai_projects/KYRIN/src/kyrin/vision/text_targets.py:18) RTL و overlap محدود را می‌فهمد.

**بازتولید:** دو span «تنظیمات صدا» به ترتیب راست‌به‌چپ، در `unique_visible_target` یک هدف ساختند؛ inventory فقط «تنظیمات» و «صدا» را تولید کرد. مدل، عبارت کاملی را که locator می‌یابد در catalog نمی‌بیند.

**[CONFIRMED]** inventory می‌تواند چند زبان را با هم بخواند، درحالی‌که هدف ASCII هنگام اجرا با `eng` خوانده می‌شود؛ [chat_verifier.py](/mnt/ai_projects/KYRIN/src/kyrin/app/qt/chat_verifier.py:251). حداقل confidence هر کلمه ۰٫۶۵ است؛ score ناموجود، از جمله PaddleOCR-VL، اجازهٔ کلیک نمی‌دهد. [paddle.py](/mnt/ai_projects/KYRIN/src/kyrin/vision/ocr/backends/paddle.py:135).

**[LIKELY]** یک threshold مشترک بین engine، زبان، word و line کالیبره نیست. گزارش تاریخی افت `Apply` از ۰٫۷۲ در eng به ۰٫۳۷ در eng+fas شاهد قبلی است، نه آزمایش تکرارشدهٔ این بررسی؛ [PROJECT_CONTEXT.md](/mnt/ai_projects/KYRIN/PROJECT_CONTEXT.md:116).

**اصلاح پیشنهادی:** normalizer/phrase assembler مشترک RTL/LTR و backend-independent، زبان هدفمند و threshold کالیبره با نمونه‌های مثبت/منفی. confidence ناموجود را یک فرض نکنید؛ پایین‌آوردن سراسری threshold نیز مناسب نیست. segmentation و کیفیت ورودی را طبق [راهنمای رسمی Tesseract](https://tesseract-ocr.github.io/tessdoc/ImproveQuality.html) ارزیابی کنید؛ نوشتن «۳۰۰ DPI» جزئیات تصویری تازه تولید نمی‌کند.

### F13 — Medium — مبدل geometry اصلاح شده، ولی صحت metadata تولیدکننده هنوز نیازمند اثبات است

**[CONFIRMED]** مبدل فعلی scaleهای `1/1.25/1.5/2`، مختصات منفی، padding/crop/resize و خروج از viewport را در آزمون مستقل پشتیبانی می‌کند؛ [capture_geometry.py](/mnt/ai_projects/KYRIN/src/kyrin/vision/capture_geometry.py:97)، [test_capture_geometry.py](/mnt/ai_projects/KYRIN/tests/vision/test_capture_geometry.py:8). نسبت‌دادن محدودیت قدیمیِ «scale دوبرابر همیشه رد می‌شود» به این قرارداد جدید غلط است.

**[CONFIRMED]** extension scale مانیتور را می‌گیرد و اختلاف ابعاد PNG با اندازهٔ scaled را به padding متقارن تبدیل می‌کند، با سقف ۲۵۶ پیکسل؛ [extension.js](/mnt/ai_projects/KYRIN/integrations/gnome-shell/window-capture-prototype@kyrin.local/extension.js:351). generic helper هنوز مسیر legacyِ تشخیص سایه از اختلاف ابعاد دارد؛ [desktop_control_helper.py](/mnt/ai_projects/KYRIN/src/kyrin/actions/platforms/desktop_control_helper.py:194).

**[SPECULATION]** capture دارای سایهٔ نامتقارن، پنجرهٔ spanning، scale متفاوتِ buffer برنامهٔ XWayland و انتقال میان mixed-DPI ممکن است با metadata فرض‌شده یکسان نباشد. خرابی هیچ‌یک روی این ماشین اثبات نشده است. **روش تأیید:** markerهای معلوم در چهار گوشه و مرکز، مقایسهٔ screenshot pixel با مختصات منطقی در scaleهای مختلف، native Wayland و XWayland، دو مانیتور و پنجرهٔ جابه‌جاشده.

**اصلاح پیشنهادی:** تست producer تا actuator، ثبت provenance scale/padding و handshake نسخه؛ legacy فقط مسیر سازگاریِ صریح باشد. واحدهای `OCR pixel / image pixel / desktop logical` جدا بمانند. از دوبار اعمال crop/scale جلوگیری شود؛ Qt اکنون box را به مختصات تصویر اصلی بازمی‌گرداند و helper با `image_pixels=True` آن را مصرف می‌کند.

### F14 — Medium — token جدید فقط بخشی از مسیر هدف را پوشش می‌دهد

**[CONFIRMED]** intent کنترل از مرحلهٔ فهم فرمان، `control_window_app` و anchor نگه می‌دارد ولی window token/capture generation اولیه را حفظ نمی‌کند؛ [model_interpreter.py](/mnt/ai_projects/KYRIN/src/kyrin/commands/model_interpreter.py:463). executor پس از inference، identity فعلی و OCR تازه می‌گیرد. در مسیر `accessible_only`، guardهای CaptureGeometry اعمال نمی‌شوند؛ [desktop_control_helper.py](/mnt/ai_projects/KYRIN/src/kyrin/actions/platforms/desktop_control_helper.py:174).

**[LIKELY]** سوییچ به پنجرهٔ دیگر همان برنامه با label و anchor مشابه در فاصلهٔ تشخیص تا اجرا، ممکن است به هدف جدید منتقل شود. geometry جدید از پنجرهٔ تازه تا لحظهٔ کلیک محافظت می‌کند؛ الزاماً ثابت نمی‌کند همان پنجرهٔ منظور کاربر در آغاز فرمان است.

**اصلاح پیشنهادی:** window token، generation مشاهده و deadline در evidence اولیه تا intent/request حفظ شوند؛ accessibility نیز window-specific باشد. تغییر پنجره، بازبینی آگاهانهٔ درخواست را لازم کند. **معیار پذیرش:** دو پنجرهٔ هم‌برنامه با هندسهٔ یکسان و label یکسان، بدون تصمیم تازه جای یکدیگر را نگیرند.

### F15 — Medium — جزئیات خطاهای جدید در مرز helper از بین می‌روند

**[CONFIRMED] محل:** helper علت‌هایی مانند `TARGET_CHANGED:content/window_token/stale_capture/stale_or_window` می‌فرستد، اما parser فقط frame/pointer و الگوی image_scale را نگه می‌دارد؛ بقیه `unknown` می‌شوند. [desktop_control.py](/mnt/ai_projects/KYRIN/src/kyrin/actions/platforms/desktop_control.py:211)، [desktop_control_helper.py](/mnt/ai_projects/KYRIN/src/kyrin/actions/platforms/desktop_control_helper.py:174).

**اصلاح پیشنهادی:** پاسخ JSON نسخه‌دار با error enum، stage، retryability و dispatch state؛ log بدون متن شخصی. این اصلاح کوچک برای تشخیص F01، timeout و geometry ارزش فوری دارد. **معیار پذیرش:** خطای content به OCR miss یا generic target changed تقلیل نیابد.

### F16 — Medium — شنیدن هم‌زمان با TTS، وقفهٔ گفتاری کامل نیست

**[CONFIRMED]** در نبود AEC، `PlaybackGuardInput` هنگام `speaker.is_active` ورودی میکروفون را سکوت می‌کند؛ [playback_guard.py](/mnt/ai_projects/KYRIN/src/kyrin/audio/playback_guard.py:22). active از enqueue روشن می‌شود، پس انتظار صف و synthesis نیز می‌تواند شنیدن را بپوشاند؛ tail پیش‌فرض ۳۵۰ms است. [speech.py](/mnt/ai_projects/KYRIN/src/kyrin/responses/speech.py:146).

**[CONFIRMED]** AEC در composition فقط با میکروفون پیش‌فرض تلاش می‌شود؛ انتخاب device مشخص این مسیر را کنار می‌گذارد؛ [ubuntu.py](/mnt/ai_projects/KYRIN/src/kyrin/app/platforms/ubuntu.py:528). رویداد عمومی `SpeechTransition.STARTED -> speaker.interrupt()` در مسیر live متصل نیست. interrupt مدل TTS می‌تواند playback را متوقف و generation را باطل کند، اما هر synthesis درون‌پردازه را فوراً قطع نمی‌کند؛ [tts/runtime.py](/mnt/ai_projects/KYRIN/src/kyrin/tts/runtime.py:401).

**اصلاح پیشنهادی:** AEC برای ورودی انتخاب‌شده، VAD با pre-roll و قطع فوری playback؛ مجوز عمل همچنان از final بگذرد. اگر AEC فراهم نیست، half-duplex صریح و دکمهٔ توقف فوری قابل اتکا عرضه شود. **معیار پذیرش:** کاربر وسط پاسخ بتواند آن را قطع کند، ابتدای گفتارش گم نشود و صدای خود عامل به فرمان تبدیل نشود.

### F17 — Medium — تاریخچهٔ متن پیش‌فرض است و آرشیو سقف نگهداری مستقل ندارد

**[CONFIRMED]** history در هر session ساخته و متن‌های نهایی فعال تا ۲۰۰۰ کاراکتر ثبت می‌شوند؛ تنظیم روشن/خاموش‌کردن persistence در `AppSettings` دیده نمی‌شود. [ubuntu.py](/mnt/ai_projects/KYRIN/src/kyrin/app/platforms/ubuntu.py:495)، [command_runtime.py](/mnt/ai_projects/KYRIN/src/kyrin/runtime/command_runtime.py:332)، [settings.py](/mnt/ai_projects/KYRIN/src/kyrin/app/settings.py:148).

**[CONFIRMED]** سقف ۲۰۰۰ turn فقط active را حذف می‌کند؛ archive می‌تواند رشد کند و `clear()` فقط `archived=0` را پاک می‌کند. [history.py](/mnt/ai_projects/KYRIN/src/kyrin/memory/history.py:103)، [history.py](/mnt/ai_projects/KYRIN/src/kyrin/memory/history.py:200). UI پاک‌سازی همین clear را صدا می‌زند؛ [window.py](/mnt/ai_projects/KYRIN/src/kyrin/app/qt/window.py:606).

**اصلاح پیشنهادی:** کنترل persistence، retention زمانی/حجمی active و archive، و تفاوت روشن «خارج‌کردن از context / حذف فعال / حذف همه»؛ provenance میکروفون/فایل و حذف دادهٔ حساس. نکات مثبت `0600`، SQL پارامتری، lock و recent محدود حفظ شوند. پایگاه دادهٔ شخصی خوانده نشد.

### F18 — Medium — سنجهٔ latency برای plan و stream کامل نیست

**[CONFIRMED] محل:** [latency.py](/mnt/ai_projects/KYRIN/src/kyrin/runtime/latency.py:31). کلید فقط `segment_id` است و اولین feedback آن را pop می‌کند؛ `stream_id/step_index` تطبیق داده نمی‌شوند. timestampها زمان دریافت event هستند، نه timestamp خود صوت.

**[LIKELY]** نتیجهٔ دیررس stream قبلی می‌تواند به segment هم‌شمارهٔ جدید نسبت داده شود؛ plan چندمرحله‌ای نیز زمان اولین نتیجه را به‌جای پایان کل کار ثبت می‌کند. **اصلاح پیشنهادی:** `session_id + ActionKey`، timestamp capture، پایان گفتار، final، صف، inference، dispatch، postcondition و اولین صدای TTS جدا؛ p50/p95 و cold/warm به تفکیک مسیر. **معیار پذیرش:** streamهای دارای segment یکسان و planهای چندمرحله‌ای attribution درست داشته باشند.

### F19 — Medium — بودجهٔ مشترک GPU/RAM و token وجود ندارد

**[CONFIRMED]** Ollama مدل را پنج دقیقه نگه می‌دارد، TTS دو مدل را warm نگه می‌دارد و STT جدا مدیریت می‌شود؛ [ollama_engine.py](/mnt/ai_projects/KYRIN/src/kyrin/commands/ollama_engine.py:304)، [tts/runtime.py](/mnt/ai_projects/KYRIN/src/kyrin/tts/runtime.py:278). مدل فرمان `num_ctx=4096` و `num_predict=768` دارد و catalog برنامه، تا ۱۰۰ کنترل و history وارد prompt می‌شوند.

**[LIKELY]** هم‌زمانی مدل‌ها روی GPU محدود می‌تواند OOM، offload یا نوسان latency بسازد؛ OOM جاری اثبات نشده است. prompt بلند چندزبانه نیز ممکن است از context مؤثر بگذرد؛ شمار گزینه، جایگزین بودجهٔ token نیست.

**اصلاح پیشنهادی:** سیاست مرکزی سبک برای residency، سقف peak memory و اولویت STT؛ TTS سبک روی CPU و VLM فقط هنگام نیاز. prompt بر اساس token budget و relevance بسته شود؛ شواهد operation/permission با truncation حذف نشوند. محدودیت حافظهٔ CPU Qwen موجود است، ولی مدیر منابع کل برنامه نیست؛ [memory_budget.py](/mnt/ai_projects/KYRIN/src/kyrin/tts/memory_budget.py:11).

### F20 — Medium — کشف قابلیت و نسخهٔ backend با نصب موفق یکسان نیست

**[CONFIRMED]** metadata افزونه‌ها به GNOME 50 محدود است؛ [metadata.json](/mnt/ai_projects/KYRIN/integrations/gnome-shell/active-app@kyrin.local/metadata.json:5). observer/activator/controller در startup براساس availability انتخاب می‌شوند؛ window presence انعطاف بیشتری برای بارشدن دیرهنگام دارد؛ [main.py](/mnt/ai_projects/KYRIN/src/kyrin/app/qt/main.py:366). handshake صریح protocol version وجود ندارد و ScreenAccess سه شکل پاسخ قدیمی/جدید را می‌پذیرد؛ [screen_access.py](/mnt/ai_projects/KYRIN/src/kyrin/app/qt/screen_access.py:154).

**[LIKELY]** extension دیررس یا ماژول قدیمیِ هنوزبارشده می‌تواند session را ناقص یا در مسیر legacy نگه دارد. سند پروژه نیز تفاوت installed و loaded را گزارش کرده است؛ [PROJECT_CONTEXT.md](/mnt/ai_projects/KYRIN/PROJECT_CONTEXT.md:85).

**اصلاح پیشنهادی:** `GetCapabilities/ProtocolVersion`، نسخهٔ واقعاً بارشده، probe بدون input، retry محدود سرویس دیررس و نمایش علت unavailable. manifest نسخه/hash مدل و runtime و CI حداقلی اضافه شود. lockfile و workflow CI در فایل‌های نسخه‌دار یافت نشدند؛ نبود lock به‌تنهایی bug runtime نیست، ولی بازتولید نصب را دشوار می‌کند.

### F21 — Medium — offline بودن worker، sandbox امنیتی نیست

**[CONFIRMED] محل:** [document_worker.py](/mnt/ai_projects/KYRIN/src/kyrin/vision/ocr/backends/document_worker.py:145) مدل محلی را با `trust_remote_code=True` و `local_files_only=True` بار می‌کند. worker با همان user اجرا می‌شود؛ offline دانلود را محدود می‌کند ولی اختیار کد داخل checkpoint را حذف نمی‌کند.

**اصلاح پیشنهادی:** artifactهای تأییدشده با hash/provenance، حداقل دسترسی فایل/شبکه برای worker خواندن سند و امکان حذف runtime آسیب‌دیده. **هیچ مدل مخرب، secret افشاشده یا نفوذی در این بررسی کشف یا اثبات نشده است.** این موضوع پیش‌شرط گسترش plugin/model import است.

### F22 — Low — چند نقطهٔ بزرگ و قراردادهای نیمه‌کامل، نگهداری را دشوار می‌کنند

**[CONFIRMED]** اندازهٔ توابع با AST: `DemoCommandInterpreter.interpret` برابر ۷۴۰ خط، `UbuntuSessionFactory.__call__` برابر ۵۸۱، `CommandCoordinator.observe` برابر ۳۳۱ و `ModelAssistedInterpreter.interpret` برابر ۳۰۱ خط. [demo_interpreter.py](/mnt/ai_projects/KYRIN/src/kyrin/commands/demo_interpreter.py:213)، [ubuntu.py](/mnt/ai_projects/KYRIN/src/kyrin/app/platforms/ubuntu.py:271). formatting check نیز ۷۷ فایل ناسازگار دارد.

**[CONFIRMED]** `ActiveWindowTextReader` هندسه را حمل می‌کند، ولی `image_size/capture_rect/frame_rect` را در خروجی مقداردهی نمی‌کند؛ locator فعلی با image_size ناموجود هدفی نمی‌سازد. مسیر Qt این اطلاعات را جدا می‌گذارد، پس این نقص به معنی خرابی کلیک اصلی نیست. [text_reader.py](/mnt/ai_projects/KYRIN/src/kyrin/vision/text_reader.py:41)، [visible_control.py](/mnt/ai_projects/KYRIN/src/kyrin/actions/visible_control.py:98).

**اصلاح پیشنهادی:** پس از اصلاح رفتار، validator، handler عملیات و lifecycle مشترک استخراج شوند؛ ساخت observation یک مسیر داشته باشد. نام production مناسب‌تر از «Demo» است، ولی تغییر نام اولویت پایین‌تری از صحت دارد. broad except در مرز thread/plugin گاهی موجه است؛ تشخیص علت باید حفظ شود، نه اینکه مکانیکی تمام آن‌ها حذف شوند.

## ۵. چرا OCR کلیک را خراب می‌کند و چه روشی جایگزین شود؟

### تشخیص بر اساس نوع شکست

| عامل | واقعیت/عدم قطعیت فعلی | تصمیم مناسب |
|---|---|---|
| policy پیش از تشخیص | **[CONFIRMED]** F02؛ برای بسیاری از labelها اصلاً OCR اجرا نمی‌شود. | ابتدا error stage را بخوانید؛ مدل OCR عوض نشود. |
| screenshot scaling / DPI | **[CONFIRMED]** converter جدید scale صریح دارد؛ producer هنوز فرض padding دارد. | آزمون زنجیرهٔ واقعی capture تا input؛ DPI metadata از scale فیزیکی جدا باشد. |
| crop و resize | **[CONFIRMED]** Qt تبدیل معکوس دارد؛ F13. | یک بار تبدیل در مرز مشخص؛ bbox در coordinate space اعلام‌شده. |
| multi-monitor | **[CONFIRMED]** مختصات منفی مجاز است. **[SPECULATION]** mixed-DPI/spanning تأیید نشده. | مانیتور چپ/بالا، scale متفاوت و انتقال پنجره جدا آزمایش شوند. |
| X11/Wayland | **[CONFIRMED]** مسیر جاری GNOME/portal و نشست Wayland است. | adapter براساس capability واقعی؛ جایگزینی با xdotool برای native Wayland مناسب نیست. |
| حرکت پنجره | **[CONFIRMED]** token/frame برای OCR جدید کنترل می‌شود. | token از آغاز درخواست و برای AT-SPI هم حفظ شود؛ F14. |
| تغییر تصویر نامرتبط | **[CONFIRMED]** کل PNG مقایسه می‌شود. | metadata و نواحی پویا از اعتبار هدف جدا شوند؛ F01. |
| confidence پایین | **[CONFIRMED]** حداقل ۰٫۶۵ برای هر span؛ score ناموجود رد می‌شود. | calibration و خواندن هدفمند ROI؛ افت یک کلمه در عبارت مهم است. |
| duplicate text | **[CONFIRMED]** locator عمومی فقط match یکتا می‌پذیرد. | رد ابهام درست است؛ role/parent/region/شناسه برای رفع ابهام لازم است. |
| fuzzy/phonetic | **[CONFIRMED]** Telegram از پیشنهاد عنوان OCR و قواعد شباهت استفاده می‌کند؛ عنوان یکتا می‌تواند مستقیماً dispatch شود. [visible_chat_grounding.py](/mnt/ai_projects/KYRIN/src/kyrin/actions/visible_chat_grounding.py:1)، [telegram.py](/mnt/ai_projects/KYRIN/src/kyrin/actions/platforms/telegram.py:242). | یکتا بودن مشاهده، اثبات هویت مخاطب نیست؛ نام/شناسهٔ تأییدشده برای عملیات داده‌ای لازم است. |
| آماده نبودن UI | **[CONFIRMED]** sleep و reread محدود هست، deadline واحد و پس‌شرط عمومی نیست. | انتظار برای state/event مشخص؛ retry محدود با بودجهٔ کل. |
| text در برابر control | **[CONFIRMED]** متن OCR clickable بودن را ثابت نمی‌کند؛ خود docstring inventory این را می‌گوید. | candidate با role/parent/state یا شواهد ساختاری تکمیل شود. |

پشتیبانی Wayland باید حفظ شود؛ ابزارهای X11 را نمی‌توان راه‌حل عمومی این نشست دانست. [توضیح خود xdotool](https://github.com/jordansissel/xdotool)، [قرارداد RemoteDesktop portal](https://flatpak.github.io/xdg-desktop-portal/docs/doc-org.freedesktop.portal.RemoteDesktop.html).

### بهترین راه برای هر حالت

این جدول **پیشنهاد طراحی** است؛ مقایسهٔ سرعت، ساختاری است و benchmark این سخت‌افزار نیست.

| روش | بهترین مورد استفاده | مزیت | محدودیت و جایگاه |
|---|---|---|---|
| API/CLI رسمی برنامه | operation شناخته‌شده با پاسخ ساخت‌یافته، مانند ایجاد tab | بدون خطای pixel و اغلب سریع | معنای API باید همان خواستهٔ کاربر باشد؛ تغییر دادهٔ سرویس لزوماً navigation پنجره نیست. اولویت اول در ابزارهای مشخص. |
| keyboard shortcut | navigation ثابت با focus و وضعیت معلوم | بسیار سبک؛ بی‌نیاز از OCR | shortcut سفارشی، layout، dialog و نسخهٔ برنامه مهم‌اند؛ باید پس‌شرط بررسی شود. |
| AT-SPI semantic action | widget استاندارد دارای name/role/action/state | مستقل‌تر از theme/scale و قابل بررسی | widget سفارشی یا tree ناقص مانع است؛ برای کنترل عمومی قابل دسترس، انتخاب نخست. |
| OCR هدفمند | label قابل خواندن با tree ناکافی | محلی و کم‌هزینه‌تر از VLM | متن، clickable بودن و هویت را ثابت نمی‌کند؛ duplicate، RTL و geometry لازم‌اند. |
| template matching / icon detector | آیکون پایدار در toolbar/ROI مشخص | CPU سبک؛ مناسب عنصر بی‌متن | theme/scale/hover/version متفاوت و false match؛ چند template و نمونهٔ منفی لازم است. |
| VLM متخصص GUI grounding | canvas یا رابط تصویری بدون شواهد کافی | از توصیف بصری candidate تولید می‌کند | latency/VRAM، hallucination مختصات، prompt injection تصویری؛ آخرین fallback با verifier مستقل. |
| hybrid محدود | استفادهٔ روزانه در برنامه‌های متفاوت | ارزان‌ترین روشِ دارای شاهد کافی | قرارداد مشترک، علت شکست روشن و بودجهٔ recovery لازم است؛ همهٔ روش‌ها در هر درخواست اجرا نشوند. |

API دسترس‌پذیری actionهای قابل فراخوانی دارد؛ صرف گرفتن مختصات تنها کاربرد AT-SPI نیست. مقدار true از `do_action` نیز به معنی پذیرفته‌شدن action است؛ state نهایی همچنان باید خوانده شود. [مستندات رسمی](https://gnome.pages.gitlab.gnome.org/at-spi2-core/libatspi/method.Action.do_action.html).

**OpenRGB:** **[CONFIRMED]** سند پروژه از tree فاقد کنترل نام‌دار در آزمایش قبلی خبر می‌دهد؛ این بررسی آن tree را دوباره نخواند. **[SPECULATION]** علت می‌تواند تنظیم accessibility Qt یا widget سفارشی باشد. با inspector فقط‌خواندنی، نقش‌ها/stateها و فعال بودن accessibility همان نسخه بررسی شود. Qt گزینهٔ `QT_LINUX_ACCESSIBILITY_ALWAYS_ON` را مستند کرده است؛ فعال‌کردن آن تضمین پشتیبانی widget سفارشی نیست و در این کار اعمال نشد. [QAccessible](https://doc.qt.io/qt-6/qaccessible.html).

برای template matching، ROI، scale pyramid و margin میان بهترین و دومین candidate لازم است؛ score شباهت احتمال موفقیت عمل نیست. افزودن OpenCV فقط در صورت نیاز اثبات‌شده انجام شود؛ وابستگی جدید در این بررسی اضافه نشده است. [راهنمای OpenCV](https://docs.opencv.org/4.13.0/d4/dc6/tutorial_py_template_matching.html).

برای VLM می‌توان خانوادهٔ کوچک‌تر متخصص GUI مانند GUI-Actor-2B را در benchmark اختصاصی ارزیابی کرد؛ نتایج عمومی آن تضمین دقت فارسی، GNOME یا OpenRGB نیست. **[SPECULATION]** اینکه نسخهٔ quantized روی دستگاه حاضر latency مناسب بدهد، هنوز معلوم نیست. وزن خام ۲B در ۴bit تقریباً ۱GB است، اما encoder تصویر، activation، KV cache و runtime حافظهٔ اضافه می‌خواهند. crop هدفمند و on-demand بر مدل بزرگِ همیشه‌مقیم ترجیح دارد. [پژوهش و مدل‌های نویسندگان GUI-Actor](https://microsoft.github.io/GUI-Actor/). هیچ دانلودی توصیهٔ اجرایی یا انجام نشده است.

### Telegram: shortcut، Bot API و TDLib معادل نیستند

**پیشنهاد:** برای «این chat را در پنجرهٔ Telegram نشان بده»، adapter دسکتاپ و shortcut رسمیِ نسخهٔ مورد استفاده با verification مناسب‌اند؛ نمونهٔ فعلی `Ctrl+0` برای Saved Messages در کد وجود دارد. برای فهرست chatها، هویت قطعی مخاطب یا عملیات ساخت‌یافتهٔ حساب، TDLib می‌تواند adapter دادهٔ جداگانه باشد.

Bot API یک bot را کنترل می‌کند و جای حساب شخصی مالک نیست. TDLib یک client با authorization، storage و updateهای مستقل می‌سازد؛ پنجرهٔ Telegram Desktop را خودکار روی همان صفحه نمی‌برد و تمام تنظیمات محلی Desktop هم API معادل ندارند. هزینهٔ نگهداری نشست، `api_id/api_hash` و دادهٔ حساب باید با نیاز محصول توجیه شود. این‌ها به پروژه افزوده نشده‌اند. [راهنمای رسمی TDLib](https://core.telegram.org/tdlib/getting-started)، [مستندات botهای Telegram](https://core.telegram.org/api/bots).

### خط لولهٔ کلیک پیشنهادی

<div dir="ltr">

```text
Intent + source evidence
    -> validate operation / target / direction / state
    -> observe window token + capabilities + deadline
    -> locate: app API / shortcut / AT-SPI / OCR / icon / VLM
    -> resolve ambiguity; bind requested target to observed evidence
    -> policy / confirmation / permission epoch / cancellation
    -> refresh target after permission dialogs; revalidate before input
    -> execute once
    -> observe semantic postcondition
    -> CONFIRMED | DISPATCHED_UNVERIFIED | FAILED | CANCELLED
                         |
                         +-> bounded, safe recovery
```

</div>

۱. **مشاهده:** token پنجره، capture ID، زمان monotonic، coordinate space و قابلیت‌های قابل استفاده ثبت شوند. action معنایی AT-SPI به screenshot اجباری وابسته نباشد.

۲. **مکان‌یابی:** برای operation شناخته‌شده، ابزار برنامه/shortcut؛ برای کنترل عمومی AT-SPI؛ سپس OCR/icon در ROI و نهایتاً VLM. `unavailable/no_match/ambiguous/stale` جدا باشند.

۳. **اتصال هدف:** هدف گفتار، label مشاهده‌شده، role، parent و دلیل تطابق حفظ شوند. مدل فقط candidate پیشنهاد کند؛ ID معتبر به‌تنهایی رضایت کاربر نیست. اصلاح target نامطمئن به رفع ابهام منجر شود.

۴. **هندسه:** قرارداد جدید حفظ و producer آن آزموده شود. فرمول زیر برای یک ناحیه با scale مشخص است؛ تصویر ترکیبی با scale متفاوت به تبدیل ناحیه‌ای نیاز دارد.

<div dir="ltr">

```text
source_x = crop_origin_x + ocr_x / ocr_resize_x
source_y = crop_origin_y + ocr_y / ocr_resize_y
desktop_x = logical_origin_x + (source_x - padding_left_px) / scale_x
desktop_y = logical_origin_y + (source_y - padding_top_px) / scale_y

Evidence:
request_id, window_token, capture_id, captured_at_monotonic
image_size, logical_rect, viewport, scale, padding, crop, resize
target_bbox, locator_strategy, role, state, deadline, permission_epoch
```

</div>

اگر bbox از قبل به source image تبدیل شده، crop/resize دوباره اعمال نشوند. point باید داخل bbox معتبر و viewport بماند. مختصات global را بدون تطبیق قرارداد به `NotifyPointerMotionAbsolute` ندهید؛ این method به PipeWire stream و فضای منطقی آن وابسته است. [قرارداد portal](https://flatpak.github.io/xdg-desktop-portal/docs/doc-org.freedesktop.portal.RemoteDesktop.html).

۵. **پیش از اجرا:** focus/token/frame، permission epoch، state، cancellation و budget کنترل شوند. dialog مجوز می‌تواند هدف را قدیمی کند؛ بعد از بسته‌شدن آن دوباره locate شود.

۶. **اجرا و تأیید:** action معنایی در صورت پشتیبانی؛ در غیر این صورت input از broker مشترک. سپس checked state، صفحهٔ مقصد یا هویت chat بررسی شود. image diff شاهد کمکی است؛ blinking cursor می‌تواند diff بسازد و Apply موفق ممکن است تغییر بصری کمی داشته باشد.

۷. **retry:** اگر ثابت است input ارسال نشده، locate/strategy بعدی مجاز است. اگر dispatch شده ولی نتیجه نامعلوم است، ابتدا state خوانده شود؛ تکرار toggle، Send، Delete یا Buy امن نیست. سقف تلاش و deadline کل مشخص باشد؛ سه strategy لزوماً به معنی سه click نیست.

**قرارداد نتیجهٔ پیشنهادی:** `request_id, strategy, target_evidence, dispatch_state, postcondition_state, failure_reason, timings`. تابع بیرونی `click_element(...) -> bool` می‌تواند wrapper باشد؛ داخل سیستم bool به‌تنهایی برای recovery کافی نیست.

## ۶. خط لولهٔ صوت، تأخیر و منابع محدود

### latency هر مرحله: مقدار تنظیمی با اندازه‌گیری اشتباه نشود

| مرحله | وضعیت فعلی با شواهد | اقدام پیشنهادی |
|---|---|---|
| wake word | **[CONFIRMED]** standby پس از STT متن را فیلتر می‌کند؛ detector صوتی مستقل در این مسیر نیست. [voice_control.py](/mnt/ai_projects/KYRIN/src/kyrin/runtime/voice_control.py:1)، [command_runtime.py](/mnt/ai_projects/KYRIN/src/kyrin/runtime/command_runtime.py:193). | اگر مصرف دائم STT مهم است، wake detector سبک CPU به‌صورت اختیاری؛ false wake/miss فارسی سنجیده شود. |
| capture/VAD | **[CONFIRMED]** Silero با ۱۶kHz و قاب ۵۱۲ نمونه، حدود ۳۲ms؛ start confirmation پیش‌فرض ۶۴ms. [silero_vad.py](/mnt/ai_projects/KYRIN/src/kyrin/audio/activity/silero_vad.py:1)، [live_speech_pipeline.py](/mnt/ai_projects/KYRIN/src/kyrin/audio/live_speech_pipeline.py:53). | CPU؛ timestamp صوت تا VAD حفظ شود. این اعداد بودجهٔ الگوریتم‌اند، benchmark کل نیستند. |
| endpoint | **[CONFIRMED]** pause عادی ۳۸۴ms و Omnilingual برابر ۸۰۰ms. [ubuntu.py](/mnt/ai_projects/KYRIN/src/kyrin/app/platforms/ubuntu.py:592). | کاهش فقط همراه سنجش split و جملهٔ ناقص، به‌ویژه فارسی. |
| STT | **[CONFIRMED]** Whisper pre-roll حدود ۰٫۵s، partial نخست ۱٫۵s، فاصلهٔ ۲٫۵s، preview هشت‌ثانیه و turn حداکثر ۳۰s دارد. [whisper.py](/mnt/ai_projects/KYRIN/src/kyrin/stt/backends/whisper.py:32). | preview و final inference جدا هزینه دارند؛ فایل partial ندارد، live هنوز دارد. |
| transport STT | **[CONFIRMED]** inference server timeout هشت‌ثانیه و startup تا ۳۰ ثانیه. [whisper_server.py](/mnt/ai_projects/KYRIN/src/kyrin/stt/backends/whisper_server.py:121). | انتخاب مدل با real-time factor و p95؛ افزایش timeout به‌تنهایی سرعت را بهبود نمی‌دهد. |
| understanding | **[CONFIRMED]** قواعد fast path؛ fallback همگام ۶۰/۱۲۰s و گاهی دوبار inference؛ F07. | فقط final؛ worker مستقل، prompt محدود و لغو واقعی. |
| action | **[CONFIRMED]** OCR تکراری، راه‌اندازی process/portal و verification تصویر دارد؛ F01/F08. | semantic action، reuse کنترل‌شدهٔ session و snapshot تازه. مختصات قدیمی cache نشود. |
| TTS | **[CONFIRMED]** صف مستقل، synthesis مدل و سپس playback؛ F16. | پاسخ کوتاه، مدل سبک CPU، زمان تا اولین صوت و امکان interrupt اندازه‌گیری شود. |

در این بررسی latency واقعی مدل و میکروفون اندازه‌گیری نشد. اعداد تاریخی مانند ۱۲٫۳ ثانیه برای بازشدن chat، گزارش مالک دربارهٔ نسخهٔ قبلی‌اند؛ baseline نسخهٔ فعلی نیستند. [PROJECT_CONTEXT.md](/mnt/ai_projects/KYRIN/PROJECT_CONTEXT.md:202).

<div dir="ltr">

```text
last spoken sample
  -> VAD endpoint wait
  -> final STT inference / transport
  -> interpretation queue / model
  -> action queue / locate / policy / dispatch
  -> postcondition

first audible answer
  = response-ready + TTS queue + synthesis-to-first-audio
```

</div>

**پیشنهاد تخصیص منابع:**

| جزء | پیش‌فرض پیشنهادی | شرط تغییر |
|---|---|---|
| capture، resample، VAD، wake detector | CPU | معمولاً GPU لازم ندارند؛ مصرف CPU اندازه‌گیری شود. |
| STT تعاملی | GPU در صورت runtime سالم و برتری p95؛ در غیر این صورت مدل سبک CPU | دقت فارسی/انگلیسی و نام برنامه‌ها، real-time factor و VRAM واقعی. |
| command understanding | قواعد برای فرمان رایج؛ مدل کوچک محلی با context محدود | CPU اگر latency قابل قبول است؛ در غیر این صورت سهم محدود GPU یا offload مدیریت‌شده. |
| OCR UI | Tesseract/روش سبک روی ROI و CPU؛ AT-SPI قبل از آن | مدل سنگین فقط برای شواهدی که روش سبک نمی‌دهد. |
| TTS | Piper/VITS/Kokoro سبک روی CPU، مطابق زبان و کیفیت مورد قبول | GPU وقتی هزینهٔ رقابت با STT اندازه‌گیری و توجیه شود. |
| VLM و وب‌کم آینده | on-demand، نرخ پایین و process قابل توقف | بعد از baseline و budget مشترک؛ روی هر frame همهٔ مدل‌ها اجرا نشوند. |

**local در برابر cloud:** پیشنهاد فعلی local است: هزینهٔ تکرارشونده و انتقال صوت/صفحه ندارد و وابستگی شبکه کمتر است. cloud می‌تواند accuracy یا زبان را بهبود دهد، ولی latency شبکه، قطعی، هزینه و افشای محتوای صفحه/صوت اضافه می‌کند؛ fallback خودکارِ بی‌اطلاع مناسب نیست. هیچ provider خاصی بدون benchmark و تصمیم محصول توصیه یا اضافه نشده است.

**وقفهٔ کاربر:** AEC باید echo خود دستگاه را از گفتار تازه جدا کند؛ سپس VAD پاسخ را قطع کند و pre-roll حفظ شود. VAD فقط نشانهٔ شروع گفتار است، نه consent یا هویت گوینده. synthesis، playback و action cancellation سه lifecycle متفاوت‌اند و باید جدا کنترل شوند.

## ۷. امنیت، مجوز و رفتار در شکست

| پرسش | پاسخ مبتنی بر کد و اقدام لازم |
|---|---|
| allowlist برنامه هست؟ | **[CONFIRMED]** بله؛ policy خالی همه را رد می‌کند، action execution پیش‌فرض خاموش است و IDهای desktop صریح‌اند. [gate.py](/mnt/ai_projects/KYRIN/src/kyrin/actions/gate.py:25)، [settings.py](/mnt/ai_projects/KYRIN/src/kyrin/app/settings.py:167). |
| shell دلخواه یا sudo از گفتار هست؟ | **[CONFIRMED]** در مسیر فعلی پیدا نشد؛ subprocessها عمدتاً argv ثابت یا ID/متن محدود دارند. ادعای command injection عمومی از STT با شواهد فعلی صحیح نیست. |
| اگر بعداً shell اضافه شود؟ | **پیشنهاد:** ابزارهای typed مانند list/create/read با ریشهٔ فایل مجاز؛ preview اثر و تأیید عملیات مخرب. raw transcript هرگز shell command نباشد؛ argv و `shell=False` به‌تنهایی جلوی خطر خود executable را نمی‌گیرند. |
| بستن/حذف/ارسال/پرداخت؟ | **[CONFIRMED]** generic sensitive/unknown رد می‌شود؛ flow تأیید عمومی ندارد؛ close اختصاصی برنامه‌ها یکسان نیست؛ F02/F11. |
| خاموشی سیستم؟ | **[CONFIRMED]** مجوز جدا، دو مرحله، phrase مشخص و expiry؛ درخواست عادی GNOME، بدون force. [flow.py](/mnt/ai_projects/KYRIN/src/kyrin/system_power/flow.py:291)، [gnome.py](/mnt/ai_projects/KYRIN/src/kyrin/system_power/gnome.py:43). پذیرفته‌شدن درخواست با خاموشی واقعی متفاوت گزارش می‌شود. |
| prompt injection از صفحه/مدل؟ | **[CONFIRMED]** مدل اجازهٔ مستقیم اجرای OS ندارد و validator مستقل هست؛ R01 نیز اصلاح شده. **[LIKELY]** گسترش VLM/حافظه بدون حفظ این مرز خطر دارد؛ OCR و متن صفحه دادهٔ نامطمئن‌اند، نه دستور سیستم یا consent. |
| microphone و webcam؟ | **[CONFIRMED]** میکروفون هنگام session باز می‌شود؛ standby همچنان STT دارد؛ OFF با توقف کامل متفاوت است. webcam در مسیر اجرایی نیست. **پیشنهاد:** نشانگر روشنِ دریافت، قطع واقعی device و مجوز مستقل دوربین در آینده. |
| احراز هویت گوینده؟ | **[CONFIRMED]** speaker verification عملی در مسیر فرمان نیست. **[LIKELY]** صدای فرد دیگر/پخش صوت می‌تواند مانند گفتار کاربر پردازش شود؛ wake name یا STT confidence احراز هویت نیست. برای اثر حساس، تأیید قابل مشاهده و هویت نشست OS حفظ شود. |
| فایل صوتی واردشده؟ | **[CONFIRMED]** همان gate و مجوزهای جاری را مستقیم مصرف می‌کند؛ منبع فایل در تصمیم اعتماد جدا نمی‌شود. [audio_file_import.py](/mnt/ai_projects/KYRIN/src/kyrin/app/qt/audio_file_import.py:112)، [ubuntu.py](/mnt/ai_projects/KYRIN/src/kyrin/app/platforms/ubuntu.py:264). **پیشنهاد:** provenance و حالت پیش‌نمایش برای فایل نامطمئن؛ تغییر رفتار محصول نیازمند تصمیم آگاهانه است. |
| secrets و logging؟ | **[CONFIRMED]** tokenها permission محدود و atomic replace دارند؛ history متن plaintext محلی است؛ screenshot مسیر عادی در حافظه است. [permission_token.py](/mnt/ai_projects/KYRIN/src/kyrin/app/permission_token.py:82)، [screen_text_reader.py](/mnt/ai_projects/KYRIN/src/kyrin/app/qt/screen_text_reader.py:222). **پیشنهاد:** log فقط stage/error/timing؛ ذخیرهٔ screenshot/text برای debug اختیاری، با redact و retention. بررسی فایل‌های secret محلی انجام نشد. |
| password field؟ | **[CONFIRMED]** API عمومی تایپ دلخواه وجود ندارد، اما تایپ search در Telegram و جهش focus F10 نیازمند field binding است؛ تضمین عمومیِ تشخیص/عدم ورود به فیلد رمز در actuator دیده نشد. |
| شکست نیمه‌راه؟ | **[CONFIRMED]** UNKNOWN و FAILED جدا هستند و exception boundary اغلب UNKNOWN می‌دهد؛ این درست است. cancellation/timeout سراسری و journal مرحله‌ها کامل نیست. **پیشنهاد:** پس از dispatch نامعلوم، مشاهده قبل از retry؛ compensation فقط برای عملی که بازگشت‌پذیری‌اش اثبات شده است. |

دسترسی AT-SPI یا subprocess هم‌user، sandbox کامل در برابر بدافزار همان user نیست. token و allowlist برای جلوگیری از اشتباه عامل مفیدند؛ نباید به‌عنوان جداسازی کامل امنیت سیستم توصیف شوند.

## ۸. معماری مناسب و گزینه‌های جایگزین

### ارزیابی معماری فعلی

**[CONFIRMED]** جدایی acquisition/STT/understanding/action/response و Protocolها مناسب است. acquisition میکروفون داخل constructor مدل تصمیم‌گیر پنهان نشده و dependency injection در بخش‌های مهم وجود دارد. مشکل اصلی، تعداد لایه‌ها نیست؛ یکسان نبودن قرارداد request/result و مالکیت lifecycle در مرزهاست. [audio_input.py](/mnt/ai_projects/KYRIN/src/kyrin/audio/audio_input.py:1)، [microphone/input.py](/mnt/ai_projects/KYRIN/src/kyrin/audio/microphone/input.py:1)، [ubuntu.py](/mnt/ai_projects/KYRIN/src/kyrin/app/platforms/ubuntu.py:221).

| گزینه | نسبت به معماری فعلی | مزیت | هزینه/ضعف | مهاجرت |
|---|---|---|---|---|
| A. هماهنگ‌کنندهٔ رویدادمحور با state machine و DesktopInputBroker | حفظ بیشتر قراردادها و adapterها؛ inference و ورودی صاحب lifecycle مشخص می‌شوند | لغو/ترتیب قابل اثبات، تست deterministic، latency مسیرهای مستقل | event schema، ownership و timeout باید دقیق طراحی شوند | متوسط؛ مرحله‌ای و پیشنهاد اصلی |
| B. هستهٔ عمدتاً async با TaskGroup و subprocessهای async | بازآرایی runtime و transportها، اتصال به Qt | deadline و structured concurrency یکدست‌تر | کتابخانهٔ native مسدودکننده با async خودکار لغو نمی‌شود؛ اتصال دو event loop و هزینهٔ بازنویسی | زیاد؛ فعلاً سود آن کمتر از A است |
| C. برنامه‌ریز محدود با registry ابزار و چرخهٔ observe-plan-act-verify | مدل plan typed پیشنهاد می‌کند؛ ابزار contract و policy دارد | گسترش حافظه/بینایی و ابزارها، کنترل وابستگی، recovery روشن | replan می‌تواند تکرار اثر و هزینهٔ مدل بسازد؛ نیازمند budget و journal | متوسط تا زیاد؛ پس از A و به‌صورت محدود |

این‌ها **پیشنهاد** هستند؛ A و C می‌توانند ترکیب شوند. رویدادمحوربودن الزاماً به معنی framework بزرگ، microservice یا تبدیل همه‌چیز به async نیست. threadهای فعلی capture/native model می‌توانند حفظ شوند.

### طراحی پیشنهادی A و سپس بخش محدود C

<div dir="ltr">

```text
Audio worker -> transcript events -> Interpretation worker -> validated intent
                                                   |
                                           Session orchestrator
                                           /        |         \
                                  Dialogue FSM   Tool registry  Memory
                                                   |
                                       Policy + permission epoch
                                                   |
                                    DesktopInputBroker (single owner)
                                                   |
                              app / AT-SPI / OCR / portal adapters
                                                   |
                                    Postcondition observer + journal
                                                   |
                                        final response / TTS
```

</div>

**پیشنهاد قرارداد ابزار:** schema ورودی، capability، risk، precondition، postcondition، deadline، cancellation و idempotency مشخص باشد. مدل plan پیشنهاد کند؛ orchestrator اجرا و policy را کنترل کند. هر اجرا request ID مستقل و eventهای `queued/started/dispatched/verified/failed/cancelled` داشته باشد.

**پیشنهاد حافظه:** متن مکالمه از fact مشاهده‌شده، ترجیح کاربر و نتیجهٔ عمل جدا باشد. «گفتم Settings باز شود» factِ «Settings باز است» نیست. state دسکتاپ کوتاه‌عمر با TTL؛ ترجیح پایدار با provenance و امکان ویرایش/حذف؛ دادهٔ شخصی فقط در retrieval محدود و با source روشن. برای شروع SQLite موجود کافی است؛ vector database پیش‌نیاز نیست.

**پیشنهاد وب‌کم آینده:** منبع مستقل تصویر، sampling محدود و eventهایی مثل `gesture_candidate`؛ تصمیم و مجوز در orchestrator باقی بمانند. face/speaker recognition به‌تنهایی مجوز عمل حساس نباشد. افزودن vision داخل MicrophoneInput یا OCR داخل planner وابستگی نامناسب ایجاد می‌کند.

## ۹. برنامهٔ اقدام اولویت‌بندی‌شده

### Critical

**[CONFIRMED]** مسیر اجرای arbitrary shell، دورزدن اثبات‌شدهٔ مجوز برای عملیات مخرب، یا افشای secret در این بازبینی کشف نشد؛ بنابراین یافته‌ای با قطعیت و شدت Critical اعلام نمی‌شود. F05 و F11 باید پیش از گسترش عملیات مخرب رفع شوند؛ افزایش دامنهٔ عمل، شدت اثرشان را بیشتر می‌کند.

### High

| شناسه | محل اصلی | چرا مهم است و اصلاح |
|---|---|---|
| F01 | [capture extension:425](/mnt/ai_projects/KYRIN/integrations/gnome-shell/window-capture-prototype@kyrin.local/extension.js:425) | false stale حتی با تصویر ثابت؛ decoded ROI/هدف معنایی، نه کل PNG. |
| F02 | [desktop_control.py:44](/mnt/ai_projects/KYRIN/src/kyrin/actions/platforms/desktop_control.py:44) | بسیاری از کلیک‌ها اصلاً به OCR نمی‌رسند؛ risk/confirmation واقعی و capability روشن. |
| F03 | [desktop_control_helper.py:288](/mnt/ai_projects/KYRIN/src/kyrin/actions/platforms/desktop_control_helper.py:288)، [plan_runner.py:78](/mnt/ai_projects/KYRIN/src/kyrin/actions/plan_runner.py:78) | نبود پس‌شرط و ادامهٔ وابستگی پس از dispatch؛ وضعیت نتیجه و verifier هر ابزار. |
| F04 | [desktop_control_inventory.py:61](/mnt/ai_projects/KYRIN/src/kyrin/actions/platforms/desktop_control_inventory.py:61) | وابستگی بی‌مورد accessibility به OCR؛ semantic action و window/state صحیح. |
| F05/F06 | [queued_dispatch.py:187](/mnt/ai_projects/KYRIN/src/kyrin/actions/queued_dispatch.py:187)، [telegram_selection.py:384](/mnt/ai_projects/KYRIN/src/kyrin/actions/telegram_selection.py:384) | عمل پس از توقف و ورودی هم‌پوشان؛ broker واحد، cancellation و epoch. |
| F07 | [model_interpreter.py:320](/mnt/ai_projects/KYRIN/src/kyrin/commands/model_interpreter.py:320) | inference روی partial و انسداد stop/final؛ worker فقط برای final. |
| F08 | [chat_verifier.py:192](/mnt/ai_projects/KYRIN/src/kyrin/app/qt/chat_verifier.py:192) | timeout ظاهری و OCR باقی‌مانده؛ deadline و cancellation سراسری. |
| F09 | [model_interpreter.py:416](/mnt/ai_projects/KYRIN/src/kyrin/commands/model_interpreter.py:416) | جهت معکوس scroll؛ استخراج و تطبیق مستقل پارامترها. |
| F10 | [telegram_portal_helper.py:281](/mnt/ai_projects/KYRIN/src/kyrin/actions/platforms/telegram_portal_helper.py:281) | layout ثابت و تایپ پس از تغییر focus؛ locator زنده و field binding. |
| F11 | [demo_interpreter.py:1081](/mnt/ai_projects/KYRIN/src/kyrin/commands/demo_interpreter.py:1081) | وضعیت نامعلوم کار ذخیره‌نشده؛ تأیید close وابسته به پنجره/پیامد. |

### Medium

| شناسه | محل اصلی | اصلاح |
|---|---|---|
| F12 | [visible_control.py:37](/mnt/ai_projects/KYRIN/src/kyrin/actions/visible_control.py:37) | یک phrase assembler برای RTL/LTR، confidence کالیبره و زبان هدفمند. |
| F13/F14 | [capture_geometry.py:19](/mnt/ai_projects/KYRIN/src/kyrin/vision/capture_geometry.py:19)، [model_interpreter.py:463](/mnt/ai_projects/KYRIN/src/kyrin/commands/model_interpreter.py:463) | آزمون geometry تولیدکننده و token از intent تا تمام actuatorها. |
| F15 | [desktop_control.py:211](/mnt/ai_projects/KYRIN/src/kyrin/actions/platforms/desktop_control.py:211) | protocol ساخت‌یافتهٔ خطا؛ حفظ علت content/stale/token. |
| F16 | [ubuntu.py:528](/mnt/ai_projects/KYRIN/src/kyrin/app/platforms/ubuntu.py:528) | AEC ورودی انتخاب‌شده، interrupt playback و تست echo/barge-in. |
| F17 | [history.py:103](/mnt/ai_projects/KYRIN/src/kyrin/memory/history.py:103) | retention فعال/آرشیو، کنترل ذخیره و حذف واقعی. |
| F18 | [latency.py:31](/mnt/ai_projects/KYRIN/src/kyrin/runtime/latency.py:31) | هویت کامل عمل و stage timings. |
| F19 | [ollama_engine.py:352](/mnt/ai_projects/KYRIN/src/kyrin/commands/ollama_engine.py:352) | budget مشترک RAM/VRAM/token و residency. |
| F20 | [main.py:366](/mnt/ai_projects/KYRIN/src/kyrin/app/qt/main.py:366) | نسخهٔ capability، probe/recovery و نصب بازتولیدپذیر/CI. |
| F21 | [document_worker.py:145](/mnt/ai_projects/KYRIN/src/kyrin/vision/ocr/backends/document_worker.py:145) | provenance/hash و محدودکردن worker مدل محلی. |

### Low

F22: یکدست‌کردن سازندهٔ observation، شکستن تدریجی توابع بزرگ، نام‌گذاری و قالب‌بندی؛ پس از تثبیت رفتار و بدون refactor وسیع هم‌زمان با اصلاح کلیک.

## ۱۰. نقشهٔ مهاجرت مرحله‌به‌مرحله

این مراحل **پیشنهاد اجرایی آینده** هستند؛ در این بررسی پیاده نشده‌اند. ترتیب با اولویت «قابلیت اطمینان، سپس سرعت، سپس امنیت» تنظیم شده، با حفظ مرزهای ضروری ایمنی.

۱. **baseline و خطای قابل مشاهده.** F15 و stage timings را اضافه کنید؛ نسخهٔ loaded extension، strategy، cold/warm و علت رد را ثبت کنید. معیار پایان: شکست policy، OCR، geometry، content و postcondition از یکدیگر قابل تشخیص باشند؛ هیچ متن شخصی در log پیش‌فرض نباشد.

۲. **رفع F01 و تعیین پوشش واقعی F02.** مقایسهٔ metadata/تصویر را اصلاح، unknown risk را با confirmation محدود مدیریت و قابلیت‌های واقعاً فعال را نمایش دهید. معیار پایان: metadata متفاوت target ثابت را رد نکند؛ Apply تأییدشده قابل آزمایش باشد؛ Send/Delete بدون تأیید اجرا نشوند.

۳. **DesktopInputBroker و lifecycle مشترک.** keyboard/pointer، completion Telegram و scroll را زیر مالک واحد ببرید؛ cancellation و permission epoch را به helperها برسانید. معیار پایان: توقف در هر نقطه پیش از input، ورودی تازه را متوقف کند؛ plan شروع‌شده پس از لغو مرحلهٔ بعد نرود؛ timeout به helper یتیم منجر نشود.

۴. **AT-SPI-first واقعی.** مستقل از OCR، node پنجرهٔ صحیح را resolve و semantic action را اجرا کنید. معیار پایان: سه کنترل استاندارد بدون OCR و با checked state صحیح کار کنند؛ کنترل hidden/defunct و پنجرهٔ دیگر رد شوند.

۵. **یکپارچه‌سازی locator و geometry.** phrase assembler، crop/resize و metadata در مسیر عمومی/Telegram مشترک شوند؛ producer و legacy جدا آزموده شوند. معیار پایان: scaleهای ۱۰۰/۱۲۵/۱۵۰/۲۰۰٪، سایه، مبدأ منفی و انتقال پنجره پوشش deterministic و سپس آزمون واقعی داشته باشند.

۶. **پس‌شرط و recovery.** ابزارهای navigation/toggle/chat پس‌شرط داشته باشند؛ plan وابسته تا verified منتظر بماند. معیار پایان: action نامعلوم دوباره کور تکرار نشود؛ failure بعد از dispatch با failure پیش از dispatch فرق کند.

۷. **فهم فرمان مستقل و لغوشونده.** partial فقط قواعد ارزان؛ final در worker؛ جهت/state و target مستقل بررسی شوند. معیار پایان: صفر inference برای partial، پاسخ سریع stop، و رد model proposal معکوس یا متناقض.

۸. **بهینه‌سازی صوت و residency.** endpoint، partial STT، AEC و TTS CPU با corpus واقعی اندازه‌گیری شوند؛ budget GPU بر اساس peak، نه فایل وزن. معیار پایان: p50/p95 و دقت/نرخ false action پیش و پس از تغییر قابل مقایسه باشند.

۹. **حافظه و توسعهٔ ابزارها.** provenance و retention، سپس registry و plan محدود؛ VLM/icon/webcam فقط برای شکاف اثبات‌شده اضافه شوند. معیار پایان: افزودن یک ابزار جدید، policy/verification/lifecycle موجود را دور نزند.

### آزمون پذیرش پیشنهادی

| گروه | نمونه‌های لازم | معیار |
|---|---|---|
| هندسه | دو resolution، scaleهای مختلف، mixed-DPI، پنجرهٔ جابه‌جاشده، Wayland/XWayland | point صحیح یا رد صریح؛ بدون کلیک خارج target. |
| محتوا | PNG با metadata متفاوت، caret، spinner خارج ROI، target تغییرکرده | عدم رد بی‌مورد و عدم پذیرش target قدیمی. |
| ابهام | دو Settings، دو پنجرهٔ هم‌PID، متن روی صفحهٔ غیرقابل کلیک | clarification/رد؛ انتخاب اولین match ممنوع. |
| عمل | toggle از قبل تنظیم‌شده، click بدون اثر، dialog کند، header دیررس | پس‌شرط درست؛ موفقیت جعلی و دوبار toggle نداشته باشد. |
| lifecycle | stop حین مدل/OCR/portal، revocation، EOF فایل، crash worker | بدون عمل دیررس؛ منابع آزاد؛ failure قابل تشخیص. |
| زبان | فارسی، انگلیسی، mixed script، کلمهٔ کوتاه و نفی/نقل‌قول | حفظ جهت/state/target و رد جملهٔ غیرامری. |
| صوت | حرف‌زدن وسط TTS، echo، میکروفون مشخص، STT کند | قطع قابل اتکا، حفظ آغاز گفتار، بدون feedback loop. |
| برنامه‌ها | حداقل سه نوع برنامه: GTK، Qt و رابط سفارشی؛ شامل Telegram | نتیجهٔ هر backend جدا ثبت شود؛ موفقیت یک برنامه تعمیم داده نشود. |

**[CONFIRMED]** پروژه ۱۰۱۲ تعریف تابع تست دارد؛ parametrization این عدد را به تعداد caseهای بیشتری تبدیل می‌کند. تست فراوان موجود است؛ شکاف اصلی، اتصال اجزا و پذیرش واقعی backend است. [test_desktop_control_helper.py](/mnt/ai_projects/KYRIN/tests/actions/test_desktop_control_helper.py:1)، [test_capture_geometry_flow.py](/mnt/ai_projects/KYRIN/tests/actions/test_capture_geometry_flow.py:1)، [test_queued_dispatch.py](/mnt/ai_projects/KYRIN/tests/actions/test_queued_dispatch.py:1). عدد تاریخی `1331 passed` نتیجهٔ اجرای فعلی این بررسی نیست.

## ۱۱. کارهای کم‌هزینه برای امروز

این فهرست **پیشنهاد** است؛ تغییرات انجام نشده‌اند.

- ابتدا error code را بررسی کنید: برای `Apply All Devices` در این checkout، تغییر OCR مسیر policy را باز نمی‌کند. این تمایز را در پیام/diagnostic نمایش دهید.
- علت‌های `content/window_token/stale_capture` را در parser نتیجه حفظ کنید؛ اصلاح کوچک با ارزش تشخیصی بالا.
- تست PNG هم‌پیکسل با metadata متفاوت و تست انیمیشن خارج target را پیش از اصلاح F01 اضافه کنید.
- fallback مدل را برای partial قطع و آزمون «جهت مدل عمداً معکوس» را اضافه کنید.
- تا تکمیل AT-SPI، برای navigation شناخته‌شده از shortcut موجود و verification استفاده کنید؛ threshold OCR را سراسری پایین نیاورید.
- برای آزمایش latency، animation داشبورد را خاموش و TTS سبک CPU را امتحان کنید؛ این‌ها متغیر آزمایش‌اند، نه علت اثبات‌شدهٔ کندی.
- یک corpus کوچک از targetهای بدون اطلاعات شخصی بسازید: متن تکراری، فارسی RTL، آیکون، سایه و scale. ذخیرهٔ screenshot واقعی فقط با رضایت و پاک‌سازی محتوای حساس.
- نصب و cacheها در صورت کار آینده مطابق [LOCAL_DATA_STORAGE.md](/mnt/ai_projects/KYRIN/docs/app/LOCAL_DATA_STORAGE.md:1) روی `/mnt/ai_projects/KYRIN/local-data/` و مدل‌های توسعه روی `models/local/` بمانند؛ مسیر مختص این ماشین داخل هستهٔ قابل حمل hard-code نشود.

## Top 5 things to do first

۱. **F01:** برابری بایت‌های PNG را از اعتبار هدف حذف و مقایسهٔ پیکسل/ناحیهٔ هدف را جایگزین کنید؛ تفاوت زمان ساخت PNG نباید کلیک را متوقف کند.

۲. **F02 و F15:** پوشش سیاست کلیک را روشن کنید؛ unknown risk به تأیید محدود و قابل انقضا برسد و علت policy با شکست OCR اشتباه نشود.

۳. **F04:** AT-SPI را مسیر نخست و مستقل از OCR کنید؛ action معنایی، پنجرهٔ دقیق و state واقعی کنترل را به کار بگیرید.

۴. **F03، F05 و F06:** ورودی دسکتاپ یک مالک داشته باشد؛ لغو تا لحظهٔ input و میان مراحل plan مؤثر باشد و پس‌شرط پیش از ادامه بررسی شود.

۵. **F07 تا F09:** مدل فقط final را در worker قابل لغو پردازش کند؛ deadline مشترک تا OCR/portal برسد و جهت/state پیشنهاد مدل مستقل تأیید شود.

</div>
