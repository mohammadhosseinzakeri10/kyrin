"""Pinned check environments must continue to satisfy project metadata."""

import tomllib
from pathlib import Path

import pytest
from packaging.requirements import Requirement
from packaging.utils import canonicalize_name

ROOT = Path(__file__).resolve().parents[2]


def _pins(profile: str) -> dict[str, str]:
    pins: dict[str, str] = {}
    for line in (ROOT / "requirements" / f"{profile}.txt").read_text().splitlines():
        if not line or line.startswith("#"):
            continue
        requirement = Requirement(line)
        specifiers = list(requirement.specifier)
        assert len(specifiers) == 1 and specifiers[0].operator == "=="
        assert requirement.url is None and requirement.marker is None
        pins[canonicalize_name(requirement.name)] = specifiers[0].version
    return pins


@pytest.mark.parametrize("profile", ["core", "dev", "bootstrap", "test-ui"])
def test_pins_satisfy_current_project_requirements(profile: str) -> None:
    project = tomllib.loads((ROOT / "pyproject.toml").read_text())
    requirements = {
        "core": project["project"]["dependencies"],
        "dev": project["project"]["optional-dependencies"]["dev"],
        "bootstrap": project["build-system"]["requires"],
        "test-ui": [
            item
            for item in project["project"]["optional-dependencies"]["desktop"]
            if canonicalize_name(Requirement(item).name) == "pyside6-essentials"
        ],
    }[profile]
    assert requirements
    pins = _pins(profile)
    for item in requirements:
        requirement = Requirement(item)
        assert pins[canonicalize_name(requirement.name)] in requirement.specifier


def test_profiles_share_versions_and_keep_optional_runtimes_out_of_core() -> None:
    combined: dict[str, str] = {}
    for profile in ["core", "dev", "bootstrap", "test-ui"]:
        for name, version in _pins(profile).items():
            assert combined.get(name, version) == version
            combined[name] = version
    project = tomllib.loads((ROOT / "pyproject.toml").read_text())
    optional_runtimes = {
        canonicalize_name(Requirement(item).name)
        for extra, requirements in project["project"]["optional-dependencies"].items()
        if extra != "dev"
        for item in requirements
    }
    assert not set(_pins("core")) & optional_runtimes
