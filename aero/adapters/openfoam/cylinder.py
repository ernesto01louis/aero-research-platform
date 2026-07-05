"""Transient low-Re cylinder — the forward-regime vortex-shedding case.

A circular cylinder at Re = 100 sheds a laminar von Karman street; the canonical
verification is the Strouhal number St = f D / U against the Roshko/Williamson
St-Re relation (St ~= 0.165 at Re = 100). This is the platform's first *transient*
OpenFOAM case (`pimpleFoam`), the unsteady machinery the flapping mission needs.

Mesh: a 4-block circular **O-grid** (inner radius D/2, outer radius
`farfield_radius_diameters`*D), arc edges on both circles, radial grading toward
the cylinder. Cylinder = no-slip wall; the whole outer circle = a single
`freestream` patch (the BC auto-switches inflow/outflow by flux). Laminar (no
turbulence transport). The solve writes the lift coefficient every
`write_interval_convective` convective times; the loader FFTs Cl(t) to recover
the shedding frequency (see `aero.adapters.openfoam.solver`).
"""

from __future__ import annotations

import math
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from aero.adapters.openfoam._foam_common import (
    RHO_INF,
    U_INF,
    expansion,
    flow_state,
    header,
    pt,
    transient_fvschemes,
    transient_fvsolution,
    transport_properties,
    turbulence_properties,
)
from aero.adapters.openfoam.motion import (
    MotionSpec,
    dynamic_mesh_dict,
    point_displacement_field,
)

_STRICT = ConfigDict(
    extra="forbid",
    frozen=True,
    str_strip_whitespace=True,
    validate_assignment=True,
    validate_default=True,
)


class CylinderSpec(BaseModel):
    """A 2D circular cylinder in cross-flow — transient laminar (vortex shedding)."""

    model_config = _STRICT

    geometry: Literal["cylinder"] = "cylinder"
    name: str = Field(..., min_length=1, description="Case name.")
    reynolds: float = Field(..., gt=0, description="Reynolds number based on diameter.")
    mach: float = Field(default=0.1, gt=0, description="Reference Mach number (recorded only).")
    diameter: float = Field(default=1.0, gt=0, description="Cylinder diameter D.")
    span: float = Field(default=1.0, gt=0, description="Spanwise extent (one cell, 2D).")
    turbulence_model: Literal["laminar"] = Field(
        default="laminar", description="Re~100 is laminar; no turbulence transport."
    )
    # This is a transient case — the adapter runs pimpleFoam, not simpleFoam.
    transient: Literal[True] = Field(default=True)

    # A small freestream tilt seeds the shedding instability: a perfectly
    # symmetric mesh + axial inflow stays symmetric for ~hundreds of convective
    # times (the unstable mode grows only from round-off). A circular cylinder is
    # axisymmetric, so a few degrees is physically equivalent and the shedding
    # frequency (hence St) is unaffected; the FFT detrends the small mean lift.
    inflow_angle_deg: float = Field(
        default=5.0, ge=0.0, description="Freestream tilt (deg) to seed vortex shedding."
    )

    # --- O-grid resolution ---
    farfield_radius_diameters: float = Field(
        default=50.0, gt=2.0, description="Outer-circle radius in diameters (blockage-free St)."
    )
    n_radial: int = Field(default=100, gt=3, description="Radial cells (cylinder -> far field).")
    n_azimuthal: int = Field(
        default=64, gt=3, description="Azimuthal cells per 90-deg block (x4 around the circle)."
    )
    radial_first_cell: float = Field(
        default=0.02, gt=0, description="First radial cell height at the wall, in diameters."
    )

    # --- transient controls (in convective times t* = t U / D) ---
    end_time_convective: float = Field(
        default=150.0, gt=0, description="Total run length in convective times (shedding + FFT)."
    )
    write_interval_convective: float = Field(
        default=0.25, gt=0, description="Cl sampling interval in convective times (FFT resolution)."
    )
    max_courant: float = Field(default=0.5, gt=0, description="Adjustable-timestep Courant cap.")

    # Prescribed rigid-body motion (Stage 11). None -> the Stage-10 static shedding case;
    # a MotionSpec -> a moving-mesh (morphing) case: the cylinder wall gets a
    # movingWallVelocity BC, a dynamicMeshDict + pointDisplacement are written, and the
    # controlDict adds a `forces` FO for the cycle-mean pressure/viscous split.
    motion: MotionSpec | None = Field(
        default=None, description="Prescribed heave motion; None => static shedding case."
    )


# --- O-grid blockMesh ---------------------------------------------------------
def _cylinder_blockmesh(spec: CylinderSpec) -> str:
    r = 0.5 * spec.diameter  # cylinder radius
    rr = spec.farfield_radius_diameters * spec.diameter  # outer radius
    span = spec.span
    # 4 sector boundaries at 45/135/225/315 deg so the wake axis (0/180) sits
    # mid-block. inner V0..V3 on the cylinder, outer V4..V7 on the far field.
    angles = [45.0, 135.0, 225.0, 315.0]
    inner = [(r * math.cos(math.radians(a)), r * math.sin(math.radians(a))) for a in angles]
    outer = [(rr * math.cos(math.radians(a)), rr * math.sin(math.radians(a))) for a in angles]
    base = inner + outer  # 0..3 inner, 4..7 outer
    nb = len(base)  # 8
    verts = [pt(x, y, 0.0) for x, y in base] + [pt(x, y, span) for x, y in base]

    g_rad = expansion(rr - r, spec.n_radial, spec.radial_first_cell * spec.diameter)
    na, nrad = spec.n_azimuthal, spec.n_radial

    # 4 sector blocks. Bottom face (z=0) wound CCW from +z:
    # inner_i -> inner_{i+1} (azimuthal) -> outer_{i+1} -> outer_i (radial out/back).
    # counts: (azimuthal, radial, span); radial graded toward the cylinder.
    def _verts(a: int, b: int, c: int, d: int) -> str:
        return " ".join(str(v) for v in (a, b, c, d, a + nb, b + nb, c + nb, d + nb))

    blocks = []
    for i in range(4):
        j = (i + 1) % 4
        # Bottom face (inner_i, outer_i, outer_j, inner_j) is CCW viewed from +z
        # (positive cell volume). v0->v1 is RADIAL (n_radial cells, graded toward
        # the cylinder); v1->v2 is AZIMUTHAL (n_azimuthal).
        blocks.append(
            f"    hex ({_verts(i, 4 + i, 4 + j, j)}) ({nrad} {na} 1) "
            f"simpleGrading ({g_rad:.8g} 1 1)"
        )

    # Arc edges: midpoint of each 90-deg arc, on the cylinder (r) and far field (rr),
    # at z=0 and z=span. blockMesh `arc v1 v2 (mx my mz)`.
    def arc(v1: int, v2: int, radius: float, mid_angle: float, z: float) -> str:
        mx = radius * math.cos(math.radians(mid_angle))
        my = radius * math.sin(math.radians(mid_angle))
        return f"    arc {v1} {v2} ({mx:.8f} {my:.8f} {z:.8f})"

    edges = []
    for i in range(4):
        j = (i + 1) % 4
        mid = angles[i] + 45.0  # midpoint of the i->i+1 sector
        edges.append(arc(i, j, r, mid, 0.0))  # inner, z=0
        edges.append(arc(4 + i, 4 + j, rr, mid, 0.0))  # outer, z=0
        edges.append(arc(i + nb, j + nb, r, mid, span))  # inner, z=span
        edges.append(arc(4 + i + nb, 4 + j + nb, rr, mid, span))  # outer, z=span

    def face(a: int, b: int) -> str:
        return f"({a} {b} {b + nb} {a + nb})"

    cyl = " ".join(face(i, (i + 1) % 4) for i in range(4))
    far = " ".join(face(4 + i, 4 + (i + 1) % 4) for i in range(4))
    # 2D: each block's z=0 quad is `front`, z=span is `back`.
    z0 = " ".join(f"({i} {4 + i} {4 + (i + 1) % 4} {(i + 1) % 4})" for i in range(4))
    zspan = " ".join(
        f"({i + nb} {4 + i + nb} {4 + (i + 1) % 4 + nb} {(i + 1) % 4 + nb})" for i in range(4)
    )

    boundary = f"""    cylinder
    {{
        type wall;
        faces ( {cyl} );
    }}
    farfield
    {{
        type patch;
        faces ( {far} );
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


# --- transient dictionaries ---------------------------------------------------
def _controldict(spec: CylinderSpec) -> str:
    # Convective time t* = t U / D; U_INF=1 so t = t* * D.
    d_over_u = spec.diameter / U_INF
    end_time = spec.end_time_convective * d_over_u
    write_interval = spec.write_interval_convective * d_over_u
    a_ref = spec.diameter * spec.span  # frontal area per unit span
    # Moving cases add a `forces` FO so the loader can report the cycle-mean
    # pressure/viscous drag split (the static shedding case does not need it).
    forces_fo = ""
    if spec.motion is not None:
        forces_fo = f"""
    forces1
    {{
        type            forces;
        libs            (forces);
        writeControl    timeStep;
        writeInterval   1;
        patches         (cylinder);
        rho             rhoInf;
        rhoInf          {RHO_INF};
        CofR            (0 0 0);
    }}"""
    return (
        header("dictionary", "controlDict")
        + f"""
application     pimpleFoam;
startFrom       startTime;
startTime       0;
stopAt          endTime;
endTime         {end_time:.8g};
deltaT          {0.1 * spec.radial_first_cell * spec.diameter:.8g};
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
        patches         (cylinder);
        rho             rhoInf;
        rhoInf          {RHO_INF};
        magUInf         {U_INF};
        lRef            {spec.diameter};
        Aref            {a_ref};
        dragDir         (1 0 0);
        liftDir         (0 1 0);
        CofR            (0 0 0);
        pitchAxis       (0 0 1);
    }}{forces_fo}
}}
"""
    )


def _fields(spec: CylinderSpec) -> dict[str, str]:
    a = math.radians(spec.inflow_angle_deg)  # small tilt seeds shedding
    u_vec = f"({U_INF * math.cos(a):.8f} {U_INF * math.sin(a):.8f} 0)"
    # A moving wall imposes no-slip in the moving frame (movingWallVelocity); a static
    # wall is plain noSlip. Getting this wrong silently biases the forces (Stage-11 risk).
    wall_u = (
        "        type movingWallVelocity;\n        value uniform (0 0 0);"
        if spec.motion is not None
        else "        type noSlip;"
    )

    def field(obj: str, cls: str, dims: str, internal: str, free: str, wall: str) -> str:
        return (
            header(cls, obj)
            + f"""
dimensions      {dims};
internalField   uniform {internal};

boundaryField
{{
    cylinder
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

    return {
        "U": field(
            "U",
            "volVectorField",
            "[0 1 -1 0 0 0 0]",
            u_vec,
            f"        type freestream;\n        freestreamValue uniform {u_vec};",
            wall_u,
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


def write_cylinder_case(spec: CylinderSpec, dest: Path) -> None:
    """Write a complete transient OpenFOAM case for the cylinder under `dest`."""
    system = dest / "system"
    constant = dest / "constant"
    zero = dest / "0"
    for d in (system, constant, zero):
        d.mkdir(parents=True, exist_ok=True)

    nu = flow_state(
        reynolds=spec.reynolds,
        ref_length=spec.diameter,
        turbulence_intensity=0.001,  # unused (laminar) but flow_state requires it
    )["nu"]
    (system / "blockMeshDict").write_text(_cylinder_blockmesh(spec), encoding="utf-8")
    (system / "controlDict").write_text(_controldict(spec), encoding="utf-8")
    (system / "fvSchemes").write_text(transient_fvschemes(), encoding="utf-8")
    (system / "fvSolution").write_text(
        transient_fvsolution(cell_displacement=spec.motion is not None), encoding="utf-8"
    )
    (constant / "transportProperties").write_text(transport_properties(nu), encoding="utf-8")
    (constant / "turbulenceProperties").write_text(
        turbulence_properties(spec.turbulence_model), encoding="utf-8"
    )
    for name, text in _fields(spec).items():
        (zero / name).write_text(text, encoding="utf-8")

    # Moving-mesh (morphing) case: the dynamicMeshDict + the pointDisplacement BC that
    # drives the cylinder wall (the far field stays fixed, the mesh deforms in between).
    if spec.motion is not None:
        (constant / "dynamicMeshDict").write_text(
            dynamic_mesh_dict(moving_patch="cylinder"), encoding="utf-8"
        )
        (zero / "pointDisplacement").write_text(
            point_displacement_field(
                moving_patch="cylinder",
                motion=spec.motion,
                fixed_patches=["farfield"],
                empty_patches=["front", "back"],
            ),
            encoding="utf-8",
        )
