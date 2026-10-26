# اجرای محلی Omnilingual ASR

شش مدل نسخهٔ دوم در مسیر `models/local/by-model/stt/omnilingual-asr/` نگه‌داری می‌شوند. هر مدل پوشهٔ مستقل خود را دارد که شامل وزن `.pt` و `omniASR_tokenizer_written_v2.model` است. KYRIN این پوشه‌ها را در «کتابخانهٔ مدل‌های گفتار» پیدا می‌کند و وزن‌ها را برای افزودن به برنامه دوباره کپی نمی‌کند.

## معماری اجرا

برنامهٔ اصلی با Python 3.14 اجرا می‌شود، ولی بستهٔ رسمی `omnilingual-asr` نسخهٔ پایین‌تر از 3.14 می‌خواهد. آداپتور KYRIN یک فرایند Python 3.12 از `local-data/kyrin/runtimes/stt/omnilingual-asr/` راه می‌اندازد. این فرایند با کارت‌های محلی `fairseq2` همان وزن‌ها و توکن‌ساز دانلودشده را باز می‌کند و از طریق پیام‌های JSON گفتار هر نوبت را تبدیل به متن می‌کند. فرایند هنگام توقف نشست بسته می‌شود.

`CTC` و `LLM` در بخش Engine یک گزینهٔ مشترک به نام `Omnilingual ASR` دارند؛ نام شش مدل در کتابخانهٔ مدل‌ها جداگانه دیده می‌شود. انتخاب زبان `en`، `fa`، `de` و `fr` به شناسهٔ رسمی مدل تبدیل می‌شود. برای زبان‌های دیگر می‌توان شناسهٔ کامل مانند `eng_Latn` را وارد کرد. مقدار `auto` شرط‌گذاری زبان را حذف می‌کند؛ در مدل‌های `LLM` این کار می‌تواند کیفیت را کاهش دهد. مدل‌های `CTC` طبق مستندات سازنده، شرط‌گذاری زبان را نادیده می‌گیرند.

پردازش هر نوبت پس از پایان گفتار انجام می‌شود؛ برای جلوگیری از اجرای تکراری مدل بزرگ، متن موقت تولید نمی‌شود. هر نوبت حداکثر ۳۰ ثانیه است. درخواست صریح GPU فقط در صورت وجود CUDA اجرا می‌شود؛ انتخاب خودکار در صورت در دسترس بودن CUDA آن را برمی‌گزیند.

برای جلوگیری از انتظار نامحدود، پاسخ آماده‌شدن فرایند فرزند حداکثر ۳۰۰ ثانیه و
پاسخ هر درخواست تشخیص گفتار حداکثر ۱۲۰ ثانیه فرصت دارد. اگر فرایند پاسخ ندهد،
KYRIN همان فرایند متعلق به خود را متوقف می‌کند و خطا را نشان می‌دهد. هنگام توقف
شنیدن نیز درخواست در حال اجرا قطع می‌شود تا آزادسازی مدل منتظر پایان محاسبه نماند.

## بازسازی محیط روی ماشین توسعهٔ فعلی

همهٔ ابزارها و حافظه‌های موقت زیر درایو پروژه قرار می‌گیرند. برای نصب، از ریشهٔ مخزن دستورهای زیر را اجرا کنید:

```bash
export UV_PYTHON_INSTALL_DIR="$PWD/local-data/kyrin/tools/python"
export UV_CACHE_DIR="$PWD/local-data/cache/uv"
export PIP_CACHE_DIR="$PWD/local-data/cache/pip"

python3.14 -m venv local-data/kyrin/tools/uv
local-data/kyrin/tools/uv/bin/python -m pip install uv==0.13.1
local-data/kyrin/tools/uv/bin/uv python install 3.12.15
local-data/kyrin/tools/uv/bin/uv venv --python 3.12 \
  local-data/kyrin/runtimes/stt/omnilingual-asr
local-data/kyrin/tools/uv/bin/uv pip install \
  --python local-data/kyrin/runtimes/stt/omnilingual-asr/bin/python \
  'omnilingual-asr==0.2.0' 'torch==2.8.0' 'torchaudio==2.8.0' \
  'numpy==1.26.4' 'pyarrow==20.0.0'
local-data/kyrin/tools/uv/bin/uv pip check \
  --python local-data/kyrin/runtimes/stt/omnilingual-asr/bin/python
```

وابستگی تازه فقط در محیط جداگانه نصب می‌شود؛ `pyproject.toml` برنامهٔ اصلی تغییر نمی‌کند. پس از نصب، برنامهٔ دسکتاپ را دوباره راه‌اندازی کنید تا گزینهٔ Engine تازه دیده شود.

## سنجش بدون میکروفن

ابزار سنجش مشترک می‌تواند یک فایل CSV با ستون‌های `id,path,language,reference` را برای این موتور نیز اجرا کند:

```bash
PYTHONPATH=src .venv/bin/python scripts/stt/evaluate_offline_stt.py \
  --backend omnilingual \
  --model-path models/local/by-model/stt/omnilingual-asr/omniASR_CTC_300M_v2 \
  --model-language en --device cpu --unpaced \
  --manifest /path/to/english-manifest.csv
```

در آزمون محلی یک فایل ۳٫۲ ثانیه‌ای با `CTC 300M` روی CPU پردازش شد و مدل متن برگرداند. دقت همان نمونه پایین بود؛ کارکرد اتصال به‌تنهایی تأیید کیفیت شناسایی نیست. بارگذاری و اجرای واقعی پنج مدل دیگر و GPU هنوز جداگانه باید سنجیده شوند.

سنجش بعدی روی مجموعهٔ مشترک فارسی و انگلیسی، چند مدل را روی CPU و `LLM 300M`
را روی GPU اجرا کرد. وضعیت دقیق مدل‌های اجراشده و کنارگذاشته‌شده به دلیل
محدودیت حافظه، همراه روش بازتولید و نتیجه‌ها، در
[مقایسهٔ مدل‌های محلی](LOCAL_MODEL_COMPARISON_FA.md) ثبت شده است. جملهٔ بالا
وضعیت آزمون اولیهٔ اتصال را توصیف می‌کند.
