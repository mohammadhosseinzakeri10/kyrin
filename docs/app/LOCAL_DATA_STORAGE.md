# Local KYRIN data on the AI-Projects drive

On the current Ubuntu development machine, installed STT and OCR models,
optional TTS runtimes, and the Hugging Face download tool live under
`/mnt/ai_projects/KYRIN/local-data/kyrin/`. The application's settings live
under `/mnt/ai_projects/KYRIN/local-data/config/kyrin/`. The entire
`local-data/` tree is excluded from Git.
The source checkout uses `models/local/by-model/tts/<family>/<model>/` as its
single TTS model catalog. TTS archives are kept under `models/archive/tts/`.
Other installed application data and optional runtimes remain in `local-data/`.
Finalized speech-text history uses `local-data/kyrin/memory/` through the
standard XDG data link. It is local, bounded, and can be cleared in Preferences.

The standard XDG paths remain available through directory symlinks:

```text
~/.local/share/kyrin -> /mnt/ai_projects/KYRIN/local-data/kyrin
~/.config/kyrin      -> /mnt/ai_projects/KYRIN/local-data/config/kyrin
```

This preserves existing model selections, virtual-environment script paths,
and application startup behavior. A download targeted at either standard
KYRIN path is physically written to the AI-Projects drive. Future setup
instructions should show the canonical `local-data/` path when possible. For
future package or model downloads, set project-specific caches as well:

```bash
PIP_CACHE_DIR=/mnt/ai_projects/KYRIN/local-data/cache/pip
HF_HOME=/mnt/ai_projects/KYRIN/local-data/cache/huggingface
```

Pass these environment variables to the corresponding `pip` and `hf` commands;
do not change the user's global cache settings.
The drive must be mounted before KYRIN starts.

Development models already under `models/local/`, archives under
`models/archive/`, and project downloads under `downloads/` are also on this
drive. Generic pip and Hugging Face caches are shared with other software and
are not part of the KYRIN data move. Desktop launchers and GNOME extensions
remain in their operating-system integration directories.

The default locations on other machines and platforms are unchanged. Do not
hard-code this machine's mount path into KYRIN's portable application code.
