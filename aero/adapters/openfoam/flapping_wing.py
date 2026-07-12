"""Rigid 2-D flapping wing in hover — the flagship forward-capability case (Stage 14).

A thin elliptic wing performs a prescribed flapping stroke (translation + pitch) in a
quiescent domain at Re ~ 10^2, reproducing Wang, Birch & Dickinson (2004)'s 2-D robotic-wing
computation. This is the last validated forward problem before the Stage-15 optimizer.

**Motion solver (ADR-024, revised after the Stage-14 R0 probe).** The large stroke
(A0/c = 2.8, i.e. +/-1.4c translation) tears a deforming (morph) mesh (R0: skewness 5503,
negative volumes), and whole-mesh solid-body motion is physically wrong for a body oscillating
in still fluid (an accelerating frame with no fictitious forces). The tier of record is
therefore **overset** (`overPimpleDyMFoam` + `dynamicOversetFvMesh`): the wing sits on a small
**component** O-grid that moves rigidly (via `multiSolidBodyMotionSolver` +
`tabulated6DoFMotion`) over a fixed Cartesian **background** mesh, so the far field is genuinely
fixed, nothing deforms, and any amplitude is admissible. ``mesh_motion="morph"`` is retained as
a documented small-amplitude alternative (single deforming mesh).

**Hover has no freestream:** the far field is an open ``pressureInletOutletVelocity`` /
``totalPressure`` boundary, the case writes only the *dimensional* ``forces`` FO
(``forceCoeffs`` divides by ``magUInf`` — meaningless), and the wing wall uses
``movingWallVelocity`` (no-slip in the moving frame, for unbiased forces). ``vorticity`` and
``Q`` fields are written at each phase-locked write time for the leading-edge-vortex evidence.
Laminar only (Re ~ 100; no transition model this rung).
"""

from __future__ import annotations

import math
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from aero.adapters.openfoam._foam_common import (
    RHO_INF,
    expansion,
    header,
    pt,
    transient_fvschemes,
    transient_fvsolution,
    transport_properties,
    turbulence_properties,
)
from aero.adapters.openfoam.motion import (
    FlappingMotionSpec,
    dynamic_mesh_dict,
    flapping_motion_table,
    flapping_point_displacement_field,
)

_STRICT = ConfigDict(
    extra="forbid",
    frozen=True,
    str_strip_whitespace=True,
    validate_assignment=True,
    validate_default=True,
)

_MOTION_TABLE_FILE = "flapping_motion.dat"
_MOTION_TABLE_REF = f"<constant>/{_MOTION_TABLE_FILE}"


class FlappingWingSpec(BaseModel):
    """A 2-D rigid elliptic wing in prescribed flapping hover — transient laminar (WBD 2004)."""

    model_config = _STRICT

    geometry: Literal["flapping_wing_2d"] = "flapping_wing_2d"
    name: str = Field(..., min_length=1, description="Case name.")
    reynolds: float = Field(
        ..., gt=0, description="Re = u_ref*chord/nu, u_ref = U_max = omega*stroke_amplitude (WBD)."
    )
    chord: float = Field(default=1.0, gt=0, description="Wing chord c (length units).")
    thickness_ratio: float = Field(
        default=0.125, gt=0.0, lt=1.0, description="Ellipse thickness/chord (WBD leave it free)."
    )
    span: float = Field(default=1.0, gt=0, description="Spanwise extent (one cell, 2D).")
    turbulence_model: Literal["laminar"] = Field(
        default="laminar", description="Re~100 is laminar; no turbulence transport."
    )
    transient: Literal[True] = Field(default=True)

    motion: FlappingMotionSpec = Field(..., description="Prescribed flapping stroke (required).")
    mesh_motion: Literal["overset", "morph"] = Field(
        default="overset",
        description="Mesh-motion strategy (ADR-024): 'overset' (rigid component over fixed "
        "background — the tier of record) or 'morph' (single deforming mesh; small amplitude "
        "only). Provenance-visible.",
    )

    # --- component O-grid resolution (chord-based; the near-wing mesh) ---
    n_radial: int = Field(default=110, gt=3, description="Radial cells (wing -> component edge).")
    n_azimuthal: int = Field(
        default=64, gt=3, description="Azimuthal cells per 90-deg block (x4 around the wing)."
    )
    radial_first_cell: float = Field(
        default=5.0e-3, gt=0, description="First radial cell height at the wall, in chords."
    )
    spline_points_per_quadrant: int = Field(
        default=16, gt=1, description="Ellipse spline sampling per 90-deg block (mesh fidelity)."
    )
    component_radius_chords: float = Field(
        default=5.0, gt=1.0, description="Overset component O-grid outer radius (chords)."
    )

    # --- background (overset) / far field (morph) ---
    background_extent_chords: float = Field(
        default=22.0, gt=5.0, description="Overset background box half-extent (chords)."
    )
    background_cells: int = Field(
        default=120, gt=8, description="Overset background cells per side (uniform Cartesian box)."
    )
    farfield_radius_chords: float = Field(
        default=25.0, gt=2.0, description="Morph single-mesh outer-circle radius (chords)."
    )

    # --- transient controls (in flapping periods) ---
    end_time_cycles: float = Field(
        default=24.0, gt=0, description="Total run length in flapping periods (~16+ converged)."
    )
    write_phases_per_cycle: int = Field(
        default=16, gt=1, description="Field writes per cycle (phase-locked LEV snapshots)."
    )
    purge_write: int = Field(
        default=40, ge=0, description="Field time-dirs retained (0 = keep all); ~2.5 cycles at 16."
    )
    max_courant: float = Field(default=2.0, gt=0, description="Courant cap (overset tolerates ~2).")

    @property
    def pivot(self) -> tuple[float, float, float]:
        """The pitch pivot (CofG for the motion).

        The O-grid is built about the ellipse *centre* (the origin), so the pivot is the offset
        of the pitch axis from the centre: ``(pivot_chord_fraction - 0.5)`` chords along the
        chord direction (``pitch_mean_deg``). WBD pitch about the wing centre => 0.5 => origin.
        """
        off = (self.motion.pivot_chord_fraction - 0.5) * self.chord
        th = math.radians(self.motion.pitch_mean_deg)
        return (off * math.cos(th), off * math.sin(th), 0.0)


# --- ellipse geometry ---------------------------------------------------------
def _ellipse_point(spec: FlappingWingSpec, geom_angle_deg: float) -> tuple[float, float]:
    """The wing-ellipse boundary point along the ray at world angle ``geom_angle_deg``.

    The ellipse (semi-major ``chord/2`` along the chord, semi-minor ``thickness_ratio*chord/2``)
    is centred at the origin and oriented at ``pitch_mean_deg``. Placing the inner O-grid corners
    at the SAME geometric angles as the outer ring keeps the radial edges untwisted (an ellipse
    point at its own *parametric* angle would not line up with the circle after rotation,
    inverting the blocks). Uses the ellipse polar radius in the rotated frame.
    """
    a = 0.5 * spec.chord
    b = 0.5 * spec.thickness_ratio * spec.chord
    theta = math.radians(geom_angle_deg)
    phi = theta - math.radians(spec.motion.pitch_mean_deg)
    r = a * b / math.hypot(b * math.cos(phi), a * math.sin(phi))
    return r * math.cos(theta), r * math.sin(theta)


def _ogrid_blockmesh(
    spec: FlappingWingSpec, *, outer_radius: float, outer_patch: str, outer_type: str
) -> str:
    """4-block O-grid: inner ellipse (spline edges) -> outer circle (arc edges).

    Same winding as the Stage-11 cylinder O-grid (positive cell volumes, radial graded toward the
    wall). Parametrised on the outer boundary so it serves both the overset component
    (outer_patch='overset', small radius) and the morph single mesh (outer_patch='farfield').
    """
    rr = outer_radius
    span = spec.span
    angles = [45.0, 135.0, 225.0, 315.0]
    inner = [_ellipse_point(spec, a) for a in angles]
    outer = [(rr * math.cos(math.radians(a)), rr * math.sin(math.radians(a))) for a in angles]
    base = inner + outer
    nb = len(base)
    verts = [pt(x, y, 0.0) for x, y in base] + [pt(x, y, span) for x, y in base]
    inner_ref = 0.5 * spec.thickness_ratio * spec.chord
    g_rad = expansion(rr - inner_ref, spec.n_radial, spec.radial_first_cell * spec.chord)
    na, nrad = spec.n_azimuthal, spec.n_radial

    def _verts(a: int, b: int, c: int, d: int) -> str:
        return " ".join(str(v) for v in (a, b, c, d, a + nb, b + nb, c + nb, d + nb))

    blocks = [
        f"    hex ({_verts(i, 4 + i, 4 + (i + 1) % 4, (i + 1) % 4)}) ({nrad} {na} 1) "
        f"simpleGrading ({g_rad:.8g} 1 1)"
        for i in range(4)
    ]

    def arc(v1: int, v2: int, mid_angle: float, z: float) -> str:
        mx = rr * math.cos(math.radians(mid_angle))
        my = rr * math.sin(math.radians(mid_angle))
        return f"    arc {v1} {v2} ({mx:.8f} {my:.8f} {z:.8f})"

    edges = []
    for i in range(4):
        j = (i + 1) % 4
        a0, a1 = angles[i], angles[i] + 90.0
        npq = spec.spline_points_per_quadrant
        pts0 = " ".join(
            f"({x:.8f} {y:.8f} 0.0)"
            for x, y in (_ellipse_point(spec, a0 + (a1 - a0) * k / npq) for k in range(1, npq))
        )
        pts1 = " ".join(
            f"({x:.8f} {y:.8f} {span:.8f})"
            for x, y in (_ellipse_point(spec, a0 + (a1 - a0) * k / npq) for k in range(1, npq))
        )
        edges.append(f"    spline {i} {j} ({pts0})")
        edges.append(f"    spline {i + nb} {j + nb} ({pts1})")
        edges.append(arc(4 + i, 4 + j, angles[i] + 45.0, 0.0))
        edges.append(arc(4 + i + nb, 4 + j + nb, angles[i] + 45.0, span))

    def face(a: int, b: int) -> str:
        return f"({a} {b} {b + nb} {a + nb})"

    wing = " ".join(face(i, (i + 1) % 4) for i in range(4))
    outer_faces = " ".join(face(4 + i, 4 + (i + 1) % 4) for i in range(4))
    z0 = " ".join(f"({i} {4 + i} {4 + (i + 1) % 4} {(i + 1) % 4})" for i in range(4))
    zspan = " ".join(
        f"({i + nb} {4 + i + nb} {4 + (i + 1) % 4 + nb} {(i + 1) % 4 + nb})" for i in range(4)
    )
    boundary = f"""    wing
    {{
        type wall;
        faces ( {wing} );
    }}
    {outer_patch}
    {{
        type {outer_type};
        faces ( {outer_faces} );
    }}
    front
    {{
        type empty;
        faces ( {z0} );
    }}
    back
    {{
        type empty;
        faces ( {zspan} );
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


def _background_blockmesh(spec: FlappingWingSpec) -> str:
    """A uniform Cartesian background box (overset donors); open ``farfield`` outer boundary."""
    half = spec.background_extent_chords * spec.chord
    n = spec.background_cells
    span = spec.span
    v = [
        pt(-half, -half, 0.0),
        pt(half, -half, 0.0),
        pt(half, half, 0.0),
        pt(-half, half, 0.0),
        pt(-half, -half, span),
        pt(half, -half, span),
        pt(half, half, span),
        pt(-half, half, span),
    ]
    verts_block = "\n".join(f"    {x}" for x in v)
    return (
        header("dictionary", "blockMeshDict")
        + "\nscale 1;\n\n"
        + f"vertices\n(\n{verts_block}\n);\n\n"
        + f"blocks\n(\n    hex (0 1 2 3 4 5 6 7) ({n} {n} 1) simpleGrading (1 1 1)\n);\n\n"
        + "edges ( );\n\n"
        + """boundary
(
    farfield
    { type patch; faces ( (0 4 7 3) (1 2 6 5) (0 1 5 4) (3 7 6 2) ); }
    front
    { type empty; faces ( (0 3 2 1) ); }
    back
    { type empty; faces ( (4 5 6 7) ); }
);

mergePatchPairs ( );
"""
    )


# --- transient dictionaries ---------------------------------------------------
def _controldict(spec: FlappingWingSpec) -> str:
    period = spec.motion.period
    end_time = spec.end_time_cycles * period
    write_interval = period / spec.write_phases_per_cycle
    px, py, pz = spec.pivot
    application = "overPimpleDyMFoam" if spec.mesh_motion == "overset" else "pimpleFoam"
    return (
        header("dictionary", "controlDict")
        + f"""
application     {application};
startFrom       startTime;
startTime       0;
stopAt          endTime;
endTime         {end_time:.8g};
deltaT          {0.02 * write_interval:.8g};
writeControl    adjustableRunTime;
writeInterval   {write_interval:.8g};
purgeWrite      {spec.purge_write};
writeFormat     ascii;
writePrecision  8;
runTimeModifiable false;
adjustTimeStep  yes;
maxCo           {spec.max_courant:.8g};
maxDeltaT       {write_interval:.8g};

functions
{{
    forces1
    {{
        type            forces;
        libs            (forces);
        writeControl    timeStep;
        writeInterval   1;
        patches         (wing);
        rho             rhoInf;
        rhoInf          {RHO_INF};
        CofR            ({px:.8g} {py:.8g} {pz:.8g});
    }}
    vorticity1
    {{
        type            vorticity;
        libs            (fieldFunctionObjects);
        writeControl    writeTime;
    }}
    Q1
    {{
        type            Q;
        libs            (fieldFunctionObjects);
        writeControl    writeTime;
    }}
}}
"""
    )


def _overset_dynamic_mesh_dict(spec: FlappingWingSpec) -> str:
    """`dynamicOversetFvMesh` + `multiSolidBodyMotionSolver`: fixed background, rigid component."""
    px, py, pz = spec.pivot
    return (
        header("dictionary", "dynamicMeshDict")
        + f"""
dynamicFvMesh   dynamicOversetFvMesh;
solver          multiSolidBodyMotionSolver;
multiSolidBodyMotionSolverCoeffs
{{
    background
    {{
        solidBodyMotionFunction linearMotion;
        linearMotionCoeffs {{ velocity (0 0 0); }}
    }}
    movingZone
    {{
        solidBodyMotionFunction tabulated6DoFMotion;
        tabulated6DoFMotionCoeffs
        {{
            CofG              ({px:.8g} {py:.8g} {pz:.8g});
            timeDataFileName  "{_MOTION_TABLE_REF}";
        }}
    }}
}}
"""
    )


def _overset_toposet_dict(spec: FlappingWingSpec) -> str:
    """Split the merged mesh into `background` + `movingZone` cellZones by connectivity."""
    corner = 0.9 * spec.background_extent_chords * spec.chord
    return (
        header("dictionary", "topoSetDict")
        + f"""
actions
(
    {{ name c0; type cellSet; action new; source regionToCell;
       insidePoints (({corner:.8g} {corner:.8g} 0.0001)); }}
    {{ name background; type cellZoneSet; action new; source setToCellZone; set c0; }}
    {{ name c1; type cellSet; action new; source cellToCell; set c0; }}
    {{ name c1; type cellSet; action invert; }}
    {{ name movingZone; type cellZoneSet; action new; source setToCellZone; set c1; }}
);
"""
    )


def _overset_setfields_dict() -> str:
    return (
        header("dictionary", "setFieldsDict")
        + """
defaultFieldValues ( volScalarFieldValue zoneID 123 );
regions
(
    cellToCell { set c0; fieldValues ( volScalarFieldValue zoneID 0 ); }
    cellToCell { set c1; fieldValues ( volScalarFieldValue zoneID 1 ); }
);
"""
    )


def _overset_fvschemes() -> str:
    return (
        header("dictionary", "fvSchemes")
        + """
ddtSchemes      { default CrankNicolson 0.7; }
gradSchemes     { default Gauss linear; }
divSchemes
{
    default         none;
    div(phi,U)      Gauss limitedLinearV 1;
    div((nuEff*dev2(T(grad(U))))) Gauss linear;
}
laplacianSchemes { default Gauss linear corrected; }
interpolationSchemes { default linear; }
snGradSchemes   { default corrected; }
oversetInterpolation { method inverseDistance; }
fluxRequired    { default no; pcorr; p; }
"""
    )


def _overset_fvsolution() -> str:
    return (
        header("dictionary", "fvSolution")
        + """
solvers
{
    cellDisplacement { solver PCG; preconditioner DIC; tolerance 1e-06; relTol 0; maxIter 100; }
    p       { solver PBiCGStab; preconditioner DILU; tolerance 1e-8; relTol 0; }
    pFinal  { $p; relTol 0; }
    pcorr   { $pFinal; solver PCG; preconditioner DIC; }
    pcorrFinal { $pcorr; relTol 0; }
    "(U)"      { solver smoothSolver; smoother symGaussSeidel; tolerance 1e-8; relTol 0; }
    "(U)Final" { $U; relTol 0; }
}
PIMPLE
{
    momentumPredictor   false;
    nOuterCorrectors    2;
    nCorrectors         2;
    nNonOrthogonalCorrectors 1;
    oversetAdjustPhi    yes;
}
relaxationFactors { equations { ".*" 1; } }
"""
    )


def _fields(spec: FlappingWingSpec) -> dict[str, str]:
    """0/ fields. Quiescent hover; movingWallVelocity wing; open far field. Overset adds the
    ``overset`` interpolation patch + a ``zoneID`` marker field."""
    overset = spec.mesh_motion == "overset"
    outer = "farfield"  # both paths name the open outer boundary `farfield`
    constraint = '    #includeEtc "caseDicts/setConstraintTypes"\n' if overset else ""
    over_u = "    overset   { type overset; value uniform (0 0 0); }\n" if overset else ""
    over_p = "    overset   { type overset; value uniform 0; }\n" if overset else ""

    def field(obj: str, cls: str, dims: str, internal: str, over: str, wing: str, far: str) -> str:
        return (
            header(cls, obj)
            + f"""
dimensions      {dims};
internalField   uniform {internal};

boundaryField
{{
{constraint}{over}    wing
    {{
{wing}
    }}
    {outer}
    {{
{far}
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
            "(0 0 0)",
            over_u,
            "        type movingWallVelocity;\n        value uniform (0 0 0);",
            "        type pressureInletOutletVelocity;\n        value uniform (0 0 0);",
        ),
        "p": field(
            "p",
            "volScalarField",
            "[0 2 -2 0 0 0 0]",
            "0",
            over_p,
            "        type zeroGradient;",
            "        type totalPressure;\n        p0 uniform 0;\n        value uniform 0;",
        ),
    }
    if overset:
        fields["zoneID"] = (
            header("volScalarField", "zoneID")
            + """
dimensions      [0 0 0 0 0 0 0];
internalField   uniform 0;

boundaryField
{
    #includeEtc "caseDicts/setConstraintTypes"
    overset   { type overset; value uniform 0; }
    ".*"      { type zeroGradient; }
}
"""
        )
    return fields


def _write_component_stub(component: Path) -> None:
    """A minimal but complete system/ so `blockMesh -case component` runs standalone."""
    (component / "system").mkdir(parents=True, exist_ok=True)
    (component / "constant").mkdir(parents=True, exist_ok=True)
    (component / "system" / "controlDict").write_text(
        header("dictionary", "controlDict")
        + "\napplication blockMesh;\nstartFrom startTime;\nstartTime 0;\nstopAt endTime;\n"
        "endTime 1;\ndeltaT 1;\nwriteControl timeStep;\nwriteInterval 1;\n",
        encoding="utf-8",
    )
    for d in ("fvSchemes", "fvSolution"):
        (component / "system" / d).write_text(header("dictionary", d) + "\n", encoding="utf-8")


def write_flapping_wing_case(spec: FlappingWingSpec, dest: Path) -> None:
    """Write a complete transient OpenFOAM case for the flapping wing under ``dest``.

    For ``mesh_motion="overset"`` (default) this writes the background blockMeshDict in the case
    root, the component O-grid in ``component/``, and the topoSet/setFields dicts; the mesh is
    assembled by ``OpenFOAMSolver.mesh`` (blockMesh x2 -> mergeMeshes -> topoSet -> setFields).
    For ``mesh_motion="morph"`` it writes a single deforming O-grid.
    """
    system = dest / "system"
    constant = dest / "constant"
    zero = dest / "0"
    for d in (system, constant, zero):
        d.mkdir(parents=True, exist_ok=True)

    # WBD Reynolds number is built on the maximum wing speed U_max (= u_ref), not a freestream.
    nu = spec.motion.u_ref * spec.chord / spec.reynolds

    (system / "controlDict").write_text(_controldict(spec), encoding="utf-8")
    (constant / "transportProperties").write_text(transport_properties(nu), encoding="utf-8")
    (constant / "turbulenceProperties").write_text(
        turbulence_properties(spec.turbulence_model), encoding="utf-8"
    )
    for name, text in _fields(spec).items():
        (zero / name).write_text(text, encoding="utf-8")

    # The prescribed motion table, generated a full period past endTime so the final solver step
    # never queries beyond the table (the tabulated6DoFMotion end-of-table error).
    end_time = spec.end_time_cycles * spec.motion.period
    (constant / _MOTION_TABLE_FILE).write_text(
        flapping_motion_table(spec.motion, end_time=end_time + spec.motion.period),
        encoding="utf-8",
    )

    if spec.mesh_motion == "overset":
        (system / "fvSchemes").write_text(_overset_fvschemes(), encoding="utf-8")
        (system / "fvSolution").write_text(_overset_fvsolution(), encoding="utf-8")
        (system / "topoSetDict").write_text(_overset_toposet_dict(spec), encoding="utf-8")
        (system / "setFieldsDict").write_text(_overset_setfields_dict(), encoding="utf-8")
        (constant / "dynamicMeshDict").write_text(
            _overset_dynamic_mesh_dict(spec), encoding="utf-8"
        )
        # background mesh in the case root; component O-grid in component/
        (system / "blockMeshDict").write_text(_background_blockmesh(spec), encoding="utf-8")
        component = dest / "component"
        _write_component_stub(component)
        (component / "system" / "blockMeshDict").write_text(
            _ogrid_blockmesh(
                spec,
                outer_radius=spec.component_radius_chords * spec.chord,
                outer_patch="overset",
                outer_type="overset",
            ),
            encoding="utf-8",
        )
    else:  # morph — single deforming O-grid
        (system / "fvSchemes").write_text(transient_fvschemes(), encoding="utf-8")
        (system / "fvSolution").write_text(
            transient_fvsolution(cell_displacement=True), encoding="utf-8"
        )
        (system / "blockMeshDict").write_text(
            _ogrid_blockmesh(
                spec,
                outer_radius=spec.farfield_radius_chords * spec.chord,
                outer_patch="farfield",
                outer_type="patch",
            ),
            encoding="utf-8",
        )
        (constant / "dynamicMeshDict").write_text(
            dynamic_mesh_dict(moving_patch="wing"), encoding="utf-8"
        )
        (zero / "pointDisplacement").write_text(
            flapping_point_displacement_field(
                moving_patch="wing",
                cofg=spec.pivot,
                table_filename=_MOTION_TABLE_REF,
                fixed_patches=["farfield"],
                empty_patches=["front", "back"],
            ),
            encoding="utf-8",
        )
