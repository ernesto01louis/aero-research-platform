"""Render an OpenFOAM case directory from a `CaseSpec`.

Stage 03 writes the case as plain string templates — no Jinja, no Hydra (the
Hydra/pydantic config boundary is Stage 04). The non-trivial part is the
`blockMeshDict`: a 2D C-grid around the airfoil, built as three blocks —

    block A  lower wake   (wake cut TE->outlet, below)
    block B  airfoil wrap (airfoil surface TE->LE->TE; wraps the front)
    block C  upper wake   (wake cut TE->outlet, above)

The airfoil surface is a `polyLine` edge through the analytic NACA 0012
points (`aero.adapters.openfoam.geometry`); the outer "C" is a `polyLine`
through a sampled semicircle + straight tails. The trailing edge is two
coincident vertices so block B is a well-formed hexahedron that wraps the
section; blockMesh merges the coincident faces.
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
_WAKE_X_EXPANSION = 50.0  # blockMesh ξ expansion along the wake cut (fine near the TE)


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


# --- geometry of the C-grid ---------------------------------------------------
def _airfoil_contour(spec: CaseSpec) -> NDArray[np.float64]:
    """Closed airfoil contour, trailing edge -> lower -> LE -> upper -> trailing edge."""
    upper = naca0012_coordinates(spec.n_surface, chord=spec.chord)  # LE -> TE, +y
    lower = upper[::-1].copy()  # TE -> LE
    lower[:, 1] *= -1.0  # mirror to the lower surface
    # TE..LE (lower) then LE..TE (upper); drop the duplicated LE row at the join.
    return np.asarray(np.vstack([lower, upper[1:]]), dtype=np.float64)


def _outer_contour(spec: CaseSpec) -> NDArray[np.float64]:
    """Outer C boundary from (1,-R) round the front semicircle to (1,+R)."""
    r = spec.farfield_radius_chords * spec.chord
    arc_n = max(spec.n_surface, 60)
    phi = np.linspace(-0.5 * np.pi, -1.5 * np.pi, arc_n)  # (0,-R) -> (-R,0) -> (0,+R)
    arc = np.column_stack([r * np.cos(phi), r * np.sin(phi)])
    tail_lo = np.array([[spec.chord, -r]])  # straight tail, b_te -> (0,-R)
    tail_hi = np.array([[spec.chord, r]])  # straight tail, (0,+R) -> t_te
    return np.asarray(np.vstack([tail_lo, arc, tail_hi]), dtype=np.float64)


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
    c, r = spec.chord, spec.farfield_radius_chords * spec.chord
    x_out = c + spec.wake_length_chords * c
    span = spec.span
    g = _eta_expansion(spec)

    # 8 distinct corner positions; te / outlet-inner are doubled (z=0 and z=span)
    # so block B wraps cleanly. Indices 0-7 at z=0, +8 at z=span.
    base = [
        (x_out, -r),  # 0 o_bot
        (c, -r),  # 1 b_te
        (c, 0.0),  # 2 te_l
        (x_out, 0.0),  # 3 o_in_l
        (c, 0.0),  # 4 te_u   (coincident with te_l)
        (x_out, 0.0),  # 5 o_in_u (coincident with o_in_l)
        (c, r),  # 6 t_te
        (x_out, r),  # 7 o_top
    ]
    verts = [_pt(x, y, 0.0) for x, y in base] + [_pt(x, y, span) for x, y in base]

    wx = _WAKE_X_EXPANSION
    blocks = [
        # A lower wake; B airfoil wrap; C upper wake. η-grading: A runs
        # outer->inner so it uses 1/g; B and C run inner->outer so they use g.
        f"    hex (1 0 3 2 9 8 11 10) ({spec.n_wake} {spec.n_normal} 1) "
        f"simpleGrading ({wx} {1.0 / g:.6g} 1)",
        f"    hex (2 4 6 1 10 12 14 9) ({2 * spec.n_surface} {spec.n_normal} 1) "
        f"simpleGrading (1 {g:.6g} 1)",
        f"    hex (4 5 7 6 12 13 15 14) ({spec.n_wake} {spec.n_normal} 1) "
        f"simpleGrading ({wx} {g:.6g} 1)",
    ]

    def poly(v1: int, v2: int, pts: NDArray[np.float64], z: float) -> str:
        body = "\n".join(f"            {_pt(float(x), float(y), z)}" for x, y in pts)
        return f"    polyLine {v1} {v2}\n        (\n{body}\n        )"

    airfoil = _airfoil_contour(spec)[1:-1]  # interior points (exclude the te vertices)
    outer = _outer_contour(spec)[1:-1]
    edges = [
        poly(2, 4, airfoil, 0.0),
        poly(10, 12, airfoil, span),
        poly(1, 6, outer, 0.0),
        poly(9, 14, outer, span),
    ]

    boundary = """    airfoil
    {
        type wall;
        faces ( (2 10 12 4) );
    }
    farfield
    {
        type patch;
        faces
        (
            (0 8 9 1)
            (3 0 8 11)
            (1 9 14 6)
            (5 13 15 7)
            (6 14 15 7)
        );
    }
    wake_lower
    {
        type patch;
        faces ( (2 3 11 10) );
    }
    wake_upper
    {
        type patch;
        faces ( (4 5 13 12) );
    }
    front
    {
        type empty;
        faces ( (1 0 3 2) (2 4 6 1) (4 5 7 6) );
    }
    back
    {
        type empty;
        faces ( (9 8 11 10) (10 12 14 9) (12 13 15 14) );
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
        # The C-grid wake cut: blocks A and C carry coincident patches there
        # (the trailing edge is a doubled vertex), stitched into an internal
        # face so the wake is continuous across y = 0.
        + "mergePatchPairs ( (wake_lower wake_upper) );\n"
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
laplacianSchemes  { default Gauss linear corrected; }
interpolationSchemes { default linear; }
snGradSchemes   { default corrected; }
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
    nNonOrthogonalCorrectors 1;
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
