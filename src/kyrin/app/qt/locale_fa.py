"""Built-in Persian control-center labels; speech and voice locales stay separate."""

PERSIAN: dict[str, str] = {
    "window_title": "KYRIN — مرکز کنترل",
    "dashboard": "داشبورد",
    "audio": "ورودی صدا",
    "recognition": "تشخیص گفتار",
    "models": "کتابخانهٔ مدل‌ها",
    "command_models": "فهم فرمان",
    "tts": "خروجی گفتار",
    "tts_heading": "خروجی گفتار",
    "tts_enabled": "پخش پاسخ‌های صوتی",
    "tts_caption": (
        "یک صدای آفلاینِ نصب‌شده انتخاب کنید. KYRIN مدل صوتی دانلود نمی‌کند. "
        "مدل سازگارِ استخراج‌شده را در پوشهٔ محلی TTS بگذارید "
        "یا مسیر آن را انتخاب کنید؛ موتور آن خودکار شناسایی می‌شود. "
        "می‌توانید تنظیمات فعلی را پیش از ذخیره‌کردن آزمایش کنید."
    ),
    "tts_engine": "موتور",
    "tts_installed": "مدل‌های محلی موجود",
    "tts_select_installed": "انتخاب مدل محلی…",
    "tts_refresh": "بازخوانی",
    "tts_system": "صدای سیستم (Speech Dispatcher)",
    "tts_folder": "پوشهٔ مدل محلی",
    "tts_voice": "صدا",
    "tts_speed": "سرعت گفتار",
    "tts_device": "پردازش صدا با",
    "tts_add_language": "افزودن صدای زبان…",
    "tts_remove_language": "حذف زبان انتخاب‌شده",
    "tts_language_code": "کد زبان (مانند fa، de، fr)",
    "tts_sample_text": "متن آزمایشی به همین زبان",
    "tts_select_folder": "پوشهٔ مدل صوتی استخراج‌شده را انتخاب کنید",
    "tts_preview": "آزمودن تنظیمات فعلی صدا",
    "tts_preview_started": "نمونه‌ای کوتاه با تنظیمات فعلی پخش می‌شود…",
    "tts_preview_unavailable": "آزمون صدا در دسترس نیست.",
    "command_models_heading": "فهم فرمان",
    "command_models_caption": (
        "برای فرمان‌هایی که قواعد سریع حل نمی‌کنند، یک مدل محلی انتخاب کنید. "
        "خروجی مدل با گفتار اصلی و مجوزهای اقدام بررسی می‌شود. "
        "پردازش با CPU ممکن است بسیار کندتر از GPU باشد."
    ),
    "command_models_rules": "فقط قواعد سریع (پیش‌فرض)",
    "command_models_engine": "موتور",
    "command_models_store": "مخزن مدل‌های محلی",
    "command_models_device": "پردازش مدل با",
    "command_models_refresh": "به‌روزرسانی فهرست مدل‌های نصب‌شده",
    "command_models_store_title": "انتخاب مخزن مدل‌های Ollama",
    "command_models_found": "{count} مدل محلی کامل پیدا شد.",
    "command_models_missing_store": "مسیر مطلق مخزن محلی Ollama را انتخاب کنید.",
    "command_models_choose": "ابتدا یک مدل فهم فرمانِ نصب‌شده انتخاب کنید.",
    "actions": "اقدام‌های دسکتاپ",
    "screen": "دسترسی به صفحه",
    "preferences": "تنظیمات",
    "welcome": "به KYRIN خوش آمدید",
    "welcome_caption": "محیط کارتان با یک فرمان صوتی در دسترس است.",
    "scene_hint": "پنجره‌ای آرام به سوی کیهان",
    "status": "وضعیت سیستم",
    "feedback_default": "پاسخ‌ها و خطاها اینجا نمایش داده می‌شوند.",
    "audio_heading": "ورودی صدا",
    "audio_caption": "میکروفونی را انتخاب کنید که KYRIN به آن گوش می‌دهد.",
    "microphone": "میکروفون",
    "default_microphone": "میکروفون پیش‌فرض سیستم",
    "missing_microphone": "میکروفون قبلی (در دسترس نیست)",
    "recognition_heading": "تشخیص گفتار",
    "recognition_caption": "مدل آفلاینِ نصب‌شده و دستگاه پردازش را انتخاب کنید.",
    "backend": "موتور",
    "model": "مدل نصب‌شده",
    "browse": "انتخاب…",
    "speech_language": "کد زبان گفتار",
    "speech_language_help": (
        "از کدی مانند en یا fa استفاده کنید. مدل چندزبانهٔ Whisper مقدار auto "
        "را هم می‌پذیرد؛ Omnilingual ASR برای مدل‌های LLM با کد زبان دقیق‌تر است؛ "
        "Vosk به مدل زبان مشخص نیاز دارد."
    ),
    "omnilingual_directory": "پوشهٔ مدل Omnilingual ASR را انتخاب کنید",
    "omnilingual_runtime_missing": "محیط اجرای Omnilingual ASR نصب نشده است.",
    "vosk_language_required": "برای Vosk کد زبان مشخصی مانند en لازم است.",
    "wake_aliases": "املاهای دیگر KYRIN (با ویرگول جدا کنید)",
    "device": "پردازش مدل با",
    "auto": "خودکار",
    "cpu": "CPU",
    "gpu": "GPU",
    "device_actual": "دستگاه فعالِ تشخیص گفتار",
    "device_actual_pending": "دستگاه فعالِ تشخیص گفتار: در انتظار شروع",
    "diagnostics_heading": "تصمیم‌های اخیر گفتار (فقط این نشست)",
    "diagnostics_clear": "پاک‌کردن گزارش گفتار",
    "diagnostics_decision": "فرمان برداشت‌شده",
    "diagnostics_no_command": "اقدامی درخواست نشد",
    "diagnostics_reason": "دلیل یا درخواست توضیح",
    "diagnostics_result": "نتیجهٔ اقدام",
    "models_heading": "کتابخانهٔ مدل‌های گفتار",
    "models_caption": (
        "همهٔ مدل‌های نصب‌شده را ببینید یا بر اساس سازگاری با CPU و GPU فیلتر کنید. "
        "فایل یک مدل Whisper می‌تواند بدون کپی دوباره در هر دو فهرست دیده شود."
    ),
    "models_all": "همهٔ مدل‌ها",
    "models_cpu": "مدل‌های CPU",
    "models_gpu": "مدل‌های GPU",
    "models_language": "Whisper: خودکار یا کد زبان؛ Vosk: کد زبان مدل",
    "models_import_cpu": "افزودن مدل برای CPU…",
    "models_import_gpu": "افزودن مدل برای GPU…",
    "models_use": "استفاده از مدل انتخاب‌شده",
    "models_empty": "هنوز مدلی در این فهرست نیست.",
    "models_external": "مدل خارجیِ فعلی",
    "models_unavailable": "کتابخانهٔ مدل‌ها در دسترس نیست.",
    "models_vosk_cpu": "Vosk در حال حاضر فقط از CPU پشتیبانی می‌کند.",
    "models_language_required": "پیش از افزودن مدل، کد زبان را وارد کنید.",
    "models_vosk_language_mismatch": (
        "به نظر می‌رسد این پوشهٔ Vosk برای {hint} باشد. کد زبان را {hint} وارد کنید."
    ),
    "models_importing": "در حال افزودن مدل به کتابخانه…",
    "models_imported": (
        "مدل افزوده شد. آن را انتخاب کنید و «استفاده از مدل انتخاب‌شده» را بزنید."
    ),
    "models_reused_language": (
        "فایل‌های این مدل Whisper از قبل نصب هستند. مدل را انتخاب کنید؛ سپس "
        "پیش از ذخیره، زبان دلخواه را در بخش تشخیص گفتار تنظیم کنید."
    ),
    "models_select_first": "ابتدا مدلی از این فهرست انتخاب کنید.",
    "models_gpu_unavailable": "اجرای GPU برای این موتور نصب نشده است.",
    "models_cpu_unavailable": "اجرای CPU برای این موتور نصب نشده است.",
    "models_selected": "مدل انتخاب شد. برای اعمال آن تغییرات را ذخیره کنید.",
    "save": "ذخیرهٔ تغییرات",
    "start": "شروع گوش‌دادن",
    "stop": "توقف گوش‌دادن",
    "microphone_off": "خاموش‌کردن کامل میکروفن",
    "voice_started": "دریافت فرمان‌ها فعال شد.",
    "voice_standby": "آماده‌باش؛ برای ادامه بگویید Start listening.",
    "voice_off": "میکروفن کاملاً خاموش شد.",
    "voice_turning_off": "در حال خاموش‌کردن میکروفن…",
    "quit": "خروج از KYRIN",
    "actions_on": "اقدام‌های دسکتاپ فعال‌اند",
    "actions_off": "اقدام‌های دسکتاپ غیرفعال‌اند",
    "allowed_apps": "برنامهٔ مجاز",
    "actions_heading": "اقدام‌های دسکتاپ",
    "actions_caption": (
        "برنامه‌های نصب‌شده‌ای را انتخاب کنید که KYRIN اجازهٔ کنترلشان را دارد."
    ),
    "enable_actions": "فعال‌کردن اقدام‌های انتخاب‌شدهٔ دسکتاپ",
    "allow_telegram_chats": "اجازهٔ بازکردن چت در Telegram (بدون ارسال پیام)",
    "remember_telegram_pointer": (
        "ذخیرهٔ دسترسی کیبورد و ماوس برای چت‌های Telegram"
    ),
    "telegram_pointer_grant_now": "تنظیم دسترسی کنترل Telegram…",
    "telegram_pointer_not_ready": (
        "مجوز کنترل ذخیره نشده است. تنظیمات را ذخیره کنید، سپس اینجا دسترسی بدهید."
    ),
    "telegram_pointer_ready": (
        "مجوز کنترل ذخیره شده است؛ سیستم می‌تواند بعداً آن را لغو کند."
    ),
    "telegram_pointer_grant_running": "درخواست Remote Desktop سیستم را تأیید کنید…",
    "telegram_pointer_grant_done": "دسترسی کیبورد و ماوس Telegram ذخیره شد.",
    "telegram_pointer_grant_failed": (
        "دسترسی کنترل ذخیره نشد. از همین‌جا دوباره تلاش کنید."
    ),
    "telegram_pointer_save_first": (
        "ابتدا تنظیمات چت و دسترسی کنترل Telegram را ذخیره کنید."
    ),
    "allow_desktop_scroll": "اجازهٔ اسکرول در برنامهٔ فعال",
    "desktop_scroll_grant_now": "تنظیم دسترسی اسکرول دسکتاپ…",
    "desktop_scroll_not_ready": "دسترسی اسکرول ذخیره نشده است؛ تنظیمات را ذخیره کنید.",
    "desktop_scroll_ready": "دسترسی اسکرول دسکتاپ ذخیره شده است.",
    "desktop_scroll_running": "درخواست Remote Desktop سیستم را تأیید کنید…",
    "desktop_scroll_done": "دسترسی اسکرول دسکتاپ ذخیره شد.",
    "desktop_scroll_failed": "دسترسی اسکرول ذخیره نشد؛ دوباره تلاش کنید.",
    "desktop_scroll_save_first": "ابتدا تنظیمات اسکرول دسکتاپ را ذخیره کنید.",
    "allow_window_controls": (
        "اجازهٔ بازگرداندن، کوچک‌کردن، بزرگ‌کردن یا تمام‌صفحه‌کردن برنامه‌های انتخاب‌شده"
    ),
    "allow_window_close": "اجازهٔ بستن پنجرهٔ برنامه‌های انتخاب‌شده",
    "allow_system_power": (
        "اجازهٔ درخواست‌های برق سیستم با تأیید دومرحله‌ای (پیش‌فرض: خاموش)"
    ),
    "actions_search": "جست‌وجوی برنامه‌های نصب‌شده…",
    "app_spoken_aliases": "نام‌های گفتاری دیگر برای برنامهٔ انتخاب‌شده",
    "app_spoken_aliases_placeholder": "نام‌ها را با ویرگول جدا کنید",
    "app_spoken_aliases_help": (
        "این نام‌ها فقط به تشخیص برنامه کمک می‌کنند و مجوز کنترل آن را نمی‌دهند. "
        "هر برنامهٔ فهرست، حتی برنامهٔ بدون تیک، قابل انتخاب است."
    ),
    "actions_select_visible": "انتخاب همهٔ موارد نمایان",
    "actions_clear_visible": "پاک‌کردن انتخاب موارد نمایان",
    "actions_selected": "انتخاب‌شده",
    "action_select_one": (
        "دست‌کم یک برنامه انتخاب کنید یا درخواست‌های برق سیستم را فعال کنید."
    ),
    "app_unavailable": "در دسترس نیست",
    "screen_heading": "دسترسی به صفحه",
    "screen_caption": (
        "اجازهٔ خواندن پنجرهٔ فعال را هنگام درخواست بدهید. GNOME یک‌بار اجازه "
        "می‌گیرد و تا زمان خاموش‌کردن این گزینه آن را به خاطر می‌سپارد. "
        "تصویری ذخیره نمی‌شود."
    ),
    "screen_enable": "به‌خاطر سپردن دسترسی به صفحه",
    "screen_active": "دسترسی به صفحه فعال است. برای لغو فوری، آن را خاموش کنید.",
    "screen_off": "دسترسی به صفحه خاموش است.",
    "screen_waiting": "در انتظار اجازهٔ GNOME…",
    "screen_unavailable": (
        "دسترسی به صفحه ممکن نیست. افزونهٔ GNOME را بررسی کنید؛ اگر فرایند دیگری "
        "نام نشست را در اختیار دارد، KYRIN را دوباره اجرا کنید."
    ),
    "screen_read": "خواندن متن پنجرهٔ فعال",
    "screen_read_clear": "پاک‌کردن متن خوانده‌شده از صفحه",
    "screen_ocr_model": "مدل محلیِ تشخیص متن تصویر",
    "screen_ocr_browse": "انتخاب پوشهٔ OCR…",
    "screen_ocr_hint": (
        "یک مدل محلیِ آماده از Tesseract یا PaddleOCR را انتخاب و ذخیره کنید. "
        "PaddleOCR-VL متن و مختصات را می‌خواند، ولی امتیاز اطمینان ندارد؛ "
        "فرمان‌های وابسته به این امتیاز برای ایمنی متوقف می‌شوند."
    ),
    "screen_read_hint": (
        "هر زمان نیاز داشتید تصویری بگیرید؛ متن دیده‌شده فقط در حافظه می‌ماند."
    ),
    "screen_reading": "در حال خواندن پنجرهٔ فعال…",
    "screen_ocr_unavailable": "موتور آفلاینِ انتخاب‌شده برای OCR در دسترس نیست.",
    "screen_capture_unavailable": "گرفتن تصویر پنجرهٔ فعال ممکن نشد.",
    "screen_window_changed": "پنجرهٔ فعال تغییر کرد. دوباره آن را بخوانید.",
    "screen_ocr_failed": "خواندن متن صفحه ممکن نشد.",
    "screen_no_text": "متن خوانایی در این پنجره پیدا نشد.",
    "screen_read_result": "تصویر از {app_id} (فرایند {pid}).",
    "screen_read_truncated": (
        "تصویر از {app_id} (فرایند {pid})؛ فقط ۲۰۰۰ نویسهٔ نخست نمایش داده می‌شود."
    ),
    "screen_document_heading": "خواندن آزمایشی سند",
    "screen_document_hint": (
        "متن پنجرهٔ فعال را با یک مدل آفلاینِ جدا بخوانید. انتخاب «مدل محلی OCR» "
        "و دکمهٔ ذخیره بر این مدل اثری ندارند. اگر پنجرهٔ KYRIN جلو باشد، "
        "تصویر همان پنجره خوانده می‌شود. اجرای CPU ممکن است چند دقیقه طول بکشد. "
        "نتیجه فقط متن است و برای کلیک یا اجرای فرمان به کار نمی‌رود."
    ),
    "screen_document_read": "خواندن با مدل سندِ انتخاب‌شده",
    "screen_document_clear": "پاک‌کردن متن خوانده‌شده با مدل سند",
    "screen_document_ready": "برای مقایسهٔ متن خروجی، مدلی انتخاب کنید.",
    "screen_document_reading": "در حال خواندن با مدل سند…",
    "screen_document_no_text": (
        "مدل {backend} از پنجرهٔ ثبت‌شدهٔ {app_id} متن خوانایی برنگرداند. "
        "برای بررسی متن‌دار بودن همین پنجره، خواندن متن صفحه در بخش بالا را "
        "نیز بیازمایید."
    ),
    "screen_document_result": "مدل {backend} پنجرهٔ فعال {app_id} را خواند.",
    "preferences_heading": "تنظیمات",
    "preferences_caption": "زبان مرکز کنترل را انتخاب کنید.",
    "interface_language": "زبان رابط برنامه",
    "system_language": "زبان سیستم",
    "power_off_button": "خاموش‌کردن…",
    "restart_button": "راه‌اندازی دوباره…",
    "log_out_button": "خروج از حساب…",
    "suspend_button": "خواباندن سیستم…",
    "cancel_button": "لغو",
    "continue_button": "ادامه",
    "confirm_button": "تأیید",
    "branding_subtitle": "هوش دسکتاپ",
    "branding_footer": "KYRIN  /  مرکز کنترل",
    "start_at_login": "اجرای KYRIN هنگام ورود به حساب",
    "apply_startup": "اعمال تنظیم شروع خودکار",
    "startup_saved": "تنظیم شروع خودکار ذخیره شد.",
    "startup_unavailable": "راه‌انداز نصب‌شدهٔ KYRIN در دسترس نیست.",
    "import_language": "افزودن بستهٔ زبان…",
    "language_help": "می‌توان بدون تغییر کد، بسته‌های زبان دیگر را اینجا افزود.",
    "conversation_memory_heading": "حافظهٔ گفت‌وگو",
    "conversation_memory_caption": (
        "کایرین تاریخچهٔ فعال و محدودی از متن نهایی گفتار را "
        "روی همین دستگاه نگه می‌دارد. "
        "صدا ذخیره نمی‌شود و گفتار قبلی مجوز اجرای فرمان تازه نیست."
    ),
    "conversation_memory_clear": "پاک‌کردن حافظهٔ فعال گفت‌وگو…",
    "conversation_memory_review": "مرور متن‌های بایگانی‌شدهٔ گفتار…",
    "conversation_memory_review_title": "حافظهٔ بایگانی‌شدهٔ گفت‌وگو",
    "conversation_memory_archive_count": "متن‌های بایگانی‌شده: {count}",
    "conversation_memory_select": "برای خواندن، یک متن را انتخاب کنید.",
    "conversation_memory_older": "بارگذاری قدیمی‌ترها",
    "conversation_memory_restore": "بازگرداندن متن انتخاب‌شده…",
    "conversation_memory_close": "بستن",
    "conversation_memory_restore_title": "این متن بازگردانده شود؟",
    "conversation_memory_restore_question": (
        "این متن دوباره در زمینهٔ گفت‌وگو در دسترس باشد؟ "
        "این متن به‌تنهایی مجوز اجرای هیچ کاری نیست."
    ),
    "conversation_memory_clear_title": "حافظهٔ فعال گفت‌وگو پاک شود؟",
    "conversation_memory_clear_question": (
        "متن‌های فعال گفتار حذف شوند؟ متن‌های بایگانی‌شده حفظ می‌شوند. "
        "این کار بازگشت‌پذیر نیست."
    ),
    "conversation_memory_cleared": "حافظهٔ فعال گفت‌وگو پاک شد.",
    "conversation_memory_unavailable": "پاک‌کردن حافظهٔ گفت‌وگو ممکن نشد.",
    "power_safe_preview": "آزمون امن تأیید خاموشی (بدون خاموش‌کردن)…",
    "power_safe_preview_busy": "پیش‌نمایش تأیید در حال اجراست یا در دسترس نیست.",
    "diagnostics_latency": "از آغاز گفتار تا نتیجهٔ فرمان",
    "diagnostics_final_to_result": "از متن نهایی تا نتیجه",
    "language_added": "بستهٔ زبان افزوده شد.",
    "ui_saved": "تنظیم زبان رابط ذخیره شد.",
    "state_stopped": "متوقف",
    "state_paused": "میکروفن کاملاً خاموش است",
    "state_standby": "آماده‌باش: بگویید Start listening",
    "state_mic_starting": "میکروفن در حال راه‌اندازی است؛ فرمان صوتی هنوز آماده نیست",
    "state_setup": "مدل تشخیص گفتار باید تنظیم شود",
    "state_starting": "در حال شروع",
    "state_running": "در حال اجرا",
    "state_stopping": "در حال توقف",
    "state_error": "خطا",
    "heard": "شنیده‌شده",
    "saved": "تنظیمات ذخیره شد.",
    "stopping_old": "پیش از اعمال تغییرات، نشست قبلی متوقف می‌شود…",
    "wait_stop": "لطفاً تا توقف نشست صبر کنید.",
    "save_first": "ابتدا تغییرات میکروفون و مدل را ذخیره کنید.",
    "choose_model": "ابتدا یک مدل گفتار انتخاب و ذخیره کنید.",
    "previous_failed": "نشست قبلی خطا داد؛ تنظیمات تازه اعمال نشد.",
    "error_device": "پردازندهٔ انتخاب‌شده برای این مدل در دسترس نیست.",
    "error_microphone": "میکروفون انتخاب‌شده در دسترس نیست. ورودی صدا را بررسی کنید.",
    "error_file": "فایل مدل یا ابزار گفتار پیدا نشد. مسیر آن را بررسی کنید.",
    "error_settings": "خواندن یا ذخیرهٔ تنظیمات ناموفق بود. فایل اصلی تغییر نکرد.",
    "error_generic": "KYRIN با خطا روبه‌رو شد",
    "path_absolute": "مسیر مدل باید مطلق باشد.",
    "vosk_missing": "پوشهٔ مدل Vosk پیدا نشد.",
    "whisper_missing": "فایل مدل Whisper پیدا نشد.",
    "whisper_server_missing": "ابزار محلی whisper-server در دسترس نیست.",
    "vosk_directory": "پوشهٔ مدل Vosk را انتخاب کنید",
    "whisper_file": "فایل مدل Whisper را انتخاب کنید",
    "language_file": "بستهٔ زبان KYRIN را انتخاب کنید",
}
