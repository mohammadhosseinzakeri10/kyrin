"""Keep the installed optional-runtime entry point compatible."""

from kyrin.tts.worker import main

if __name__ == "__main__":
    raise SystemExit(main())
