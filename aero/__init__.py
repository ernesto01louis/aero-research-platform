"""aero — open-source peer-review-grade computational aerodynamics platform.

Per Constitution Invariant 1 (PLATFORM-NOT-HUB), this top-level package
imports only stdlib + numpy + pydantic. Solver-, ML-, and cloud-specific
imports are gated behind optional extras (`aero[openfoam]`, `aero[su2]`,
`aero[pyfr]`, `aero[nekrs]`, `aero[jax-fluids]`, `aero[physicsnemo-cu12]`,
`aero[precice]`, `aero[gpu-rental]`, `aero[uq]`, `aero[agentic]`,
`aero[literature]`, `aero[orchestration]`).

CI job `import-platform-only` (live by Stage 06) verifies that a fresh
`pip install aero` (no extras) succeeds and that this module imports
cleanly without any heavy dependency present.
"""

from __future__ import annotations

from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as _pkg_version

try:
    __version__: str = _pkg_version("aero")
except PackageNotFoundError:
    # Imported from a source tree with no installed distribution metadata. The sentinel is
    # deliberately NOT a plausible release number (Stage 21, ADR-049 H-04): the old fallback
    # "0.0.1+local" looked like a real version and would silently mislabel anything stamped
    # with it. tests/unit/test_version_single_source.py pins the installed value to pyproject.
    __version__ = "0+unknown"

__all__ = ["__version__"]
