"""The fluid participant of the Stage-20 flexible-foil FSI case — DIMENSIONAL.

Every other transient writer in this package solves a dimensionless problem: ``U_INF`` and
``RHO_INF`` are both 1.0 and the Reynolds number fixes ``nu``. This one cannot. preCICE
exchanges ``Force`` as an **absolute force in newtons**, and CalculiX solves in SI with a
real Young's modulus and a real density, so the fluid side has to be in SI too or the two
participants disagree about what a force is by a factor of ``rho U^2`` --- silently, while
converging. So ``plunging_airfoil.py`` is deliberately NOT reused despite meshing the same
C-grid: it hard-codes ``RHO_INF = U_INF = 1.0``.

Four things here are load-bearing and each fails quietly if omitted:

1. **The preCICE adapter function object.** Without ``libs
   ("libpreciceAdapterFunctionObject.so")`` and a ``preciceAdapterFunctionObject`` in
   ``controlDict``, pimpleFoam runs a perfectly happy UNCOUPLED solve to ``endTime``, exits
   0, and the solid blocks on a coupling partner that never arrives until the supervisor's
   ceiling fires. Nothing about that looks like an error until someone reads the forces.
2. **Both wall patches everywhere.** The Heathcote-Gursul section has a blunt trailing
   edge, so the C-grid emits ``airfoil`` AND ``airfoil_te``. Both must appear in every
   ``0/`` ``boundaryField``, in both force objects' ``patches``, in the ``preciceDict``
   interface, and in the mesh-motion diffusivity. Dropping ``airfoil_te`` from the force
   objects biases ``C_T`` on ONE ARM ONLY -- the base is 76.5 um on the flexible foil and
   380.7 um on the rigid one -- which lands straight in the gated increment.
3. **A fixed time step.** ``adjustTimeStep no`` with ``deltaT`` equal to the coupling
   time-window size. An adaptive step would fight the adapter for control of ``dt`` and
   make the two arms' records incommensurable, which the paired A-family forbids.
4. **``timePrecision 12``.** At the default 6, consecutive force rows collapse to the same
   printed time at this ``dt`` and the de-duplication in
   :mod:`aero.adapters.openfoam.force_io` deletes them -- silently, before Stage 20 taught
   it to count what it dropped.

The mesh is the existing eight-block C-grid with the teardrop/plate section swapped in
(``CaseSpec.section``), so the grid stays self-similar under refinement and a three-grid
GCI remains admissible.
"""

from __future__ import annotations

from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from aero.adapters.openfoam._foam_common import (
    header,
    transient_fvschemes,
    transient_fvsolution,
    transport_properties,
    turbulence_properties,
)
from aero.adapters.openfoam.case_writer import _blockmeshdict
from aero.adapters.openfoam.schemas import CaseSpec, TeardropPlateSection

__all__ = [
    "FLUID_PARTICIPANT",
    "WALL_PATCHES",
    "FlexibleFoilSpec",
    "write_flexible_foil_case",
]

_STRICT = ConfigDict(
    extra="forbid",
    frozen=True,
    str_strip_whitespace=True,
    validate_assignment=True,
    validate_default=True,
)

#: The two wall patches the blunt-TE C-grid emits. Everything that names a wall must name
#: both; see the module docstring for what dropping one costs.
WALL_PATCHES = ("airfoil", "airfoil_te")

FLUID_PARTICIPANT = "Fluid"

#: OpenFOAM's default is 6, at which consecutive force rows collapse to the same printed
#: time for any dt below ~1e-6 of the end time -- and the collapsed rows are then deleted.
_TIME_PRECISION = 12


class FlexibleFoilSpec(BaseModel):
    """The dimensional fluid participant: a flexible foil in a water tunnel, plunging.

    The foil does not move under a prescribed boundary condition here. Its surface
    displacement arrives from the SOLID through preCICE, which is why the wall patches
    carry a plain ``fixedValue`` in ``pointDisplacement`` (the adapter overwrites it) and
    ``movingWallVelocity`` in ``U`` (so the no-slip condition is enforced in the moving
    frame -- with a plain ``noSlip`` the forces are biased by the wall's own velocity).
    """

    model_config = _STRICT

    geometry: Literal["flexible_foil"] = "flexible_foil"
    name: str = Field(..., min_length=1)

    # --- dimensional flow state (SI) ---
    u_inf: float = Field(..., gt=0.0, description="Freestream speed [m/s].")
    rho: float = Field(..., gt=0.0, description="Density [kg/m^3]; water at 1000.")
    nu: float = Field(..., gt=0.0, description="Kinematic viscosity [m^2/s]; water at 1e-6.")
    chord: float = Field(..., gt=0.0, description="Chord [m].")
    span: float = Field(..., gt=0.0, description="Slab thickness [m]; MUST equal the solid's.")

    # --- section (the teardrop + plate the C-grid wraps) ---
    section: TeardropPlateSection

    # --- coupling ---
    time_window_size: float = Field(
        ..., gt=0.0, description="Coupling window [s]; the fluid dt equals it exactly."
    )
    max_time: float = Field(..., gt=0.0, description="Coupled end time [s].")
    precice_config: str = Field(default="../precice-config.xml", min_length=1)
    ddt_scheme: str = Field(
        default="Euler",
        description=(
            "Euler until the I8 checkpoint-fidelity probe establishes that the adapter "
            "restores U.oldTime().oldTime() across coupling iterations; see ADR-039."
        ),
    )

    # --- C-grid resolution (the pre-registered rung knobs) ---
    farfield_extent_chords: float = Field(default=20.0, gt=1.0)
    n_surface: int = Field(default=108, gt=3)
    n_normal: int = Field(default=108, gt=3)
    n_front: int = Field(default=54, gt=3)
    n_wake: int = Field(default=86, gt=3)
    n_te: int = Field(default=4, ge=1, description="Cells across the blunt plate base.")
    first_cell_height: float = Field(
        default=5.0e-4,
        gt=0.0,
        description=(
            "Wall spacing in chords. The CaseSpec default of 2.0e-6 was authored for a "
            "y+<1 RAS TMR mesh and is unrunnable here -- 0.18 um on a 90 mm chord, which "
            "would need dt ~ 1.7e-6 s. 5.0e-4 is the pre-registered value (the Stage-11/13 "
            "PlungingAirfoilSpec precedent), and it measured BETTER on every mesh-quality "
            "metric than the spike's default (handoff 6.16)."
        ),
    )

    # --- output ---
    field_write_interval_windows: int = Field(
        default=2000,
        ge=1,
        description="Coupling windows between full field writes (the force FOs write every step).",
    )

    rbf_support_radius_spacings: float = Field(
        default=8.0,
        gt=1.0,
        description=(
            "RBF support radius, in surface-cell spacings. Upstream's literal 1. is one "
            "metre -- eleven chords here -- which would smear the mapping across the whole "
            "foil; a radius of a few cells is what a compact-polynomial basis wants."
        ),
    )

    @model_validator(mode="after")
    def _the_section_matches_the_meshed_base(self) -> FlexibleFoilSpec:
        """The plate's thickness and the C-grid's blunt base are the same number.

        ``CaseSpec`` validates this too, but failing here names the flexible-foil field
        that is actually wrong instead of a derived one.
        """
        if not 0.0 < self.section.join_x < self.chord:
            raise ValueError(
                f"join_x ({self.section.join_x}) must lie inside the chord ({self.chord})"
            )
        return self

    @property
    def reynolds(self) -> float:
        return self.u_inf * self.chord / self.nu

    @property
    def trailing_edge_thickness(self) -> float:
        """The blunt base, in chords -- exactly the plate's full thickness."""
        return 2.0 * self.section.plate_half_thickness / self.chord

    @property
    def surface_spacing(self) -> float:
        """Approximate wetted-surface cell size [m].

        The C-grid's surface blocks are ``simpleGrading (1.0 ...)`` -- uniform in ARC
        LENGTH, not cosine-clustered (the cosine spacing is shape fidelity, not the cell
        distribution), and each side carries ``2 * n_surface`` cells over roughly one
        chord of arc. Approximate on purpose: it sizes an RBF support radius, where being
        within a factor of two of the true spacing is what matters and being off by four
        orders -- upstream's one metre -- is what does not.
        """
        return self.chord / (2.0 * self.n_surface)

    @property
    def rbf_support_radius(self) -> float:
        """The support radius [m] the rendered precice-config.xml carries."""
        return self.rbf_support_radius_spacings * self.surface_spacing

    @property
    def n_windows(self) -> int:
        return round(self.max_time / self.time_window_size)

    def mesh_spec(self) -> CaseSpec:
        """The ``CaseSpec`` carrying the geometry the shared C-grid writer needs."""
        return CaseSpec(
            name=self.name,
            reynolds=self.reynolds,
            mach=0.01,
            aoa_deg=0.0,
            chord=self.chord,
            span=self.span,
            turbulence_model="laminar",
            farfield_extent_chords=self.farfield_extent_chords,
            n_surface=self.n_surface,
            n_normal=self.n_normal,
            n_front=self.n_front,
            n_wake=self.n_wake,
            first_cell_height=self.first_cell_height,
            trailing_edge_thickness=self.trailing_edge_thickness,
            n_te=self.n_te,
            section=self.section,
        )


def _patch_list(patches: tuple[str, ...]) -> str:
    return "(" + " ".join(patches) + ")"


def _controldict(spec: FlexibleFoilSpec) -> str:
    a_ref = spec.chord * spec.span
    write_interval = spec.field_write_interval_windows
    return (
        header("dictionary", "controlDict")
        + f"""
application     pimpleFoam;
startFrom       startTime;
startTime       0;
stopAt          endTime;
endTime         {spec.max_time:.12g};
deltaT          {spec.time_window_size:.12g};
writeControl    timeStep;
writeInterval   {write_interval};
purgeWrite      2;
writeFormat     ascii;
writePrecision  12;
writeCompression off;
timeFormat      general;
timePrecision   {_TIME_PRECISION};
runTimeModifiable false;
adjustTimeStep  no;

// WITHOUT the two lines below pimpleFoam runs an UNCOUPLED solve to endTime and exits 0.
libs ("libpreciceAdapterFunctionObject.so");

functions
{{
    preCICE_Adapter
    {{
        type            preciceAdapterFunctionObject;
        errors          strict;
    }}
    // Dimensional forces [N] -- this is the readout of record. rhoInf is the REAL density,
    // so what the force objects integrate is the same newton the solid receives.
    forces1
    {{
        type            forces;
        libs            (forces);
        writeControl    timeStep;
        writeInterval   1;
        patches         {_patch_list(WALL_PATCHES)};
        rho             rhoInf;
        rhoInf          {spec.rho:.12g};
        CofR            (0 0 0);
    }}
    // Coefficients, as an independent cross-check of the dimensional integral above.
    forceCoeffs1
    {{
        type            forceCoeffs;
        libs            (forces);
        writeControl    timeStep;
        writeInterval   1;
        patches         {_patch_list(WALL_PATCHES)};
        rho             rhoInf;
        rhoInf          {spec.rho:.12g};
        magUInf         {spec.u_inf:.12g};
        lRef            {spec.chord:.12g};
        Aref            {a_ref:.12g};
        dragDir         (1 0 0);
        liftDir         (0 1 0);
        CofR            (0 0 0);
        pitchAxis       (0 0 1);
    }}
}}
"""
    )


def _precice_dict(spec: FlexibleFoilSpec) -> str:
    return (
        header("dictionary", "preciceDict")
        + f"""
preciceConfig "{spec.precice_config}";

participant {FLUID_PARTICIPANT};

modules (FSI);

interfaces
{{
  Interface1
  {{
    mesh              Fluid-Mesh;
    patches           {_patch_list(WALL_PATCHES)};
    locations         faceCenters;

    readData
    (
      Displacement
    );

    writeData
    (
      Force
    );
  }};
}};

// The REAL density: pimpleFoam solves in kinematic variables, so the adapter needs rho to
// hand preCICE an absolute force in newtons -- which is what CalculiX is loaded with.
FSI
{{
  rho rho [1 -3 0 0 0 0 0] {spec.rho:.12g};
}}
"""
    )


def _dynamic_mesh_dict(spec: FlexibleFoilSpec) -> str:
    """Morphing mesh driven by the interface displacement preCICE delivers.

    ``quadratic inverseDistance`` (upstream's choice for this class, rather than the plain
    ``inverseDistance`` of the Stage-11 heave case) makes the motion stiffness fall off as
    the square of the distance from the wall, so the near-wall layer moves almost rigidly
    with the foil and the wall spacing survives the stroke.
    """
    return (
        header("dictionary", "dynamicMeshDict")
        + f"""
dynamicFvMesh    dynamicMotionSolverFvMesh;
motionSolverLibs ("libfvMotionSolvers.so");
solver           displacementLaplacian;
displacementLaplacianCoeffs
{{
    diffusivity  quadratic inverseDistance {_patch_list(WALL_PATCHES)};
}}
"""
    )


def _field(obj: str, cls: str, dims: str, internal: str, farfield: str, wall: str) -> str:
    walls = "\n".join(
        f"""    {patch}
    {{
{wall}
    }}"""
        for patch in WALL_PATCHES
    )
    return (
        header(cls, obj)
        + f"""
dimensions      {dims};
internalField   uniform {internal};

boundaryField
{{
{walls}
    farfield
    {{
{farfield}
    }}
    front {{ type empty; }}
    back  {{ type empty; }}
}}
"""
    )


def _fields(spec: FlexibleFoilSpec) -> dict[str, str]:
    u_vec = f"({spec.u_inf:.12g} 0 0)"
    return {
        "U": _field(
            "U",
            "volVectorField",
            "[0 1 -1 0 0 0 0]",
            u_vec,
            f"        type freestream;\n        freestreamValue uniform {u_vec};",
            # No-slip in the MOVING frame. With a plain noSlip the wall's own velocity
            # leaks into the integrated force, which is the quantity being gated.
            "        type movingWallVelocity;\n        value uniform (0 0 0);",
        ),
        "p": _field(
            "p",
            "volScalarField",
            "[0 2 -2 0 0 0 0]",
            "0",
            "        type freestreamPressure;\n        freestreamValue uniform 0;",
            "        type zeroGradient;",
        ),
        "pointDisplacement": _field(
            "pointDisplacement",
            "pointVectorField",
            "[0 1 0 0 0 0 0]",
            "(0 0 0)",
            "        type fixedValue;\n        value uniform (0 0 0);",
            # fixedValue, NOT a prescribed oscillation: the adapter overwrites these values
            # every coupling iteration with the displacement the solid computed. A
            # prescribed motion here would drive the foil independently of the solid and
            # the run would still converge.
            "        type fixedValue;\n        value uniform (0 0 0);",
        ),
    }


def write_flexible_foil_case(spec: FlexibleFoilSpec, dest: Path) -> None:
    """Write the complete dimensional fluid participant under `dest`."""
    system = dest / "system"
    constant = dest / "constant"
    zero = dest / "0"
    for directory in (system, constant, zero):
        directory.mkdir(parents=True, exist_ok=True)

    (system / "blockMeshDict").write_text(_blockmeshdict(spec.mesh_spec()), encoding="utf-8")
    (system / "controlDict").write_text(_controldict(spec), encoding="utf-8")
    (system / "preciceDict").write_text(_precice_dict(spec), encoding="utf-8")
    (system / "fvSchemes").write_text(
        transient_fvschemes(turbulence_model="laminar", ddt_scheme=spec.ddt_scheme),
        encoding="utf-8",
    )
    (system / "fvSolution").write_text(
        transient_fvsolution(cell_displacement=True, turbulence_model="laminar"),
        encoding="utf-8",
    )
    (constant / "transportProperties").write_text(transport_properties(spec.nu), encoding="utf-8")
    (constant / "turbulenceProperties").write_text(
        turbulence_properties("laminar"), encoding="utf-8"
    )
    (constant / "dynamicMeshDict").write_text(_dynamic_mesh_dict(spec), encoding="utf-8")
    for name, text in _fields(spec).items():
        (zero / name).write_text(text, encoding="utf-8")
