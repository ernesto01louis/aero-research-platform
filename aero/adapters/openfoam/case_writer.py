"""Render an OpenFOAM case directory from an airfoil `CaseSpec`.

The case is written as plain string templates — no Jinja. The non-trivial part
is the `blockMeshDict`: a 2D **multi-block C-grid** around the airfoil.

Stage 05 replaced the Stage-03 four-block O-grid (a closed ring at a 20-chord
circular far field, whose sharp trailing edge was badly skewed and which biased
Cd ~+11 %). The C-grid is eight blocks with a rectangular far field at
`farfield_extent_chords` and an explicit **wake cut** running downstream from
the trailing edge — the wake cut gives the sharp TE a well-defined discrete
continuation instead of forcing the grid to wrap a singular point. See ADR-005.

Block layout (upper half; the lower half mirrors it about the chord line):

    UF  inlet  -> LE    (front block, no wall)
    UA1 LE     -> mid   (upper surface, wall)
    UA2 mid    -> TE    (upper surface, wall)
    UW  TE     -> outlet (wake-cut block, no wall)

The airfoil surface is split at mid-chord so the upper- and lower-surface
`polyLine` edges never share an edge key (a single edge `(LE, TE)` cannot carry
two different curves). The front line (inlet->LE) and the wake cut (TE->outlet)
are internal faces shared by the upper and lower blocks — every vertex is
distinct, every block is a positive-volume hexahedron, no `mergePatchPairs`.
"""

from __future__ import annotations

import math
from pathlib import Path

import numpy as np
from numpy.typing import NDArray

from aero.adapters.openfoam._foam_common import (
    RHO_INF,
    U_INF,
    expansion,
    flow_state,
    fvschemes,
    fvsolution,
    header,
    pt,
    transport_properties,
    turbulence_properties,
)
from aero.adapters.openfoam.geometry import naca0012_coordinates
from aero.adapters.openfoam.schemas import CaseSpec


# --- airfoil surface, split at mid-chord --------------------------------------
def _surfaces(spec: CaseSpec) -> dict[str, NDArray[np.float64]]:
    """Upper and lower surface point arrays, each LE -> TE, with `2*n_surface+1`
    points so index `n_surface` is the exact mid-chord split point."""
    n = spec.n_surface
    upper = naca0012_coordinates(2 * n + 1, chord=spec.chord)  # LE -> TE, +y
    lower = upper.copy()
    lower[:, 1] *= -1.0
    return {"upper": np.asarray(upper, np.float64), "lower": np.asarray(lower, np.float64)}


# --- OpenFOAM dictionary rendering -------------------------------------------
def _blockmeshdict(spec: CaseSpec) -> str:
    c = spec.chord
    ext = spec.farfield_extent_chords * c  # rectangular far-field half-extent
    span = spec.span
    surf = _surfaces(spec)
    n = spec.n_surface
    umid = surf["upper"][n]
    xm, ym = float(umid[0]), float(umid[1])

    # --- 16 base vertices at z=0 (duplicated at z=span as +16) ---
    base = [
        (-ext, 0.0),  # 0  inlet point
        (0.0, 0.0),  # 1  leading edge
        (xm, ym),  # 2  upper mid-chord
        (c, 0.0),  # 3  trailing edge
        (xm, -ym),  # 4  lower mid-chord
        (ext, 0.0),  # 5  outlet point
        (-ext, ext),  # 6  far field, above inlet
        (0.0, ext),  # 7  far field, above LE
        (xm, ext),  # 8  far field, above mid
        (c, ext),  # 9  far field, above TE
        (ext, ext),  # 10 far field, above outlet
        (-ext, -ext),  # 11 far field, below inlet
        (0.0, -ext),  # 12 far field, below LE
        (xm, -ext),  # 13 far field, below mid
        (c, -ext),  # 14 far field, below TE
        (ext, -ext),  # 15 far field, below outlet
    ]
    verts = [pt(x, y, 0.0) for x, y in base] + [pt(x, y, span) for x, y in base]

    # --- grading ---
    g_eta = expansion(ext, spec.n_normal, spec.first_cell_height * c)
    e_front = expansion(ext, spec.n_front, 0.01 * c)
    e_wake = expansion(ext, spec.n_wake, 0.01 * c)
    ns, nn, nf, nw = spec.n_surface, spec.n_normal, spec.n_front, spec.n_wake

    # --- 8 blocks: z=0 face wound CCW-from-above, +16 for the z=span face ---
    # (v0 v1 v2 v3) at z=0 then (v0 v1 v2 v3)+16; counts along (v0->v1, v1->v2, z).
    def hexb(a: int, b: int, d: int, e: int, n1: int, n2: int, gx: float, gy: float) -> str:
        face = (a, b, d, e)
        top = tuple(v + 16 for v in face)
        vs = " ".join(str(v) for v in face + top)
        return f"    hex ({vs}) ({n1} {n2} 1) simpleGrading ({gx:.8g} {gy:.8g} 1)"

    blocks = [
        hexb(0, 1, 7, 6, nf, nn, 1.0 / e_front, g_eta),  # UF
        hexb(1, 2, 8, 7, ns, nn, 1.0, g_eta),  # UA1
        hexb(2, 3, 9, 8, ns, nn, 1.0, g_eta),  # UA2
        hexb(3, 5, 10, 9, nw, nn, e_wake, g_eta),  # UW
        hexb(11, 12, 1, 0, nf, nn, 1.0 / e_front, 1.0 / g_eta),  # LF
        hexb(12, 13, 4, 1, ns, nn, 1.0, 1.0 / g_eta),  # LA1
        hexb(13, 14, 3, 4, ns, nn, 1.0, 1.0 / g_eta),  # LA2
        hexb(14, 15, 5, 3, nw, nn, e_wake, 1.0 / g_eta),  # LW
    ]

    # --- polyLine edges along the airfoil surface (interior points only) ---
    def poly(v1: int, v2: int, pts: NDArray[np.float64], z: float) -> str:
        body = "\n".join(f"            {pt(float(x), float(y), z)}" for x, y in pts)
        return f"    polyLine {v1} {v2}\n        (\n{body}\n        )"

    edges = []
    # (v1, v2, interior point slice) — LE->mid and mid->TE, upper then lower.
    specs = [
        (1, 2, surf["upper"][1:n]),
        (2, 3, surf["upper"][n + 1 : 2 * n]),
        (1, 4, surf["lower"][1:n]),
        (4, 3, surf["lower"][n + 1 : 2 * n]),
    ]
    for v1, v2, interior in specs:
        edges.append(poly(v1, v2, interior, 0.0))
        edges.append(poly(v1 + 16, v2 + 16, interior, span))

    # --- boundary patches ---
    def face(a: int, b: int) -> str:
        return f"({a} {b} {b + 16} {a + 16})"

    # airfoil wall: the inner edge of each surface block.
    wall = " ".join(face(a, b) for a, b in ((1, 2), (2, 3), (1, 4), (4, 3)))
    # far field: every outer / inlet / outlet face (freestream BC handles in/out).
    outer = [
        (0, 6),
        (0, 11),
        (5, 10),
        (15, 5),  # inlet (left), outlet (right)
        (6, 7),
        (7, 8),
        (8, 9),
        (9, 10),  # top
        (11, 12),
        (12, 13),
        (13, 14),
        (14, 15),  # bottom
    ]
    farfield = " ".join(face(a, b) for a, b in outer)
    # 2D: every block's z=0 face is `front`, its z=span face is `back`.
    z_faces = [
        (0, 1, 7, 6),
        (1, 2, 8, 7),
        (2, 3, 9, 8),
        (3, 5, 10, 9),
        (11, 12, 1, 0),
        (12, 13, 4, 1),
        (13, 14, 3, 4),
        (14, 15, 5, 3),
    ]
    front = " ".join(f"({a} {b} {d} {e})" for a, b, d, e in z_faces)
    back = " ".join(f"({a + 16} {b + 16} {d + 16} {e + 16})" for a, b, d, e in z_faces)

    boundary = f"""    airfoil
    {{
        type wall;
        faces ( {wall} );
    }}
    farfield
    {{
        type patch;
        faces ( {farfield} );
    }}
    front
    {{
        type empty;
        faces ( {front} );
    }}
    back
    {{
        type empty;
        faces ( {back} );
    }}"""

    verts_block = "\n".join(f"    {v}" for v in verts)
    return (
        header("dictionary", "blockMeshDict")
        + "\nscale 1;\n\n"
        + f"vertices\n(\n{verts_block}\n);\n\n"
        + "blocks\n(\n"
        + "\n".join(blocks)
        + "\n);\n\n"
        + "edges\n(\n"
        + "\n".join(edges)
        + "\n);\n\n"
        + f"boundary\n(\n{boundary}\n);\n\n"
        + "mergePatchPairs ( );\n"
    )


def _controldict(spec: CaseSpec) -> str:
    aoa = math.radians(spec.aoa_deg)
    drag_dir = f"({math.cos(aoa):.8f} {math.sin(aoa):.8f} 0)"
    lift_dir = f"({-math.sin(aoa):.8f} {math.cos(aoa):.8f} 0)"
    a_ref = spec.chord * spec.span
    return (
        header("dictionary", "controlDict")
        + f"""
application     simpleFoam;
startFrom       startTime;
startTime       0;
stopAt          endTime;
endTime         {spec.end_time};
deltaT          1;
writeControl    timeStep;
writeInterval   {spec.end_time};
purgeWrite      2;
writeFormat     ascii;
writePrecision  8;
runTimeModifiable false;

functions
{{
    forceCoeffs1
    {{
        type            forceCoeffs;
        libs            (forces);
        writeControl    timeStep;
        writeInterval   1;
        patches         (airfoil);
        rho             rhoInf;
        rhoInf          {RHO_INF};
        magUInf         {U_INF};
        lRef            {spec.chord};
        Aref            {a_ref};
        dragDir         {drag_dir};
        liftDir         {lift_dir};
        CofR            (0.25 0 0);
        pitchAxis       (0 0 1);
    }}
}}
"""
    )


def _field(obj: str, cls: str, dims: str, internal: str, farfield: str, airfoil: str) -> str:
    return (
        header(cls, obj)
        + f"""
dimensions      {dims};
internalField   uniform {internal};

boundaryField
{{
    airfoil
    {{
{airfoil}
    }}
    farfield
    {{
{farfield}
    }}
    front {{ type empty; }}
    back  {{ type empty; }}
}}
"""
    )


def _fields(spec: CaseSpec) -> dict[str, str]:
    st = flow_state(
        reynolds=spec.reynolds,
        ref_length=spec.chord,
        turbulence_intensity=spec.turbulence_intensity,
    )
    aoa = math.radians(spec.aoa_deg)
    u_vec = f"({U_INF * math.cos(aoa):.8f} {U_INF * math.sin(aoa):.8f} 0)"
    k, omega, nut = st["k"], st["omega"], st["nut"]
    return {
        "U": _field(
            "U",
            "volVectorField",
            "[0 1 -1 0 0 0 0]",
            u_vec,
            f"        type freestream;\n        freestreamValue uniform {u_vec};",
            "        type noSlip;",
        ),
        "p": _field(
            "p",
            "volScalarField",
            "[0 2 -2 0 0 0 0]",
            "0",
            "        type freestreamPressure;\n        freestreamValue uniform 0;",
            "        type zeroGradient;",
        ),
        "nut": _field(
            "nut",
            "volScalarField",
            "[0 2 -1 0 0 0 0]",
            f"{nut:.8g}",
            f"        type freestream;\n        freestreamValue uniform {nut:.8g};",
            "        type nutkWallFunction;\n        value uniform 0;",
        ),
        "k": _field(
            "k",
            "volScalarField",
            "[0 2 -2 0 0 0 0]",
            f"{k:.8g}",
            f"        type inletOutlet;\n        inletValue uniform {k:.8g};"
            f"\n        value uniform {k:.8g};",
            f"        type kqRWallFunction;\n        value uniform {k:.8g};",
        ),
        "omega": _field(
            "omega",
            "volScalarField",
            "[0 0 -1 0 0 0 0]",
            f"{omega:.8g}",
            f"        type inletOutlet;\n        inletValue uniform {omega:.8g};"
            f"\n        value uniform {omega:.8g};",
            f"        type omegaWallFunction;\n        value uniform {omega:.8g};",
        ),
    }


def write_case(spec: CaseSpec, dest: Path) -> None:
    """Write a complete OpenFOAM case (`system/`, `constant/`, `0/`) under `dest`."""
    system = dest / "system"
    constant = dest / "constant"
    zero = dest / "0"
    for d in (system, constant, zero):
        d.mkdir(parents=True, exist_ok=True)

    nu = flow_state(
        reynolds=spec.reynolds,
        ref_length=spec.chord,
        turbulence_intensity=spec.turbulence_intensity,
    )["nu"]
    (system / "blockMeshDict").write_text(_blockmeshdict(spec), encoding="utf-8")
    (system / "controlDict").write_text(_controldict(spec), encoding="utf-8")
    (system / "fvSchemes").write_text(fvschemes(), encoding="utf-8")
    (system / "fvSolution").write_text(fvsolution(), encoding="utf-8")
    (constant / "transportProperties").write_text(transport_properties(nu), encoding="utf-8")
    (constant / "turbulenceProperties").write_text(
        turbulence_properties(spec.turbulence_model), encoding="utf-8"
    )
    for name, text in _fields(spec).items():
        (zero / name).write_text(text, encoding="utf-8")
