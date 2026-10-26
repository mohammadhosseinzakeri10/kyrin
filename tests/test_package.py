"""Tests for the base KYRIN package."""

import kyrin


def test_package_imports() -> None:
    """Ensure the KYRIN package can be imported successfully."""
    assert kyrin is not None
