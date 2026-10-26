"""Resolve platform app IDs to KYRIN IDs through explicit trusted bindings."""

from collections.abc import Mapping

from kyrin.desktop.app_catalog import AppCatalog


class AppIdentityResolver:
    """Use exact IDs only; a catalog label never establishes identity."""

    def __init__(
        self,
        app_ids: Mapping[str, str],
        catalog: AppCatalog | None = None,
    ) -> None:
        if any(
            not external.strip() or not internal.strip()
            for external, internal in app_ids.items()
        ):
            raise ValueError("app identifiers must not be empty")
        self._app_ids = dict(app_ids)
        self._catalog = catalog

    def resolve(self, platform_id: str | None) -> str | None:
        if platform_id is None:
            return None
        app_id = self._app_ids.get(platform_id)
        if app_id is None:
            return None
        if self._catalog is not None and self._catalog.find_app(platform_id) is None:
            return None
        return app_id
