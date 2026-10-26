# Offline spoken responses in the live command diagnostic

## Behavior

The command coordinator asks for a repetition only after a **final** transcript
looks like an incomplete, unrecognized, or explicitly addressed command.
Ordinary conversation, silence, and partial transcripts do not trigger a
repetition. An STT result such as `to open telegram` (a previously observed
dropped negation prefix) is treated as unclear: it cannot authorize an action
and asks the speaker to repeat. The exact negative command
`do not open telegram` remains a no-op.
This small demo interpreter cannot detect every unclear utterance or infer the
speaker's intent from arbitrary STT errors.

`ResponsePresenter` converts the response request into localized text and a
requested channel. Persian and English messages currently exist. The live
`commands` diagnostic always prints that text. Unclear-command repetition and
approximate app-name clarification use `TEXT_ONLY`, so the user can immediately
repeat or answer without waiting for a spoken prompt. For `TEXT_AND_VOICE`,
`ResponseSpeaker` also queues it for `SpeechDispatcherSynthesizer`. The backend
uses a dedicated local Unix SSIP connection to Speech Dispatcher with the
`espeak-ng` output module and response language. BEGIN/END/CANCEL notifications
track actual playback; cancellation uses `CANCEL SELF`, never a global stop.
`spd-say --list-output-modules` is used only to autospawn the existing service
when its local socket is absent. No Python dependency or remote service is added. The speech contract is separate from STT and can be
implemented by another offline backend later. `TEXT_ONLY` responses are never
sent to speech output.

If speech output is missing, fails, or its bounded queue is full, the text is
still shown and a diagnostic warning is printed. Completion notifications
report the local service's lifecycle; audible output still requires a human
listening check. If a submitted message loses its cancellation acknowledgement,
playback remains uncertain and the half-duplex microphone guard remains active.
Restore the local speech service and restart KYRIN before relying on capture;
service disconnection is not treated as proof that playback stopped.
At diagnostic shutdown, queued voice gets a bounded chance to finish; if it
does not, the text remains visible and a warning reports the incomplete voice.

## Preventing self-hearing

<div dir="rtl" lang="fa">

**قرارداد فعلی F16 ــ ۲۰۲۶/۱۰/۲۴:** حالت مشغول (`is_active`) شامل صف و تولید
صوت است؛ محافظ ورودی از وضعیت پخش (`is_playing`) و دنبالهٔ ۳۵۰ میلی‌ثانیه‌ای
استفاده می‌کند. صف و تولید صوتِ مدل، میکروفون را ساکت نمی‌کنند. backend فاقد
گزارش وضعیت پخش، محافظ محافظه‌کارانهٔ قبلی را نگه می‌دارد. جایگزینی صوت با
سکوت، طول، قالب و زمان دریافت را حفظ می‌کند و خارج از `MicrophoneInput` است.

نشست Ubuntu، هویت واقعیِ حل‌شدهٔ ورودی پیش‌فرض یا انتخاب‌شده را به PipeWire
می‌رساند. مسیرهای پشتیبانی‌شده، نگاشت یکتای کارت/دستگاه ALSA، نام یا شرح
یکتای منبع PulseAudio و پل‌های مشخص `pulse`/`pipewire` با فرادادهٔ منبع
پیش‌فرض هستند. نام مبهم، ورودی ناشناخته و alias عمومیِ غیرقابل‌اثبات، AEC
را فعال نمی‌کنند. `target.object` هدف دریافت را تثبیت می‌کند و fallback،
جابه‌جایی و اتصال دوباره به هدف دیگر غیرفعال‌اند. وجود منبع مجازی و اتصال‌های
میکروفون و مرجع بلندگو، پیش از اعلام فراهم‌بودن مسیر بررسی می‌شوند.

در مسیر AEC، شروع تأییدشدهٔ گفتار مستقیماً در worker تشخیص فعالیت، پاسخ
صوتی را قطع می‌کند؛ این callback پشت STT یا صف رابط منتظر نمی‌ماند. همهٔ
پنجره‌های صوتی به‌ترتیب به STT می‌رسند و بافر نیم‌ثانیه‌ای ابتدای گفتار در
backendهای مبتنی بر نوبت حفظ می‌شود. تشخیص فعالیت گفتار (VAD) فقط پاسخ
صوتی را متوقف می‌کند؛ اجازهٔ عملیات، هویت گوینده یا تأیید dialog نیست.
تصمیم‌گیری و مجوز عملیات همچنان به متن نهایی و سیاست‌های قبلی وابسته‌اند.

بدون AEC، رابط حالت **نیمه‌دوطرفه** را نشان می‌دهد و صدای میکروفون هنگام
پخش و دنبالهٔ پژواک ساکت می‌شود. دکمهٔ **توقف پاسخ صوتی** در تمام صفحه‌ها
مستقیماً پاسخ جاری و صف صوت را باطل می‌کند؛ پس از مکث کوتاه می‌توان صحبت
کرد. این دکمه میکروفون، مجوزها و عملیات در حال اجرا را لغو نمی‌کند. صوتی
که پس از وقفه دیر آماده شود پخش نمی‌شود؛ تولید درون‌پردازه‌ای ممکن است تا
پایان فراخوانی ادامه یابد. این رفتار با توقف پخش و لغو عملیات سه چرخهٔ
مجزا دارد. پیش‌نمایش صدا و اعلان مرحلهٔ تأیید نیز همین اعتبارسنجی را دارند.

مرجع حذف پژواک، monitor بلندگوی پیش‌فرض PipeWire است؛ خروجی واقعی باید از
همان مسیر عبور کند. هیچ پیش‌فرض سراسری تغییر نمی‌کند. منبع موقت با نشست
بسته می‌شود. ابزار خط فرمان همچنان فقط محافظ نیمه‌دوطرفه دارد. آزمون‌های
ساختگی، نگاشت، اتصال، صف، وقفه، صوت دیررس، حفظ آغاز گفتار، سکوت پژواک و
استقلال توقف دستی را پوشش می‌دهند. این آزمون‌ها کیفیت صوتی را ثابت نمی‌کنند.
**آزمون زندهٔ میکروفون/بلندگو، سرویس صوتی نصب‌شده، میزان حذف پژواک و
قطع گفتار واقعی انجام نشده است.** گام بعد، آزمون صاحب دستگاه با ورودی
انتخاب‌شده، گفتار روی پاسخ و بررسی شنیده‌شدن اولین واژه و نبود فرمان کاذب
است؛ مسیر بدون AEC و توقف دستی نیز باید روی همان دستگاه بررسی شوند.

</div>

On desktop exit, the synthesizer interrupts playback and stops an active
isolated model worker. If in-process CPU generation still holds the model lock,
shutdown waits at most two seconds for that lock. It does not close a model
while generation is using it. The response speaker then gets a one-second
join deadline and the exiting process reclaims its remaining CPU memory.
Normal model switches still retire cached models once generation finishes.
This exceptional path has a deterministic blocked-generation test; an actual
stalled hardware runtime has not been induced on the owner's machine.

For system-power confirmation, a live safe-preview test initially appeared to
advance without user speech. The follow-up diagnostic showed `[BLANK_AUDIO]`,
and the new button still said `Continue`: this was the initial checking screen
changing to the first confirmation stage, not an accepted voice reply. The
dialogue now labels these stages explicitly. The owner also heard repeated
speech in the first run; unclear power replies now display a text-only reminder
instead of creating another spoken prompt. PipeWire barge-in remains enabled.

The desktop Voice Output page now has a saved **Play spoken responses** switch.
It defaults to on for existing settings. Turning it off and applying settings
interrupts the current announcement and suppresses subsequent voice, while
visual responses and microphone command processing continue. Turning it back
on restores voice using the selected engine and language routes. The switch is
enforced by the shared `ResponseSpeaker`, including system-power prompts.
Power-stage announcements replace the previous announcement in the queue and
interrupt active local-model playback, so the next stage does not wait for the
previous stage's audio to finish. A physical listening retest is still needed.

## Running

The existing `scripts/audio/check_live_speech.py --mode commands` invocation
speaks response requests by default when `spd-say` is installed. Its speech
backend requires the local Speech Dispatcher `espeak-ng` module. Use
`--no-voice-responses` when silent diagnostics are needed. STT/VAD-only modes
remain silent. The diagnostic is a desktop-action dry run by default; explicit
`--execute-actions` and `--launch-app` bindings enable limited app launch.
It never saves microphone audio. A later application UI can consume the same `PresentedResponse` and
`SpeechSynthesizer` contracts without reusing this diagnostic script.

Only Persian and English response catalogs are present. The installed
`espeak-ng` module exposes both on the development machine, but voice quality
and device output depend on local configuration. Windows, macOS, and mobile
speech adapters remain future platform work. This is an offline voice
prototype, not a packaged cross-platform TTS installation.

The local speech lifecycle follows the upstream
[SSIP protocol](https://github.com/brailcom/speechd/blob/master/doc/ssip.texi).
AEC configuration follows the official [Echo Cancel module](https://docs.pipewire.org/page_module_echo_cancel.html),
[stream target properties](https://docs.pipewire.org/page_man_pipewire-props_7.html)
and [ALSA identity keys](https://docs.pipewire.org/group__spa__keys.html).

<div dir="rtl" lang="fa">

**F19، ۲۰۲۶/۱۰/۲۴:** اقامت و پذیرش مدل در ترکیب Ubuntu اکنون از
[سیاست مشترک منابع](../app/MODEL_RESOURCE_POLICY.md) پیروی می‌کند؛
تنظیم صریح دستگاه و قراردادهای مجوز حفظ شده‌اند. آزمون زنده و baseline
سرعت/حافظهٔ این سیاست هنوز انجام نشده‌اند.

</div>
