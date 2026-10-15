"""The package version has ONE source: ``pyproject.toml`` (Stage 21, ADR-049 H-04).

At stage open the version lived in four disagreeing places: pyproject ``0.0.1``, the
``aero/__init__.py`` fallback ``0.0.1+local``, CITATION.cff ``0.0.4``, and a required test
hard-coding ``^0.0.1``. Now ``aero.__version__`` comes from the installed metadata, and this
test pins the installed metadata, the uv.lock root and CITATION.cff to pyproject. CITATION.cff
joined the pin at the v0.1.0 bump, when its stale ``0.0.4`` was corrected. Its ``date-released``
must also equal the CHANGELOG date of that version (ADR-049 R3).
"""

from __future__ import annotations

import re
import tomllib
from pathlib import Path

import aero
import pytest
import yaml

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


def test_citation_cff_is_the_pyproject_version_and_the_changelog_date() -> None:
    cff = yaml.safe_load((REPO / "CITATION.cff").read_text(encoding="utf-8"))
    version = _pyproject_version()
    assert cff["version"] == version
    changelog = (REPO / "CHANGELOG.md").read_text(encoding="utf-8")
    m = re.search(rf"^## \[{re.escape(version)}\] - (\d{{4}}-\d{{2}}-\d{{2}})$", changelog, re.M)
    assert m is not None, f"CHANGELOG.md has no '## [{version}] - YYYY-MM-DD' heading"
    assert str(cff["date-released"]) == m.group(1)


def test_the_fallback_is_not_a_plausible_release() -> None:
    source = (REPO / "aero" / "__init__.py").read_text()
    assert '__version__ = "0+unknown"' in source
    assert '__version__ = "0.0.1+local"' not in source
