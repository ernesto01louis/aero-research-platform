"""Solver-agnostic mesh-generation helpers used by the PyFR and NekRS adapters.

Stage 07. These helpers run *host-side* at `Solver.prepare()` time and emit
solver-native input files (gmsh `.msh2` for PyFR, Nek5000 `.box`/`.par`/`.udf`
for NekRS) into the case directory on the shared NFS dataset. The SIF then
reads them from `/case` at `mesh()` time and runs its native mesher (`pyfr
import`, `genbox` + `genmap`).

PLATFORM-NOT-HUB clean: stdlib + numpy + pydantic only. The helpers do not
import `gmsh` or `pyfr` — the SIFs hold those binaries.
"""

from aero.adapters._meshing.gmsh_high_order import (
    write_taylor_green_msh2,
)
from aero.adapters._meshing.nekmesh_wrapper import (
    write_taylor_green_box,
)

__all__ = [
    "write_taylor_green_box",
    "write_taylor_green_msh2",
]
