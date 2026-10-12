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
    # In-tree development / editable install where metadata isn't yet wired:
    # fall back to a sentinel so callers can detect dev state.
    __version__ = "0.0.1+local"

__all__ = ["__version__"]
