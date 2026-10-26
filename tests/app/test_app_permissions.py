"""Desktop choices keep stable IDs even when names collide or apps disappear."""

from kyrin.app.app_permissions import app_choices
from kyrin.app.settings import AllowedApp
from kyrin.desktop.app_catalog import InstalledApp


class FakeCatalog:
    def __init__(self, apps: tuple[InstalledApp, ...]) -> None:
        self.apps = apps

    def list_apps(self) -> tuple[InstalledApp, ...]:
        return self.apps

    def list_menu_apps(self) -> tuple[InstalledApp, ...]:
        return self.apps

    def find_app(self, platform_id: str) -> InstalledApp | None:
        return next((app for app in self.apps if app.platform_id == platform_id), None)


def test_duplicate_names_get_distinct_stable_bindings() -> None:
    catalog = FakeCatalog(
        (
            InstalledApp("second.desktop", "Browser"),
            InstalledApp("first.desktop", "Browser"),
        )
    )
    first = app_choices(catalog, ())
    second = app_choices(catalog, ())

    assert first == second
    assert {choice.binding.desktop_id for choice in first} == {
        "first.desktop",
        "second.desktop",
    }
    assert len({choice.binding.app_id for choice in first}) == 2
    assert all(choice.installed for choice in first)


def test_existing_id_and_missing_app_remain_visible() -> None:
    existing = (
        AllowedApp("telegram", "telegram.desktop"),
        AllowedApp("old-browser", "removed.desktop"),
    )
    catalog = FakeCatalog((InstalledApp("telegram.desktop", "Telegram"),))

    choices = app_choices(catalog, existing)

    assert choices[0].binding == existing[0]
    assert choices[1].binding == existing[1]
    assert not choices[1].installed


def test_numeric_or_non_latin_display_name_still_has_valid_internal_id() -> None:
    choices = app_choices(
        FakeCatalog(
            (
                InstalledApp("3d.desktop", "3D Viewer"),
                InstalledApp("fa.desktop", "برنامه"),
            )
        ),
        (),
    )
    assert {choice.binding.app_id for choice in choices} == {"app-3d-viewer", "app"}
