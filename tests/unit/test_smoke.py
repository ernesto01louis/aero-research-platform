"""Stage 01 smoke test — the very first test in the project.

Verifies that:
1. `import aero` succeeds.
2. The package has a `__version__` attribute.
3. The version string is a plain X.Y.Z release (single-sourced from
   pyproject.toml; see test_version_single_source.py).

This test runs in CI on every PR and locally via the pre-commit
`pytest-unit` hook. Failing this test means the package layout is broken
and no subsequent stage will work.
"""

from __future__ import annotations

import re

import aero


def test_aero_imports() -> None:
    """The package imports cleanly with only base deps installed."""
    assert aero is not None


def test_aero_has_version() -> None:
    """`aero.__version__` is present and is a non-empty string."""
    assert hasattr(aero, "__version__")
    assert isinstance(aero.__version__, str)
    assert aero.__version__


def test_aero_version_format() -> None:
    """The version is a plain PEP 440 release (``X.Y.Z``), never the "0+unknown" sentinel.

    Which release it is lives in pyproject.toml alone; tests/unit/test_version_single_source.py
    pins ``aero.__version__``, the uv.lock root and CITATION.cff to it (Stage 21, ADR-049 H-04).
    This test used to hard-code 0.0.1 and had to be edited at every bump.
    """
    assert re.fullmatch(r"\d+\.\d+\.\d+", aero.__version__), (
        f"Unexpected version string {aero.__version__!r}: aero is not installed from this "
        "source tree (run `uv sync`), or the version is not a plain X.Y.Z release."
    )
