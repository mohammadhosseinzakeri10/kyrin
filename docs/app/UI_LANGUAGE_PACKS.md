# KYRIN interface language packs

The control center defaults to English on a fresh installation and includes
selectable Persian interface text. Existing saved choices are retained under
the [V1 language policy](../LANGUAGE_POLICY.md). Its interface
language is separate from the language used by a speech-recognition model:
changing the menus does not change STT, command understanding, or the spoken
response voice. **System language** selects an available matching interface
locale, falling back to English when none is installed.

To add a translated interface, open **Preferences → Add language pack…** and
select a local JSON file. The imported language appears in **Interface
language**. Select it and click **Save changes**. No Python code needs to be
edited. The selection and imported pack are stored in the user's KYRIN XDG
configuration directory, not in the installed program files.

A pack is a JSON object with exactly these top-level fields:

- `locale`: a code such as `fr`, `de`, or `fa`. A local `fa` pack may override
  the built-in Persian strings.
- `name`: the language name shown in the selector.
- `strings`: translations for known keys in
  `src/kyrin/app/qt/translations.py`'s `ENGLISH` catalog.

The importer validates the pack's fields, translation keys, nonempty strings,
and format placeholders. A pack may cover only part of the interface: missing
keys fall back to English. It does not replace the built-in English catalog.
Without a local `fa` override, the built-in Persian catalog is merged over
English, so any untranslated keys still fall back to English.
If a selected local pack is damaged or
missing at startup, the control center opens in English and shows an error;
the existing preference file is preserved until the user explicitly saves a
new selection. Right-to-left languages use a right-to-left window layout;
paths and language codes remain left to right.

Previously imported packs remain usable when they lack newer labels; those
labels appear in English until the pack is updated. English and Persian are
built in. Other language packs are imported from local files; KYRIN does not
download translations in the app.
