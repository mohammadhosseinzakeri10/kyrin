"""A registered name can suggest an app but cannot bypass confirmation."""

from pathlib import Path

from kyrin.actions.gate import ActionGate, ActionPolicy
from kyrin.actions.models import ActionRequest
from kyrin.commands.coordinator import CommandCoordinator
from kyrin.commands.demo_interpreter import DemoCommandInterpreter
from kyrin.commands.models import (
    CommandCandidateUpdate,
    CommandIntent,
    CommandKind,
    CommandResolution,
    ResponseChannel,
    ResponseKind,
    ResponseRequest,
)
from kyrin.desktop.app_catalog import InstalledApp
from kyrin.desktop.platforms.xdg import XdgDesktopAppCatalog
from kyrin.desktop.spoken_app_names import CatalogSpokenAppResolver
from kyrin.responses.presenter import ResponsePresenter
from kyrin.stt.transcript import TranscriptStatus, TranscriptUpdate


def _entry(root: Path, desktop_id: str, name: str, *, browser: bool = False) -> None:
    path = root / "applications" / desktop_id
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        f"[Desktop Entry]\nType=Application\nName={name}\n"
        + ("Categories=Network;WebBrowser;\n" if browser else ""),
        encoding="utf-8",
    )


def _final(segment: int, text: str) -> TranscriptUpdate:
    return TranscriptUpdate(segment, text, TranscriptStatus.FINAL, "en")


def test_generic_browser_asks_between_permitted_browsers_before_action(
    tmp_path: Path,
) -> None:
    _entry(tmp_path, "chrome.desktop", "Google Chrome", browser=True)
    _entry(tmp_path, "firefox.desktop", "Firefox", browser=True)
    _entry(tmp_path, "private.desktop", "Private Browser", browser=True)
    _entry(tmp_path, "editor.desktop", "Editor")
    resolver = CatalogSpokenAppResolver(
        XdgDesktopAppCatalog((tmp_path,)),
        {
            "chrome.desktop": "google-chrome",
            "firefox.desktop": "firefox",
            "editor.desktop": "editor",
        },
    )
    assert tuple(item.app_id for item in resolver.browser_candidates()) == (
        "firefox",
        "google-chrome",
    )
    coordinator = CommandCoordinator(
        DemoCommandInterpreter(
            resolver, browser_candidates=resolver.browser_candidates()
        )
    )
    gate = ActionGate(
        ActionPolicy(allowed_apps=frozenset({"google-chrome", "firefox"}))
    )
    first = coordinator.observe(_final(0, "Open browser"))
    assert first[0] == CommandResolution(0, None, language="en")
    assert isinstance(first[1], ResponseRequest)
    assert first[1].kind is ResponseKind.CHOOSE_APP
    assert first[1].app_candidates == ("Firefox", "Google Chrome")
    assert gate.observe(first[0]) is None
    assert ResponsePresenter("en").present(first[1]).text == (
        "Which app do you mean? 1. Firefox; 2. Google Chrome. Say its number or name."
    )
    unclear = coordinator.observe(_final(1, "yes"))
    assert unclear[0] == CommandResolution(1, None, language="en")
    assert isinstance(unclear[1], ResponseRequest)
    assert unclear[1].kind is ResponseKind.CHOOSE_APP
    selected = coordinator.observe(_final(2, "number one"))
    assert selected == (
        CommandResolution(
            2, CommandIntent(CommandKind.OPEN_APP, "firefox"), language="en"
        ),
    )
    assert isinstance(gate.observe(selected[0]), ActionRequest)


def test_persian_browser_name_asks_for_only_permitted_browser(
    tmp_path: Path,
) -> None:
    _entry(tmp_path, "chrome.desktop", "Google Chrome", browser=True)
    resolver = CatalogSpokenAppResolver(
        XdgDesktopAppCatalog((tmp_path,)), {"chrome.desktop": "google-chrome"}
    )
    coordinator = CommandCoordinator(
        DemoCommandInterpreter(
            resolver, browser_candidates=resolver.browser_candidates()
        )
    )
    first = coordinator.observe(
        TranscriptUpdate(0, "مرورگر را باز کن", TranscriptStatus.FINAL, "fa")
    )
    assert first[0] == CommandResolution(0, None, language="fa")
    assert isinstance(first[1], ResponseRequest)
    assert first[1].kind is ResponseKind.CONFIRM_APP
    accepted = coordinator.observe(
        TranscriptUpdate(1, "بله", TranscriptStatus.FINAL, "fa")
    )
    assert isinstance(accepted[0], CommandResolution)
    assert accepted[0].intent == CommandIntent(CommandKind.OPEN_APP, "google-chrome")


def test_observed_whisper_spellings_resolve_with_registered_telegram(
    tmp_path: Path,
) -> None:
    _entry(tmp_path, "telegram.desktop", "Telegram")
    resolver = CatalogSpokenAppResolver(
        XdgDesktopAppCatalog((tmp_path,)),
        {"telegram.desktop": "telegram"},
        {"telegram": ("تلگرام", "تلیگرام")},
    )
    coordinator = CommandCoordinator(DemoCommandInterpreter(resolver))
    for segment, spoken, language in (
        (0, "Kairin Open Telegram", "en"),
        (1, "تلیگرام را باز کن", "fa"),
    ):
        assert coordinator.observe(
            TranscriptUpdate(segment, spoken, TranscriptStatus.FINAL, language)
        ) == (
            CommandResolution(
                segment,
                CommandIntent(CommandKind.OPEN_APP, "telegram"),
                language=language,
            ),
        )
    assert coordinator.observe(_final(2, "Kairin do not open Telegram")) == (
        CommandResolution(2, None, language="en"),
    )


def test_catalog_alias_and_approximate_name_require_different_decisions(
    tmp_path: Path,
) -> None:
    _entry(tmp_path, "whatsapp.desktop", "WhatsApp")
    _entry(tmp_path, "telegram.desktop", "Telegram")
    _entry(tmp_path, "unbound.desktop", "Unbound")
    resolver = CatalogSpokenAppResolver(
        XdgDesktopAppCatalog((tmp_path,)),
        {"whatsapp.desktop": "whatsapp", "telegram.desktop": "telegram"},
        {"whatsapp": ("what's up",)},
    )
    assert resolver.resolve("what's up").candidates[0].app_id == "whatsapp"
    assert resolver.resolve("whatsapp").exact
    assert resolver.resolve("WhatsAp").exact is False
    assert resolver.resolve("Unbound").candidates == ()
    assert resolver.resolve("filler drum").candidates == ()

    coordinator = CommandCoordinator(DemoCommandInterpreter(resolver))
    gate = ActionGate(ActionPolicy(allowed_apps=frozenset({"whatsapp"})))
    direct = coordinator.observe(_final(0, "Go to WhatsApp"))
    assert direct == (
        CommandResolution(
            0, CommandIntent(CommandKind.OPEN_APP, "whatsapp"), language="en"
        ),
    )
    assert isinstance(gate.observe(direct[0]), ActionRequest)

    coordinator = CommandCoordinator(DemoCommandInterpreter(resolver))
    gate = ActionGate(ActionPolicy(allowed_apps=frozenset({"whatsapp"})))
    alias = coordinator.observe(_final(0, "Go to what's up"))
    assert alias == (
        CommandResolution(
            0, CommandIntent(CommandKind.OPEN_APP, "whatsapp"), language="en"
        ),
    )
    assert isinstance(gate.observe(alias[0]), ActionRequest)

    proposed = coordinator.observe(_final(1, "Go to WhatsAp"))
    assert proposed[0] == CommandResolution(1, None, language="en")
    assert isinstance(proposed[1], ResponseRequest)
    assert proposed[1].kind is ResponseKind.CONFIRM_APP
    assert ResponsePresenter("en").present(proposed[1]).text == (
        "Did you mean the WhatsApp app?"
    )
    assert gate.observe(proposed[0]) is None
    accepted = coordinator.observe(_final(2, "yes"))
    assert accepted == (
        CommandResolution(
            2, CommandIntent(CommandKind.OPEN_APP, "whatsapp"), language="en"
        ),
    )


def test_registered_long_name_supplies_short_name_and_stt_hint(tmp_path: Path) -> None:
    _entry(tmp_path, "code.desktop", "Visual Studio Code")
    _entry(tmp_path, "other.desktop", "Another Editing Program")
    resolver = CatalogSpokenAppResolver(
        XdgDesktopAppCatalog((tmp_path,)), {"code.desktop": "visual-studio-code"}
    )
    assert resolver.resolve("VS Code").exact
    assert resolver.resolve("VSCode").exact
    assert resolver.resolve("Visual Studio Code").candidates[0].app_id == (
        "visual-studio-code"
    )
    assert resolver.vocabulary_hints() == ("Visual Studio Code", "VS Code")
    coordinator = CommandCoordinator(DemoCommandInterpreter(resolver))
    assert coordinator.observe(_final(0, "Please open VS Code"))[0] == (
        CommandResolution(
            0,
            CommandIntent(CommandKind.OPEN_APP, "visual-studio-code"),
            language="en",
        )
    )
    assert coordinator.observe(_final(1, "Open VS Code")) == (
        CommandResolution(
            1,
            CommandIntent(CommandKind.OPEN_APP, "visual-studio-code"),
            language="en",
        ),
    )


def test_colliding_derived_short_names_do_not_execute(tmp_path: Path) -> None:
    _entry(tmp_path, "code.desktop", "Visual Studio Code")
    _entry(tmp_path, "other.desktop", "Video Streaming Code")
    resolver = CatalogSpokenAppResolver(
        XdgDesktopAppCatalog((tmp_path,)),
        {"code.desktop": "visual-studio-code", "other.desktop": "video-code"},
    )
    match = resolver.resolve("VS Code")
    assert match.exact and len(match.candidates) == 2
    events = CommandCoordinator(DemoCommandInterpreter(resolver)).observe(
        _final(0, "Open VS Code")
    )
    assert events[0] == CommandResolution(0, None, language="en")
    assert isinstance(events[1], ResponseRequest)
    assert events[1].kind is ResponseKind.CHOOSE_APP


def test_registered_camel_case_name_accepts_spoken_word_boundary(
    tmp_path: Path,
) -> None:
    _entry(tmp_path, "openrgb.desktop", "OpenRGB")
    resolver = CatalogSpokenAppResolver(
        XdgDesktopAppCatalog((tmp_path,)), {"openrgb.desktop": "openrgb"}
    )
    assert resolver.resolve("Open RGB").exact
    assert CommandCoordinator(DemoCommandInterpreter(resolver)).observe(
        _final(0, "Open Open RGB")
    ) == (
        CommandResolution(
            0, CommandIntent(CommandKind.OPEN_APP, "openrgb"), language="en"
        ),
    )


def test_colliding_camel_case_name_still_requires_choice(tmp_path: Path) -> None:
    _entry(tmp_path, "openrgb.desktop", "OpenRGB")
    _entry(tmp_path, "open-rgb.desktop", "Open RGB")
    resolver = CatalogSpokenAppResolver(
        XdgDesktopAppCatalog((tmp_path,)),
        {"openrgb.desktop": "openrgb", "open-rgb.desktop": "open-rgb"},
    )
    events = CommandCoordinator(DemoCommandInterpreter(resolver)).observe(
        _final(0, "Open Open RGB")
    )
    assert events[0] == CommandResolution(0, None, language="en")
    assert isinstance(events[1], ResponseRequest)
    assert events[1].kind is ResponseKind.CHOOSE_APP


def test_rejected_suggestion_never_becomes_an_action(tmp_path: Path) -> None:
    _entry(tmp_path, "whatsapp.desktop", "WhatsApp")
    resolver = CatalogSpokenAppResolver(
        XdgDesktopAppCatalog((tmp_path,)), {"whatsapp.desktop": "whatsapp"}
    )
    coordinator = CommandCoordinator(DemoCommandInterpreter(resolver))
    coordinator.observe(_final(0, "open WhatsAp"))
    assert coordinator.pending_clarification is not None
    assert coordinator.observe(_final(1, "no")) == (
        CommandResolution(1, None, language="en"),
    )
    assert coordinator.pending_clarification is None
    assert coordinator.observe(_final(2, "yes")) == (
        CommandResolution(2, None, language="en"),
    )


def test_observed_persian_browser_spelling_asks_before_action(tmp_path: Path) -> None:
    _entry(tmp_path, "browser.desktop", "browser")
    resolver = CatalogSpokenAppResolver(
        XdgDesktopAppCatalog((tmp_path,)),
        {"browser.desktop": "browser"},
        {"browser": ("مرورگر",)},
    )
    coordinator = CommandCoordinator(DemoCommandInterpreter(resolver))
    gate = ActionGate(ActionPolicy(allowed_apps=frozenset({"browser"})))
    first = coordinator.observe(
        TranscriptUpdate(0, "مرورگی را باز کن", TranscriptStatus.FINAL, "fa")
    )
    assert first[0] == CommandResolution(0, None, language="fa")
    assert gate.observe(first[0]) is None
    assert isinstance(first[1], ResponseRequest)
    assert first[1].kind is ResponseKind.CONFIRM_APP
    assert first[1].channel is ResponseChannel.TEXT_ONLY
    assert ResponsePresenter("fa").present(first[1]).text == (
        "منظورتان برنامهٔ مرورگر است؟"
    )

    accepted = coordinator.observe(
        TranscriptUpdate(1, "بله", TranscriptStatus.FINAL, "fa")
    )
    assert accepted == (
        CommandResolution(
            1, CommandIntent(CommandKind.OPEN_APP, "browser"), language="fa"
        ),
    )
    assert isinstance(gate.observe(accepted[0]), ActionRequest)


def test_exact_colloquial_case_marker_keeps_name_check_strict(tmp_path: Path) -> None:
    _entry(tmp_path, "browser.desktop", "Browser")
    resolver = CatalogSpokenAppResolver(
        XdgDesktopAppCatalog((tmp_path,)),
        {"browser.desktop": "browser"},
        {"browser": ("مرورگر",)},
    )
    coordinator = CommandCoordinator(DemoCommandInterpreter(resolver))
    direct = coordinator.observe(
        TranscriptUpdate(0, "مرورگر رو باز کن", TranscriptStatus.FINAL, "fa")
    )
    assert direct == (
        CommandResolution(
            0, CommandIntent(CommandKind.OPEN_APP, "browser"), language="fa"
        ),
    )
    unclear = coordinator.observe(
        TranscriptUpdate(1, "مرورگی رو باز کن", TranscriptStatus.FINAL, "fa")
    )
    assert unclear[0] == CommandResolution(1, None, language="fa")
    assert isinstance(unclear[1], ResponseRequest)
    assert unclear[1].kind is ResponseKind.CONFIRM_APP


def test_new_unclear_command_cancels_older_app_confirmation(tmp_path: Path) -> None:
    _entry(tmp_path, "browser.desktop", "Browser")
    resolver = CatalogSpokenAppResolver(
        XdgDesktopAppCatalog((tmp_path,)),
        {"browser.desktop": "browser"},
        {"browser": ("مرورگر",)},
    )
    coordinator = CommandCoordinator(DemoCommandInterpreter(resolver))
    coordinator.observe(
        TranscriptUpdate(0, "مرورگی را باز کن", TranscriptStatus.FINAL, "fa")
    )
    assert coordinator.pending_clarification is not None
    unclear = coordinator.observe(
        TranscriptUpdate(1, "مرورگر رو باسکن", TranscriptStatus.FINAL, "fa")
    )
    assert unclear[0] == CommandResolution(1, None, language="fa")
    assert isinstance(unclear[1], ResponseRequest)
    assert unclear[1].kind is ResponseKind.REPEAT_COMMAND
    assert coordinator.pending_clarification is None
    assert coordinator.observe(
        TranscriptUpdate(2, "بله", TranscriptStatus.FINAL, "fa")
    ) == (CommandResolution(2, None, language="fa"),)


def test_negative_reply_cancels_stale_persian_app_confirmation(tmp_path: Path) -> None:
    _entry(tmp_path, "browser.desktop", "browser")
    resolver = CatalogSpokenAppResolver(
        XdgDesktopAppCatalog((tmp_path,)),
        {"browser.desktop": "browser"},
        {"browser": ("مرورگر",)},
    )
    coordinator = CommandCoordinator(DemoCommandInterpreter(resolver))
    gate = ActionGate(ActionPolicy(allowed_apps=frozenset({"browser"})))
    coordinator.observe(
        TranscriptUpdate(0, "مرورگی را باز کن", TranscriptStatus.FINAL, "fa")
    )
    cancelled = coordinator.observe(
        TranscriptUpdate(1, "مارورگره باز نکن", TranscriptStatus.FINAL, "fa")
    )
    assert cancelled == (CommandResolution(1, None, language="fa"),)
    assert gate.observe(cancelled[0]) is None
    assert coordinator.pending_clarification is None
    later_yes = coordinator.observe(
        TranscriptUpdate(2, "بله", TranscriptStatus.FINAL, "fa")
    )
    assert later_yes == (CommandResolution(2, None, language="fa"),)
    assert gate.observe(later_yes[0]) is None


def test_live_persian_name_variants_only_suggest_browser(tmp_path: Path) -> None:
    _entry(tmp_path, "browser.desktop", "browser")
    resolver = CatalogSpokenAppResolver(
        XdgDesktopAppCatalog((tmp_path,)),
        {"browser.desktop": "browser"},
        {"browser": ("مرورگر",)},
    )
    gate = ActionGate(ActionPolicy(allowed_apps=frozenset({"browser"})))
    for heard in ("مرور جار را باز کن", "مورور جره باز کن"):
        name = heard.removesuffix(" باز کن").removesuffix(" را")
        assert resolver.resolve(name).candidates == ()
        assert resolver.suggest(name).candidates
        coordinator = CommandCoordinator(DemoCommandInterpreter(resolver))
        proposed = coordinator.observe(
            TranscriptUpdate(0, heard, TranscriptStatus.FINAL, "fa")
        )
        assert proposed[0] == CommandResolution(0, None, language="fa")
        assert gate.observe(proposed[0]) is None
        assert isinstance(proposed[1], ResponseRequest)
        assert proposed[1].kind is ResponseKind.CONFIRM_APP
        assert ResponsePresenter("fa").present(proposed[1]).text == (
            "منظورتان برنامهٔ مرورگر است؟"
        )
        declined = coordinator.observe(
            TranscriptUpdate(1, "نه", TranscriptStatus.FINAL, "fa")
        )
        assert declined == (CommandResolution(1, None, language="fa"),)
        assert gate.observe(declined[0]) is None


def test_uncertain_persian_verb_only_requests_repetition(tmp_path: Path) -> None:
    _entry(tmp_path, "browser.desktop", "browser")
    resolver = CatalogSpokenAppResolver(
        XdgDesktopAppCatalog((tmp_path,)),
        {"browser.desktop": "browser"},
        {"browser": ("مرورگر",)},
    )
    coordinator = CommandCoordinator(DemoCommandInterpreter(resolver))
    gate = ActionGate(ActionPolicy(allowed_apps=frozenset({"browser"})))
    for stream_id, heard in enumerate(("مورورگیر را باسکو", "مروریا را باسکن")):
        events = coordinator.observe(
            TranscriptUpdate(0, heard, TranscriptStatus.FINAL, "fa")
        )
        assert events[0] == CommandResolution(
            0, None, stream_id=stream_id, language="fa"
        )
        assert gate.observe(events[0]) is None
        assert isinstance(events[1], ResponseRequest)
        assert events[1].kind is ResponseKind.REPEAT_COMMAND
        assert coordinator.pending_clarification is None
        coordinator.start_new_stream()
    assert coordinator.observe(
        TranscriptUpdate(0, "بله", TranscriptStatus.FINAL, "fa")
    ) == (CommandResolution(0, None, stream_id=2, language="fa"),)


def test_negative_persian_open_never_becomes_suggestion(tmp_path: Path) -> None:
    _entry(tmp_path, "browser.desktop", "browser")
    resolver = CatalogSpokenAppResolver(
        XdgDesktopAppCatalog((tmp_path,)),
        {"browser.desktop": "browser"},
        {"browser": ("مرورگر",)},
    )
    coordinator = CommandCoordinator(DemoCommandInterpreter(resolver))
    coordinator.observe(
        TranscriptUpdate(0, "مرور جار را باز کن", TranscriptStatus.FINAL, "fa")
    )
    assert coordinator.pending_clarification is not None
    assert coordinator.observe(
        TranscriptUpdate(1, "مرور جار را باز نکن", TranscriptStatus.FINAL, "fa")
    ) == (CommandResolution(1, None, language="fa"),)
    assert coordinator.pending_clarification is None
    assert coordinator.observe(
        TranscriptUpdate(2, "بله", TranscriptStatus.FINAL, "fa")
    ) == (CommandResolution(2, None, language="fa"),)


def test_partial_match_and_negation_never_authorize_an_action(tmp_path: Path) -> None:
    _entry(tmp_path, "telegram.desktop", "Telegram")
    resolver = CatalogSpokenAppResolver(
        XdgDesktopAppCatalog((tmp_path,)), {"telegram.desktop": "telegram"}
    )
    coordinator = CommandCoordinator(DemoCommandInterpreter(resolver))
    gate = ActionGate(ActionPolicy(allowed_apps=frozenset({"telegram"})))
    partial = coordinator.observe(
        TranscriptUpdate(0, "open Telegram", TranscriptStatus.PARTIAL, "en")
    )
    assert partial == (
        CommandCandidateUpdate(0, CommandIntent(CommandKind.OPEN_APP, "telegram")),
    )
    assert gate.observe(partial[0]) is None
    final = coordinator.observe(_final(0, "do not open Telegram"))
    assert final == (CommandResolution(0, None, language="en"),)
    assert gate.observe(final[-1]) is None


def test_same_label_for_distinct_apps_asks_for_choice(tmp_path: Path) -> None:
    _entry(tmp_path, "first.desktop", "Google Chrome")
    _entry(tmp_path, "second.desktop", "Google Chrome")
    resolver = CatalogSpokenAppResolver(
        XdgDesktopAppCatalog((tmp_path,)),
        {"first.desktop": "chrome_a", "second.desktop": "chrome_b"},
        {"chrome_a": ("Chrome Work",)},
    )
    coordinator = CommandCoordinator(DemoCommandInterpreter(resolver))
    result = coordinator.observe(_final(0, "open Google Chrome"))
    assert result[0] == CommandResolution(0, None, language="en")
    assert isinstance(result[1], ResponseRequest)
    assert result[1].kind is ResponseKind.CHOOSE_APP
    # Saying the same ambiguous label again must not select either application.
    second = coordinator.observe(_final(1, "Google Chrome"))
    assert second[0] == CommandResolution(1, None, language="en")
    assert isinstance(second[1], ResponseRequest)
    assert second[1].kind is ResponseKind.CHOOSE_APP
    assert ResponsePresenter("en").present(second[1]).text == (
        "Multiple apps are named Google Chrome. Please use a different name."
    )
    selected = coordinator.observe(_final(2, "Chrome Work"))
    assert selected == (
        CommandResolution(
            2, CommandIntent(CommandKind.OPEN_APP, "chrome_a"), language="en"
        ),
    )


def test_refresh_replaces_stale_catalog_snapshot(tmp_path: Path) -> None:
    _entry(tmp_path, "chat.desktop", "Chat One")
    resolver = CatalogSpokenAppResolver(
        XdgDesktopAppCatalog((tmp_path,)), {"chat.desktop": "chat"}
    )
    assert resolver.resolve("Chat One").exact
    _entry(tmp_path, "chat.desktop", "Chat Two")
    resolver.refresh()
    assert resolver.resolve("Chat One").candidates == ()
    assert resolver.resolve("Chat Two").exact


class _DeviceCatalog:
    """A non-XDG catalog proves matching does not depend on Ubuntu paths."""

    def __init__(self, apps: tuple[InstalledApp, ...]) -> None:
        self.apps = apps

    def list_apps(self) -> tuple[InstalledApp, ...]:
        return self.apps

    def find_app(self, platform_id: str) -> InstalledApp | None:
        return next((app for app in self.apps if app.platform_id == platform_id), None)


def test_catalog_names_are_dynamic_and_unbound_apps_block_wrong_suggestions() -> None:
    catalog = _DeviceCatalog(
        (
            InstalledApp("vendor.edit", "Nova Edit"),
            InstalledApp("vendor.editor", "Nova Editor"),
        )
    )
    resolver = CatalogSpokenAppResolver(
        catalog,
        {"vendor.edit": "nova_edit"},
        registered_aliases={"vendor.edit": ("ویرایشگر نووا",)},
    )
    assert resolver.resolve("ویرایشگر نووا").exact
    assert resolver.resolve("Nova Editor").candidates == ()
    assert resolver.suggest("Nova Edito").candidates == ()

    catalog.apps = (InstalledApp("vendor.edit", "Nova Edit"),)
    resolver.refresh()
    assert tuple(
        candidate.app_id for candidate in resolver.suggest("Nova Edito").candidates
    ) == ("nova_edit",)


def test_alias_collision_with_unbound_registered_app_never_grants_permission() -> None:
    catalog = _DeviceCatalog(
        (
            InstalledApp("vendor.notes", "Acme Notes"),
            InstalledApp("vendor.chat", "Acme Chat"),
        )
    )
    resolver = CatalogSpokenAppResolver(
        catalog,
        {"vendor.notes": "notes"},
        registered_aliases={
            "vendor.notes": ("کار من",),
            "vendor.chat": ("کار من",),
        },
    )
    assert resolver.resolve("کار من").candidates == ()
    coordinator = CommandCoordinator(DemoCommandInterpreter(resolver))
    result = coordinator.observe(_final(0, "open کار من"))
    assert result[0] == CommandResolution(0, None, language="en")
    assert isinstance(result[1], ResponseRequest)
    assert result[1].kind is ResponseKind.REPEAT_COMMAND


def test_explicit_user_name_selects_one_of_duplicate_registered_chrome_labels(
    tmp_path: Path,
) -> None:
    _entry(tmp_path, "com.google.Chrome.desktop", "Google Chrome", browser=True)
    _entry(tmp_path, "google-chrome.desktop", "Google Chrome", browser=True)
    catalog = XdgDesktopAppCatalog((tmp_path,))
    binding = {"google-chrome.desktop": "google-chrome"}
    unresolved = CatalogSpokenAppResolver(catalog, binding)
    assert unresolved.resolve("Google Chrome").candidates == ()

    selected = CatalogSpokenAppResolver(
        catalog,
        binding,
        registered_aliases={"google-chrome.desktop": ("Google Chrome",)},
    )
    assert tuple(
        candidate.app_id for candidate in selected.resolve("Google Chrome").candidates
    ) == ("google-chrome",)
    coordinator = CommandCoordinator(DemoCommandInterpreter(selected))
    decision = coordinator.observe(_final(0, "open google chrome"))
    assert decision == (
        CommandResolution(
            0, CommandIntent(CommandKind.OPEN_APP, "google-chrome"), language="en"
        ),
    )
    gate = ActionGate(ActionPolicy(allowed_apps=frozenset({"google-chrome"})))
    assert isinstance(gate.observe(decision[0]), ActionRequest)


def test_catalog_supplied_localized_name_is_an_exact_app_name() -> None:
    resolver = CatalogSpokenAppResolver(
        _DeviceCatalog((
            InstalledApp(
                "vendor.notes", "Acme Notes", alternate_names=("یادداشت‌های اَکمه",)
            ),
        )),
        {"vendor.notes": "notes"},
    )
    assert resolver.resolve("یادداشت‌های اَکمه").exact
