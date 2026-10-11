# Interface language settings

The Ubuntu control center has a separate **Preferences → Interface language**
setting. It does not change speech recognition, command understanding, spoken
responses, or the language of text found on screen.

The application includes English and Persian. **System language** selects the
best installed match for the operating-system locale and otherwise uses
English. An explicit language choice remains saved across launches. Persian
uses a right-to-left layout; paths and technical model identifiers remain in
their original direction.

Additional languages can be added with **Add language pack…**. A pack is a
UTF-8 JSON file, for example:

```json
{
  "locale": "it",
  "name": "Italiano",
  "strings": {
    "dashboard": "Pannello",
    "preferences": "Preferenze"
  }
}
```

The importer accepts only known UI keys, nonempty translations, and matching
format placeholders. Untranslated keys use English. Locale tags may include a
script and region, such as `zh-Hant-TW`. Imports are validated before the
user's language file is replaced. Language selection is saved separately from
the microphone, STT model, and desktop-action permissions.

For a fully localized release, each visible UI key needs reviewed translation
and layout testing. Runtime speech and system-action prompts are separate
content, so changing the interface language does not silently change their
confirmation phrases or voice settings.
