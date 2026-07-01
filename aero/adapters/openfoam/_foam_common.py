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


def fvsolution(
    *, pressure_solver: str = "GAMG", u_relax: float = 0.9, kw_relax: float = 0.7
) -> str:
    """SIMPLE solver controls — pressure solver + smoothSolver for the rest.

    `pressure_solver` is `GAMG` (the default; fast on well-conditioned meshes)
    or `PCG`. PCG with a DIC preconditioner is far more robust on meshes with
    extreme cell aspect ratios, where GAMG's coarsening stalls — the TMR
    long-channel cases use it.

    `u_relax` / `kw_relax` are the SIMPLE(C) momentum and turbulence
    under-relaxation factors (defaults 0.9 / 0.7 — the well-conditioned
    airfoil values). Harder meshes (the blunt-TE base wake) take lower values
    for stability; the converged solution is unchanged, only the path to it.
    """
    if pressure_solver == "PCG":
        p_block = """    p
    {
        solver          PCG;
        preconditioner  DIC;
        tolerance       1e-8;
        relTol          0.01;
    }"""
    else:
        p_block = """    p
    {
        solver          GAMG;
        smoother        GaussSeidel;
        tolerance       1e-8;
        relTol          0.05;
    }"""
    return (
        header("dictionary", "fvSolution")
        + """
solvers
{
"""
        + p_block
        + """
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
        U               """
        + f"{u_relax:.8g};"
        + """
        "(k|omega)"     """
        + f"{kw_relax:.8g};"
        + """
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
    """`constant/turbulenceProperties` — a RAS closure, or laminar.

    `model == "laminar"` selects `simulationType laminar`: the momentum equation
    sees only the molecular viscosity (no k/omega/nut transport). Used by the
    forward-regime low-Re cases (Blasius flat plate, laminar airfoil) where the
    flow is below transition. Any other value is a RAS `RASModel`.
    """
    if model == "laminar":
        return (
            header("dictionary", "turbulenceProperties")
            + """
simulationType  laminar;
"""
        )
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


# --- transient (pimpleFoam) dictionaries --------------------------------------
def transient_fvschemes() -> str:
    """Transient laminar schemes — first-order Euler in time, second-order space.

    Shared by the transient/moving cases (cylinder, plunging airfoil). Euler is the
    robust default for the low-Re unsteady cases; the div/laplacian schemes match the
    Stage-10 cylinder path so the static cylinder renders identically.
    """
    return (
        header("dictionary", "fvSchemes")
        + """
ddtSchemes      { default Euler; }
gradSchemes     { default Gauss linear; }
divSchemes
{
    default         none;
    div(phi,U)      Gauss linearUpwind grad(U);
    div((nuEff*dev2(T(grad(U))))) Gauss linear;
}
laplacianSchemes  { default Gauss linear corrected; }
interpolationSchemes { default linear; }
snGradSchemes   { default corrected; }
"""
    )


def transient_fvsolution(*, cell_displacement: bool = False) -> str:
    """PIMPLE controls for a transient solve, optionally with a mesh-motion solver.

    With ``cell_displacement=True`` a ``cellDisplacement`` solver block is added for the
    ``displacementLaplacian`` mesh-motion equation (the moving-mesh cases). With the
    default ``False`` the rendered dictionary is byte-identical to the Stage-10 static
    cylinder's ``fvSolution`` (no regression to the transient-cylinder GO).
    """
    cd_block = ""
    if cell_displacement:
        cd_block = """    cellDisplacement
    {
        solver          PCG;
        preconditioner  DIC;
        tolerance       1e-8;
        relTol          0;
    }
"""
    return (
        header("dictionary", "fvSolution")
        + f"""
solvers
{{
    p
    {{
        solver          GAMG;
        smoother        GaussSeidel;
        tolerance       1e-7;
        relTol          0.01;
    }}
    pFinal
    {{
        $p;
        relTol          0;
    }}
    "(U|UFinal)"
    {{
        solver          smoothSolver;
        smoother        symGaussSeidel;
        tolerance       1e-8;
        relTol          0;
    }}
{cd_block}}}

PIMPLE
{{
    nOuterCorrectors    2;
    nCorrectors         2;
    nNonOrthogonalCorrectors 1;
}}
"""
    )
