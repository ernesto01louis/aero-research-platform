"""aero — open-source peer-review-grade computational aerodynamics platform.

Per Constitution Invariant 1 (PLATFORM-NOT-HUB), this top-level package
imports only stdlib + numpy + pydantic. Solver-, ML- and cloud-specific
imports are gated behind optional extras: `cad`, `dev`, `gpu-rental`,
`jax-fluids`, `nekrs`, `openfoam`, `physicsnemo-cu12`, `precice`,
`provenance`, `pyfr`, `su2`, `surrogate-smoke`, `vv` (pyproject.toml).

CI job `import-platform-only` (Stage 06) verifies that an install with no
extras imports cleanly without any heavy dependency present. Install from a
clone with `uv sync`, or the wheel attached to a GitHub Release. The PyPI
name `aero` belongs to an unrelated project.
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
