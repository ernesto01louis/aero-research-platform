"""The package version has ONE source: ``pyproject.toml`` (Stage 21, ADR-049 H-04).

At stage open the version lived in four disagreeing places: pyproject ``0.0.1``, the
``aero/__init__.py`` fallback ``0.0.1+local``, CITATION.cff ``0.0.4``, and a required test
hard-coding ``^0.0.1``. Now ``aero.__version__`` comes from the installed metadata, and this
test pins the installed metadata and the uv.lock root to pyproject. CITATION.cff joins the pin
at the v0.1.0 bump, when its stale ``0.0.4`` is corrected.
"""

from __future__ import annotations

import tomllib
from pathlib import Path

import aero
import pytest

pytestmark = pytest.mark.stage_21

REPO = Path(__file__).resolve().parents[2]


def _pyproject_version() -> str:
    data = tomllib.loads((REPO / "pyproject.toml").read_text())
    version = data["project"]["version"]
    assert isinstance(version, str)
    return version


def test_installed_version_is_the_pyproject_version() -> None:
    assert aero.__version__ == _pyproject_version()


def test_uv_lock_root_is_the_pyproject_version() -> None:
    lock = tomllib.loads((REPO / "uv.lock").read_text())
    roots = [p for p in lock["package"] if p["name"] == "aero"]
    assert len(roots) == 1
    assert roots[0]["version"] == _pyproject_version()


def test_the_fallback_is_not_a_plausible_release() -> None:
    source = (REPO / "aero" / "__init__.py").read_text()
    assert '__version__ = "0+unknown"' in source
    assert '__version__ = "0.0.1+local"' not in source
