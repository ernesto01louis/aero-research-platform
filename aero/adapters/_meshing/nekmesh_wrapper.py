"""Nek5000-format mesh emitters that run host-side; tools live inside the SIF.

NekRS reuses Nek5000's `.re2` binary mesh format and its companion `.par`
(SIMSON-style runtime parameters) + `.udf` (user-defined functions). The
canonical structured-cube case generator is `genbox`; pre-partitioning is
`genmap`. Both ship inside the NekRS SIF — we never need them on the host.

What we *do* emit host-side is the small text input that drives `genbox`:
a `.box` file describing the cube and its element count. The NekRS adapter's
`Solver.mesh()` step bind-mounts the case dir into the SIF and runs

    cd /case && genbox <case>.box && genmap <case>

producing `<case>.re2` and `<case>.ma2` for the solver to consume.
"""

from __future__ import annotations

import math
from pathlib import Path


def write_taylor_green_box(
    path: Path,
    *,
    case_name: str,
    n_elements_per_dir: int,
    domain_half_extent: float = math.pi,
) -> int:
    """Write a `<case>.box` file for genbox to expand into a TG cube `.re2`.

    The `.box` format is Nek5000 ASCII: header, mesh template, element
    counts in each direction, coordinate ranges, boundary-condition codes.
    For Taylor-Green we want a triply-periodic cube — boundary codes `P  `
    on all six faces.

    Returns `n_elements_per_dir**3`, the element count the caller records
    on `MeshHandle.n_elements`. NekRS's spectral order N is set in the
    `.par` file (not here); `n_dof = n_elements * (N+1)**3`.
    """
    if n_elements_per_dir < 2:
        raise ValueError(f"n_elements_per_dir must be >= 2, got {n_elements_per_dir}")
    if domain_half_extent <= 0:
        raise ValueError(f"domain_half_extent must be > 0, got {domain_half_extent}")

    n = n_elements_per_dir
    half_extent = domain_half_extent
    lines = [
        "## genbox input for the aero Taylor-Green vortex case",
        (
            f"## case={case_name}  n={n}^3  "
            f"domain=[-{half_extent:.6f}, {half_extent:.6f}]^3  triply periodic"
        ),
        "1                      # nFields (one velocity field; T is implicit)",
        f"-{n} -{n} -{n}         # negative = uniform spacing in (x, y, z)",
        f"{-half_extent:.6f} {half_extent:.6f}  1.0  # x_min, x_max, geometric ratio",
        f"{-half_extent:.6f} {half_extent:.6f}  1.0  # y_min, y_max, geometric ratio",
        f"{-half_extent:.6f} {half_extent:.6f}  1.0  # z_min, z_max, geometric ratio",
        "P  ,P  ,P  ,P  ,P  ,P  # BC codes (-x +x -y +y -z +z): all periodic",
        "",
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")
    return n**3
