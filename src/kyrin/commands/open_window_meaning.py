"""High-certainty EN/FA concept slots for showing currently open windows.

This is a fast path, not a list of complete utterances. Uncovered wording is
left for the replaceable command-understanding engine.
"""

import re
import unicodedata


def requests_open_window_overview(text: str, language: str | None) -> bool:
    """Require a display action, a collective scope, and open desktop windows."""
    code = language.strip().casefold().split("-", 1)[0] if language else ""
    normalized = unicodedata.normalize("NFKC", text).casefold()
    normalized = normalized.replace("ي", "ی").replace("ك", "ک")
    normalized = normalized.replace("\u200c", " ").replace("’", "'")
    if re.search(r'["“”«»]', text):
        return False
    if code == "en":
        if not re.match(
            r"^(?:(?:please|could you|can you|would you|let me)\s+)*"
            r"(?:show|display|view|see|list)\b",
            normalized.strip(),
        ):
            return False
        words = set(re.findall(r"[a-z]+", normalized))
        if words & {
            "not",
            "never",
            "don",
            "dont",
            "cannot",
            "cant",
            "won",
            "installed",
            "downloaded",
            "tab",
            "tabs",
            "file",
            "files",
            "browser",
            "or",
            "then",
            "and",
        } or re.search(r"\bcan['’]t\b", normalized):
            return False
        collective = bool(words & {"all", "every"}) or (
            "list" in words
            and bool(words & {"running", "open"})
            and bool(words & {"apps", "applications", "programs", "windows"})
        )
        display = bool(words & {"show", "display", "view", "see", "list"})
        windows = bool(words & {"window", "windows"})
        apps = bool(
            words
            & {"app", "apps", "application", "applications", "program", "programs"}
        )
        running = bool(words & {"open", "running", "active"})
        return collective and display and (windows or apps and running)
    if code == "fa":
        words = set(re.findall(r"[^\W_]+", normalized, flags=re.UNICODE))
        if (
            words & {"نصب", "تب", "فایل", "یا", "بعد", "سپس"}
            or any(word.startswith(("نکن", "نده", "نمی", "نشود")) for word in words)
            or re.search(r"\bو\b.+\b(?:باز|ببند|خاموش|حذف)\s+کن", normalized)
        ):
            return False
        collective = bool(words & {"همه", "تمام", "کل"})
        display = bool(words & {"نشان", "نمایش", "ببینم", "لیست"})
        windows = bool(words & {"پنجره", "پنجرهها"})
        apps = bool(words & {"برنامه", "برنامهها"})
        running = bool(words & {"باز", "فعال", "اجرا"})
        return collective and display and (windows or apps and running)
    return False
