# Conversation memory

<div dir="rtl" lang="fa">

**قرارداد فعلی ــ ۲۰۲۶/۱۰/۲۴، F17:** با تصمیم مالک، ذخیره در نصب تازه
خاموش است. تنظیمات نسخهٔ ۱۵ و قدیمی‌تر هنگام خواندن، رفتار روشن قبلی را حفظ
می‌کنند؛ فایل تنظیمات صرفاً با خواندن بازنویسی نمی‌شود. سقف پیش‌فرض فعال
۲۰۰۰ متن، بدون انقضای زمانی، و بایگانی بدون سقف یا انقضای خودکار باقی می‌ماند.
هیچ محدودیت مخرب تازه‌ای بر دادهٔ موجود تحمیل نشده است.

در ترجیحات، ذخیره و چهار محدودیت مستقل تعداد/سن فعال و بایگانی قابل تنظیم‌اند.
صفر در رابط و `null` در تنظیمات یعنی نامحدود. کاهش محدودیت تأیید جداگانه
می‌خواهد و با دکمهٔ ذخیرهٔ تغییرات اعمال می‌شود. سن از زمان ثبت اولیهٔ متن
محاسبه می‌شود؛ بایگانی و بازگردانی آن را تازه نمی‌کنند. متن دقیقاً روی مرز سن
حفظ می‌شود؛ فقط متن قدیمی‌تر حذف می‌شود. سقف تعداد، تازه‌ترین شناسه‌های درج
را نگه می‌دارد. محدودیت‌ها هنگام شروع نشست دارای ذخیره، درج، خواندن تاریخچه
و بایگانی/بازگردانی اجرا می‌شوند؛ در زمان بسته‌بودن برنامه زمان‌بند حذف وجود ندارد.
بازگردانی نباید متن فعال دیگری را کنار بزند یا متن منقضی برای زمینه را زنده کند.

خاموش‌کردن ذخیره، اتصال تاریخچه به نشست میکروفون و فایل را قطع می‌کند:
نه پایگاه داده ایجاد/باز می‌شود، نه متن قبلی برای مدل خوانده می‌شود و نه متن
جدید ذخیره می‌شود. دادهٔ موجود حفظ می‌شود. نمایش متن در گزارش عیب‌یابیِ
حافظه‌ای و زمینهٔ کوتاه‌مدت همان نشست، مستقل از این ذخیرهٔ پایدار است.
مرور صریح بایگانی همچنان ممکن است و سیاست ذخیره‌شدهٔ نگهداری را رعایت می‌کند.

سه عملیات مستقل رابط عبارت‌اند از «بایگانی و خروج از زمینه»، «حذف فعال» و
«حذف همهٔ فعال و بایگانی این پایگاه داده». هر سه تأیید جداگانه دارند؛ بایگانی
با رعایت سیاست نگهداری قابل بازگردانی است و دو حذف برگشت‌پذیر نیستند.
برای جلوگیری از ثبت دوبارهٔ متن در حین عملیات، ابتدا باید میکروفون کاملاً
متوقف و پردازش فایل تمام یا لغو شود. پس از موفقیت، گزارش عیب‌یابی، فهرست و
پیش‌نمایش باز بایگانی پاک می‌شوند. `clear()` قرارداد قدیمیِ حذف فعال را حفظ
می‌کند؛ دامنهٔ صریح با `clear_active()` و `clear_all()` مشخص است.
حذف همه شامل نسخه‌های پشتیبان، snapshotهای جداگانه یا فایل‌های صوتی منبع نیست؛
حذف سطرهای SQLite تضمین پاک‌سازی فیزیکی رسانه نیست.

آزمون‌ها فقط پایگاه دادهٔ موقت را باز می‌کنند و ساعت تزریقی، مرز سن، سقف مستقل،
بازگردانی، مهاجرت غیرمخرب تنظیمات، خاموش‌بودن ذخیره برای میکروفون و فایل،
تأیید و پاک‌سازی رابط را پوشش می‌دهند. پایگاه دادهٔ شخصی برای این اصلاح باز
نشده و آزمون زندهٔ برنامه انجام نشده است.

</div>

When persistence is enabled, KYRIN stores only finalized speech text, its reported
language, a UTC time,
and session/stream/segment identifiers. Partial STT text and audio are not
saved. The SQLite database is created at the standard XDG data path
`~/.local/share/kyrin/memory/conversation.sqlite3`. On the owner's Ubuntu
machine this directory points to
`/mnt/ai_projects/KYRIN/local-data/kyrin/memory/`, which is excluded from Git.
Other platforms can supply their own data directory without changing the
history interface.

By default, the database retains at most 2,000 active finalized turns; archived
turns are preserved outside that active limit. Both limits and optional ages
can now be configured as described above. The interpreter sees no more than six
active recent turns, shortened to 240 characters each, and only on a final
transcript. These are background context for the local command model;
the current utterance still has to independently support any executable
operation and target. Old transcripts cannot grant confirmation or action
permission. An operation fragment such as `Open`, `Open chat`, `Minimize`, or `کوچک کن`
can join a nearby final target such as `Telegram` for up to four seconds
within the same STT stream. English prefix and Persian suffix forms are
assembled according to the existing interpreter grammar; fragments are never
restored from the database. A new command, negation, yes/no
answer, system-power dialogue, or stream restart discards that fragment. A
language-label change alone does not discard it because multilingual STT labels
can vary between segments.

Preferences provides **Clear active conversation memory…** with a separate
confirmation. It clears active turns only; archived historical rows remain
available for separate review. **Review archived speech transcripts…** opens
a paged local list only when requested. Selecting a row reveals its full text;
**Restore selected transcript…** requires another confirmation and restores
only that row. Neither reviewing nor restoring authorizes an action. Storage
errors are reported without stopping listening. The
history and fragment interfaces are independent of STT and model backends.
The SQLite connection is guarded for the UI thread that creates a session and
the worker thread that processes speech.

Ubuntu session composition tests set `XDG_DATA_HOME` to a fresh temporary
directory for each test. Their fake transcripts therefore exercise persistence
without reading or writing the user's conversation database. A regression
assertion checks the temporary path and its saved test turns.

An earlier test run may have written fake transcripts before this isolation was
added. The existing user database was inspected read-only and left unchanged:
transcript text alone cannot prove which historical turns came from a test
versus a real session. Do not delete records by matching common command text.

On the owner's machine, all 81 pre-isolation turns were subsequently marked
archived in one SQLite transaction. This includes three turns that did not
match the literal test phrases; their origin is also uncertain. The rows remain
in the database, and a separate 0600 snapshot was saved under
`local-data/kyrin/memory/snapshots/` before archiving. New turns are active;
`recent()` excludes archived turns. `archive_active()` and
`restore_archived()` make the operation reversible without guessing origin.

The repeatable synthetic benchmark at
`scripts/commands/benchmark_conversation_history.py` creates a temporary
database on the same XDG data drive and removes it afterward. On the owner's
AI-Projects drive, 300 appends had median 0.845 ms and p95 1.354 ms; 300
six-turn reads had median 0.011 ms and p95 0.012 ms. This measures SQLite
operations, not microphone-to-action latency or all possible disk stalls. The
write remains synchronous on the speech event consumer; a bounded writer queue
should be considered only if a live trace shows material delay. Recent retrieval is recency
based; topic ranking and cross-session references require their own evaluation
before they may influence commands.

The control center also records text-free latency markers in the current
listening session. After action feedback, Speech Recognition diagnostics show
the interval from the confirmed start of speech activity to action result and
the interval from final STT text to action result. This includes command
understanding, policy, execution and verification, but excludes startup and
the first roughly 64 ms of VAD confirmation. It does not retain audio or
transcript text beyond the separately configured conversation history.

The supervised safe latency probe in
`scripts/commands/measure_safe_live_latency.py` reads the saved local STT and
command-model selections, uses a temporary conversation database, and replaces
the desktop executor with an inert result. It never opens Telegram. On one
owner-spoken `Open Telegram` trial on 2026-10-13, the confirmed activity start
to final STT text took 1,100.28 ms; final text to inert action result took
0.32 ms; total was 1,100.60 ms. This is a single warm-session observation of
this command, not a population benchmark. The command may use the rule-based
fast path, so it does not establish the latency of every LLM interpretation.
