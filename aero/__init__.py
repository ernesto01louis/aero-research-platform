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
    # In-tree development / editable install where metadata isn't yet wired:
    # fall back to a sentinel so callers can detect dev state.
    __version__ = "0.0.1+local"

__all__ = ["__version__"]
