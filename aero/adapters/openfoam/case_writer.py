"""Render an OpenFOAM case directory from a `CaseSpec`.

Stage 03 writes the case as plain string templates — no Jinja, no Hydra (the
Hydra/pydantic config boundary is Stage 04). The non-trivial part is the
`blockMeshDict`: a 2D **O-grid** around the airfoil, built as four blocks,
each wrapping one quarter of the section —

    A  trailing edge -> upper mid     C  leading edge  -> lower mid
    B  upper mid     -> leading edge  D  lower mid      -> trailing edge

The airfoil surface is a `polyLine` edge per quarter, through the analytic
NACA 0012 points (`aero.adapters.openfoam.geometry`); the outer boundary is a
circle at the far-field radius (`arc` edges). Every vertex is distinct and
every block is a well-formed, positive-volume hexahedron — no doubled
trailing-edge vertex, no `mergePatchPairs`.
"""

from __future__ import annotations

import math
from pathlib import Path

import numpy as np
from numpy.typing import NDArray

from aero.adapters.openfoam.geometry import naca0012_coordinates
from aero.adapters.openfoam.schemas import CaseSpec

_U_INF = 1.0  # reference freestream speed; the solve is dimensionless (Re fixes nu)
_RHO_INF = 1.0  # reference density (incompressible: forceCoeffs dimensionalising)


# --- physical state -----------------------------------------------------------
def _flow_state(spec: CaseSpec) -> dict[str, float]:
    """Derive the dimensionless flow state and turbulence inlet values."""
    nu = _U_INF * spec.chord / spec.reynolds
    # Freestream turbulence: k from intensity, omega from a low viscosity ratio
    # (external aerodynamics — keep the freestream nearly laminar).
    k = 1.5 * (spec.turbulence_intensity * _U_INF) ** 2
    nut_ratio = 0.1
    nut = nut_ratio * nu
    omega = k / nut
    return {"nu": nu, "k": k, "omega": omega, "nut": nut}


# --- grading ------------------------------------------------------------------
def _cell_ratio(length: float, n: int, first: float) -> float:
    """Geometric cell-to-cell ratio so the first of `n` cells has size `first`.

    Solves ``first * (r**n - 1) / (r - 1) == length`` for ``r >= 1`` by
    bisection. Returns 1.0 (uniform) when `first` already over-fills `length`.
    """
    if first * n >= length:
        return 1.0
    lo, hi = 1.0 + 1.0e-9, 4.0
    for _ in range(200):
        mid = 0.5 * (lo + hi)
        total = first * (mid**n - 1.0) / (mid - 1.0)
        if total < length:
            lo = mid
        else:
            hi = mid
    return 0.5 * (lo + hi)


def _eta_expansion(spec: CaseSpec) -> float:
    """blockMesh simpleGrading expansion (last/first cell) for the wall-normal η."""
    length = spec.farfield_radius_chords * spec.chord
    ratio = _cell_ratio(length, spec.n_normal, spec.first_cell_height * spec.chord)
    return ratio ** (spec.n_normal - 1)


# --- airfoil geometry, split into four O-grid quarters ------------------------
def _quarters(spec: CaseSpec) -> dict[str, NDArray[np.float64]]:
    """The four airfoil-quarter point arrays, each ordered from block v0 to v1.

    `naca0012_coordinates` returns the upper surface LE->TE with an odd point
    count, so the middle index is the mid-chord split point.
    """
    n = spec.n_surface
    upper = naca0012_coordinates(2 * n + 1, chord=spec.chord)  # LE -> TE, +y
    lower = upper.copy()
    lower[:, 1] *= -1.0
    return {
        # A: upper mid -> TE          B: LE -> upper mid
        "A": np.asarray(upper[n:], dtype=np.float64),
        "B": np.asarray(upper[: n + 1], dtype=np.float64),
        # C: lower mid -> LE          D: TE -> lower mid
        "C": np.asarray(lower[n::-1], dtype=np.float64),
        "D": np.asarray(lower[: n - 1 : -1], dtype=np.float64),
    }


# --- OpenFOAM dictionary rendering -------------------------------------------
def _header(cls: str, obj: str) -> str:
    return (
        "/*--------------------------------*- C++ -*----------------------------------*\\\n"
        "| aero-research-platform — generated OpenFOAM case (Stage 03 walking skeleton) |\n"
        "\\*---------------------------------------------------------------------------*/\n"
        "FoamFile\n{\n"
        "    version     2.0;\n"
        "    format      ascii;\n"
        f"    class       {cls};\n"
        f"    object      {obj};\n"
        "}\n"
        "// * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * //\n"
    )


def _pt(x: float, y: float, z: float) -> str:
    return f"({x:.8f} {y:.8f} {z:.8f})"


def _blockmeshdict(spec: CaseSpec) -> str:
    c = spec.chord
    cx = 0.5 * c  # O-grid centre (mid-chord)
    r = spec.farfield_radius_chords * c
    span = spec.span
    g = _eta_expansion(spec)
    quarters = _quarters(spec)

    mid = quarters["B"][-1]  # upper mid-chord split point
    um = (float(mid[0]), float(mid[1]))
    lm = (float(mid[0]), -float(mid[1]))
    # 0 te, 1 um, 2 le, 3 lm; 4 O_te, 5 O_um, 6 O_le, 7 O_lm. +8 at z=span.
    base = [
        (c, 0.0),  # 0 trailing edge
        um,  # 1 upper mid
        (0.0, 0.0),  # 2 leading edge
        lm,  # 3 lower mid
        (cx + r, 0.0),  # 4 outer, aft
        (cx, r),  # 5 outer, top
        (cx - r, 0.0),  # 6 outer, fore
        (cx, -r),  # 7 outer, bottom
    ]
    verts = [_pt(x, y, 0.0) for x, y in base] + [_pt(x, y, span) for x, y in base]

    nq, nn = spec.n_surface, spec.n_normal
    # Four O-grid blocks, each ξ along a quarter of the airfoil, η outward.
    # Vertex orders are wound clockwise-in-xy so every block has positive volume.
    blocks = [
        f"    hex (1 0 4 5 9 8 12 13) ({nq} {nn} 1) simpleGrading (1 {g:.6g} 1)",
        f"    hex (2 1 5 6 10 9 13 14) ({nq} {nn} 1) simpleGrading (1 {g:.6g} 1)",
        f"    hex (3 2 6 7 11 10 14 15) ({nq} {nn} 1) simpleGrading (1 {g:.6g} 1)",
        f"    hex (0 3 7 4 8 11 15 12) ({nq} {nn} 1) simpleGrading (1 {g:.6g} 1)",
    ]

    def poly(v1: int, v2: int, pts: NDArray[np.float64], z: float) -> str:
        body = "\n".join(f"            {_pt(float(x), float(y), z)}" for x, y in pts)
        return f"    polyLine {v1} {v2}\n        (\n{body}\n        )"

    # Inner-edge polyLines: interior points only (the endpoints are vertices).
    edges = []
    for (v1, v2), key in (((1, 0), "A"), ((2, 1), "B"), ((3, 2), "C"), ((0, 3), "D")):
        interior = quarters[key][1:-1]
        edges.append(poly(v1, v2, interior, 0.0))
        edges.append(poly(v1 + 8, v2 + 8, interior, span))

    # Outer-boundary arcs: a circle of radius r about the O-grid centre — keeps
    # the wall-normal grid lines near-orthogonal out to the far field.
    def arc(v1: int, v2: int, deg: float, z: float) -> str:
        mx = cx + r * math.cos(math.radians(deg))
        my = r * math.sin(math.radians(deg))
        return f"    arc {v1} {v2} {_pt(mx, my, z)}"

    for v1, v2, deg in ((4, 5, 45.0), (5, 6, 135.0), (6, 7, 225.0), (7, 4, 315.0)):
        edges.append(arc(v1, v2, deg, 0.0))
        edges.append(arc(v1 + 8, v2 + 8, deg, span))

    boundary = """    airfoil
    {
        type wall;
        faces ( (1 0 8 9) (2 1 9 10) (3 2 10 11) (0 3 11 8) );
    }
    farfield
    {
        type patch;
        faces ( (5 4 12 13) (6 5 13 14) (7 6 14 15) (4 7 15 12) );
    }
    front
    {
        type empty;
        faces ( (1 0 4 5) (2 1 5 6) (3 2 6 7) (0 3 7 4) );
    }
    back
    {
        type empty;
        faces ( (9 8 12 13) (10 9 13 14) (11 10 14 15) (8 11 15 12) );
    }"""

    verts_block = "\n".join(f"    {v}" for v in verts)
    blocks_block = "\n".join(blocks)
    edges_block = "\n".join(edges)
    return (
        _header("dictionary", "blockMeshDict")
        + "\nscale 1;\n\n"
        + f"vertices\n(\n{verts_block}\n);\n\n"
        + f"blocks\n(\n{blocks_block}\n);\n\n"
        + f"edges\n(\n{edges_block}\n);\n\n"
        + f"boundary\n(\n{boundary}\n);\n\n"
        + "mergePatchPairs ( );\n"
    )


def _controldict(spec: CaseSpec) -> str:
    aoa = math.radians(spec.aoa_deg)
    drag_dir = f"({math.cos(aoa):.8f} {math.sin(aoa):.8f} 0)"
    lift_dir = f"({-math.sin(aoa):.8f} {math.cos(aoa):.8f} 0)"
    a_ref = spec.chord * spec.span
    return (
        _header("dictionary", "controlDict")
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
        rhoInf          {_RHO_INF};
        magUInf         {_U_INF};
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


def _fvschemes() -> str:
    return (
        _header("dictionary", "fvSchemes")
        + """
ddtSchemes      { default steadyState; }
gradSchemes     { default Gauss linear; }
divSchemes
{
    default         none;
    div(phi,U)      bounded Gauss linearUpwind grad(U);
    div(phi,k)      bounded Gauss upwind;
    div(phi,omega)  bounded Gauss upwind;
    div((nuEff*dev2(T(grad(U))))) Gauss linear;
}
laplacianSchemes  { default Gauss linear limited corrected 0.5; }
interpolationSchemes { default linear; }
snGradSchemes   { default limited corrected 0.5; }
wallDist        { method meshWave; }
"""
    )


def _fvsolution(spec: CaseSpec) -> str:
    return (
        _header("dictionary", "fvSolution")
        + """
solvers
{
    p
    {
        solver          GAMG;
        smoother        GaussSeidel;
        tolerance       1e-8;
        relTol          0.05;
    }
    "(U|k|omega)"
    {
        solver          smoothSolver;
        smoother        symGaussSeidel;
        tolerance       1e-9;
        relTol          0.1;
    }
}

SIMPLE
{
    consistent          yes;
    nNonOrthogonalCorrectors 2;
    residualControl
    {
        p               1e-5;
        U               1e-5;
        "(k|omega)"     1e-5;
    }
}

relaxationFactors
{
    equations
    {
        U               0.9;
        "(k|omega)"     0.7;
    }
}
"""
    )


def _transportproperties(spec: CaseSpec) -> str:
    nu = _flow_state(spec)["nu"]
    return (
        _header("dictionary", "transportProperties")
        + f"""
transportModel  Newtonian;
nu              {nu:.10g};
"""
    )


def _turbulenceproperties(spec: CaseSpec) -> str:
    return (
        _header("dictionary", "turbulenceProperties")
        + f"""
simulationType  RAS;
RAS
{{
    RASModel        {spec.turbulence_model};
    turbulence      on;
    printCoeffs     on;
}}
"""
    )


def _field(obj: str, cls: str, dims: str, internal: str, farfield: str, airfoil: str) -> str:
    return (
        _header(cls, obj)
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
    st = _flow_state(spec)
    aoa = math.radians(spec.aoa_deg)
    u_vec = f"({_U_INF * math.cos(aoa):.8f} {_U_INF * math.sin(aoa):.8f} 0)"
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

    (system / "blockMeshDict").write_text(_blockmeshdict(spec), encoding="utf-8")
    (system / "controlDict").write_text(_controldict(spec), encoding="utf-8")
    (system / "fvSchemes").write_text(_fvschemes(), encoding="utf-8")
    (system / "fvSolution").write_text(_fvsolution(spec), encoding="utf-8")
    (constant / "transportProperties").write_text(_transportproperties(spec), encoding="utf-8")
    (constant / "turbulenceProperties").write_text(_turbulenceproperties(spec), encoding="utf-8")
    for name, text in _fields(spec).items():
        (zero / name).write_text(text, encoding="utf-8")
