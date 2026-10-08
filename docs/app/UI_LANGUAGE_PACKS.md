# KYRIN interface language packs

The built-in control-center language is English. Its language is separate from
the language used by a speech-recognition model. Speech transcripts and user
responses can therefore contain other languages while the controls stay in
English.

To add a translated interface, open **Preferences → Add language pack…** and
select a local JSON file. The imported language appears in **Interface
language**. Select it and click **Save changes**. No Python code needs to be
edited. The selection and imported pack are stored in the user's KYRIN XDG
configuration directory, not in the installed program files.

A pack is a JSON object with exactly these top-level fields:

- `locale`: a code such as `fr`, `de`, or `fa`.
- `name`: the language name shown in the selector.
- `strings`: translations for every key in
  `src/kyrin/app/qt/translations.py`'s `ENGLISH` catalog.

The importer checks completeness before installing a pack. It does not replace
the built-in English catalog. If the selected pack is missing or damaged at
startup, the control center opens in English and shows an error. The existing
configuration file remains untouched until the user explicitly saves a new
selection. Languages that read right to left use a right-to-left window
layout; paths and language codes remain left to right.

Only English is bundled at present. The current interface imports packs from
local files; an in-app catalog or downloader is a separate future feature.
