"""Stage 01 smoke test — the very first test in the project.

Verifies that:
1. `import aero` succeeds.
2. The package has a `__version__` attribute.
3. The version string is parseable and starts with the expected pre-release
   prefix `0.0.1` (this is the Stage-01 tag; later stages bump per
   `CHANGELOG.md`).

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
    """Version string starts with the expected Stage-01 prefix.

    Accepts both `0.0.1` (installed from a built wheel) and
    `0.0.1+local` (in-tree editable install where metadata is missing).
    """
    pattern = re.compile(r"^0\.0\.1(\+.*)?$")
    assert pattern.match(aero.__version__), (
        f"Unexpected version string {aero.__version__!r}; "
        "Stage 01 should pin at 0.0.1. Update this test once a new stage bumps."
    )
