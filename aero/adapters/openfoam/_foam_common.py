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

from pydantic import BaseModel, ConfigDict, Field, model_validator

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


def decompose_par_dict(ranks: int) -> str:
    """`system/decomposeParDict` — `scotch` over `ranks` subdomains.

    `scotch` needs no per-case geometry hints (unlike `simple`/`hierarchical`, whose `n`
    vector would have to track the block topology of every rung), so the dictionary is a
    pure function of the rank count and cannot drift out of step with the mesh.

    The rank count is pre-registered, never negotiated: `decomposePar` will happily exit 0
    having produced FEWER `processor*` directories than asked for, and that is a different
    configuration wearing the pre-registered one's clothes. The caller verifies the
    directory count host-side (ADR-040 L4/W2).
    """
    if ranks < 1:
        raise ValueError(f"ranks must be >= 1, got {ranks}")
    return (
        header("dictionary", "decomposeParDict")
        + f"""
numberOfSubdomains {ranks};
method          scotch;
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

#: The time schemes a transient case may render. Deliberately a closed set: `ddtSchemes`
#: accepts many names OpenFOAM would happily run and this platform has never validated,
#: and a typo (`backwards`) would otherwise reach the solver as a run-time failure hours in.
_TRANSIENT_DDT_SCHEMES = frozenset({"Euler", "backward", "CrankNicolson 0.9"})


def transient_fvschemes(*, turbulence_model: str = "laminar", ddt_scheme: str = "Euler") -> str:
    """Transient schemes — first-order Euler in time by default, second-order space.

    Shared by the transient/moving cases (cylinder, plunging airfoil). Euler is the
    robust default for the low-Re unsteady cases; the div/laplacian schemes match the
    Stage-10 cylinder path so the static cylinder renders identically. With a non-laminar
    ``turbulence_model`` the RAS transport div schemes are added (``k``/``omega``, plus
    ``gammaInt``/``ReThetat`` for ``kOmegaSSTLM``) — required because ``divSchemes`` uses
    ``default none``. ``laminar`` (the default) is byte-identical to the Stage-10 cylinder.

    ``ddt_scheme`` is additive and defaults to the value every existing caller already
    rendered, so the three byte pins in ``tests/stage_20`` hold unchanged. It exists for
    Stage 20, where second-order time (``backward``) is admissible ONLY if the preCICE
    OpenFOAM adapter is shown to checkpoint and restore ``U.oldTime().oldTime()`` across
    coupling iterations — the pre-flight I8 probe. Nothing in this repo establishes that it
    does, and every preCICE OpenFOAM tutorial uses ``Euler``, so ``backward`` is not a
    default here: choosing it without the probe would put a temporal-accuracy claim on the
    record that the record does not support.
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
    if ddt_scheme not in _TRANSIENT_DDT_SCHEMES:
        raise ValueError(
            f"ddt_scheme must be one of {sorted(_TRANSIENT_DDT_SCHEMES)}, got {ddt_scheme!r}"
        )
    return (
        header("dictionary", "fvSchemes")
        + f"""
ddtSchemes      {{ default {ddt_scheme}; }}
"""
        + """gradSchemes     { default Gauss linear; }
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


#: Linear solvers the pressure equation may be given. A closed set, so a typo is a
#: ``ValidationError`` at write time rather than an OpenFOAM abort hours into a solve.
_P_SOLVERS = frozenset({"GAMG", "PCG", "PBiCGStab"})
#: Smoothers GAMG may use. ``DICGaussSeidel`` measured 2.2x faster than ``GaussSeidel``
#: on this mesh (ADR-040 screening) — GAMG's coarse-grid correction was not working under
#: a plain Gauss-Seidel smoother at cell aspect ratios near 310.
_P_SMOOTHERS = frozenset({"GaussSeidel", "DICGaussSeidel", "symGaussSeidel", "DIC"})


class FluidNumericsSpec(BaseModel):
    """The fluid linear-solver stack and PIMPLE corrector counts, AS SPEC DATA.

    These were literals inside this writer until ADR-040. That was a provenance hole:
    ``config_hash`` is computed over the *spec*, so two campaigns run at different numerics
    hashed identically and the four-tuple could not tell them apart — the same hole ADR-037
    closed for the rung knobs, one layer down. Worse, the campaign driver's ``_reattach``
    guard re-derives the config digest precisely to catch "the code moved under a live
    campaign", and it was blind to exactly this class of edit.

    Every value is a **token string**, not a float. ``f"{1e-7:.12g}"`` renders ``1e-07``
    while the pinned deck says ``1e-7``; a float-typed field would silently move bytes that
    six writers and five stages' records depend on.

    The defaults are the ADR-039 numerics exactly, so the rendered dictionary is
    byte-identical until a caller asks for something else (pinned by
    ``tests/unit/test_fvsolution_bytes_before_numerics_spec.py``).
    """

    model_config = ConfigDict(extra="forbid", frozen=True, validate_default=True)

    label: str = Field(
        default="adr039-baseline",
        min_length=1,
        description="Names the stack in bundles and screening tables; enters config_hash.",
    )
    p_solver: str = Field(default="GAMG", description="Pressure-equation linear solver.")
    p_smoother: str = Field(default="GaussSeidel", description="Smoother, when the solver is GAMG.")
    p_tolerance: str = Field(default="1e-7", min_length=1, description="Absolute tolerance token.")
    p_rel_tol: str = Field(default="0.01", min_length=1, description="Relative tolerance token.")
    pcorr_tolerance: str = Field(default="0.02", min_length=1)
    gamg_controls: tuple[tuple[str, str], ...] = Field(
        default=(),
        description=(
            "Extra GAMG entries (nCellsInCoarsestLevel, agglomerator, cacheAgglomeration, "
            "sweep counts) as ordered key/value token pairs. Ordered rather than a mapping "
            "so the serialization - and therefore config_hash - is deterministic. Empty "
            "renders nothing, which is what keeps the default bytes unmoved."
        ),
    )
    n_outer_correctors: int = Field(default=2, ge=1, le=50)
    n_correctors: int = Field(default=2, ge=1, le=10)
    n_non_orthogonal_correctors: int = Field(default=1, ge=0, le=10)

    @model_validator(mode="after")
    def _tokens_are_known(self) -> FluidNumericsSpec:
        problems = []
        if self.p_solver not in _P_SOLVERS:
            problems.append(f"p_solver {self.p_solver!r} not in {sorted(_P_SOLVERS)}")
        if self.p_solver == "GAMG" and self.p_smoother not in _P_SMOOTHERS:
            problems.append(f"p_smoother {self.p_smoother!r} not in {sorted(_P_SMOOTHERS)}")
        if problems:
            raise ValueError("; ".join(problems))
        return self

    @property
    def cell_displacement_key(self) -> str:
        """``cellDisplacement``, or the regex form when every inner iteration is final.

        MEASURED (ADR-040 screening, variant s6): at ``nOuterCorrectors 1`` OpenFOAM tags
        every inner iteration final and looks up ``cellDisplacementFinal``, which a deck
        carrying only ``cellDisplacement`` does not have — ``FOAM FATAL IO ERROR`` on the
        first time step. So a single-outer-corrector deck is not just a PIMPLE knob; it
        needs the regex key. Conditional rather than unconditional because the regex form
        would move the bytes of five other stages' decks.
        """
        return '"cellDisplacement.*"' if self.n_outer_correctors == 1 else "cellDisplacement"

    def gamg_lines(self, indent: str = "        ") -> str:
        """Extra GAMG entries, padded to the deck's column and ALWAYS space-separated.

        ``{key:<16}{value}`` would work for every key in the base blocks and fail for
        ``nCellsInCoarsestLevel`` (21 characters), which renders as
        ``nCellsInCoarsestLevel100;`` — a token OpenFOAM cannot parse. Pad to 15 and add
        the separator, so a long key degrades to one space instead of none.
        """
        return "".join(f"{indent}{key:<15} {value};\n" for key, value in self.gamg_controls)


def transient_fvsolution(
    *,
    cell_displacement: bool = False,
    turbulence_model: str = "laminar",
    numerics: FluidNumericsSpec | None = None,
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

    ``numerics`` carries the pressure stack and corrector counts (ADR-040). Omitted, it is
    ``FluidNumericsSpec()`` — the ADR-039 values — and every byte is unchanged.
    """
    n = numerics if numerics is not None else FluidNumericsSpec()
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
        pcorr_block = f"""    "pcorr.*"
    {{
        solver          {n.p_solver};
        smoother        {n.p_smoother};
        tolerance       {n.pcorr_tolerance};
        relTol          0;
{n.gamg_lines()}    }}
"""
        cd_block = f"""    {n.cell_displacement_key}
    {{
        solver          PCG;
        preconditioner  DIC;
        tolerance       1e-8;
        relTol          0;
    }}
"""
        correct_phi = "    correctPhi          yes;\n"
    return (
        header("dictionary", "fvSolution")
        + f"""
solvers
{{
{pcorr_block}    p
    {{
        solver          {n.p_solver};
        smoother        {n.p_smoother};
        tolerance       {n.p_tolerance};
        relTol          {n.p_rel_tol};
{n.gamg_lines()}    }}
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
{correct_phi}    nOuterCorrectors    {n.n_outer_correctors};
    nCorrectors         {n.n_correctors};
    nNonOrthogonalCorrectors {n.n_non_orthogonal_correctors};
}}
"""
    )
