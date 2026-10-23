<div dir="rtl" lang="fa">

# بازبینی معماری، قابلیت اعتماد و کنترل رابط کاربری Kyrin

تاریخ: ۲۰۲۶/۱۰/۲۳ — مبنا: وضعیت جاری پروژه، شامل تغییرات ثبت‌نشدهٔ موجود؛ آخرین commit ثبت‌شده: `d67013d3ebe5a4a2f3027db056677f665b749485`.

## ۱. نتیجهٔ اصلی و حدود بررسی

**توصیهٔ اصلی: پیش از افزودن مدل بینایی یا قابلیت وب‌کم، قرارداد اجرای عمل را اصلاح کنید.** مشکل کلیک ترکیبی از تشخیص متن، اتصال درخواست به هدف درست، تبدیل مختصات، تازگی مشاهده و تأیید نتیجه است. تعویض OCR فقط یکی از این حلقه‌ها را تغییر می‌دهد. معماری فعلی مرزهای مفیدی دارد و بازنویسی کامل آن توجیه ندارد؛ بهترین مسیر، تکامل تدریجی به یک هستهٔ رویدادمحور با ابزارهای دارای پیش‌شرط و پس‌شرط و یک مجری واحد برای ورودی سیستم‌عامل است.

این گزارش **تحلیل** است. هیچ اصلاحی در کد، تنظیمات، تست‌ها، مدل‌ها یا مستندات موجود انجام نشده است. تنها خروجی ایجادشده توسط این بررسی همین فایل است.

### روش و میزان اطمینان

- `[CONFIRMED]`: رفتار یا ساختار مستقیماً در کد دیده شده، یا با اجرای کنترل‌شدهٔ همان منطق و وابستگی‌های ساختگی بازتولید شده است. این برچسب به‌تنهایی به معنی مشاهدهٔ خطا روی دسکتاپ واقعی نیست.
- `[LIKELY]`: نتیجهٔ محتمل بر اساس شواهد مشخص؛ شرایط و روش اعتبارسنجی آن نوشته شده است.
- `[SPECULATION]`: فرضیه‌ای که هنوز شواهد کافی ندارد و باید آزمایش شود.
- «پیشنهاد» و «معیار پذیرش» مشخص‌کنندهٔ طراحی آینده‌اند، نه توصیف قابلیت موجود. شدت‌های `Critical / High / Medium / Low` اولویت مهندسی این پروژه‌اند و امتیاز رسمی امنیتی نیستند.

**[CONFIRMED] پوشش بررسی:** ساختار تمام فایل‌های نسخه‌دار و فایل‌های جدیدِ خارج از ignore فهرست شد؛ فایل‌های متنی کد، پیکربندی، اسکریپت‌ها، تست‌ها و مستندات به‌صورت ماشینی خوانده شدند؛ مسیرهای اصلی صوت، تصمیم، مجوز، کلیک، Telegram، تاریخچه و چرخهٔ عمر به‌صورت عمیق بررسی شدند. در شمارش ایستای تست‌ها ۹۸۲ تعریف تابع تست وجود داشت؛ این عدد تعداد حالت‌های حاصل از parametrization نیست. بررسی دستی تک‌تک خطوط همهٔ تست‌ها، کد وابستگی‌های ثالث و وزن‌های باینری مدل‌ها ادعا نمی‌شود. [راهنمای ساختار](/mnt/ai_projects/KYRIN/docs/development/PROJECT_LAYOUT.md:1) و [زمینهٔ مهندسی](/mnt/ai_projects/KYRIN/PROJECT_CONTEXT.md:1) نیز در کنار کد استفاده شدند.

**[CONFIRMED] اعتبارسنجی انجام‌شده:** parsing ایستای فایل‌های Python بدون خطای syntax؛ اجرای `ruff check --no-cache --statistics src tests scripts` با خروج موفق؛ بازتولیدهای درون حافظه برای اتصال اشتباه هدف، scroll نامعتبر، پایان فایل صوتی، حالت انتظار، نگاشت مختصات و ساخت عبارت فارسی. در بازتولیدها عملیات سیستم‌عامل جایگزین ساختگی داشت و نوشتن فایل و ایجاد subprocess مسدود بود. کل مجموعهٔ `pytest` و `mypy` اجرا نشد؛ آزمون زندهٔ میکروفون، OCR روی صفحهٔ شخصی، کلیک واقعی و benchmark مدل نیز انجام نشد. عدد تاریخی «۱۳۳۱ passed» در [PROJECT_CONTEXT.md](/mnt/ai_projects/KYRIN/PROJECT_CONTEXT.md:100)، نتیجهٔ این بازبینی نیست.

**[CONFIRMED] محیط قابل مشاهده:** متغیرهای نشست این فرایند `XDG_SESSION_TYPE=wayland`، `WAYLAND_DISPLAY=wayland-0` و `XDG_CURRENT_DESKTOP=ubuntu:GNOME` هستند. Python سیستم و محیط پروژه در زمان بررسی `3.14.4` بود. بنابراین نحو جدیدی مانند `except OSError, ValueError:` را در این پروژه نباید به‌اشتباه syntax error دانست. [pyproject.toml](/mnt/ai_projects/KYRIN/pyproject.toml:11) نیز Python 3.14 را الزام می‌کند. وجود متغیر محیطی، موفقیت دسترسی portal یا نصب بودن نسخهٔ جاری extension را اثبات نمی‌کند.

**فرض‌های صریح:** مقدار دقیق VRAM، مدل‌های انتخاب‌شده در نشست زنده، چیدمان مانیتورها، scale نمایشگرها و محتوای پایگاه دادهٔ شخصی بررسی نشده‌اند. پیشنهاد تخصیص CPU/GPU مشروط به اندازه‌گیری همین موارد است. سند تازه و خارج از Git یعنی [AGENTS1.md](/mnt/ai_projects/KYRIN/AGENTS1.md:1) به‌عنوان یادداشت طراحی کلیک دیده شد؛ ساختار پیشنهادی آن به‌معنای پیاده‌سازی موجود نیست و در این کارِ تحلیل، فایل یا آزمایش عملی خواسته‌شده در آن ایجاد نشد.

## ۲. پروژه اکنون چه می‌کند؟

### ساختار و نقطهٔ شروع

| بخش | مسئولیت مشاهده‌شده و محل اصلی |
|---|---|
| ورودی برنامه | `[CONFIRMED]` دستور `kyrin-desktop` به `kyrin.app.qt.main:main` می‌رسد؛ ساخت Qt، تنظیمات، ابزارهای مشاهده و کنترل: [pyproject.toml](/mnt/ai_projects/KYRIN/pyproject.toml:54)، [main.py](/mnt/ai_projects/KYRIN/src/kyrin/app/qt/main.py:163). |
| ترکیب وابستگی‌ها | `[CONFIRMED]` انتخاب STT، interpreter، policy، executor، تاریخچه، صوت و پاسخ در `UbuntuSessionFactory`: [ubuntu.py](/mnt/ai_projects/KYRIN/src/kyrin/app/platforms/ubuntu.py:271). |
| دریافت و پردازش صوت | `[CONFIRMED]` قرارداد مستقل `AudioInput`، میکروفون، تبدیل نرخ، قاب‌بندی، VAD، کنترل backlog و مسیر جداگانهٔ فایل: [live_speech_pipeline.py](/mnt/ai_projects/KYRIN/src/kyrin/audio/live_speech_pipeline.py:1)، [file_speech_pipeline.py](/mnt/ai_projects/KYRIN/src/kyrin/audio/file_speech_pipeline.py:1). |
| فهم فرمان | `[CONFIRMED]` مسیر سریع قواعد فارسی/انگلیسی، مسیر تکمیلی مدل محلی، clarification و فرمان چندمرحله‌ای: [demo_interpreter.py](/mnt/ai_projects/KYRIN/src/kyrin/commands/demo_interpreter.py:213)، [model_interpreter.py](/mnt/ai_projects/KYRIN/src/kyrin/commands/model_interpreter.py:195)، [coordinator.py](/mnt/ai_projects/KYRIN/src/kyrin/commands/coordinator.py:107). |
| سیاست و اجرا | `[CONFIRMED]` `ActionGate` و صف FIFO محدود، زنجیرهٔ executorهای برنامه و desktop، همراه با نتیجهٔ ساخت‌یافته: [gate.py](/mnt/ai_projects/KYRIN/src/kyrin/actions/gate.py:25)، [queued_dispatch.py](/mnt/ai_projects/KYRIN/src/kyrin/actions/queued_dispatch.py:59). |
| مشاهده و کنترل Linux | `[CONFIRMED]` GNOME extension برای پنجره و تصویر، AT-SPI، OCR و RemoteDesktop portal برای ورودی؛ به‌جای اتکا به X11: [desktop_control_helper.py](/mnt/ai_projects/KYRIN/src/kyrin/actions/platforms/desktop_control_helper.py:55)، [extension.js](/mnt/ai_projects/KYRIN/integrations/gnome-shell/window-capture-prototype@kyrin.local/extension.js:303). |
| خروجی | `[CONFIRMED]` پاسخ متنی، نشانگر GNOME و صف TTS مستقل: [speech.py](/mnt/ai_projects/KYRIN/src/kyrin/responses/speech.py:83). |
| حافظه | `[CONFIRMED]` تاریخچهٔ متن نهایی با SQLite از قبل وجود دارد و آخرین شش متن به context می‌رسند؛ این هنوز حافظهٔ بلندمدتِ ساخت‌یافتهٔ ترجیحات و رویدادها نیست: [history.py](/mnt/ai_projects/KYRIN/src/kyrin/memory/history.py:45)، [ubuntu.py](/mnt/ai_projects/KYRIN/src/kyrin/app/platforms/ubuntu.py:495). |

**[CONFIRMED] وابستگی‌ها:** هسته شامل `numpy`، `onnxruntime`، `soxr` و `sounddevice` است؛ Qt و `sherpa-onnx` در extra دسکتاپ و چند backend دیگر در extraهای اختیاری قرار دارند. علاوه بر pip، مسیرهای عملی به ابزارهایی مانند `busctl`، portal، GNOME extension، runtimeهای STT/OCR/TTS و برای فایل صوتی `ffmpeg` وابسته‌اند. تنها نصب بسته‌های Python برای همهٔ قابلیت‌ها کافی نیست. [pyproject.toml](/mnt/ai_projects/KYRIN/pyproject.toml:18)، [LOCAL_AUDIO_FILE_INPUT.md](/mnt/ai_projects/KYRIN/docs/audio/LOCAL_AUDIO_FILE_INPUT.md:1).

### جریان داده و کنترل

<div dir="ltr">

```text
Microphone / local audio file
          |
          v
capture -> resample/frame -> Silero VAD -> STT worker
                                             |
                                      partial / final events
                                             |
                                             v
                                  LiveCommandRuntime
                                             |
                        +--------------------+-------------------+
                        |                                        |
                 voice-mode handling                  CommandCoordinator
                                                          |
                                               rules -> optional LLM
                                                          |
                                               final typed command
                                                          |
                                                 bounded action FIFO
                                                          |
                                                      ActionGate
                                                          |
                                                  executor adapters
                                                          |
                                      GNOME / portal / application actions
                                                          |
                                             ActionResult / observation
                                                          |
                                               text / mascot / TTS

Focused window -> capture / AT-SPI / OCR -> options + target evidence
Final transcripts -> SQLite history -> bounded recent context
```

</div>

**[CONFIRMED] نکتهٔ معماری:** اجرای عمل صف مستقل دارد، ولی فراخوانی interpreter و مدل در مصرف‌کنندهٔ رویداد صوتی همگام است. شکل بالا نباید به‌عنوان وجود worker مستقل برای همهٔ مراحل تعبیر شود؛ این مسئله در R10 بررسی می‌شود.

**[CONFIRMED] تفاوت با توصیف اولیه:** در checkout بررسی‌شده اجرای آزاد دستور shell از متن گفتار پیدا نشد. کنترل Ptyxis برای پنجره، tab و preferences آرگومان‌های ثابت دارد؛ `shell=True` یا `eval` برای متن فرمان دیده نشد. بنابراین «دستیار دارای اجرای shell دلخواه» توصیف دقیقی از این نسخه نیست. [ptyxis.py](/mnt/ai_projects/KYRIN/src/kyrin/actions/platforms/ptyxis.py:12)، [ptyxis.py](/mnt/ai_projects/KYRIN/src/kyrin/actions/platforms/ptyxis.py:123). قابلیت عمومی کلیک و تاریخچه نیز از توصیف اولیه جلوترند؛ وب‌کم، تشخیص چهره و احراز هویت گوینده در مسیر اجرایی بررسی‌شده وجود ندارند.

## ۳. یافته‌های اولویت‌دار: کلیک و اتصال فرمان به هدف

### R01 — گزینهٔ انتخاب‌شدهٔ مدل الزاماً همان هدف درخواست‌شده نیست — Critical

**[CONFIRMED]** در [model_interpreter.py](/mnt/ai_projects/KYRIN/src/kyrin/commands/model_interpreter.py:379)، وجود `target_phrase` در گفتار بررسی می‌شود، اما انتخاب کنترل با `target_id` انجام می‌شود و intent نهایی از `option.label` ساخته می‌شود. در مسیر دارای گزینه‌های ازپیش‌خوانده‌شده، هیچ الزام مستقلی وجود ندارد که این label با هدف گفتار هم‌معنا یا مطابق alias تأییدشده باشد. مسیر خاصِ کشف بعدیِ گزینهٔ دقیق، این خلأ را در تمام مسیرها برطرف نمی‌کند.

**بازتولید:** با گزینه‌های `1=Settings` و `2=Quit`، درخواست `I want Settings opened` و خروجی ساختگی مدل شامل `target_phrase="Settings", target_id="2"`، interpreter واقعی با قواعد و بازبینی عمل، `ReadyCommand(target="Quit")` تولید کرد. کلیکی انجام نشد. این آزمایش نقص مرز اعتبارسنجی را ثابت می‌کند، نه اینکه مدل واقعی همواره چنین خروجی‌ای می‌دهد.

**چرا مهم است:** اعتبار شناسه فقط ثابت می‌کند گزینه‌ای روی صفحه وجود دارد؛ رضایت کاربر برای همان گزینه را ثابت نمی‌کند. حتی OCR بی‌نقص و مختصات کاملاً صحیح می‌توانند در این وضعیت «دکمهٔ اشتباه را درست کلیک کنند». فیلتر حساسیت نیز `Quit` را پوشش نمی‌دهد؛ R13 محدودیت‌های بیشتری دارد.

**اصلاح پیشنهادی:** هدف گفتار، گزینهٔ انتخاب‌شده و عملیات را مستقل از مدل به هم متصل کنید. تطابق دقیق نرمال‌شده یا alias مشخص کافی است؛ اصلاح املایی/معنایی دورتر باید به گزینهٔ قابل مشاهده برای رفع ابهام تبدیل شود. مدل حق انتخاب آزاد هر ID معتبر را نداشته باشد. نتیجهٔ locator باید شناسهٔ مشاهده و دلیل تطابق را حفظ کند. **معیار پذیرش:** خروجی متناقض ID/label هرگز به `ActionRequest` نرسد؛ آزمون منفی برای گزینهٔ کم‌خطر و مخرب هر دو اضافه شود.

### R02 — مدل می‌تواند scroll را برخلاف متن منفی پیشنهاد کند و پذیرفته شود — High

**[CONFIRMED]** شاخهٔ scroll در [model_interpreter.py](/mnt/ai_projects/KYRIN/src/kyrin/commands/model_interpreter.py:365) پیش از `SourceOperationVerifier` در خط ۴۴۵ برمی‌گردد. وجود پنجره و فعال بودن قابلیت کنترل، جای بررسی معنای درخواست را گرفته است.

**بازتولید:** خروجی ساختگی `SCROLL_DOWN` برای هر دو متن `Please do not scroll down` و `What is the weather today?` در context مجاز و دارای پنجرهٔ مشاهده‌شده، به `ReadyCommand(SCROLL_DOWN)` رسید. این نتیجه با `review_model_action` واقعی هم برقرار بود.

**اصلاح پیشنهادی:** همهٔ عملیات، از جمله scroll و visible control، یک بررسی مستقلِ درخواست صریح، نفی و هدف داشته باشند؛ شاخه‌های زودهنگام از این قاعده مستثنا نباشند. برای زبان فاقد بررسی قابل اتکا، عدم اجرا یا clarification انتخاب شود. **معیار پذیرش:** جملهٔ منفی، نقل‌قول فرمان و جملهٔ غیرامری، حتی با خروجی نامعتبر مدل، ورودی سیستم‌عامل تولید نکنند.

### R03 — تبدیل مختصات، scale واقعی و سایه را با یک قرارداد صریح تفکیک نمی‌کند — High

**[CONFIRMED]** در [desktop_control_helper.py](/mnt/ai_projects/KYRIN/src/kyrin/actions/platforms/desktop_control_helper.py:164)، اختلاف مساوی عرض و ارتفاع PNG با frame، در شرایط مشخص به‌عنوان سایهٔ متقارن تفسیر می‌شود. در غیر این صورت فقط اختلاف بسیار کوچک، حداکثر حدود ۲٪ یا چهار پیکسل، rescale می‌شود؛ اختلاف بزرگ‌تر رد می‌شود. بنابراین پشتیبانی عمومی از scaleهای `1.25/1.5/2` وجود ندارد. رد کردن این ورودی‌ها محافظه‌کارانه است، ولی قابلیت HiDPI را کامل نمی‌کند.

**بازتولیدهای هندسی با همان تابع و bus ساختگی:**

| ورودی مصنوعی | نتیجهٔ واقعی منطق | تفسیر |
|---|---|---|
| frame برابر `800×600`، PNG برابر `1600×1200` | `TARGET_CHANGED:image_scale_800x600_png_1600x1200` | `[CONFIRMED]` نگاشت scale دوبرابر انجام نمی‌شود. |
| frame مربع `400×400`، PNG برابر `500×500`، مرکز هدف `(125,125)` و مبدأ صفر | dispatch به `(75,75)` | `[CONFIRMED]` اختلاف به‌عنوان سایهٔ ۵۰ پیکسلی تفسیر می‌شود. اگر این PNG ناشی از scale برابر `1.25` باشد، نقطهٔ صحیح `(100,100)` است. |

**[LIKELY]** سناریوی دوم در هندسه‌ای که scale با شرط سایه اشتباه شود می‌تواند کلیک را منحرف کند؛ تولید چنین تصویری توسط backend واقعی این ماشین آزمایش نشده است. در مقابل، سند پروژه برای OpenRGB سایهٔ واقعی ۲۵ پیکسلی و dispatch موفق را گزارش کرده است؛ این اصلاح خاص را نباید نادیده گرفت یا خطا دانست. [PROJECT_CONTEXT.md](/mnt/ai_projects/KYRIN/PROJECT_CONTEXT.md:130).

**اصلاح پیشنهادی:** همراه تصویر، تبدیل صریح `image pixel -> logical desktop coordinate` و provenance آن حمل شود؛ padding، crop، scale و origin جدا باشند. از اختلاف ابعاد به‌تنهایی نوع تبدیل استنتاج نشود. آزمون مستقل برای scale و سایهٔ هم‌زمان، نه فقط هر یک جداگانه، لازم است.

### R04 — مسیر کلیک Telegram از قرارداد هندسی مسیر عمومی عقب مانده است — High

**[CONFIRMED]** [ChatSearchMatch](/mnt/ai_projects/KYRIN/src/kyrin/actions/telegram_verification.py:15) اطلاعات `capture_rect/frame_rect` ندارد؛ [telegram.py](/mnt/ai_projects/KYRIN/src/kyrin/actions/platforms/telegram.py:767) فقط جعبه و ابعاد تصویر را می‌فرستد. [telegram_portal_helper.py](/mnt/ai_projects/KYRIN/src/kyrin/actions/platforms/telegram_portal_helper.py:303) تقریباً برابری ابعاد frame و تصویر را می‌خواهد و سپس origin پنجره را به مختصات OCR اضافه می‌کند.

**[LIKELY]** تصویر دارای سایه، تفاوت ناحیهٔ capture با frame یا HiDPI می‌تواند این مسیر را متوقف کند یا فرض نگاشت آن را نامعتبر سازد؛ موفقیت مسیر عمومی، موفقیت Telegram را تضمین نمی‌کند. **اصلاح پیشنهادی:** هر دو مسیر از یک `CaptureGeometry` و یک مبدل مختصات آزموده‌شده استفاده کنند. همسان‌سازی قرارداد بر کپی کردن patch سایه در helper دوم اولویت دارد.

### R05 — هویت برنامه و PID، هویت یکتای پنجره و تازگی محتوا نیست — High

**[CONFIRMED]** [IdentifiedWindowText](/mnt/ai_projects/KYRIN/src/kyrin/vision/text_reader.py:22) `app_id`، PID و geometry دارد، اما window token و timestamp ندارد. intent کلیک نیز تنها `control_window_app` را از مشاهده نگه می‌دارد؛ [model_interpreter.py](/mnt/ai_projects/KYRIN/src/kyrin/commands/model_interpreter.py:410). executor تغییر identity را پیش و پس از OCR بررسی می‌کند و helper تغییر frame را می‌گیرد؛ این‌ها کنترل‌های مفیدی هستند، اما کامل نیستند.

**[LIKELY]** دو پنجرهٔ یک برنامه با PID یکسان و هندسهٔ مشابه، dialog تازه در همان پنجره، یا جابه‌جایی محتوا در زمان انتظار portal می‌توانند از این کنترل‌ها عبور کنند. خود extension هنگام گرفتن تصویر focus را کنترل می‌کند؛ مسئله، فاصلهٔ مشاهده تا اجرای بعدی است. زمان مجاز helper تا ۴۵ ثانیه است: [desktop_control.py](/mnt/ai_projects/KYRIN/src/kyrin/actions/platforms/desktop_control.py:145).

**اصلاح پیشنهادی:** `window_token` پایدار، نسل مشاهده، زمان monotonic و مهلت اعتبار هدف تا مجری حمل شوند. `get_stable_sequence()` از قبل در [active-app extension](/mnt/ai_projects/KYRIN/integrations/gnome-shell/active-app@kyrin.local/extension.js:392) استفاده می‌شود و نقطهٔ شروع مناسبی است. پس از گرفتن مجوز ورودی، locator باید دوباره اعتبارسنجی شود. **معیار پذیرش:** تعویض دو پنجرهٔ هم‌برنامه و نمایش dialog بعد از locate، بدون کلیک بر هدف قدیمی متوقف شوند.

### R06 — dispatch با تحقق نتیجه یکسان نیست؛ بعضی مراحل بعدی زود ادامه می‌یابند — High

**[CONFIRMED]** helper عمومی پس از ارسال دکمهٔ ماوس `CLICK_DISPATCHED` می‌دهد و [desktop_control.py](/mnt/ai_projects/KYRIN/src/kyrin/actions/platforms/desktop_control.py:220) آن را صادقانه به `LAUNCH_ACCEPTED` تبدیل می‌کند؛ state پس از کلیک دوباره خوانده نمی‌شود. برای toggle، حالت «از قبل تنظیم‌شده» بررسی می‌شود، ولی حالت حاصل از تغییر بررسی نمی‌شود.

**[CONFIRMED]** Telegram در مسیر ردیفِ ازقبل‌نمایان عمداً پس از dispatch برمی‌گردد؛ در مسیر نتیجهٔ جست‌وجو header را نیز بررسی می‌کند و برای عنوان‌های تکراری از ادعای هویت قطعی پرهیز می‌کند. [telegram.py](/mnt/ai_projects/KYRIN/src/kyrin/actions/platforms/telegram.py:828). بنابراین ادعای «هیچ verificationی وجود ندارد» نادرست است؛ پوشش آن یکسان نیست.

**[CONFIRMED]** [plan_runner.py](/mnt/ai_projects/KYRIN/src/kyrin/actions/plan_runner.py:78) فقط با `FAILED/UNKNOWN` متوقف می‌شود و `LAUNCH_ACCEPTED` می‌تواند اجازهٔ مرحلهٔ بعد را بدهد. برای `OPEN_CHAT` یک بررسی وابستگیِ مخصوص وجود دارد، ولی قرارداد عمومی برای پس‌شرط همهٔ مراحل وجود ندارد.

**اصلاح پیشنهادی:** هر ابزار پس‌شرط روشن داشته باشد: dialog مورد انتظار، مقدار `checked`، پنجرهٔ جدید یا شناسهٔ chat. مرحلهٔ وابسته تا اثبات همان پس‌شرط شروع نشود. تغییر تصویر فقط شاهد کمکی است: blinking cursor یا حرکت pointer نیز تصویر را تغییر می‌دهد، و عملی مانند Apply ممکن است تغییر تصویری محسوسی نداشته باشد.

### R07 — AT-SPI موجود است، اما هنوز مزیت اصلی آن استفاده نمی‌شود — High

**[CONFIRMED]** پروژه از صفر نیازمند افزودن accessibility نیست. inventory موجود، نام/role/state را می‌خواند. با این حال، در اجرای کنترل مستقیم معمولاً OCR پیش از fallback دسترس‌پذیری امتحان می‌شود؛ inventory و executor هر دو به آماده بودن مسیر screen/OCR وابسته‌اند. [desktop_control.py](/mnt/ai_projects/KYRIN/src/kyrin/actions/platforms/desktop_control.py:100)، [desktop_control_inventory.py](/mnt/ai_projects/KYRIN/src/kyrin/actions/platforms/desktop_control_inventory.py:61).

**[CONFIRMED]** [desktop_accessibility_inventory.py](/mnt/ai_projects/KYRIN/src/kyrin/actions/platforms/desktop_accessibility_inventory.py:23) و [_accessible_control](/mnt/ai_projects/KYRIN/src/kyrin/actions/platforms/desktop_control_helper.py:55) جست‌وجو را در subtree برنامهٔ دارای PID انجام می‌دهند، عمدتاً `ENABLED` را بررسی می‌کنند و نقش‌های محدودی می‌پذیرند. `SHOWING/VISIBLE/SENSITIVE/DEFUNCT`، ancestor پنجرهٔ دقیق و ابعاد معتبر به‌صورت کامل کنترل نمی‌شوند. مسیر اجرا در نهایت مرکز rectangle را کلیک می‌کند؛ `Action.do_action` استفاده نمی‌شود.

**[LIKELY]** کنترل پنهان، node قدیمی، متن یکسان در پنجرهٔ دیگر یا widget فاقد role فعلی می‌تواند به ambiguity، رد بی‌مورد یا انتخاب نامناسب منجر شود. **اصلاح پیشنهادی:** ابتدا node در پنجرهٔ صحیح و state مناسب resolve شود؛ action واقعی از interface آن خوانده و در صورت پشتیبانی فراخوانی شود؛ برای selection/text نیز interface متناظر به کار رود. نتیجه سپس مشاهده شود. دسترسی accessibility از آمادگی OCR مستقل باشد. نام action یا وجود آن را ثابت فرض نکنید. [مستندات Action.do_action](https://gnome.pages.gitlab.gnome.org/at-spi2-core/libatspi/method.Action.do_action.html)، [مستندات StateType](https://gnome.pages.gitlab.gnome.org/at-spi2-core/libatspi/enum.StateType.html).

### R08 — confidence، جهت متن و segmentation در مسیرهای OCR یکسان نیستند — High

**[CONFIRMED]** [visible_control.py](/mnt/ai_projects/KYRIN/src/kyrin/actions/visible_control.py:37) برای گزینه‌سازی حداقل confidence برابر `0.65` و گروه‌بندی حداکثر چهار span با حرکت از چپ به راست، اختلاف top تا ۸ و gap تا ۲۰ پیکسل دارد. در مقابل، [text_targets.py](/mnt/ai_projects/KYRIN/src/kyrin/vision/text_targets.py:17) برای هدف دقیق RTL و overlap محدود را پشتیبانی می‌کند. بازتولید با دو span فارسی در ترتیب راست‌به‌چپ نشان داد هدف دقیق پیدا می‌شود، ولی عبارت کامل در inventory تولید نمی‌شود.

**[CONFIRMED]** [chat_verifier.py](/mnt/ai_projects/KYRIN/src/kyrin/app/qt/chat_verifier.py:251) در inventory تا چهار زبان را ترکیب می‌کند، ولی هنگام درخواست یک label انگلیسی مشخص می‌تواند فقط `eng` را انتخاب کند. بنابراین مدل ممکن است گزینه‌ای را نبیند که اجرای مستقیم آن قابل تشخیص است. تفاوت word-level و line-level OCR نیز در جست‌وجوی عبارت اهمیت دارد؛ متن خوانا لزوماً span مناسب برای label کوتاه نمی‌سازد.

**[LIKELY]** آستانهٔ ثابت میان backendها، زبان‌ها و طول labelها calibration مناسبی ندارد. سند پروژه برای `Apply` confidence برابر `0.37` با `eng+fas` و `0.72` با `eng` گزارش کرده است؛ این مشاهدهٔ تاریخی در این بررسی تکرار نشده است. [PROJECT_CONTEXT.md](/mnt/ai_projects/KYRIN/PROJECT_CONTEXT.md:116).

**اصلاح پیشنهادی:** یک normalizer و phrase assembler مشترک با پشتیبانی RTL/LTR، حفظ bounding box و calibration بر corpus واقعی بسازید. زبان UI یا label را محدود کنید؛ خواندن چندبارهٔ هدفمند از crop بهتر از اجرای کور همهٔ زبان‌هاست. آستانه را صرفاً پایین نیاورید: برای label کوتاه مانند `OK` و گزینهٔ مخرب شواهد قوی‌تری لازم است. [راهنمای رسمی بهبود ورودی Tesseract](https://github.com/tesseract-ocr/tessdoc/blob/main/ImproveQuality.md?plain=1) نیز اهمیت segmentation و کیفیت تصویر را توضیح می‌دهد؛ تغییر metadata به «۳۰۰ DPI» به‌تنهایی جزئیات پیکسلی تولید نمی‌کند.

### R09 — layoutهای Telegram هنوز به اندازه و موقعیت نسبی ثابت وابسته‌اند — High

**[CONFIRMED]** cropها در [screen_text_reader.py](/mnt/ai_projects/KYRIN/src/kyrin/app/qt/screen_text_reader.py:38)، قواعد ستون عنوان/زمان/preview در [telegram_verification.py](/mnt/ai_projects/KYRIN/src/kyrin/actions/telegram_verification.py:111) و محل hamburger در [telegram_portal_helper.py](/mnt/ai_projects/KYRIN/src/kyrin/actions/platforms/telegram_portal_helper.py:493) به نسبت‌ها یا پیکسل‌های ثابت تکیه دارند. تبدیل معکوس crop و بزرگ‌نمایی دوبرابری در [screen_text_reader.py](/mnt/ai_projects/KYRIN/src/kyrin/app/qt/screen_text_reader.py:100) انجام می‌شود؛ مشکل، نبود کامل تبدیل crop نیست.

**[LIKELY]** تغییر عرض sidebar، اندازهٔ فونت، حالت باریک پنجره، theme یا RTL این فرض‌ها را می‌شکند. **اصلاح پیشنهادی:** navigation شناخته‌شده با shortcut معتبر و پیش‌شرط focus انجام شود؛ برای ردیف chat از ساختار accessibility یا تشخیص layout جاری استفاده شود. قواعد Telegram در adapter آن بمانند و وارد locator عمومی نشوند. **معیار پذیرش:** حالت باریک/عریض، دو scale و نام‌های تکراری با نتیجهٔ قابل تشخیص پوشش داده شوند.

## ۴. یافته‌های runtime، صف و تأخیر

### R10 — مدل، مصرف رویداد گفتار و رسیدگی به فرمان توقف را مسدود می‌کند — High

**[CONFIRMED]** [command_runtime.py](/mnt/ai_projects/KYRIN/src/kyrin/runtime/command_runtime.py:266) به‌صورت همگام تصمیم‌گیری می‌کند؛ transport مدل در [ollama_engine.py](/mnt/ai_projects/KYRIN/src/kyrin/commands/ollama_engine.py:365) تا ۶۰ ثانیه و در انتخاب CPU تا ۱۲۰ ثانیه timeout دارد. inventory و گاهی inference دوم نیز در همین مسیرند. وجود صف مستقل action این گلوگاه را برطرف نمی‌کند.

**[LIKELY]** هنگام کندی مدل، دریافت رویداد توقف و وضعیت‌های جدید عقب می‌افتد؛ صف رویداد ۲۵۶تایی و backlog صوت محدود در [live_speech_pipeline.py](/mnt/ai_projects/KYRIN/src/kyrin/audio/live_speech_pipeline.py:137) می‌توانند باعث فشار برگشتی یا کنار گذاشتن صوت قدیمی شوند. پس از بازگشت inference نیز پیش از `worker.submit` بررسی دوبارهٔ نسل فعال بودن فرمان وجود ندارد.

**اصلاح پیشنهادی:** فهم فرمان به worker مستقل با صف محدود و deadline منتقل شود؛ کنترل stop/standby مسیر اولویت‌دار داشته باشد. پاسخ مدل متعلق به نسل لغوشده یا مشاهدهٔ منقضی، پیش از gate کنار گذاشته شود. صرفاً `async` کردن امضا بدون جدا کردن I/O و inference مسدودکننده کافی نیست.

### R11 — حالت انتظار، فرمان‌های ازقبل‌صف‌شده را باطل نمی‌کند — High

**[CONFIRMED]** [set_commands_active](/mnt/ai_projects/KYRIN/src/kyrin/runtime/command_runtime.py:173) فقط flag و reset گفت‌وگو را تغییر می‌دهد؛ صف action مستقل باقی می‌ماند. `stop()` نیز فقط controller، انتخاب Telegram و power flow را متوقف می‌کند و لغو مستقیمِ مجری عمومی ندارد. [queued_dispatch.py](/mnt/ai_projects/KYRIN/src/kyrin/actions/queued_dispatch.py:103) در close عمل جاری را تا ۲۰ ثانیه انتظار می‌کشد، در حالی که helper کلیک timeout برابر ۴۵ ثانیه دارد.

**بازتولید:** عمل اول با executor ساختگی مسدود شد، عمل دوم در صف قرار گرفت، سپس `set_commands_active(False)` فراخوانی شد. پس از آزادسازی عمل اول، هر دو عمل اجرا شدند. هیچ برنامهٔ واقعی کنترل نشد.

**[LIKELY]** در توقف کامل نیز ممکن است helper جاری بعد از اعلام مشکل توقف هنوز ورودی ارسال کند. **اصلاح پیشنهادی:** هر درخواست `session_generation` و cancellation token داشته باشد؛ standby/stop درخواست‌های شروع‌نشده را باطل کنند و مجری پیش از input دوباره token را کنترل کند. فرایند helper متعلق به درخواست باید قابل خاتمه باشد و release دکمه‌ها در cleanup طراحی شود. لغو، عمل قبلاً انجام‌شده را برنمی‌گرداند؛ نتیجهٔ آن باید `UNKNOWN` یا نتیجهٔ مشاهده‌شده باشد، نه ادعای rollback.

**TODO — خطر باقی‌ماندهٔ R11:** تغییر نسل نشست، فقط درخواست‌هایی را که هنوز در مجری شروع نشده‌اند باطل می‌کند. helper کلیکی که پیش از standby یا stop شروع شده، همچنان ممکن است پس از آن ورودی ارسال کند. فرایند helper در این اصلاح متوقف یا کشته نمی‌شود. برای رفع این خطر، قرارداد لغو درون helper، بررسی لغو درست پیش از ارسال دکمه و آزادسازی تضمین‌شدهٔ دکمه در cleanup لازم است؛ نتیجهٔ عملِ آغازشده نیز باید مشاهده یا `UNKNOWN` گزارش شود.

### R12 — پایان طبیعی فایل صوتی، فرمان‌های منتظر اجرا را لغو می‌کند — High

**[CONFIRMED]** `finally` در [command_runtime.py](/mnt/ai_projects/KYRIN/src/kyrin/runtime/command_runtime.py:293) برای پایان طبیعی و توقف کاربر یکسان `worker.close()` را فراخوانی می‌کند. close در [queued_dispatch.py](/mnt/ai_projects/KYRIN/src/kyrin/actions/queued_dispatch.py:103) همهٔ فرمان‌های شروع‌نشده را لغو می‌کند. مسیر فایل برخلاف میکروفون می‌تواند بسیار سریع تمام شود: [file_speech_pipeline.py](/mnt/ai_projects/KYRIN/src/kyrin/audio/file_speech_pipeline.py:105).

**بازتولید:** source محدود با سه transcript نهایی، پس از شروع عمل اول پایان یافت؛ مجری اول عمداً کند بود. نتیجه: فقط فرمان `0` اجرا شد و برای فرمان‌های `1` و `2` رویداد `CANCELLED` تولید شد. این رفتار با runtime واقعی و مجری ساختگی بازتولید شد.

**اصلاح پیشنهادی:** پایان طبیعی `drain` با مهلت مشخص داشته باشد؛ توقف صریح `cancel_pending` باشد. برای فایل، ظرفیت چهارفرمانی صف نیازمند backpressure یا acknowledgement است؛ سرعت decode نباید فرمان معتبر را با `BUSY` یا پایان stream از دسترس خارج کند. آزمون موجود [test_queued_dispatch.py](/mnt/ai_projects/KYRIN/tests/actions/test_queued_dispatch.py:75) درستی cancel روی close را می‌سنجد؛ مسئله، استفاده از همان semantics در EOF است.

### R13 — فهرست واژه‌های حساس، مرز مطمئن مجوز برای کلیک نیست — High

**[CONFIRMED]** [desktop_control.py](/mnt/ai_projects/KYRIN/src/kyrin/actions/platforms/desktop_control.py:26) یک denylist دارد که با `split()` یا برابری کل label بررسی می‌شود. ارزیابی مستقیم همین شرط، `Delete` را مسدود کرد اما `Delete...`، `Log out now` و `Erase disk` را عبور داد؛ در مورد عبارت چندکلمه‌ای، وجود `log out` در مجموعه به‌معنای یافتن آن داخل جمله نیست.

**چرا مهم است:** اجازهٔ کلی `allow_focused_control` با اجازهٔ هر پیامد یکسان نیست. ترکیب این ضعف با R01 سطح اثر انتخاب اشتباه مدل را بیشتر می‌کند. **اصلاح پیشنهادی:** policy بر operation و پیامد تکیه کند؛ control شناخته‌شدهٔ ارسال/حذف/پرداخت/خروج با جزئیات هدف تأیید شود یا تا وجود چنین جریان تأییدی اجرا نشود. اصلاح Unicode و punctuation یک quick win است، اما denylist کامل و امن ایجاد نمی‌کند. unknown-risk را هم‌ارز harmless نگیرید.

### R14 — timeout در caller، کار OCR را متوقف نمی‌کند — High

**[CONFIRMED]** در [chat_verifier.py](/mnt/ai_projects/KYRIN/src/kyrin/app/qt/chat_verifier.py:180)، درخواست عمومی OCR پس از ۱۸ ثانیه برمی‌گردد؛ `_ask` فقط `finished` را set می‌کند. `_pending` و `reader.busy` تا تکمیل worker باقی می‌مانند. backend [paddle.py](/mnt/ai_projects/KYRIN/src/kyrin/vision/ocr/backends/paddle.py:95) برای هر خواندن subprocess با timeout برابر ۶۰ یا ۹۰ ثانیه می‌سازد. callback مسیر visible choices می‌تواند fallback بعدی را نیز آغاز کند: [chat_verifier.py](/mnt/ai_projects/KYRIN/src/kyrin/app/qt/chat_verifier.py:430).

**[LIKELY]** کاربر «پیدا نشد/در دسترس نیست» می‌شنود، اما OCR هنوز منابع را مصرف می‌کند و درخواست بعدی به علت busy رد می‌شود. deadline حلقه‌های Telegram نیز با یک فراخوانی داخلیِ طولانی، deadline سراسری واقعی نیست. [telegram.py](/mnt/ai_projects/KYRIN/src/kyrin/actions/platforms/telegram.py:959).

**اصلاح پیشنهادی:** deadline مطلق و cancellation تا capture و backend منتقل شود؛ timeout درخواست، مجوز شروع fallback بعدی را لغو کند. backend سنگین در worker پایدار و قابل توقف نگهداری شود، با سیاست آزادسازی حافظه؛ زمان warm-up از زمان inference جدا ثبت شود. افزایش سادهٔ timeout مشکل lifecycle را حل نمی‌کند.

### R15 — قطع پاسخ صوتی با صحبت کاربر در همهٔ حالت‌ها کار نمی‌کند — High

**[CONFIRMED]** در نبود AEC، [PlaybackGuardInput](/mnt/ai_projects/KYRIN/src/kyrin/audio/playback_guard.py:22) صوت ورودی را هنگام فعال بودن speaker با سکوت جایگزین می‌کند. flag فعال در [speech.py](/mnt/ai_projects/KYRIN/src/kyrin/responses/speech.py:141) از زمان enqueue روشن می‌شود؛ بنابراین دورهٔ synthesis و انتظار پاسخ هم ممکن است پوشانده شود. tail پیش‌فرض ۳۵۰ میلی‌ثانیه است.

**[CONFIRMED]** AEC با PipeWire وجود دارد، اما در ترکیب فعلی برای میکروفون پیش‌فرض تلاش می‌شود؛ انتخاب میکروفون مشخص این مسیر را کنار می‌گذارد. [ubuntu.py](/mnt/ai_projects/KYRIN/src/kyrin/app/platforms/ubuntu.py:528). همچنین اتصال عمومی `SpeechTransition.STARTED -> speaker.interrupt()` در مسیر live وجود ندارد؛ interrupt برای جریان‌هایی مانند power flow و تغییر تنظیم TTS استفاده می‌شود. [main.py](/mnt/ai_projects/KYRIN/src/kyrin/app/qt/main.py:256)، [ubuntu.py](/mnt/ai_projects/KYRIN/src/kyrin/app/platforms/ubuntu.py:624).

**اصلاح پیشنهادی:** echo reference برای میکروفون انتخاب‌شده برقرار شود؛ VAD معتبر ابتدا پاسخ صوتی را قطع کند و buffer کوتاه گفتار حفظ شود. تأیید یا اجرای فرمان همچنان به متن نهایی و policy وابسته بماند. اگر AEC در دسترس نیست، حالت half-duplex صریح و کنترل توقف دستی فوری ارائه شود. توقف playback باید از لغو synthesis هم تفکیک شود؛ [tts/runtime.py](/mnt/ai_projects/KYRIN/src/kyrin/tts/runtime.py:401) generation و پخش را قطع می‌کند، اما همهٔ محاسبات backend را فوراً متوقف نمی‌کند.

## ۵. یافته‌های تکمیلی: نگهداری، حافظه و امنیت

### R16 — مرز مجوز پنجره در D-Bus از policy پایتون مستقل است — Medium

**[CONFIRMED]** [ControlAppWindow](/mnt/ai_projects/KYRIN/integrations/gnome-shell/active-app@kyrin.local/extension.js:369) عملیات از جمله close را می‌پذیرد و در همان متد هویت caller یا session مجاز Kyrin بررسی نمی‌شود. allowanceهای Python در این endpoint اعمال نمی‌شوند؛ مسیرهای picker نیز دادهٔ مجوز را از caller می‌گیرند. این با حفاظت owner در extension تصویر یکسان نیست.

**محدودهٔ خطر:** caller محلی دارای دسترسی به session bus مطرح است؛ دسترسی از اینترنت، افزایش سطح به root یا exploit روی سیستم واقعی اثبات نشده است. **اصلاح پیشنهادی:** endpoint تغییردهنده به session/capability مشخص متصل شود و با قطع owner لغو شود. چون helperهای `busctl` اتصال جدا می‌سازند، بررسی سادهٔ owner فرایند اصلی بدون طراحی broker می‌تواند رفتار فعلی را بشکند. یک broker با اتصال پایدار راه روشن‌تری است.

### R17 — تاریخچهٔ متنی فعال است و archive سقف کل را دور می‌زند — Medium

**[CONFIRMED]** factory هنگام ساخت مسیر فرمان تاریخچه را می‌سازد؛ [ubuntu.py](/mnt/ai_projects/KYRIN/src/kyrin/app/platforms/ubuntu.py:495). [command_runtime.py](/mnt/ai_projects/KYRIN/src/kyrin/runtime/command_runtime.py:310) متن‌های نهاییِ عبورکرده از فیلتر حالت شنیدن را، حتی اگر فرمان قابل اجرا نباشند، تا ۲۰۰۰ کاراکتر ذخیره می‌کند. در تنظیمات فعلی گزینهٔ صریح مستقل برای خاموش کردن این ذخیره‌سازی مشاهده نشد.

**[CONFIRMED]** سقف ۲۰۰۰ turn در [history.py](/mnt/ai_projects/KYRIN/src/kyrin/memory/history.py:105) فقط برای `archived=0` است. archiveهای پی‌درپی کل داده را بدون این سقف افزایش می‌دهند؛ `clear()` در [خط ۲۰۰](/mnt/ai_projects/KYRIN/src/kyrin/memory/history.py:200) نیز archive را حذف نمی‌کند. این الزاماً با قصد UI برای «پاک کردن فعال‌ها» ناسازگار نیست، اما حذف کامل تاریخچه نیست.

**اصلاح پیشنهادی:** کلید روشن/خاموش، سقف کل یا retention زمانی، حذف جداگانهٔ archive و توضیح دقیق دامنهٔ حذف اضافه شود. منبع داده (`microphone/file`)، حساسیت و provenance برای حافظهٔ آینده ثبت شوند. نکات مثبت موجود: permission فایل `0600`، SQL پارامتری، lock اتصال و reads محدود؛ این‌ها حفظ شوند. محتوای پایگاه دادهٔ شخصی در این بررسی خوانده نشد.

### R18 — معیار تأخیر، هویت کامل عمل را نگه نمی‌دارد — Medium

**[CONFIRMED]** [latency.py](/mnt/ai_projects/KYRIN/src/kyrin/runtime/latency.py:16) فقط `segment_id` را کلید می‌کند؛ اولین `ActionFeedback` با `pop` marker را حذف می‌کند. `stream_id` و `step_index` در matching نیستند و زمان‌ها زمان دریافت رویدادند، نه الزاماً زمان capture صوت.

**[LIKELY]** نتایج دیررس stream قبلی با شناسه‌های تکرارشده می‌توانند به نمونهٔ جدید نسبت داده شوند؛ در plan چندمرحله‌ای نیز زمان اولین نتیجه جای زمان تکمیل کل plan را می‌گیرد. **اصلاح پیشنهادی:** `session_id + ActionKey`، زمان capture، پایان گفتار، final STT، enqueue/start action، postcondition و اولین نمونهٔ TTS جدا ثبت شوند. آمار p50/p95 به تفکیک مسیر سریع/مدل، CPU/GPU و cold/warm منتشر شود.

### R19 — بودجهٔ مشترک منابع و prompt وجود ندارد — Medium

**[CONFIRMED]** STT، مدل فرمان و TTS جدا مدیریت می‌شوند؛ Ollama از `keep_alive="5m"` استفاده می‌کند و TTS دو مدل رایج را warm نگه می‌دارد. [ollama_engine.py](/mnt/ai_projects/KYRIN/src/kyrin/commands/ollama_engine.py:304)، [tts/runtime.py](/mnt/ai_projects/KYRIN/src/kyrin/tts/runtime.py:278). context مدل `4096` و سقف تولید `768` است: [ollama_engine.py](/mnt/ai_projects/KYRIN/src/kyrin/commands/ollama_engine.py:353).

**[LIKELY]** هم‌زمانی مدل‌ها روی GPU محدود می‌تواند latency و پایداری حافظه را بدتر کند؛ وجود OOM در این نشست اثبات نشده است. همچنین catalog برنامه‌ها، گزینه‌های صفحه، history و prompt بدون بودجه‌بندی token ممکن است از context مؤثر فراتر روند؛ میزان آن با نام‌های فارسی و catalog واقعی باید اندازه‌گیری شود.

**اصلاح پیشنهادی:** یک مدیر منابع سبک، اولویت GPU برای STT تعاملی، TTS سبک CPU و VLM فقط هنگام نیاز تعریف کند. تعداد گزینه‌ها بر اساس relevance و بودجهٔ token محدود شود؛ فیلدهای مجوز و شواهد اصلی هرگز با truncation حذف نشوند. مصرف حافظهٔ کل و زمان جابه‌جایی مدل‌ها سنجیده شود، نه فقط اندازهٔ فایل وزن.

### R20 — نصب و بازیابی قابلیت‌ها قرارداد نسخهٔ کافی ندارند — Medium

**[CONFIRMED]** نسخهٔ GNOME در [metadata.json](/mnt/ai_projects/KYRIN/integrations/gnome-shell/active-app@kyrin.local/metadata.json:5) به `50` محدود است و حداقل Python برابر `3.14` است. lockfile و workflow CI در فایل‌های نسخه‌دار بررسی‌شده وجود ندارد. بنابراین «پشتیبانی عمومی از هر Ubuntu» از کد نتیجه نمی‌شود.

**[CONFIRMED]** انتخاب چند factory مشاهده/کنترل در [main.py](/mnt/ai_projects/KYRIN/src/kyrin/app/qt/main.py:366) به availability زمان startup وابسته است؛ فقط برخی قابلیت‌ها بعداً کشف می‌شوند. **[LIKELY]** فعال‌شدن دیرهنگام extension می‌تواند بدون restart قابلیت‌ها را ناقص باقی بگذارد. سند پروژه نیز تفاوت فایل نصب‌شده با ماژول واقعاً بارشده را گزارش کرده است: [PROJECT_CONTEXT.md](/mnt/ai_projects/KYRIN/PROJECT_CONTEXT.md:85).

**اصلاح پیشنهادی:** startup probe بدون input، `GetCapabilities/ProtocolVersion`، تشخیص session، retry محدود برای سرویس دیررس و گزارش نسخهٔ بارشده اضافه شود. فایل نصب‌شده و فرایند فعال جدا نمایش داده شوند. نسخه‌های runtimeها و hash مدل‌های مورد آزمون در manifest ثبت شوند؛ artifactهای حجیم مطابق سیاست پروژه روی `/mnt/ai_projects/KYRIN/` بمانند.

### R21 — بعضی مدل‌های OCR کد محلی مدل را با اعتماد کامل بار می‌کنند — Medium

**[CONFIRMED]** [document_worker.py](/mnt/ai_projects/KYRIN/src/kyrin/vision/ocr/backends/document_worker.py:145) از `trust_remote_code=True` همراه `local_files_only=True` استفاده می‌کند. حالت offline دانلود را محدود می‌کند، ولی مانع اجرای کد داخل مدل نمی‌شود. subprocess با همان user نیز sandbox امنیتی کامل نیست.

**اصلاح پیشنهادی:** provenance و hash بستهٔ مدل/runtime ثبت و فقط artifact بررسی‌شده بار شود؛ برای worker پردازش اسناد، دسترسی فایل و شبکه متناسب با نیاز محدود شود. **هیچ مدل مخرب یا سرقت اطلاعاتی در این بررسی کشف یا اثبات نشده است.**

### R22 — پیچیدگی در چند نقطهٔ مرکزی متمرکز شده است — Medium

**[CONFIRMED]** با شمارش AST، `DemoCommandInterpreter.interpret` حدود ۷۴۰ خط، `UbuntuSessionFactory.__call__` حدود ۵۸۰ خط، `CommandCoordinator.observe` حدود ۳۳۱ خط و `ModelAssistedInterpreter.interpret` حدود ۲۹۷ خط است. [demo_interpreter.py](/mnt/ai_projects/KYRIN/src/kyrin/commands/demo_interpreter.py:213)، [ubuntu.py](/mnt/ai_projects/KYRIN/src/kyrin/app/platforms/ubuntu.py:271)، [coordinator.py](/mnt/ai_projects/KYRIN/src/kyrin/commands/coordinator.py:107)، [model_interpreter.py](/mnt/ai_projects/KYRIN/src/kyrin/commands/model_interpreter.py:195).

**پیامد قابل مشاهده:** بررسی مشترک عملیات در یک شاخه انجام می‌شود و در شاخهٔ دیگر جا می‌ماند؛ دو مسیر کلیک قرارداد هندسی متفاوت پیدا کرده‌اند. این صرفاً سلیقهٔ نام‌گذاری نیست. **اصلاح پیشنهادی:** ابتدا validator مشترک، geometry مشترک و lifecycle درخواست را استخراج کنید؛ سپس handlerهای operation را جدا کنید. تغییر نام `DemoCommandInterpreter` به نامی مطابق نقش production، اولویت پایین‌تری از اصلاح رفتار دارد. وجود Protocolها، type annotation و dependency injection فعلی مبنای مناسب این تفکیک است.

### R23 — پوشش تست فراوان است، اما مرزهای اتصال نیاز به تست تازه دارند — Medium

**[CONFIRMED]** تست‌های geometry، pointer delay، permission، model failure و صف وجود دارند؛ از جمله [test_desktop_control_helper.py](/mnt/ai_projects/KYRIN/tests/actions/test_desktop_control_helper.py:30)، [test_model_interpreter.py](/mnt/ai_projects/KYRIN/tests/commands/test_model_interpreter.py:527) و [test_queued_dispatch.py](/mnt/ai_projects/KYRIN/tests/actions/test_queued_dispatch.py:39). تست‌های فعلی helper حتی سایه را پوشش می‌دهند؛ ادعای «پروژه تست ندارد» غلط است.

**[CONFIRMED]** با این حال بازتولیدهای R01، R02، R11 و R12 در ترکیب اجزا شکست منطقی نشان دادند. **اصلاح پیشنهادی:** تست‌های قرارداد میان لایه‌ها اولویت بگیرند: خروجی متناقض مدل، EOF در زمان اجرای کند، لغو هنگام inference/portal، دو پنجرهٔ یک PID، scale همراه سایه و OCR پایان‌یافته پس از timeout. mockهای موفق جای تست واقعی portal/extension را نگیرند؛ دو سطح deterministic و hardware acceptance جدا گزارش شوند.

### R24 — نام‌گذاری و تشخیص خطا را می‌توان پس از اصلاح رفتار ساده‌تر کرد — Low

**[CONFIRMED]** عنوان «Demo» برای interpreter اصلی، تفاوت `ready` با «قابل استفاده بودن فقط accessibility»، و چند تبدیل متفاوت `None/False/UNKNOWN` فهم خطا را دشوار می‌کنند؛ [demo_interpreter.py](/mnt/ai_projects/KYRIN/src/kyrin/commands/demo_interpreter.py:213)، [chat_verifier.py](/mnt/ai_projects/KYRIN/src/kyrin/app/qt/chat_verifier.py:192). **پیشنهاد:** خطاهای ساخت‌یافتهٔ `permission_denied / no_match / ambiguous / stale / timeout / backend_unavailable` حفظ شوند و پیام کاربر از علت فنی جدا باشد. log مدت و کلاس خطا کافی است؛ ذخیرهٔ پیش‌فرض متن صفحه یا screenshot برای debug لازم نیست.

## ۶. تشخیص دقیق مسئلهٔ کلیک و انتخاب جایگزین

### چرا «متن را پیدا کن و مرکز آن را بزن» کافی نیست؟

| عامل | وضعیت در این نسخه | نتیجهٔ مهندسی |
|---|---|---|
| کیفیت OCR و confidence | `[CONFIRMED]` محدودیت آستانه و زبان در R08؛ اصلاح quotation و overlap قبلاً انجام شده است. | patchهای حل‌شده را تکرار نکنید؛ corpus فارسی/انگلیسی و calibration لازم است. |
| وجود متن تکراری | `[CONFIRMED]` `unique_visible_target` فقط یک تطابقِ پذیرفته‌شده می‌خواهد؛ [visible_control.py](/mnt/ai_projects/KYRIN/src/kyrin/actions/visible_control.py:79). | رد کردن ambiguity درست است؛ انتخاب اولین match راه‌حل نیست. parent/role/region/شناسهٔ پایدار برای رفع ابهام اضافه شود. |
| fuzzy matching | `[CONFIRMED]` lookup نهایی عمومی عمدتاً literal است، اما مدل می‌تواند label دیگری را از ID برگزیند؛ R01. | شباهت املایی فقط برای ساخت candidate استفاده شود؛ بدون شواهد مستقل به مجوز کلیک تبدیل نشود. |
| متن در برابر کنترل | `[CONFIRMED]` inventory OCR حتی متن غیرقابل کلیک را هم می‌تواند گزینه کند؛ توضیح خود تابع نیز این محدودیت را می‌گوید. | نقش، parent، شکل/ناحیه و پس‌شرط باید شواهد تکمیلی باشند. متن روی صفحه command نیست. |
| scale و DPI | `[CONFIRMED]` قرارداد فعلی محدود و heuristic است؛ R03. | واحد screenshot pixel، OCR pixel و logical desktop pixel باید جدا باشد. |
| crop و بزرگ‌نمایی | `[CONFIRMED]` تبدیل معکوس crop در reader وجود دارد، اما همهٔ اطلاعات هندسی تا Telegram نمی‌رسد؛ R04 و R09. | تمام تبدیل‌ها ترکیب‌پذیر و با metadata باشند؛ از double-scaling جلوگیری شود. |
| چند مانیتور | `[CONFIRMED]` frame مختصات signed دارد؛ مبدأ منفی به‌خودی‌خود در کد ممنوع نیست. `[SPECULATION]` mixed-DPI و پنجرهٔ spanning هنوز نیازمند آزمون واقعی‌اند. | خرابی همهٔ چندمانیتورها ادعا نمی‌شود. مانیتور سمت چپ/بالا، scale متفاوت و انتقال پنجره باید جدا آزموده شوند. |
| حرکت پنجره | `[CONFIRMED]` تغییر frame بررسی می‌شود؛ تغییر محتوای همان پنجره و هویت پنجرهٔ هم‌PID کامل پوشش ندارد؛ R05. | token و freshness مستقل از geometry لازم است. |
| آماده نبودن UI | `[CONFIRMED]` انتظار pointer و چند خواندن پایدار Telegram وجود دارد؛ پس‌شرط عمومی و deadline واحد نیست. | به event/state مشخص یا polling محدود وابسته شوید، نه sleep ثابتِ طولانی. |
| X11 و Wayland | `[CONFIRMED]` نشست فعلی Wayland و مسیر موجود portal/GNOME است. | adapter بر اساس قابلیت واقعی انتخاب شود؛ وجود executable معادل کارکرد آن نیست. |

در X11، ابزارهایی مانند `xdotool` برای ورودی قابل استفاده‌اند؛ همان ابزار راه‌حل عمومی برنامه‌های native Wayland نیست. خود پروژهٔ xdotool این محدودیت را توضیح می‌دهد. در Wayland مسیر portal یا backend پشتیبانی‌شدهٔ compositor لازم است. [مستندات xdotool](https://github.com/jordansissel/xdotool)، [RemoteDesktop portal](https://flatpak.github.io/xdg-desktop-portal/docs/doc-org.freedesktop.portal.RemoteDesktop.html).

**پیشنهاد هندسی:** این تبدیل فقط برای capture با scale یکنواخت مثال است؛ اگر تصویر ترکیبی از چند مانیتور با scale متفاوت باشد، تبدیل هر ناحیه باید جدا تعریف شود.

<div dir="ltr">

```text
ocr_point -> undo OCR resize -> add crop origin -> screenshot_point

desktop_x = capture_origin_x + (screenshot_x - padding_left_px) / scale_x
desktop_y = capture_origin_y + (screenshot_y - padding_top_px)  / scale_y

Required metadata:
  window_token, capture_id, captured_at_monotonic
  coordinate_space, monitor_id, logical_rect, image_size
  scale_x, scale_y, padding_px, crop_origin_px, ocr_resize
```

</div>

`padding` در این فرمول پیکسلِ تصویر و `capture_origin` مختصات منطقی ناحیهٔ بدون padding است. اگر backend تعریف دیگری دارد، قرارداد باید همان را صریح کند؛ نام مبهم `x/y` کافی نیست. نقطهٔ نهایی باید داخل target و viewport معتبر باشد و پیش از dispatch دوباره اعتبار آن بررسی شود.

### بهترین روش برای هر مورد

این جدول **پیشنهاد طراحی** است؛ برتری‌های سرعت و قابلیت اعتماد، مقایسهٔ ساختاری‌اند و benchmark اندازه‌گیری‌شدهٔ این ماشین نیستند.

| روش | بهترین کاربرد | مزیت | محدودیت و تصمیم پیشنهادی |
|---|---|---|---|
| API یا فرمان رسمی برنامه | عمل مشخص مانند بازکردن برنامه، ایجاد tab یا تعامل داده‌ای با سرویس | هدف و نتیجه ساخت‌یافته؛ بدون خطای pixel | معنای API باید با هدف کاربر یکی باشد؛ تغییر داده در سرویس معادل navigation پنجرهٔ دسکتاپ نیست. برای عملیات دارای API قابل اتکا، اولویت اول. |
| keyboard shortcut | navigation ثابت و شناخته‌شده پس از تأیید focus | سریع و کم‌هزینه؛ بدون OCR | context، layout کیبورد، shortcut سفارشی و dialog مهم‌اند؛ shortcut باید در نسخهٔ هدف بررسی و نتیجه مشاهده شود. adapterهای فعلی Telegram/Ptyxis نقطهٔ شروع‌اند. |
| AT-SPI semantic action | کنترل استاندارد با name/role/action/state معتبر | شناسایی مستقل از theme و scale؛ امکان خواندن state | همهٔ برنامه‌ها tree خوب ندارند؛ virtualized UI، widget سفارشی و تنظیم accessibility ممکن است مانع باشند. مسیر پیش‌فرض کنترل عمومی پس از اصلاح R07. |
| OCR همراه شواهد ساختاری | کنترل دارای label که accessibility مناسبی ندارد | محلی، نسبتاً سبک، قابل استفاده برای فارسی و انگلیسی با مدل درست | متن به‌تنهایی clickable بودن را ثابت نمی‌کند؛ duplicates، segmentation و geometry باقی می‌مانند. fallback هدفمند روی ناحیهٔ کوچک. |
| template matching / icon detection | آیکون ثابت در toolbar مشخص و theme/version معلوم | CPU کم‌هزینه و بدون LLM؛ برای عناصر بدون متن مفید | template با theme، scale و حالت hover تغییر می‌کند؛ چند scale و نمونهٔ منفی لازم است. الگوریتم match امتیاز شباهت می‌دهد، احتمال موفقیت عمل نمی‌دهد. |
| VLM برای UI grounding | رابط سفارشی، canvas یا کنترل تصویریِ فاقد شواهد کافی | candidate تولید می‌کند و توصیف بصری را به ناحیه ربط می‌دهد | latency، VRAM، خطای مکان‌یابی و دستورهای فریبندهٔ داخل تصویر؛ فقط candidate با bbox، crop و شاهد تولید کند و از policy عبور کند. |
| ترکیب محدود روش‌ها | استفادهٔ واقعی روزانه در چند برنامه | استفاده از ارزان‌ترین شاهد کافی؛ fallback قابل توضیح | نیازمند قرارداد واحد و ثبت علت شکست؛ اجرای همهٔ backendها در هر درخواست توصیه نمی‌شود. |

**AT-SPI برای OpenRGB تضمین نیست.** `[CONFIRMED]` سند پروژه می‌گوید در بررسی قبلی tree فاقد کنترل‌های نام‌دار بوده است. `[SPECULATION]` ممکن است تنظیم accessibility Qt، نسخهٔ برنامه یا widget سفارشی علت باشد؛ برای تشخیص، tree همان نسخه با تنظیم فعال‌سازی accessibility بررسی شود. Qt برای Linux وضعیت accessibility روی D-Bus و متغیر `QT_LINUX_ACCESSIBILITY_ALWAYS_ON` را مستند کرده است، اما فعال‌سازی آن برای widget فاقد پیاده‌سازی مناسب معجزه نمی‌کند. [مستندات QAccessible](https://doc.qt.io/qt-6/qaccessible.html).

برای template matching از جست‌وجوی محدود در ROI و مجموعهٔ template وابسته به theme/scale استفاده شود؛ تبدیل bbox آن باید دقیقاً از همان geometry مشترک عبور کند. منبع الگوریتم: [راهنمای رسمی OpenCV](https://docs.opencv.org/4.13.0/d4/dc6/tutorial_py_template_matching.html).

برای VLM، مدل‌های تخصصی GUI مانند [UI-TARS-1.5-7B](https://huggingface.co/ByteDance-Seed/UI-TARS-1.5-7B) نمونهٔ قابل ارزیابی‌اند، نه پیشنهاد نصب فوری برای GPU محدود. حتی برآورد وزن خام ۴بیتی، حافظهٔ activation، KV cache، encoder تصویر و سربار runtime را شامل نمی‌شود. `[SPECULATION]` اینکه مدل کوچک‌تر یا quantized روی این دستگاه هم سریع و هم دقیق باشد، فقط با corpus خود Kyrin مشخص می‌شود. ابتدا crop محدود و اجرای on-demand بررسی شود؛ CPU fallback برای VLM هم الزاماً interactive نیست.

### Telegram: کجا API بهتر است؟

**پیشنهاد:** برای «این chat را در Telegram Desktop نشان بده»، shortcut و adapter رابط دسکتاپ با verification مناسب‌اند. برای «فهرست chatها را بخوان» یا تعامل ساخت‌یافته با دادهٔ حساب، TDLib می‌تواند مسیر جداگانه‌ای باشد. **Bot API جای حساب شخصی را نمی‌گیرد**؛ TDLib نیز یک client با ورود، مجوز و state مستقل می‌سازد و به‌طور خودکار پنجرهٔ Telegram Desktop را روی همان صفحه نمی‌برد. تغییرات UI و تنظیمات محلی دسکتاپ لزوماً API معادل ندارند. انتخاب این مسیر باید بر اساس نیاز محصول باشد، نه صرفاً فرار از OCR. [APIهای رسمی Telegram](https://core.telegram.org/)، [شروع کار با TDLib](https://core.telegram.org/tdlib/getting-started).

### خط لولهٔ کلیک پیشنهادی

<div dir="ltr">

```text
User intent
    -> validate operation + requested target
    -> observe current window + capabilities
    -> locate candidates (API / shortcut / AT-SPI / OCR / icon / VLM)
    -> resolve ambiguity + bind target to evidence
    -> check policy + precondition + deadline + cancellation
    -> revalidate window/target immediately before dispatch
    -> execute once
    -> observe semantic postcondition
    -> CONFIRMED | DISPATCHED_UNVERIFIED | FAILED | CANCELLED
                     |
                     +-> bounded recovery only when safe
```

</div>

۱. **مشاهده:** یک snapshot دارای token، timestamp، geometry و capability بگیرید. برای action دسترس‌پذیری، screenshot اجباری نباشد. اگر ابتدا dialog مجوز portal باز می‌شود، snapshot قبل از آن مصرف نشود؛ بعد از بازگشت دوباره مشاهده کنید.

۲. **مکان‌یابی:** برای عمل شناخته‌شده، adapter رسمی/shortcut؛ برای کنترل عمومی، AT-SPI؛ سپس OCR یا icon در ROI؛ و فقط در صورت نیاز VLM. شکست هر روش باید `unavailable`، `no_match` یا `ambiguous` را از هم جدا کند.

۳. **تطبیق درخواست:** `requested_target` و `observed_target` جدا حفظ شوند. similarity بالا بدون نقش/parent/operation معتبر کافی نیست. در ambiguity، نام parent یا گزینه‌ها برای رفع ابهام استفاده شود؛ انتخاب خودکار اولین یا نزدیک‌ترین متن ممنوع باشد.

۴. **بررسی پیش از عمل:** پنجره، focus، generation، state، مهلت و permission دوباره بررسی شوند. اگر کاربر pointer یا focus را جابه‌جا کرده است، درخواست قدیمی دوباره locate شود یا متوقف گردد؛ ورودی کاربر نباید با تصحیح پی‌درپی pointer خنثی شود.

۵. **اجرا:** `do_action/select/set_value` در صورت پشتیبانی؛ در غیر این صورت حرکت و click از actuator مشترک. در portal، `NotifyPointerMotionAbsolute` مختصات نسبت به PipeWire stream می‌خواهد؛ جایگزین مستقیم مختصات global فعلی نیست. backend باید فضای مختصات خود را اعلام کند. [قرارداد مختصات portal](https://flatpak.github.io/xdg-desktop-portal/docs/doc-org.freedesktop.portal.RemoteDesktop.html).

۶. **بررسی نتیجه:** برای toggle مقدار نهایی؛ برای بازکردن settings، وجود dialog یا عنوان و کنترل مشخص؛ برای chat، شناسه یا شواهد یکتای header؛ برای Apply، state قابل مشاهدهٔ برنامه در صورت دسترسی. اگر نتیجه قابل مشاهده نیست، همان `DISPATCHED_UNVERIFIED` باقی بماند. image diff به‌تنهایی معیار موفقیت نباشد.

۷. **بازیابی محدود:** اگر ثابت شده input ارسال نشده، یک locate مجدد یا strategy بعدی مجاز است. اگر input ارسال شده ولی نتیجه نامعلوم است، ابتدا وضعیت فعلی بررسی شود؛ **کلیک دوبارهٔ toggle، Send، Delete یا Buy تکرار امن نیست.** برای عمل واقعاً idempotent می‌توان یک retry محدود با بودجهٔ مشترک داشت. «سه strategy، پس سه click» سیاست عمومی مناسبی نیست.

**قرارداد پیشنهادی نتیجه:** به‌جای `bool` تنها، نتیجه دارای `request_id`، `strategy`، `target_evidence`، `dispatch_state`، `postcondition_state`، `failure_reason` و timings باشد. API سادهٔ `click_element(...) -> bool` می‌تواند فقط wrapper بیرونی باشد؛ حذف جزئیات در لایهٔ داخلی امکان recovery صحیح را از بین می‌برد.

## ۷. خط لولهٔ صوت و تخصیص منابع

### زمان‌بندی فعلی: تنظیمات با اندازه‌گیری اشتباه نشوند

| مرحله | واقعیت مشاهده‌شده | اقدام پیشنهادی |
|---|---|---|
| بیدارباش | `[CONFIRMED]` حالت standby فرمان‌های متنیِ پس از STT را فیلتر می‌کند؛ wake-word detector صوتیِ مستقل در این مسیر نیست. [command_runtime.py](/mnt/ai_projects/KYRIN/src/kyrin/runtime/command_runtime.py:193)، [voice_control.py](/mnt/ai_projects/KYRIN/src/kyrin/runtime/voice_control.py:1). | اگر مصرف دائمی STT مسئله است، wake detector سبک CPU به‌صورت اختیاری اضافه شود؛ حساسیت و false wake فارسی سنجیده شود. |
| دریافت و VAD | `[CONFIRMED]` Silero و framing ۱۶ کیلوهرتز با قاب ۵۱۲ نمونه، یعنی ۳۲ms؛ تأیید شروع پیش‌فرض ۶۴ms است. [silero_vad.py](/mnt/ai_projects/KYRIN/src/kyrin/audio/activity/silero_vad.py:1)، [live_speech_pipeline.py](/mnt/ai_projects/KYRIN/src/kyrin/audio/live_speech_pipeline.py:53). | VAD روی CPU بماند؛ latency صوت با timestamp capture سنجیده شود. |
| پایان گفتار | `[CONFIRMED]` pause پیش‌فرض ۳۸۴ms و برای backend موسوم به `omnilingual` برابر ۸۰۰ms است. [ubuntu.py](/mnt/ai_projects/KYRIN/src/kyrin/app/platforms/ubuntu.py:592). | این زمان بخش مستقیم تأخیر پس از آخرین کلمه است؛ کاهش آن با نرخ جملهٔ ناقص و split فارسی ارزیابی شود. |
| STT زنده | `[CONFIRMED]` Whisper از ۰٫۵s pre-roll و partialهای با شروع ۱٫۵s و فاصلهٔ ۲٫۵s استفاده می‌کند؛ پنجرهٔ preview تا ۸s و turn تا ۳۰s. [whisper.py](/mnt/ai_projects/KYRIN/src/kyrin/stt/backends/whisper.py:32). | partial و final محاسبات مجزا دارند؛ هزینهٔ preview سنجیده شود. برای کاربر بی‌نیاز از preview، خاموش‌کردن یا کاهش بسامد آن می‌تواند مفید باشد. |
| transport STT | `[CONFIRMED]` timeout درخواست Whisper server برابر ۸s است. [whisper_server.py](/mnt/ai_projects/KYRIN/src/kyrin/stt/backends/whisper_server.py:187). | timeout و مدل انتخابی باید با سرعت واقعی CPU/GPU سازگار باشند؛ CPU کند با افزایش timeout به دستیار سریع تبدیل نمی‌شود. |
| فهم فرمان | `[CONFIRMED]` fast rules از LLM عبور نمی‌کند؛ مسیر مدل timeoutهای ۶۰/۱۲۰s و گاهی دو inference دارد. | فرمان‌های رایج با قواعد باقی بمانند؛ inference در worker مستقل و با بودجهٔ زمان محصول اجرا شود. |
| اجرای GUI | `[CONFIRMED]` inventory، capture، OCR، ساخت helper، portal و verification ممکن است چندبار پشت سر هم رخ دهند. | AT-SPI و shortcut، reuse نشست ورودی و cache فقط برای metadata پایدار؛ مختصات قدیمی cache نشوند. |
| TTS | `[CONFIRMED]` صف مستقل وجود دارد، ولی synthesis و پخش مراحل جدا و زمان تا اولین نمونه هنوز جدا گزارش نمی‌شود. [speech.py](/mnt/ai_projects/KYRIN/src/kyrin/responses/speech.py:83). | پاسخ‌های کوتاه، TTS سبک CPU، prewarm محدود و لغو سریع؛ پاسخ توضیحی طولانی نباید مانع شنیدن فرمان شود. |

مدل ذهنی اندازه‌گیریِ پیشنهادی:

<div dir="ltr">

```text
last spoken sample -> endpoint/VAD wait -> STT final
  -> interpretation queue + inference
  -> action queue + locate + dispatch + postcondition

first audible response = response-ready + TTS queue + synthesis-to-first-audio
```

</div>

**[CONFIRMED، منبع مستندات؛ بازاندازه‌گیری نشده]** [LIVE_PATH_COMPARISON.md](/mnt/ai_projects/KYRIN/docs/stt/LIVE_PATH_COMPARISON.md:92) برای چهار clip روی GPU گرم، تأخیر اولین final نسبت به پایان فایل را حدود `0.10s` برای `small` و `0.24s` برای `turbo-q5` گزارش می‌کند؛ همان سند برای CPU `small` حدود `10.4–11.4s` و برای درخواست مستقیم دیگر `8.23s` inference گزارش کرده است. این‌ها latency پایان‌به‌پایان فرمان یا آمار عمومی فارسی نیستند. [CONVERSATION_MEMORY.md](/mnt/ai_projects/KYRIN/docs/commands/CONVERSATION_MEMORY.md:75) نیز یک آزمایش warm با executor بی‌اثر و زمان حدود `1100.60ms` از شروع تأییدشدهٔ گفتار دارد؛ زمان واقعی بازشدن Telegram را اندازه نمی‌گیرد.

**هدف اولیهٔ پیشنهادی، نه ادعای عملکرد فعلی:** برای فرمان کوتاهِ مسیر قواعد، p95 از آخرین نمونهٔ گفتار تا آغاز اجرای عمل حدود ۱٫۵ ثانیه یا کمتر هدف‌گذاری شود؛ برای قطع خروجی صوتی پس از تشخیص گفتار معتبر، حدود ۲۰۰ms یا کمتر. اگر سخت‌افزار/زبان این هدف را نمی‌دهد، stageهای اندازه‌گیری‌شده نشان دهند کدام بخش باید تغییر کند. برای کل عملیات GUI، زمان پس‌شرط جدا گزارش شود؛ اعلام «انجام شد» را جلو نیندازید تا عدد latency زیباتر شود.

### محلی یا ابری، CPU یا GPU؟

این جدول **پیشنهاد برای محدودیت VRAM** است؛ انتخاب قطعی مدل به benchmark محلی نیاز دارد.

| جزء | انتخاب پیشنهادی | دلیل و شرط |
|---|---|---|
| VAD و wake detector اختیاری | CPU، مدل کوچک و همیشه آماده | نباید برای منابع با STT رقابت کند. openWakeWord نمونهٔ متن‌باز قابل بررسی است، ولی مدل‌های آمادهٔ فعلی آن طبق مستندات عمدتاً انگلیسی‌اند؛ بیدارباش فارسی/نام Kyrin نیازمند ارزیابی یا آموزش اختصاصی است. [مخزن رسمی](https://github.com/dscripka/openWakeWord). |
| STT | GPU برای کوچک‌ترین مدل چندزبانه‌ای که آزمون فارسی را می‌گذراند | تشخیص نفی، نام برنامه و نام مخاطب از امتیاز WER کلی مهم‌تر است. quantization را با افت دقت بسنجید؛ `whisper.cpp` رسماً quantization را پشتیبانی می‌کند. [مخزن رسمی](https://github.com/ggml-org/whisper.cpp#quantization). |
| فهم فرمان رایج | قواعد روی CPU | latency و رفتار قابل آزمون؛ مسیر موجود حفظ شود. |
| فهم انعطاف‌پذیر | مدل محلی کوچک با خروجی schemaدار؛ CPU یا بارگذاری محدود GPU | اگر GPU فقط یک مدل تعاملی را جا می‌دهد، STT اولویت دارد. کوچک بودن مدل، نیاز به validator مستقل را حذف نمی‌کند. |
| TTS | backend سبک موجود، ترجیحاً CPU و یک یا دو صدای لازم | کیفیت صدای لوکس نباید باعث قطع شنیدن یا جابه‌جایی مداوم STT شود. فارسی باید با صدای دارای پشتیبانی واقعی آزمایش شود. |
| OCR | Tesseract یا recognizer سبک روی CPU و crop هدفمند | backend سندی/VLM سنگین را برای هر کلیک روشن نکنید؛ latency cold و warm جدا سنجیده شود. |
| VLM | on-demand، بعد از شکست روش‌های ارزان | قبل از load، ظرفیت حافظه و امکان آزادسازی مدل غیرضروری بررسی شود؛ residency هم‌زمان همهٔ مدل‌ها مطلوب نیست. |
| cloud | مسیر اختیاریِ صریح برای نیاز مشخص، نه پیش‌فرض | ممکن است compute محلی را کم کند، اما شبکه، هزینه، دسترسی سرویس و انتقال صوت/تصویر به آن وابسته می‌شوند. برتری latency یا رایگان‌بودن دائمی فرض نشود. |

**پیشنهاد barge-in:** capture و VAD هنگام synthesis/pخش زنده بمانند؛ AEC از خروجی واقعی مرجع بگیرد؛ آغاز گفتار معتبر فقط TTS را متوقف کند، سپس STT ادامهٔ فرمان را بفهمد. فرمان لغوِ عمل از interrupt خروجی جدا باشد. هنگام نبود AEC، قابلیت half-duplex و توقف دستی واضح‌تر و قابل اعتمادتر از ادعای شنیدن هم‌زمان است.

## ۸. امنیت و شکست نیمه‌کاره

| موضوع | ارزیابی مبتنی بر کد | تصمیم پیشنهادی |
|---|---|---|
| allowlist | `[CONFIRMED]` `ActionPolicy` فهرست برنامه و operation دارد و policy خالی منع می‌کند؛ [gate.py](/mnt/ai_projects/KYRIN/src/kyrin/actions/gate.py:25). | این مرز حفظ و تا endpoint مجری امتداد داده شود؛ خروجی مدل مستقیماً capability نسازد. |
| shell و sudo | `[CONFIRMED]` مسیر آزاد shell از voice در این checkout دیده نشد؛ Ptyxis آرگومان‌های ثابت دارد. | اگر بعداً افزوده شد، ابزارهای محدود با argv نوع‌دار، cwd مشخص، timeout و پیش‌نمایش عمل حساس ارائه شوند. `subprocess.run([...])` به‌تنهایی محتوای خطرناک argv یک shell را امن نمی‌کند. |
| بستن برنامهٔ دارای دادهٔ ذخیره‌نشده | `[CONFIRMED]` تأیید ویژهٔ Terminal وجود دارد؛ برای هر برنامهٔ مجاز چنین تأییدی در `_review_window_action` نیست. [demo_interpreter.py](/mnt/ai_projects/KYRIN/src/kyrin/commands/demo_interpreter.py:1081). GNOME از `window.delete` استفاده می‌کند، نه kill اجباری. | `[LIKELY]` برنامه ممکن است dialog ذخیره نشان دهد؛ تشخیص unsaved state عمومی تضمین نشده است. بسته‌شدن پنجره یا dialog تأیید باید مشاهده شود؛ force close خودکار افزوده نشود. |
| خاموشی و restart | `[CONFIRMED]` جریان مستقل دو تأییدی با timeout و لغو دارد؛ [flow.py](/mnt/ai_projects/KYRIN/src/kyrin/system_power/flow.py:120). | الگوی request-bound و expiry آن برای اعمال حساس دیگر مفید است؛ «هیچ تأییدی وجود ندارد» دربارهٔ پروژه صحیح نیست. |
| تزریق از متن گفتار | `[CONFIRMED]` shell interpolation از transcript پیدا نشد، اما مرز معنایی R01/R02 ناقص است. | حمله یا خطای زبانی می‌تواند بدون shell injection هم به عمل نامطلوب برسد؛ schema و target binding هر دو لازم‌اند. |
| prompt injection از صفحه یا history | `[CONFIRMED]` context مدل شامل نام‌ها/متن و سابقه است. `[SPECULATION]` میزان موفقیت دستورهای فریبندهٔ داخل label، chat یا حافظه در این نسخه اندازه‌گیری نشده است. | محتوای صفحه و تاریخچه دادهٔ غیرقابل‌اعتماد باشند، نه دستور؛ corpus با labelهایی شبیه «ignore previous instructions» و خروجی مدل متناقض بسازید. policy مستقل باید اثر آن را محدود کند. |
| میکروفون و وب‌کم | `[CONFIRMED]` standby کنونی الزاماً به معنی بسته بودن میکروفون یا توقف STT نیست؛ R15 و بخش صوت. مسیر وب‌کم/تشخیص گوینده پیاده‌سازی‌شده دیده نشد. | UI میان «میکروفون خاموش»، «منتظر بیدارباش» و «فرمان فعال» فرق بگذارد. وب‌کم آینده مجوز و نشانگر مستقل، پردازش محلی و retention مشخص داشته باشد. |
| اطلاعات محرمانه | `[CONFIRMED]` تاریخچه متن را نگه می‌دارد؛ screenshot عادی از مسیر حافظه عبور می‌کند. tokenهای محلی و permission فایل به‌تنهایی sandbox در برابر فرایند مخرب همان user نیستند. [permission_token.py](/mnt/ai_projects/KYRIN/src/kyrin/app/permission_token.py:1). | transcript، screenshot و labelهای کامل پیش‌فرض وارد log نشوند. capture debug فقط opt-in، محدود و قابل حذف باشد؛ در صورت افزودن TDLib، session credential جدا از تاریخچه و log نگهداری شود. |
| قطع permission یا خرابی وسط عمل | `[CONFIRMED]` چند executor نتیجهٔ `UNKNOWN` را از failure قطعی جدا می‌کنند؛ R06 و R14 نشان می‌دهند همهٔ lifecycleها یکپارچه نیستند. | اگر ارسال input محتمل است، retry کور نکنید. read-back یا reconciliation انجام شود؛ گزارش شامل مرحلهٔ آخرِ قطعی باشد. |

**پیشنهاد دربارهٔ هویت:** تشخیص چهره یا گوینده در آینده می‌تواند context و تجربهٔ کاربری را بهتر کند، اما به‌تنهایی مجوز shell، حذف فایل یا ارسال پیام نباشد. احراز هویت و تشخیص اینکه «چه کسی احتمالاً صحبت کرد» دو قرارداد متفاوت‌اند. این یک پیشنهاد طراحی است؛ آسیب‌پذیری مربوط به قابلیت هنوز پیاده‌سازی‌نشده ادعا نمی‌شود.

## ۹. معماری پیشنهادی و مقایسه با وضع موجود

**[CONFIRMED] وضع موجود:** لایه‌های audio/STT/command/action از هم جدا هستند، Protocol و dependency injection استفاده شده و action worker ترتیب اجرا را حفظ می‌کند. ضعف اصلی در قرارداد مشترک state، deadline، geometry، cancellation و verification است. بنابراین مهاجرت تدریجی کم‌ریسک‌تر از ساخت مجدد کل پروژه است.

| گزینه | نسبت به وضع موجود | مزایا | هزینه و محدودیت | ارزیابی |
|---|---|---|---|---|
| **۱. یکپارچهٔ ماژولار و رویدادمحور با ابزارهای نوع‌دار** | مصرف صوت و کنترل فوری از inference جدا؛ یک broker مالک ورودی OS؛ locator/actuator/verifier قابل تعویض | استفادهٔ مجدد از بیشتر کد؛ لغو و مشاهدهٔ منسجم؛ تست قرارداد ساده‌تر؛ مناسب latency و VRAM محدود | نیازمند تعریف lifecycle و تبدیل تدریجی executorها؛ async/thread correctness باید آزموده شود | **پیشنهاد اصلی.** تلاش متوسط، قابل تقسیم به گام‌های کوچک. |
| **۲. معماری ابزارمحور با adapter عمیق برای برنامه‌های منتخب** | API/shortcut/AT-SPI اختصاصی پشت همان Tool interface؛ مثلاً TDLib برای نیاز داده‌ای Telegram | قابلیت اعتماد بالاتر در چند کار پرتکرار؛ کاهش OCR و inference | توسعه و نگهداری adapterها، ورود و credentialهای API، پوشش محدودتر برنامه‌ها؛ API همیشه UI را کنترل نمی‌کند | مکمل گزینهٔ ۱ برای کارهای پرتکرار. تلاش متوسط تا زیاد به ازای هر integration. |
| **۳. agent تصویری با حلقهٔ VLM در مرکز** | screenshot و مدل، اقدام بعدی را در هر مرحله پیشنهاد می‌کنند | انعطاف رابط‌های ناشناخته؛ کاهش ruleهای برخی layoutها | latency و VRAM بیشتر، رفتار کم‌قطعیت‌تر، هزینهٔ validation و recovery؛ همچنان به geometry/policy/verification نیاز دارد | برای مرحلهٔ فعلی توصیه نمی‌شود. بعداً fallback محدود یا آزمایش جدا. تلاش زیاد. |

این برآوردها نسبی‌اند؛ زمان تقویمی بدون اندازهٔ تیم، سطح آشنایی و acceptance matrix قابل اتکا نیست. افزودن framework چندعاملی یا orchestration سنگین برای رفع مشکلات فعلی ضروری نیست.

### مرزهای پیشنهادی گزینهٔ اول

- **Audio service:** فقط acquisition، preprocessing، VAD و transcript event؛ جدایی `AudioInput` و `MicrophoneInput` حفظ شود.
- **Interaction controller:** state machine روشن برای standby، listening، interpreting، executing، waiting-confirmation و stopping؛ eventهای لغو اولویت داشته باشند.
- **Interpreter worker:** rules یا مدل، فقط پیشنهاد `ToolCall` نوع‌دار؛ بدون دسترسی مستقیم به ماوس، shell یا مجوزها.
- **Tool registry:** برای هر ابزار schema، permission، risk، precondition، postcondition، deadline و retry policy ثبت شود. plugin به معنی ماژول داخلی با قرارداد ثابت است؛ سیستم نصب افزونهٔ پیچیده فعلاً لازم نیست.
- **Observation service:** AT-SPI، screenshot/OCR و اطلاعات پنجره با token و timestamp مشترک؛ cache فقط تا وقتی اعتبار آن اثبات می‌شود.
- **Action broker:** تنها نویسندهٔ ورودی سیستم‌عامل، دارای capability و cancellation؛ adapterها تعیین می‌کنند «چه عملی»، broker تضمین می‌کند «با چه مجوز و کدام مشاهده».
- **Verifier:** نتیجهٔ معنایی را تعیین کند و وضعیت نامعلوم را حفظ کند؛ ابزار بعدی تنها با dependency تحقق‌یافته اجرا شود.
- **Resource manager:** بودجهٔ CPU/GPU و residency مدل‌ها؛ warm-up قابل مشاهده و قابل لغو.

### حلقهٔ عامل و حافظه

**پیشنهاد حلقهٔ عامل:** `observe -> propose -> validate -> execute -> verify -> update state`، با سقف تعداد گام و deadline مشترک. plan بلند از یک screenshot ساخته و بی‌وقفه اجرا نشود. پس از هر عملِ تغییردهندهٔ UI، مراحل وابسته با وضعیت تازه resolve شوند. recovery هم ابزار و policy داشته باشد؛ «وقتی شکست خورد هرچه مدل گفت انجام بده» fallback معتبر نیست.

**پیشنهاد حافظه:** SQLite فعلی حفظ شود و سه مفهوم جدا شود: تاریخچهٔ خام اختیاری، رویدادهای ساخت‌یافتهٔ عمل/نتیجه، و ترجیحات صریح کاربر. هر مورد provenance، زمان، TTL و سطح اعتماد داشته باشد. retrieval برای فهم «همان برنامه» مفید است، ولی نباید از گفت‌وگوی قدیمی مجوز تازه استخراج کند. برای این اندازهٔ پروژه، افزودن vector database پیش از تعریف semantics حافظه ضرورتی ندارد.

**پیشنهاد وب‌کم آینده:** پردازش frame با نرخ و صف محدود، حذف frame قدیمی، worker مستقل و مدل سبک CPU/ONNX در صورت کفایت؛ frameهای vision نباید صوت را عقب بیندازند. eventهای gesture و identity نیز مثل transcript صرفاً شواهد باشند و از همان gate عبور کنند. این مرحله بعد از پایدارشدن ابزار و cancel اجرا شود.

## ۱۰. برنامهٔ اقدام و مهاجرت

### فهرست اولویت اجرایی

جزئیات «محل، علت و اصلاح» هر مورد در Rهای بالا آمده است؛ این جدول ترتیب انجام را مشخص می‌کند.

| اولویت | موارد | خروجی مورد انتظار |
|---|---|---|
| **Critical** | R01 | خروجی متناقض مدل نتواند هدف دیگری را به عمل تبدیل کند. |
| **High — نوبت اول** | R03، R04، R05، R06، R07 | کلیک با geometry مشترک، هویت پنجره، AT-SPI واقعی و پس‌شرط؛ رفع مسئلهٔ اصلی محصول. |
| **High — هم‌زمان با مرز اجرای امن** | R02، R11، R12، R13 | نفی محترم بماند، standby اثر فوری روی صف داشته باشد، EOF فرمان را حذف نکند، کنترل حساس بدون policy عبور نکند. |
| **High — نوبت دوم** | R08، R09، R10، R14، R15 | OCR سازگارتر، UI آماده، مدل غیرمسدودکننده، deadline واقعی و قطع پاسخ صوتی قابل اتکا. |
| **Medium** | R16 تا R23 | مجوز endpoint، retention، metrics دقیق، مدیریت منابع، نسخهٔ نصب‌شده و تست اتصال اجزا. |
| **Low** | R24 | نام‌گذاری و پیام خطای روشن، پس از تثبیت قراردادهای رفتاری. |

### مراحل مهاجرت پیشنهادی

۱. **ثبت baseline قابل تکرار.** نسخهٔ source و extension فعال، session، scale، مدل و compute device را ثبت کنید. مجموعه‌ای کوچک از سناریوهای واقعی OpenRGB، Telegram و یک برنامهٔ استاندارد بسازید. خروجی هر آزمایش شامل موفقیت وظیفه، کلیک اشتباه، ambiguity، abstention و latency باشد. معیار اتمام: شکست‌های شناخته‌شده قبل از اصلاح، با ورودی و نسخهٔ مشخص قابل توضیح باشند.

۲. **بستن مرز اعتبارسنجی و صف.** R01/R02/R11/R12/R13 با تست‌های ساختگیِ مستقل از دسکتاپ اصلاح شوند. `drain` و `cancel` جدا شوند؛ generation در interpret و dispatch بررسی شود. معیار اتمام: بازتولیدهای گزارش دیگر عمل نامعتبر تولید نکنند و پایان فایل تمام فرمان‌های پذیرفته‌شده را تعیین تکلیف کند.

۳. **یکسان‌کردن Observation و Geometry.** token پنجره، زمان، capture transform و target evidence مشترک شوند؛ Telegram و کنترل عمومی همان قرارداد را مصرف کنند. معیار اتمام: scaleهای مختلف، سایه، crop، مبدأ منفی و پنجرهٔ جابه‌جاشده در آزمون هندسی مستقل پاس شوند؛ یک acceptance زنده روی Wayland هم نتیجه را تأیید کند.

۴. **جداکردن Locate، Execute و Verify.** AT-SPI action را به مسیر اول کنترل عمومی تبدیل کنید؛ OCR و icon فقط fallback باشند. برای چند operation پرکاربرد پس‌شرط واقعی تعریف کنید. معیار اتمام: dispatch بدون نتیجهٔ مشاهده‌شده موفقیت قطعی اعلام نشود و عمل dependent قبل از پس‌شرط شروع نشود.

۵. **یکپارچه‌کردن lifecycle و deadline.** inference از event consumer جدا، OCR قابل لغو و broker ورودی دارای token شود. worker پایدار برای backend سنگین فقط پس از داشتن shutdown صحیح اضافه شود. معیار اتمام: stop در هنگام OCR، inference و portal، خروجی قدیمی را از dispatch منع کند؛ worker منقضی مانع درخواست بعدی نماند.

۶. **بهینه‌سازی صوت بر اساس عدد.** markerهای R18، بار منابع، هزینهٔ partial و AEC برای میکروفون انتخابی بررسی شوند. مدل کوچک‌تر با آزمون دقت فارسی/نفی انتخاب شود. معیار اتمام: p50/p95 مرحله‌ای، نرخ false wake و رفتار interruption معلوم باشد؛ تنظیم جدید هم دقت و هم latency قابل قبول بدهد.

۷. **تثبیت محصول و سپس توسعه.** startup capability/version probe، retention، manifest وابستگی و تست پذیرش extension اضافه شوند. سپس adapterهای API و حافظهٔ ساخت‌یافته؛ وب‌کم و VLM پس از این مرحله. معیار اتمام: کاربر بداند کدام قابلیت واقعاً آماده است و نبود هر backend مسیر شکست مشخص داشته باشد.

### کارهای کوچک و مؤثر برای امروز

این‌ها پیشنهادند و در این بررسی اجرا نشده‌اند:

- در [model_interpreter.py](/mnt/ai_projects/KYRIN/src/kyrin/commands/model_interpreter.py:379)، تناقض ID و هدف صریح را ببندید و تست `Settings -> Quit` اضافه کنید؛ شاخهٔ scroll را نیز از بررسی نفی عبور دهید.
- در [queued_dispatch.py](/mnt/ai_projects/KYRIN/src/kyrin/actions/queued_dispatch.py:103) و [command_runtime.py](/mnt/ai_projects/KYRIN/src/kyrin/runtime/command_runtime.py:293)، EOF طبیعی را از cancel کاربر جدا کنید؛ این اصلاح کوچک به قابلیت تازهٔ فایل صوتی اثر مستقیم دارد.
- برای هر شکست کلیک فقط metadata کم‌حساسیت ثبت کنید: backend، reason، geometry، scale شناخته‌شده/نامعلوم و زمان هر مرحله؛ به‌جای افزودن sleep یا پایین‌آوردن confidence، علت شکست را قابل تفکیک کنید.
- آستانه و normalization گزینه‌سازی را با هدف‌یابی دقیق مشترک کنید و همان نمونهٔ فارسی RTL را به تست اضافه کنید؛ از بازنویسی کامل OCR شروع نکنید.
- در خروجی محصول، `LAUNCH_ACCEPTED` را «ورودی ارسال شد؛ نتیجه تأیید نشده» نشان دهید و برای toggle یک read-back اضافه کنید؛ این تغییر کوچک از اعلام موفقیت اشتباه جلوگیری می‌کند.
- یک probe خواندنی برای نسخهٔ extension فعال، session و قابلیت‌های portal/accessibility طراحی کنید؛ فایل جدید آن بخشی از کار بعدی است، نه این گزارش.

### ماتریس پذیرش پیشنهادی

| محور | حالت‌های لازم | انتظار |
|---|---|---|
| هندسه | scaleهای ۱، ۱٫۲۵، ۱٫۵ و ۲؛ سایه؛ crop؛ مانیتور با مبدأ منفی؛ mixed-DPI | نقطه داخل target درست یا توقف صریح به علت transform نامعلوم؛ هیچ حدس خاموشی انجام نشود. |
| هویت | دو پنجره از یک PID، dialog جدید، حرکت پنجره در زمان OCR/permission | snapshot قدیمی به input تبدیل نشود. |
| متن | فارسی RTL، انگلیسی، mixed script، quotation، overlap، دو label یکسان، label کوتاه | تطابق و ambiguity قابل توضیح؛ fuzzy بدون شواهد اجرا نشود. |
| مدل | ID نامرتبط، عملیات مخالف نفی، JSON معتبر ولی معنای نامعتبر، context فریبنده | validator مستقل جلوی action را بگیرد. |
| lifecycle | stop/standby در هر مرحله، EOF با action کند، timeout OCR، قطع portal | نتیجهٔ هر درخواست تعیین تکلیف شود؛ helper رهاشده بعداً کلیک نکند. |
| پس‌شرط | click بی‌اثر، dialog موفق، toggle ازقبل‌تنظیم‌شده، نتیجهٔ نامعلوم | تنها حالت اثبات‌شده `CONFIRMED` شود؛ retry غیرایمن انجام نشود. |
| صوت | صحبت روی TTS، میکروفون انتخابی، AEC ناموجود، سکوت درون جملهٔ فارسی | interruption و segmentation سنجیده شوند؛ حذف گفتار پنهان نماند. |

در corpus پذیرشِ اولیه، **کلیک روی هدف اشتباه باید صفر باشد**؛ abstention صریح از کلیک اشتباه بهتر است. صفر مورد در یک مجموعهٔ محدود، تضمین آماریِ نبود خطا در همهٔ برنامه‌ها نیست؛ تعداد نمونه و دامنهٔ شرایط همراه نتیجه گزارش شود. برای سنجش پیشرفت، نرخ موفقیت وظیفه و نرخ توقف بی‌مورد نیز ثبت شوند تا صرفاً با «هرگز کلیک نکردن» معیار ایمنی پاس نشود.

## Top 5 things to do first

۱. **هدف مدل را به درخواست واقعی ببندید.** R01 و R02: ID معتبر یا JSON معتبر کافی نیست؛ گزینهٔ نامرتبط و فرمان منفی باید پیش از gate رد شوند. [model_interpreter.py](/mnt/ai_projects/KYRIN/src/kyrin/commands/model_interpreter.py:365).

۲. **قرارداد مشترک geometry و هویت پنجره بسازید.** R03 تا R05: یک تبدیل صریح برای scale، سایه و crop؛ همان قرارداد برای Telegram و کنترل عمومی، با token و زمان مشاهده. [desktop_control_helper.py](/mnt/ai_projects/KYRIN/src/kyrin/actions/platforms/desktop_control_helper.py:164)، [telegram.py](/mnt/ai_projects/KYRIN/src/kyrin/actions/platforms/telegram.py:767).

۳. **از AT-SPI برای اجرای معنایی استفاده کنید.** R07: name/role/state/window درست را بررسی کنید، سپس action واقعی را صدا بزنید؛ OCR فقط fallbackِ نیازمند شواهد بیشتر باشد. [desktop_control_helper.py](/mnt/ai_projects/KYRIN/src/kyrin/actions/platforms/desktop_control_helper.py:55).

۴. **نتیجهٔ عمل را قبل از اعلام موفقیت و ادامهٔ plan بررسی کنید.** R06: پس‌شرط معنایی و retry محدود؛ image diff و dispatch به‌تنهایی موفقیت نیستند. [desktop_control.py](/mnt/ai_projects/KYRIN/src/kyrin/actions/platforms/desktop_control.py:220)، [plan_runner.py](/mnt/ai_projects/KYRIN/src/kyrin/actions/plan_runner.py:78).

۵. **لغو، deadline و پایان طبیعی را درست کنید.** R10 تا R12 و R14: standby فرمان قدیمی را باطل کند، EOF صف را drain کند و timeout کار پس‌زمینه را رها نکند. [command_runtime.py](/mnt/ai_projects/KYRIN/src/kyrin/runtime/command_runtime.py:166)، [queued_dispatch.py](/mnt/ai_projects/KYRIN/src/kyrin/actions/queued_dispatch.py:103)، [chat_verifier.py](/mnt/ai_projects/KYRIN/src/kyrin/app/qt/chat_verifier.py:192).

</div>
