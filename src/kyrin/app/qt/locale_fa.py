"""Built-in Persian control-center labels; speech and voice locales stay separate."""

PERSIAN: dict[str, str] = {
    "window_title": "KYRIN — مرکز کنترل",
    "dashboard": "داشبورد",
    "audio": "ورودی صدا",
    "recognition": "تشخیص گفتار",
    "models": "کتابخانهٔ مدل‌ها",
    "command_models": "فهم فرمان",
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
        "را هم می‌پذیرد؛ Vosk به مدل زبان مشخص نیاز دارد."
    ),
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
    "allow_window_controls": (
        "اجازهٔ بازگرداندن، کوچک‌کردن، بزرگ‌کردن یا تمام‌صفحه‌کردن برنامه‌های انتخاب‌شده"
    ),
    "allow_window_close": "اجازهٔ بستن پنجرهٔ برنامه‌های انتخاب‌شده",
    "allow_system_power": (
        "اجازهٔ درخواست‌های برق سیستم با تأیید دومرحله‌ای (پیش‌فرض: خاموش)"
    ),
    "actions_search": "جست‌وجوی برنامه‌های نصب‌شده…",
    "actions_select_visible": "انتخاب همهٔ موارد نمایان",
    "actions_clear_visible": "پاک‌کردن انتخاب موارد نمایان",
    "actions_selected": "انتخاب‌شده",
    "action_select_one": (
        "دست‌کم یک برنامه انتخاب کنید یا درخواست‌های برق سیستم را فعال کنید."
    ),
    "app_unavailable": "در دسترس نیست",
    "screen_heading": "دسترسی به صفحه",
    "screen_caption": (
        "فقط تا زمانی که این نشست برنامه باز است، اجازهٔ خواندن پنجرهٔ فعال را بدهید. "
        "GNOME یک‌بار اجازه می‌گیرد؛ تصویری ذخیره نمی‌شود."
    ),
    "screen_enable": "اجازهٔ دسترسی به صفحه برای این نشست",
    "screen_active": "دسترسی به صفحه فعال است. برای لغو فوری، آن را خاموش کنید.",
    "screen_off": "دسترسی به صفحه خاموش است.",
    "screen_waiting": "در انتظار اجازهٔ GNOME…",
    "screen_unavailable": (
        "دسترسی به صفحه ممکن نیست. افزونهٔ GNOME را بررسی کنید؛ اگر فرایند دیگری "
        "نام نشست را در اختیار دارد، KYRIN را دوباره اجرا کنید."
    ),
    "screen_read": "خواندن متن پنجرهٔ فعال",
    "screen_read_hint": (
        "هر زمان نیاز داشتید تصویری بگیرید؛ متن دیده‌شده فقط در حافظه می‌ماند."
    ),
    "screen_reading": "در حال خواندن پنجرهٔ فعال…",
    "screen_ocr_unavailable": "موتور آفلاینِ خواندن متن انگلیسی نصب نشده است.",
    "screen_capture_unavailable": "گرفتن تصویر پنجرهٔ فعال ممکن نشد.",
    "screen_window_changed": "پنجرهٔ فعال تغییر کرد. دوباره آن را بخوانید.",
    "screen_ocr_failed": "خواندن متن صفحه ممکن نشد.",
    "screen_no_text": "متن خوانایی در این پنجره پیدا نشد.",
    "screen_read_result": "تصویر از {app_id} (فرایند {pid}).",
    "screen_read_truncated": (
        "تصویر از {app_id} (فرایند {pid})؛ فقط ۲۰۰۰ نویسهٔ نخست نمایش داده می‌شود."
    ),
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
    "language_added": "بستهٔ زبان افزوده شد.",
    "ui_saved": "تنظیم زبان رابط ذخیره شد.",
    "state_stopped": "متوقف",
    "state_paused": "گوش‌دادن خاموش است",
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
