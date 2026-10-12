"""Repository-file code paths fail loudly outside a source checkout (Stage 21, ADR-049 H-16)."""

from __future__ import annotations

from pathlib import Path

import pytest
from aero._repo import SourceCheckoutRequiredError, source_checkout_root

pytestmark = pytest.mark.stage_21

REPO = Path(__file__).resolve().parents[2]


def test_the_checkout_root_is_found() -> None:
    assert source_checkout_root() == REPO.resolve()


def test_a_site_packages_like_parent_is_refused(tmp_path: Path) -> None:
    (tmp_path / "aero").mkdir()
    (tmp_path / "aero" / "__init__.py").write_text("")
    with pytest.raises(SourceCheckoutRequiredError, match="not a source checkout"):
        source_checkout_root(tmp_path)


def test_another_project_with_a_pyproject_is_refused(tmp_path: Path) -> None:
    (tmp_path / "aero").mkdir()
    (tmp_path / "aero" / "__init__.py").write_text("")
    (tmp_path / "pyproject.toml").write_text('[project]\nname = "someone-else"\n')
    with pytest.raises(SourceCheckoutRequiredError):
        source_checkout_root(tmp_path)


@pytest.mark.parametrize(
    "module",
    [
        "aero.cli",
        "aero.vv.fsi.hg2007_flexible_foil",
        "aero.vv.external_geometry.turek_hron_cfd",
        "aero.vv.fsi.turek_hron_fsi3",
    ],
)
def test_every_repo_root_helper_delegates(module: str) -> None:
    import importlib

    mod = importlib.import_module(module)
    assert mod._repo_root() == REPO.resolve()
    source = Path(mod.__file__).read_text()
    assert "parents[3]" not in source and "parents[1]" not in source
