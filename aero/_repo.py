"""Locate the aero-research-platform SOURCE CHECKOUT, or fail loudly (Stage 21, ADR-049 H-16).

Several code paths read files that live in the repository rather than inside the ``aero``
package: ``containers/SHA256SUMS``, ``conf/``, ``data/references/``. They used to find them via
``Path(__file__).parents[N]``, which is only correct for an editable install from a checkout.
Under a wheel install the same arithmetic points into ``site-packages`` and the failure surfaced
later, as a missing file with a misleading path. This helper checks that the computed root
really is a checkout of this repository and raises otherwise (FAIL-LOUD).

The result-crate reader (ADR-047) never calls this. A crate must verify without the repository.
"""

from __future__ import annotations

from pathlib import Path

__all__ = ["SourceCheckoutRequiredError", "source_checkout_root"]


class SourceCheckoutRequiredError(RuntimeError):
    """A repository-file code path ran outside a source checkout of aero-research-platform."""


def source_checkout_root(anchor: Path | None = None) -> Path:
    """Return the repository root that contains this ``aero`` package, or raise.

    ``anchor`` is the directory expected to be the root. It defaults to the parent of the
    installed ``aero`` package, and exists for tests.
    """
    root = (anchor if anchor is not None else Path(__file__).resolve().parents[1]).resolve()
    pyproject = root / "pyproject.toml"
    if (
        not (root / "aero" / "__init__.py").is_file()
        or not pyproject.is_file()
        or 'name = "aero"' not in pyproject.read_text(encoding="utf-8")
    ):
        raise SourceCheckoutRequiredError(
            f"{root} is not a source checkout of aero-research-platform: this code path reads "
            "repository files (containers/, conf/, data/references/) and needs `git clone` + "
            "`uv sync`, not a wheel install."
        )
    return root
