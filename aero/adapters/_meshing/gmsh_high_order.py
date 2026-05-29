"""gmsh-format mesh emitters that run host-side, no gmsh dependency required.

For PyFR's Taylor-Green vortex the only mesh needed is a uniform triply-
periodic hex cube `[-pi, pi]^3` with `n x n x n` cells. We can emit the
gmsh MSH 2.2 ASCII file by hand from numpy — much simpler than shelling out
to `gmsh` and avoids requiring gmsh on the host (it ships only inside the
PyFR SIF, used by `pyfr import` at `Solver.mesh()` time).

The MSH 2.2 format is well-documented at <https://gmsh.info/doc/texinfo/
gmsh.html#MSH-file-format-version-2>; we emit the Nodes block and a Elements
block of element-type 5 (8-node hexahedron). Six "side groups" (one per
periodic face pair) are emitted as element-type 3 quads so PyFR's
`pyfr import` can attach periodic boundary conditions.

PyFR's periodic BCs are declared in the `solver.ini` `[soln-bcs-...]` blocks
that point at these named physical surfaces, e.g. `[soln-bcs-x_minus]
type = periodic_x`.
"""

from __future__ import annotations

import math
from pathlib import Path

import numpy as np
import numpy.typing as npt

# Periodic BC face physical-group ids the emitted .geo declares — referenced
# from `aero/adapters/pyfr/case_writer.py` when stamping `solver.ini`.
PERIODIC_FACE_TAGS: dict[str, int] = {
    "x_minus": 1,
    "x_plus": 2,
    "y_minus": 3,
    "y_plus": 4,
    "z_minus": 5,
    "z_plus": 6,
}
VOLUME_TAG: int = 100  # the hex volume's physical tag


def _node_index(i: int, j: int, k: int, npts: int) -> int:
    """Lexicographic node id in a structured (npts+1)^3 grid, 1-based for gmsh."""
    return 1 + i + j * npts + k * npts * npts


def write_taylor_green_msh2(
    path: Path,
    *,
    n_elements_per_dir: int,
    domain_half_extent: float = math.pi,
) -> int:
    """Write a triply-periodic hex cube mesh in gmsh MSH 2.2 ASCII format.

    The cube is `[-L, L]^3` with `n x n x n` hexahedral elements. Six named
    physical surfaces (`x_minus`, `x_plus`, `y_minus`, `y_plus`, `z_minus`,
    `z_plus`) carry the periodic BC tags from `PERIODIC_FACE_TAGS`. The hex
    volume carries `VOLUME_TAG`. Returns `n_elements_per_dir**3` — the total
    element count, for the caller to record on `MeshHandle.n_elements`.

    Numbering: nodes lexicographic, 1-indexed (gmsh convention). Hex element
    node order is the gmsh-5 convention (`HEX8`):
        (i,j,k), (i+1,j,k), (i+1,j+1,k), (i,j+1,k),
        (i,j,k+1), (i+1,j,k+1), (i+1,j+1,k+1), (i,j+1,k+1).
    """
    if n_elements_per_dir < 2:
        raise ValueError(f"n_elements_per_dir must be >= 2, got {n_elements_per_dir}")
    if domain_half_extent <= 0:
        raise ValueError(f"domain_half_extent must be > 0, got {domain_half_extent}")

    n = n_elements_per_dir
    npts = n + 1  # nodes per direction
    coords: npt.NDArray[np.float64] = np.linspace(-domain_half_extent, domain_half_extent, npts)

    lines: list[str] = []
    lines.append("$MeshFormat")
    lines.append("2.2 0 8")
    lines.append("$EndMeshFormat")

    # Physical names — gmsh dim, tag, "name" triples.
    lines.append("$PhysicsNames")  # gmsh accepts both spellings; canonical is PhysicalNames
    # Standardise on the canonical spelling.
    lines[-1] = "$PhysicalNames"
    lines.append(str(6 + 1))  # six surfaces + one volume
    for name, tag in PERIODIC_FACE_TAGS.items():
        lines.append(f'2 {tag} "{name}"')
    lines.append(f'3 {VOLUME_TAG} "fluid"')
    lines.append("$EndPhysicalNames")

    # Nodes — lexicographic.
    n_total_nodes = npts**3
    lines.append("$Nodes")
    lines.append(str(n_total_nodes))
    for k in range(npts):
        z = coords[k]
        for j in range(npts):
            y = coords[j]
            for i in range(npts):
                x = coords[i]
                node_id = _node_index(i, j, k, npts)
                lines.append(f"{node_id} {x:.16g} {y:.16g} {z:.16g}")
    lines.append("$EndNodes")

    # Elements — n^3 hexahedra + 6 * n^2 quads (one per periodic face).
    n_hex = n * n * n
    n_quad = 6 * n * n
    lines.append("$Elements")
    lines.append(str(n_hex + n_quad))
    elem_id = 1

    # Hexahedra (gmsh type 5). Tags: number-of-tags (2), physical, geometrical.
    for k in range(n):
        for j in range(n):
            for i in range(n):
                nodes = [
                    _node_index(i, j, k, npts),
                    _node_index(i + 1, j, k, npts),
                    _node_index(i + 1, j + 1, k, npts),
                    _node_index(i, j + 1, k, npts),
                    _node_index(i, j, k + 1, npts),
                    _node_index(i + 1, j, k + 1, npts),
                    _node_index(i + 1, j + 1, k + 1, npts),
                    _node_index(i, j + 1, k + 1, npts),
                ]
                node_str = " ".join(str(n_id) for n_id in nodes)
                lines.append(f"{elem_id} 5 2 {VOLUME_TAG} 1 {node_str}")
                elem_id += 1

    # Periodic faces — six surfaces, each n*n quad faces (gmsh type 3).
    # Quad node order: counter-clockwise looking from the outside.
    for name, tag in PERIODIC_FACE_TAGS.items():
        axis, side = name.split("_")
        for a in range(n):
            for b in range(n):
                if axis == "x":
                    i = 0 if side == "minus" else n
                    quad = [
                        _node_index(i, a, b, npts),
                        _node_index(i, a + 1, b, npts),
                        _node_index(i, a + 1, b + 1, npts),
                        _node_index(i, a, b + 1, npts),
                    ]
                elif axis == "y":
                    j = 0 if side == "minus" else n
                    quad = [
                        _node_index(a, j, b, npts),
                        _node_index(a + 1, j, b, npts),
                        _node_index(a + 1, j, b + 1, npts),
                        _node_index(a, j, b + 1, npts),
                    ]
                else:  # axis == "z"
                    k = 0 if side == "minus" else n
                    quad = [
                        _node_index(a, b, k, npts),
                        _node_index(a + 1, b, k, npts),
                        _node_index(a + 1, b + 1, k, npts),
                        _node_index(a, b + 1, k, npts),
                    ]
                quad_str = " ".join(str(q) for q in quad)
                lines.append(f"{elem_id} 3 2 {tag} 1 {quad_str}")
                elem_id += 1

    lines.append("$EndElements")
    lines.append("")  # trailing newline for posixly correct text file

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")
    return n_hex
