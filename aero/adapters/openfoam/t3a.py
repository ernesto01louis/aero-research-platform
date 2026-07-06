"""ERCOFTAC T3A transitional flat plate — a ported OpenFOAM-ESI v2412 tutorial case.

The T3A bypass-transition flat plate (Savill 1993/1996; ERCOFTAC T3 series) is the
canonical verification case for the Langtry-Menter gamma-Re_theta transition model
(`kOmegaSSTLM`). A flat plate under a ~3% free-stream turbulence intensity transitions from
a laminar to a turbulent boundary layer at Re_x ~ 1.4e5; the skin-friction distribution
Cf(x) is the measured quantity (its minimum marks transition onset, then it rises to the
turbulent branch).

**This case is a faithful port of the ESI v2412 tutorial**
``incompressible/simpleFoam/T3A`` (mesh + fields + solver dictionaries), NOT a parametric
platform case. Faithfulness is deliberate: the predicted transition location is sensitive to
the free-stream turbulence *decay* from the inlet to the plate leading edge, which depends on
the specific mesh + inlet omega — so reproducing the validated tutorial verbatim is the
lowest-risk way to demonstrate the platform's kOmegaSSTLM binding reproduces the published
onset. The only deviations from the tutorial:

* the controlDict graph function objects (``wallShearStressGraph`` / ``kGraph``) are replaced
  by the platform's ``wallShearStress`` + ``sampleWall`` (raw ``surfaces``) sampler on the
  ``plate`` patch, so ``aero.adapters.openfoam.fields.extract_wall_distributions`` can read
  Cf(x) exactly as it does for the TMR flat plate;
* an explicit ``defaultPatch { name frontAndBack; type empty; }`` names the 2-D span faces
  (the fields carry a ``frontAndBack`` empty entry);
* the block cell counts scale by ``spec.mesh_factor`` (for a mesh-refinement GCI; 1.0 = the
  tutorial mesh).

The case is **dimensional** (U_inf = 5.4 m/s, nu = 1.5e-5) — unlike the rest of the platform
(U_inf = 1), because the T3A free-stream turbulence intensity Tu = sqrt(2k/3)/U is fixed at
~3.3% only at the tutorial's specific U and k. Cf extraction therefore passes ``u_inf`` to the
wall-distribution parser (which otherwise assumes U_inf = 1).
"""

from __future__ import annotations

from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from aero.adapters.openfoam._foam_common import header

# --- fixed tutorial constants (dimensional) -----------------------------------
T3A_U_INF = 5.4  # m/s free-stream speed (fixes Tu = sqrt(2k/3)/U ~= 3.3%)
T3A_NU = 1.5e-5  # m^2/s kinematic viscosity
T3A_K_INLET = 0.047633  # m^2/s^2 free-stream tke
T3A_OMEGA_INLET = 264.63  # 1/s free-stream specific dissipation
T3A_RETHETAT_INLET = 160.99  # free-stream transition-onset Re_theta (tutorial value)
T3A_PLATE_X0 = 0.04  # m physical x of the plate leading edge (mesh origin is upstream)
T3A_PLATE_LENGTH = 3.0  # m plate length (x = 0.04 .. 3.04)

_STRICT = ConfigDict(
    extra="forbid",
    frozen=True,
    str_strip_whitespace=True,
    validate_assignment=True,
    validate_default=True,
)


class T3ASpec(BaseModel):
    """ERCOFTAC T3A transitional flat plate (ported ESI v2412 tutorial, kOmegaSSTLM)."""

    model_config = _STRICT

    geometry: Literal["t3a_flat_plate"] = "t3a_flat_plate"
    name: str = Field(..., min_length=1)
    # Recorded (Re based on the plate length; the case is dimensional, not Re-scaled).
    reynolds: float = Field(default=T3A_U_INF * T3A_PLATE_LENGTH / T3A_NU, gt=0)
    mach: float = Field(default=0.016, gt=0, description="Reference Mach (recorded only).")
    turbulence_model: Literal["kOmegaSSTLM"] = "kOmegaSSTLM"
    u_inf: float = Field(default=T3A_U_INF, gt=0, description="Free-stream speed (dimensional).")
    nu: float = Field(default=T3A_NU, gt=0)
    k_inlet: float = Field(default=T3A_K_INLET, gt=0)
    omega_inlet: float = Field(default=T3A_OMEGA_INLET, gt=0)
    re_theta_t_inlet: float = Field(default=T3A_RETHETAT_INLET, gt=0)
    end_time: int = Field(default=1000, gt=0, description="Max SIMPLE iterations.")
    mesh_factor: float = Field(
        default=1.0, gt=0, description="Cell-count multiplier (1.0 = tutorial mesh; for GCI)."
    )


# --- ported mesh --------------------------------------------------------------
# The 40 vertices of the ESI T3A tutorial blockMeshDict, verbatim (a contoured
# leading-edge nose + a graded flat plate from x=0.04 to x=3.04, 2-D one cell in z).
_VERTICES = """    (0 0 -0.05)
    (0.02 0 -0.05)
    (0 0.0146724657096209 -0.05)
    (0.0260775342903791 0.0146724657096209 -0.05)
    (0 0 0.05)
    (0.02 0 0.05)
    (0 0.0146724657096209 0.05)
    (0.0260775342903791 0.0146724657096209 0.05)
    (0.04 0 -0.05)
    (0.04 0 0.05)
    (0.0402196699141101 5.30330085889911e-04 -0.05)
    (0.0402196699141101 5.30330085889911e-04 0.05)
    (0.04075 0.00075 -0.05)
    (0.04075 0.02075 -0.05)
    (0.0 1 -0.05)
    (0.0260775342903791 1 -0.05)
    (0.04075 1 -0.05)
    (0.04075 0.00075 0.05)
    (0.04075 0.02075 0.05)
    (0.0 1 0.05)
    (0.0260775342903791 1 0.05)
    (0.04075 1 0.05)
    (0.08 0.00075 -0.05)
    (0.08 0.02075 -0.05)
    (0.08 1.0 -0.05)
    (0.08 0.00075 0.05)
    (0.08 0.02075 0.05)
    (0.08 1.0 0.05)
    (1.14 0.00075 -0.05)
    (1.14 0.02075 -0.05)
    (1.14 1.0 -0.05)
    (1.14 0.00075 0.05)
    (1.14 0.02075 0.05)
    (1.14 1.0 0.05)
    (3.04 0.00075 -0.05)
    (3.04 0.02075 -0.05)
    (3.04 1.0 -0.05)
    (3.04 0.00075 0.05)
    (3.04 0.02075 0.05)
    (3.04 1.0 0.05)"""

# Each block: (vertex indices, base (n1, n2), grading string). n1/n2 scale by mesh_factor.
_BLOCKS: tuple[tuple[str, tuple[int, int], str], ...] = (
    ("0 1 3 2 4 5 7 6", (7, 20), "0.471868 1 1"),
    ("1 8 10 3 5 9 11 7", (40, 20), "0.022 1 1"),
    ("3 10 12 13 7 11 17 18", (40, 20), "0.022 1 1"),
    ("2 3 15 14 6 7 20 19", (7, 40), "0.471868 50.03857 1"),
    ("3 13 16 15 7 18 21 20", (20, 40), "1 50.03857 1"),
    ("12 22 23 13 17 25 26 18", (80, 40), "70.9389 45.455 1"),
    ("13 23 24 16 18 26 27 21", (80, 40), "70.9389 50.03857 1"),
    ("22 28 29 23 25 31 32 26", (160, 40), "7.2902 45.455 1"),
    ("23 29 30 24 26 32 33 27", (160, 40), "7.2902 50.03857 1"),
    ("28 34 35 29 31 37 38 32", (60, 40), "3.9909 45.455 1"),
    ("29 35 36 30 32 38 39 33", (60, 40), "3.9909 50.03857 1"),
)

_EDGES = """    arc 1 3 (0.0215794997003908 0.00794068122157562 -0.05)
    arc 5 7 (0.0215794997003908 0.00794068122157562 0.05)
    arc 8 10 (0.0400570903506165 2.87012574273817e-04 -0.05)
    arc 9 11 (0.0400570903506165 2.87012574273817e-04 0.05)
    arc 3 13 (0.0328093187784244 0.0191705002996092 -0.05)
    arc 7 18 (0.0328093187784244 0.0191705002996092 0.05)
    arc 10 12 (0.0404629874257262 6.92909649383465e-04 -0.05)
    arc 11 17 (0.0404629874257262 6.92909649383465e-04 0.05)"""

_BOUNDARY = """    above
    {
        type patch;
        faces
        (
            (0 1 5 4)
            (1 8 9 5)
        );
    }
    top
    {
        type patch;
        faces
        (
            (14 15 20 19)
            (15 16 21 20)
            (16 24 27 21)
            (24 30 33 27)
            (30 36 39 33)
        );
    }
    inlet
    {
        type patch;
        faces
        (
            (0 4 6 2)
            (2 6 19 14)
        );
    }
    outlet
    {
        type patch;
        faces
        (
            (34 37 38 35)
            (35 38 39 36)
        );
    }
    plate
    {
        type wall;
        faces
        (
            (8 9 11 10)
            (10 11 17 12)
            (12 22 25 17)
            (22 28 31 25)
            (28 34 37 31)
        );
    }"""


def _scaled(n: int, factor: float) -> int:
    """Scale a block cell count by ``factor`` (>=1 cell)."""
    return max(1, round(n * factor))


def _blockmeshdict(spec: T3ASpec) -> str:
    blocks = "\n".join(
        f"    hex ({v}) ({_scaled(n1, spec.mesh_factor)} {_scaled(n2, spec.mesh_factor)} 1) "
        f"simpleGrading ({g})"
        for v, (n1, n2), g in _BLOCKS
    )
    return (
        header("dictionary", "blockMeshDict")
        + f"""
scale   1;

vertices
(
{_VERTICES}
);

blocks
(
{blocks}
);

edges
(
{_EDGES}
);

defaultPatch
{{
    name    frontAndBack;
    type    empty;
}}

boundary
(
{_BOUNDARY}
);
"""
    )


# --- ported fields ------------------------------------------------------------
def _fields(spec: T3ASpec) -> dict[str, str]:
    """The 7 ported 0/ fields (U p k omega nut gammaInt ReThetat) with tutorial BCs."""

    def vol(obj: str, cls: str, dims: str, internal: str, patches: str) -> str:
        return (
            header(cls, obj)
            + f"""
dimensions      {dims};
internalField   uniform {internal};

boundaryField
{{
{patches}
    frontAndBack
    {{
        type            empty;
    }}
}}
"""
        )

    return {
        "U": vol(
            "U",
            "volVectorField",
            "[0 1 -1 0 0 0 0]",
            f"({spec.u_inf:.8g} 0 0)",
            """    inlet
    {
        type            fixedValue;
        value           $internalField;
    }
    outlet
    {
        type            zeroGradient;
    }
    plate
    {
        type            noSlip;
    }
    above
    {
        type            slip;
    }
    top
    {
        type            slip;
    }""",
        ),
        "p": vol(
            "p",
            "volScalarField",
            "[0 2 -2 0 0 0 0]",
            "0",
            """    inlet
    {
        type            zeroGradient;
    }
    outlet
    {
        type            fixedValue;
        value           $internalField;
    }
    plate
    {
        type            zeroGradient;
    }
    above
    {
        type            zeroGradient;
    }
    top
    {
        type            zeroGradient;
    }""",
        ),
        "k": vol(
            "k",
            "volScalarField",
            "[0 2 -2 0 0 0 0]",
            f"{spec.k_inlet:.8g}",
            """    inlet
    {
        type            fixedValue;
        value           $internalField;
    }
    outlet
    {
        type            zeroGradient;
    }
    plate
    {
        type            fixedValue;
        value           uniform 0;
    }
    above
    {
        type            zeroGradient;
    }
    top
    {
        type            zeroGradient;
    }""",
        ),
        "omega": vol(
            "omega",
            "volScalarField",
            "[0 0 -1 0 0 0 0]",
            f"{spec.omega_inlet:.8g}",
            """    inlet
    {
        type            fixedValue;
        value           $internalField;
    }
    outlet
    {
        type            zeroGradient;
    }
    plate
    {
        type            omegaWallFunction;
        value           $internalField;
    }
    above
    {
        type            zeroGradient;
    }
    top
    {
        type            zeroGradient;
    }""",
        ),
        "nut": vol(
            "nut",
            "volScalarField",
            "[0 2 -1 0 0 0 0]",
            "0",
            """    inlet
    {
        type            calculated;
        value           $internalField;
    }
    outlet
    {
        type            calculated;
        value           $internalField;
    }
    plate
    {
        type            nutkWallFunction;
        value           uniform 0;
    }
    above
    {
        type            calculated;
        value           $internalField;
    }
    top
    {
        type            calculated;
        value           $internalField;
    }""",
        ),
        "gammaInt": vol(
            "gammaInt",
            "volScalarField",
            "[0 0 0 0 0 0 0]",
            "1",
            """    inlet
    {
        type            fixedValue;
        value           $internalField;
    }
    outlet
    {
        type            zeroGradient;
    }
    plate
    {
        type            zeroGradient;
    }
    above
    {
        type            zeroGradient;
    }
    top
    {
        type            zeroGradient;
    }""",
        ),
        "ReThetat": vol(
            "ReThetat",
            "volScalarField",
            "[0 0 0 0 0 0 0]",
            f"{spec.re_theta_t_inlet:.8g}",
            """    inlet
    {
        type            fixedValue;
        value           $internalField;
    }
    outlet
    {
        type            zeroGradient;
    }
    plate
    {
        type            zeroGradient;
    }
    above
    {
        type            zeroGradient;
    }
    top
    {
        type            zeroGradient;
    }""",
        ),
    }


# --- ported solver dictionaries -----------------------------------------------
def _turbulence_properties() -> str:
    return (
        header("dictionary", "turbulenceProperties")
        + """
simulationType      RAS;
RAS
{
    RASModel        kOmegaSSTLM;
    turbulence      on;
    printCoeffs     on;
}
"""
    )


def _transport_properties(nu: float) -> str:
    return (
        header("dictionary", "transportProperties")
        + f"""
transportModel  Newtonian;
nu              {nu:.8g};
"""
    )


def _fvschemes() -> str:
    """The tutorial's exact fvSchemes (linearUpwind turbulence transport, corrected)."""
    return (
        header("dictionary", "fvSchemes")
        + """
ddtSchemes      { default steadyState; }
gradSchemes     { default Gauss linear; }
divSchemes
{
    default             none;
    div(phi,U)          bounded Gauss linearUpwind grad;
    turbulence          bounded Gauss linearUpwind grad;
    div(phi,k)          $turbulence;
    div(phi,omega)      $turbulence;
    div(phi,gammaInt)   $turbulence;
    div(phi,ReThetat)   $turbulence;
    div((nuEff*dev2(T(grad(U))))) Gauss linear;
}
laplacianSchemes  { default Gauss linear corrected; }
interpolationSchemes { default linear; }
snGradSchemes   { default corrected; }
wallDist        { method meshWave; }
"""
    )


def _fvsolution() -> str:
    """The tutorial's exact fvSolution (GAMG p + smoothSolver turbulence group)."""
    return (
        header("dictionary", "fvSolution")
        + """
solvers
{
    p
    {
        solver          GAMG;
        tolerance       1e-6;
        relTol          0.1;
        smoother        GaussSeidel;
    }
    "(U|k|omega|gammaInt|ReThetat)"
    {
        solver          smoothSolver;
        smoother        symGaussSeidel;
        tolerance       1e-8;
        relTol          0.1;
        maxIter         10;
    }
}

SIMPLE
{
    consistent      yes;
    residualControl
    {
        p               1e-5;
        U               1e-6;
        "(k|omega|gammaInt|ReThetat)" 1e-4;
    }
}

relaxationFactors
{
    equations
    {
        ".*"            0.9;
    }
}
"""
    )


def _controldict(spec: T3ASpec) -> str:
    """simpleFoam controlDict with the platform's wallShearStress + sampleWall(plate) sampler.

    Replaces the tutorial's graph function objects so
    ``extract_wall_distributions(..., patch="plate")`` reads Cf(x) from the raw surfaces.
    """
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
purgeWrite      0;
writeFormat     ascii;
writePrecision  8;
writeCompression off;
timeFormat      general;
timePrecision   6;
runTimeModifiable false;

functions
{{
    wallShearStress1
    {{
        type            wallShearStress;
        libs            (fieldFunctionObjects);
        patches         (plate);
        writeControl    writeTime;
    }}
    sampleWall
    {{
        type            surfaces;
        libs            (sampling);
        writeControl    writeTime;
        surfaceFormat   raw;
        fields          (p wallShearStress);
        surfaces
        {{
            plate
            {{
                type        patch;
                patches     (plate);
                interpolate false;
            }}
        }}
    }}
}}
"""
    )


def write_t3a_case(spec: T3ASpec, dest: Path) -> None:
    """Write a complete ported T3A transitional-flat-plate case under ``dest``."""
    system = dest / "system"
    constant = dest / "constant"
    zero = dest / "0"
    for d in (system, constant, zero):
        d.mkdir(parents=True, exist_ok=True)

    (system / "blockMeshDict").write_text(_blockmeshdict(spec), encoding="utf-8")
    (system / "controlDict").write_text(_controldict(spec), encoding="utf-8")
    (system / "fvSchemes").write_text(_fvschemes(), encoding="utf-8")
    (system / "fvSolution").write_text(_fvsolution(), encoding="utf-8")
    (constant / "transportProperties").write_text(_transport_properties(spec.nu), encoding="utf-8")
    (constant / "turbulenceProperties").write_text(_turbulence_properties(), encoding="utf-8")
    for name, text in _fields(spec).items():
        (zero / name).write_text(text, encoding="utf-8")
