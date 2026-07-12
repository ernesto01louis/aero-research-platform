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
def rethetat_freestream(turbulence_intensity: float) -> float:
    """Freestream transition-onset momentum-thickness Reynolds number Re_theta_t(Tu).

    The Langtry-Menter (2009) empirical correlation used to set the freestream/inlet
    `ReThetat` for the gamma-Re_theta (`kOmegaSSTLM`) transition model. `Tu` is the freestream
    turbulence intensity in **percent** (so `turbulence_intensity` fraction x 100). Low Tu
    → high Re_theta_t → late/no transition; high Tu → early bypass transition. Verified against
    the ESI v2412 T3A tutorial (Tu≈3.3% → ~169, tutorial pins 160.99).

    Ref: Langtry & Menter (2009), AIAA J 47(12):2894; Menter et al. (2006).
    """
    tu = max(turbulence_intensity * 100.0, 0.027)  # percent; guard tiny/zero Tu
    if tu <= 1.3:
        return 1173.51 - 589.428 * tu + 0.2196 / (tu * tu)
    return float(331.50 * (tu - 0.5658) ** -0.671)


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
    laminar — standard practice for external aerodynamics. `re_theta_t` is the
    Langtry-Menter freestream Re_theta_t for the `kOmegaSSTLM` transition path (only
    consumed when that model is selected).
    """
    nu = U_INF * ref_length / reynolds
    k = 1.5 * (turbulence_intensity * U_INF) ** 2
    nut = _FREESTREAM_NUT_RATIO * nu
    omega = k / nut
    return {
        "nu": nu,
        "k": k,
        "omega": omega,
        "nut": nut,
        "re_theta_t": rethetat_freestream(turbulence_intensity),
    }


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


def fvschemes(*, transition: bool = False) -> str:
    """Discretisation schemes — steady-state RANS, second-order-ish, bounded.

    With ``transition=True`` the two gamma-Re_theta (`kOmegaSSTLM`) transport terms
    ``div(phi,gammaInt)`` / ``div(phi,ReThetat)`` are added (required because
    ``divSchemes`` uses ``default none``); off, the rendered dictionary is unchanged.
    """
    transition_div = (
        "    div(phi,gammaInt) bounded Gauss upwind;\n    div(phi,ReThetat) bounded Gauss upwind;\n"
        if transition
        else ""
    )
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
"""
        + transition_div
        + """    div((nuEff*dev2(T(grad(U))))) Gauss linear;
}
laplacianSchemes  { default Gauss linear limited corrected 0.5; }
interpolationSchemes { default linear; }
snGradSchemes   { default limited corrected 0.5; }
wallDist        { method meshWave; }
"""
    )


def fvsolution(
    *,
    pressure_solver: str = "GAMG",
    u_relax: float = 0.9,
    kw_relax: float = 0.7,
    transition: bool = False,
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
    # gamma-Re_theta transport fields join the turbulence solver / residual / relaxation groups.
    turb_fields = "k|omega|gammaInt|ReThetat" if transition else "k|omega"
    return (
        header("dictionary", "fvSolution")
        + """
solvers
{
"""
        + p_block
        + f"""
    "(U|{turb_fields})"
    {{
        solver          smoothSolver;
        smoother        symGaussSeidel;
        tolerance       1e-9;
        relTol          0.1;
    }}
}}

SIMPLE
{{
    consistent          yes;
    nNonOrthogonalCorrectors 2;
    residualControl
    {{
        p               1e-6;
        U               1e-6;
        "({turb_fields})"     1e-6;
    }}
}}

relaxationFactors
{{
    equations
    {{
        U               {u_relax:.8g};
        "({turb_fields})"     {kw_relax:.8g};
    }}
}}
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
def transient_fvschemes(*, turbulence_model: str = "laminar") -> str:
    """Transient schemes — first-order Euler in time, second-order space.

    Shared by the transient/moving cases (cylinder, plunging airfoil). Euler is the
    robust default for the low-Re unsteady cases; the div/laplacian schemes match the
    Stage-10 cylinder path so the static cylinder renders identically. With a non-laminar
    ``turbulence_model`` the RAS transport div schemes are added (``k``/``omega``, plus
    ``gammaInt``/``ReThetat`` for ``kOmegaSSTLM``) — required because ``divSchemes`` uses
    ``default none``. ``laminar`` (the default) is byte-identical to the Stage-10 cylinder.
    """
    turb_div = ""
    turb_walldist = ""
    if turbulence_model != "laminar":
        turb_div = "    div(phi,k)      Gauss upwind;\n    div(phi,omega)  Gauss upwind;\n"
        if turbulence_model == "kOmegaSSTLM":
            turb_div += "    div(phi,gammaInt) Gauss upwind;\n    div(phi,ReThetat) Gauss upwind;\n"
        # k-omega SST's blending functions need the wall distance; without a wallDist
        # entry pimpleFoam exits before the first step (Stage-16 URANS probe). Laminar
        # stays byte-identical to the Stage-10 cylinder (no entry).
        turb_walldist = "wallDist        { method meshWave; }\n"
    return (
        header("dictionary", "fvSchemes")
        + """
ddtSchemes      { default Euler; }
gradSchemes     { default Gauss linear; }
divSchemes
{
    default         none;
    div(phi,U)      Gauss linearUpwind grad(U);
"""
        + turb_div
        + """    div((nuEff*dev2(T(grad(U))))) Gauss linear;
}
laplacianSchemes  { default Gauss linear corrected; }
interpolationSchemes { default linear; }
snGradSchemes   { default corrected; }
"""
        + turb_walldist
    )


def transient_fvsolution(
    *, cell_displacement: bool = False, turbulence_model: str = "laminar"
) -> str:
    """PIMPLE controls for a transient solve, optionally with a mesh-motion solver.

    With ``cell_displacement=True`` the moving-mesh solvers are added: a ``"pcorr.*"``
    flux-correction solver (for ``correctPhi``, which makes the face fluxes consistent with
    the mesh motion — pimpleFoam aborts without it) and a ``cellDisplacement`` solver for the
    ``displacementLaplacian`` mesh-motion equation, plus ``correctPhi yes`` in PIMPLE. With a
    non-laminar ``turbulence_model`` a ``smoothSolver`` block for the RAS transport fields
    (``k``/``omega`` and, for ``kOmegaSSTLM``, ``gammaInt``/``ReThetat``) + their ``Final``
    variants is added. With ``cell_displacement=False`` and ``turbulence_model="laminar"`` the
    rendered dictionary is byte-identical to the Stage-10 static cylinder's ``fvSolution``.
    """
    pcorr_block = ""
    cd_block = ""
    correct_phi = ""
    turb_block = ""
    if turbulence_model != "laminar":
        turb_fields = (
            "k|omega|gammaInt|ReThetat" if turbulence_model == "kOmegaSSTLM" else "k|omega"
        )
        turb_block = f"""    "({turb_fields})(|Final)"
    {{
        solver          smoothSolver;
        smoother        symGaussSeidel;
        tolerance       1e-8;
        relTol          0;
    }}
"""
    if cell_displacement:
        pcorr_block = """    "pcorr.*"
    {
        solver          GAMG;
        smoother        GaussSeidel;
        tolerance       0.02;
        relTol          0;
    }
"""
        cd_block = """    cellDisplacement
    {
        solver          PCG;
        preconditioner  DIC;
        tolerance       1e-8;
        relTol          0;
    }
"""
        correct_phi = "    correctPhi          yes;\n"
    return (
        header("dictionary", "fvSolution")
        + f"""
solvers
{{
{pcorr_block}    p
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
{turb_block}{cd_block}}}

PIMPLE
{{
{correct_phi}    nOuterCorrectors    2;
    nCorrectors         2;
    nNonOrthogonalCorrectors 1;
}}
"""
    )
