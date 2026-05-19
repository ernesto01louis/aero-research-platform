"""Geometry-independent OpenFOAM case-rendering helpers.

These are the pieces every OpenFOAM case shares regardless of geometry — the
dictionary header, point formatting, geometric cell grading, the dimensionless
flow state, and the solver/scheme/transport/turbulence dictionaries. They were
factored out of `case_writer.py` (the airfoil writer) in Stage 05 so the new
TMR writers (`tmr_case_writer.py` — flat plate, 2D bump) reuse them rather than
duplicate them.

Nothing here knows about a specific geometry: functions take primitive
parameters, not a `CaseSpec`, so both the airfoil `CaseSpec` and the TMR
discriminated specs can drive them.
"""

from __future__ import annotations

U_INF = 1.0  # reference freestream speed; the solve is dimensionless (Re fixes nu)
RHO_INF = 1.0  # reference density (incompressible: forceCoeffs dimensionalising)

# Freestream eddy-viscosity ratio nut/nu. NASA TMR specifies a nearly-laminar
# freestream for the k-omega SST verification cases (mu_t/mu_inf ~ 0.009): the
# wall-bounded turbulence is self-sustaining via production, so a higher
# freestream ratio only adds spurious eddy viscosity that convects into the
# boundary layer and inflates skin friction (Stage 05 measured ~+20% on Cd
# with the Stage-03 value of 0.1). See ADR-005.
_FREESTREAM_NUT_RATIO = 0.009


# --- physical state -----------------------------------------------------------
def flow_state(
    *,
    reynolds: float,
    ref_length: float,
    turbulence_intensity: float,
) -> dict[str, float]:
    """Derive the dimensionless flow state and turbulence inlet values.

    `ref_length` is the Reynolds-number length scale (chord for an airfoil,
    plate length for the flat plate). Freestream `k` comes from the intensity;
    `omega` from a low eddy-viscosity ratio so the freestream stays nearly
    laminar — standard practice for external aerodynamics.
    """
    nu = U_INF * ref_length / reynolds
    k = 1.5 * (turbulence_intensity * U_INF) ** 2
    nut = _FREESTREAM_NUT_RATIO * nu
    omega = k / nut
    return {"nu": nu, "k": k, "omega": omega, "nut": nut}


# --- grading ------------------------------------------------------------------
def cell_ratio(length: float, n: int, first: float) -> float:
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


def expansion(length: float, n: int, first: float) -> float:
    """blockMesh `simpleGrading` expansion (last-cell / first-cell) over `length`.

    `first` is the desired first-cell size; the geometric ratio that fits `n`
    such cells into `length` is raised to ``n - 1`` to give the end-to-end
    expansion blockMesh expects.
    """
    ratio = cell_ratio(length, n, first)
    return ratio ** (n - 1)


# --- OpenFOAM dictionary rendering -------------------------------------------
def header(cls: str, obj: str) -> str:
    """The standard `FoamFile` dictionary header."""
    return (
        "/*--------------------------------*- C++ -*----------------------------------*\\\n"
        "| aero-research-platform — generated OpenFOAM case                            |\n"
        "\\*---------------------------------------------------------------------------*/\n"
        "FoamFile\n{\n"
        "    version     2.0;\n"
        "    format      ascii;\n"
        f"    class       {cls};\n"
        f"    object      {obj};\n"
        "}\n"
        "// * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * //\n"
    )


def pt(x: float, y: float, z: float) -> str:
    """Format a single `(x y z)` point at fixed precision."""
    return f"({x:.8f} {y:.8f} {z:.8f})"


def fvschemes() -> str:
    """Discretisation schemes — steady-state RANS, second-order-ish, bounded."""
    return (
        header("dictionary", "fvSchemes")
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


def fvsolution() -> str:
    """SIMPLE solver controls — GAMG pressure, smoothSolver for the rest."""
    return (
        header("dictionary", "fvSolution")
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
        p               1e-6;
        U               1e-6;
        "(k|omega)"     1e-6;
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


def transport_properties(nu: float) -> str:
    """`constant/transportProperties` — Newtonian, kinematic viscosity `nu`."""
    return (
        header("dictionary", "transportProperties")
        + f"""
transportModel  Newtonian;
nu              {nu:.10g};
"""
    )


def turbulence_properties(model: str) -> str:
    """`constant/turbulenceProperties` — a RAS closure."""
    return (
        header("dictionary", "turbulenceProperties")
        + f"""
simulationType  RAS;
RAS
{{
    RASModel        {model};
    turbulence      on;
    printCoeffs     on;
}}
"""
    )
