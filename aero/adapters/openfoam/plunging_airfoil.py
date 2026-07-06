"""Plunging (heaving) airfoil — a transient moving-mesh case for thrust/propulsion.

The Stage-11 flapping-ladder anchor (Heathcote-Gursul 2007): a rigid NACA-0012 heaving
sinusoidally in a freestream produces net thrust above a critical Strouhal number. This
is a moving-mesh (morphing) case built on the same C-grid as the steady airfoil
(reuses ``case_writer._blockmeshdict``) but transient + laminar + moving: the airfoil
wall gets a ``movingWallVelocity`` BC and an ``oscillatingDisplacement``
``pointDisplacement`` drives the heave, with a fixed far field and an inverse-distance
diffusivity that keeps the boundary layer rigid (ADR-018).

Kept **laminar / 2-D** (transition is Stage 13): fully-laminar 2-D Navier-Stokes
reproduces the plunging-foil wake + thrust well at Re ~ 1e4 (the thrust is dominated by
the leading-edge vortex + circulatory/added-mass pressure forces, not the boundary-layer
state). The loader (`OpenFOAMSolver._load_moving`) reports thrust / power / propulsive
efficiency over the converged cycles.
"""

from __future__ import annotations

from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from aero.adapters.openfoam._foam_common import (
    RHO_INF,
    U_INF,
    flow_state,
    header,
    transient_fvschemes,
    transient_fvsolution,
    transport_properties,
    turbulence_properties,
)
from aero.adapters.openfoam.case_writer import _blockmeshdict
from aero.adapters.openfoam.motion import (
    MotionSpec,
    dynamic_mesh_dict,
    point_displacement_field,
)
from aero.adapters.openfoam.schemas import CaseSpec

_STRICT = ConfigDict(
    extra="forbid",
    frozen=True,
    str_strip_whitespace=True,
    validate_assignment=True,
    validate_default=True,
)


class PlungingAirfoilSpec(BaseModel):
    """A 2-D NACA-0012 heaving in a freestream — transient laminar moving-mesh case.

    ``motion`` is required (a plunging foil always moves). The Heathcote-Gursul Strouhal
    is ``St = 2 f h0 / U``; the V&V case sets ``motion.frequency`` from a target St and
    ``motion.amplitude = 0.175 * chord``. Deliberately no ``aoa_deg`` / ``diameter`` — the
    loader duck-types the propulsion branch on "has chord, no diameter".
    """

    model_config = _STRICT

    geometry: Literal["plunging_airfoil"] = "plunging_airfoil"
    name: str = Field(..., min_length=1)
    reynolds: float = Field(..., gt=0, description="Chord-based Reynolds number.")
    mach: float = Field(default=0.1, gt=0, description="Reference Mach (recorded only).")
    chord: float = Field(default=1.0, gt=0)
    span: float = Field(default=1.0, gt=0, description="Spanwise extent (one cell, 2D).")
    turbulence_model: Literal["laminar", "kOmegaSSTLM"] = Field(
        default="laminar",
        description="'laminar' (2-D low-Re, the Stage-11 default) or 'kOmegaSSTLM' (gamma-Re_theta "
        "transition — the Stage-13 probe of whether transitional losses close the over-prediction).",
    )
    transient: Literal[True] = Field(default=True)
    motion: MotionSpec = Field(..., description="Prescribed heave (required).")

    # --- C-grid resolution ---
    farfield_extent_chords: float = Field(default=20.0, gt=1.0)
    n_surface: int = Field(default=100, gt=3)
    n_normal: int = Field(default=100, gt=3)
    n_front: int = Field(default=50, gt=3)
    n_wake: int = Field(default=80, gt=3)
    first_cell_height: float = Field(default=5.0e-4, gt=0, description="Wall spacing (chords).")
    turbulence_intensity: float = Field(
        default=0.001,
        gt=0,
        description="Free-stream turbulence intensity (fraction) for the kOmegaSSTLM path; "
        "sets k/omega and (via the Langtry-Menter correlation) the free-stream Re_theta. "
        "Ignored when laminar.",
    )

    # --- transient controls (convective times t* = t U / c) ---
    end_time_convective: float = Field(default=200.0, gt=0)
    write_interval_convective: float = Field(default=0.1, gt=0)
    max_courant: float = Field(default=0.5, gt=0)


def _mesh_spec(spec: PlungingAirfoilSpec) -> CaseSpec:
    """A steady-airfoil ``CaseSpec`` carrying just the geometry the C-grid mesh needs.

    Reuses ``case_writer._blockmeshdict`` (the eight-block sharp-TE C-grid) verbatim —
    the plunging foil differs only in the transient/laminar/moving *solve* settings, not
    the mesh topology.
    """
    return CaseSpec(
        name=spec.name,
        reynolds=spec.reynolds,
        mach=spec.mach,
        aoa_deg=0.0,
        chord=spec.chord,
        span=spec.span,
        turbulence_model="laminar",
        farfield_extent_chords=spec.farfield_extent_chords,
        n_surface=spec.n_surface,
        n_normal=spec.n_normal,
        n_front=spec.n_front,
        n_wake=spec.n_wake,
        first_cell_height=spec.first_cell_height,
    )


def _controldict(spec: PlungingAirfoilSpec) -> str:
    c_over_u = spec.chord / U_INF
    end_time = spec.end_time_convective * c_over_u
    write_interval = spec.write_interval_convective * c_over_u
    a_ref = spec.chord * spec.span
    return (
        header("dictionary", "controlDict")
        + f"""
application     pimpleFoam;
startFrom       startTime;
startTime       0;
stopAt          endTime;
endTime         {end_time:.8g};
deltaT          {0.1 * spec.first_cell_height * spec.chord:.8g};
writeControl    adjustableRunTime;
writeInterval   {write_interval:.8g};
purgeWrite      5;
writeFormat     ascii;
writePrecision  8;
runTimeModifiable false;
adjustTimeStep  yes;
maxCo           {spec.max_courant:.8g};
maxDeltaT       {write_interval:.8g};

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
        dragDir         (1 0 0);
        liftDir         (0 1 0);
        CofR            (0.25 0 0);
        pitchAxis       (0 0 1);
    }}
    forces1
    {{
        type            forces;
        libs            (forces);
        writeControl    timeStep;
        writeInterval   1;
        patches         (airfoil);
        rho             rhoInf;
        rhoInf          {RHO_INF};
        CofR            (0.25 0 0);
    }}
}}
"""
    )


def _fields(spec: PlungingAirfoilSpec) -> dict[str, str]:
    u_vec = f"({U_INF:.8f} 0 0)"  # zero incidence; heave is imposed by the mesh motion

    def field(obj: str, cls: str, dims: str, internal: str, free: str, wall: str) -> str:
        return (
            header(cls, obj)
            + f"""
dimensions      {dims};
internalField   uniform {internal};

boundaryField
{{
    airfoil
    {{
{wall}
    }}
    farfield
    {{
{free}
    }}
    front {{ type empty; }}
    back  {{ type empty; }}
}}
"""
        )

    fields = {
        "U": field(
            "U",
            "volVectorField",
            "[0 1 -1 0 0 0 0]",
            u_vec,
            f"        type freestream;\n        freestreamValue uniform {u_vec};",
            # No-slip in the MOVING frame — critical, or the forces are biased.
            "        type movingWallVelocity;\n        value uniform (0 0 0);",
        ),
        "p": field(
            "p",
            "volScalarField",
            "[0 2 -2 0 0 0 0]",
            "0",
            "        type freestreamPressure;\n        freestreamValue uniform 0;",
            "        type zeroGradient;",
        ),
    }
    if spec.turbulence_model == "laminar":
        return fields

    # kOmegaSSTLM (gamma-Re_theta) transition path: the full kOmegaSST field set + the two
    # transition transport fields. Wall-resolved (y+<1) treatment; the moving wall keeps the
    # movingWallVelocity BC on U (above) but the turbulence fields use the standard wall
    # functions (same as the steady airfoil kOmegaSSTLM path in case_writer._fields).
    st = flow_state(
        reynolds=spec.reynolds,
        ref_length=spec.chord,
        turbulence_intensity=spec.turbulence_intensity,
    )
    k, omega, nut, re_theta_t = st["k"], st["omega"], st["nut"], st["re_theta_t"]
    fields["nut"] = field(
        "nut",
        "volScalarField",
        "[0 2 -1 0 0 0 0]",
        f"{nut:.8g}",
        f"        type freestream;\n        freestreamValue uniform {nut:.8g};",
        "        type nutLowReWallFunction;\n        value uniform 0;",
    )
    fields["k"] = field(
        "k",
        "volScalarField",
        "[0 2 -2 0 0 0 0]",
        f"{k:.8g}",
        f"        type inletOutlet;\n        inletValue uniform {k:.8g};\n        value uniform {k:.8g};",
        f"        type kqRWallFunction;\n        value uniform {k:.8g};",
    )
    fields["omega"] = field(
        "omega",
        "volScalarField",
        "[0 0 -1 0 0 0 0]",
        f"{omega:.8g}",
        f"        type inletOutlet;\n        inletValue uniform {omega:.8g};\n        value uniform {omega:.8g};",
        f"        type omegaWallFunction;\n        value uniform {omega:.8g};",
    )
    fields["gammaInt"] = field(
        "gammaInt",
        "volScalarField",
        "[0 0 0 0 0 0 0]",
        "1",
        "        type inletOutlet;\n        inletValue uniform 1;\n        value uniform 1;",
        "        type zeroGradient;",
    )
    fields["ReThetat"] = field(
        "ReThetat",
        "volScalarField",
        "[0 0 0 0 0 0 0]",
        f"{re_theta_t:.8g}",
        f"        type inletOutlet;\n        inletValue uniform {re_theta_t:.8g};\n        value uniform {re_theta_t:.8g};",
        "        type zeroGradient;",
    )
    return fields


def write_plunging_airfoil_case(spec: PlungingAirfoilSpec, dest: Path) -> None:
    """Write a complete transient moving-mesh plunging-airfoil case under `dest`."""
    system = dest / "system"
    constant = dest / "constant"
    zero = dest / "0"
    for d in (system, constant, zero):
        d.mkdir(parents=True, exist_ok=True)

    nu = flow_state(reynolds=spec.reynolds, ref_length=spec.chord, turbulence_intensity=0.001)["nu"]
    (system / "blockMeshDict").write_text(_blockmeshdict(_mesh_spec(spec)), encoding="utf-8")
    (system / "controlDict").write_text(_controldict(spec), encoding="utf-8")
    (system / "fvSchemes").write_text(
        transient_fvschemes(turbulence_model=spec.turbulence_model), encoding="utf-8"
    )
    (system / "fvSolution").write_text(
        transient_fvsolution(cell_displacement=True, turbulence_model=spec.turbulence_model),
        encoding="utf-8",
    )
    (constant / "transportProperties").write_text(transport_properties(nu), encoding="utf-8")
    (constant / "turbulenceProperties").write_text(
        turbulence_properties(spec.turbulence_model), encoding="utf-8"
    )
    for name, text in _fields(spec).items():
        (zero / name).write_text(text, encoding="utf-8")

    (constant / "dynamicMeshDict").write_text(
        dynamic_mesh_dict(moving_patch="airfoil"), encoding="utf-8"
    )
    (zero / "pointDisplacement").write_text(
        point_displacement_field(
            moving_patch="airfoil",
            motion=spec.motion,
            fixed_patches=["farfield"],
            empty_patches=["front", "back"],
        ),
        encoding="utf-8",
    )


def heave_frequency_for_strouhal(
    *, strouhal: float, amplitude: float, u_inf: float = U_INF
) -> float:
    """Forcing frequency f for a target ``St = 2 f h0 / U`` (Heathcote-Gursul convention).

    The V&V case uses this to set ``MotionSpec.frequency`` from a target Strouhal at the
    fixed heave amplitude ``h0 = amplitude``.
    """
    if amplitude <= 0.0:
        raise ValueError(f"amplitude must be positive, got {amplitude}")
    return strouhal * u_inf / (2.0 * amplitude)
