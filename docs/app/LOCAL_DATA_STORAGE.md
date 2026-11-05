# Local KYRIN data

KYRIN follows XDG locations on Linux. The default paths below apply when the
corresponding XDG variables are unset.

| Data | Default path |
| --- | --- |
| Settings | `~/.config/kyrin/settings.json` |
| Imported model library and application data | `~/.local/share/kyrin/` |
| Optional conversation history | `~/.local/share/kyrin/memory/conversation.sqlite3` |

In a source checkout, `models/local/by-model/` holds optional development
models. The app can discover a checkout catalog, including TTS packages under
`models/local/by-model/tts/<family>/<model>/`. Imported STT models live in the
application data directory. See [model notes](../../models/README.md) and
the [model library](MODEL_LIBRARY.md).

To keep development downloads and caches on the checkout's volume, run from
the repository root and set the cache paths for the current shell:

```bash
export PIP_CACHE_DIR="$PWD/local-data/pip-cache"
export HF_HOME="$PWD/local-data/cache/huggingface"
```

`local-data/`, `models/local/`, `models/archive/` and `downloads/` are
ignored by Git. Keep settings, permission tokens, recordings and local
diagnostics private. User-installed desktop launchers and GNOME extensions
use the desktop environment's standard paths.
