"""Render OpenFOAM cases for the NASA TMR verification geometries.

`write_tmr_case` dispatches on the `TMRCaseSpec` discriminator:

* **flat plate** — two structured blocks (an upstream symmetry run, then the
  no-slip plate), a flat rectangular domain;
* **2D bump** — three blocks (inlet / bump / outlet), the lower wall a
  `polyLine` following the analytic bump.

Both write a `wallShearStress` field function object and a `surfaces` sampler
that dumps raw `(x y z field...)` files on the wall patch — that columnar
output is what `aero.adapters.openfoam.fields.extract_wall_distributions`
reads to build the Cf / Cp distributions the V&V harness compares.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
from numpy.typing import NDArray

from aero.adapters.openfoam._foam_common import (
    U_INF,
    expansion,
    flow_state,
    fvschemes,
    fvsolution,
    header,
    pt,
    transport_properties,
    turbulence_properties,
)
from aero.adapters.openfoam.tmr_geometry import bump_lower_wall
from aero.adapters.openfoam.tmr_specs import Bump2DSpec, FlatPlateSpec, TMRCaseSpec

# Surface-sampling function objects shared by both TMR geometries. `raw` format
# writes one file per field under postProcessing/sampleWall/<time>/.
_SAMPLING_FUNCTIONS = """
functions
{
    wallShearStress1
    {
        type            wallShearStress;
        libs            (fieldFunctionObjects);
        patches         (wall);
        writeControl    writeTime;
    }
    sampleWall
    {
        type            surfaces;
        libs            (sampling);
        writeControl    writeTime;
        surfaceFormat   raw;
        fields          (p wallShearStress);
        surfaces
        {
            wall
            {
                type        patch;
                patches     (wall);
                interpolate false;
            }
        }
    }
}
"""


def _controldict(end_time: int) -> str:
    return (
        header("dictionary", "controlDict")
        + f"""
application     simpleFoam;
startFrom       startTime;
startTime       0;
stopAt          endTime;
endTime         {end_time};
deltaT          1;
writeControl    timeStep;
writeInterval   {end_time};
purgeWrite      2;
writeFormat     ascii;
writePrecision  8;
runTimeModifiable false;
"""
        + _SAMPLING_FUNCTIONS
    )


def _field(obj: str, cls: str, dims: str, internal: str, patch_bcs: dict[str, str]) -> str:
    """A field file with an explicit boundary condition per patch."""
    blocks = []
    for patch, bc in patch_bcs.items():
        blocks.append(f"    {patch}\n    {{\n{bc}\n    }}")
    return (
        header(cls, obj)
        + f"""
dimensions      {dims};
internalField   uniform {internal};

boundaryField
{{
"""
        + "\n".join(blocks)
        + "\n}\n"
    )


def _tmr_fields(
    *,
    reynolds: float,
    ref_length: float,
    turbulence_intensity: float,
    wall_patches: list[str],
    slip_patch: str,
    slip_type: str,
) -> dict[str, str]:
    """Field files for a TMR case.

    `farfield` is a freestream patch (inlet/top/outlet); `wall_patches` are
    no-slip viscous walls; `slip_patch` is the symmetry patch (`slip_type` is
    `symmetry`). Every field carries an explicit BC for every patch.
    """
    st = flow_state(
        reynolds=reynolds,
        ref_length=ref_length,
        turbulence_intensity=turbulence_intensity,
    )
    k, omega, nut = st["k"], st["omega"], st["nut"]
    u_vec = f"({U_INF:.8f} 0 0)"

    def per_field(free: str, wall: str, internal: str, obj: str, cls: str, dims: str) -> str:
        bcs = {"farfield": free, slip_patch: f"        type {slip_type};"}
        for wp in wall_patches:
            bcs[wp] = wall
        bcs["front"] = "        type empty;"
        bcs["back"] = "        type empty;"
        return _field(obj, cls, dims, internal, bcs)

    return {
        "U": per_field(
            f"        type freestream;\n        freestreamValue uniform {u_vec};",
            "        type noSlip;",
            u_vec,
            "U",
            "volVectorField",
            "[0 1 -1 0 0 0 0]",
        ),
        "p": per_field(
            "        type freestreamPressure;\n        freestreamValue uniform 0;",
            "        type zeroGradient;",
            "0",
            "p",
            "volScalarField",
            "[0 2 -2 0 0 0 0]",
        ),
        "nut": per_field(
            f"        type freestream;\n        freestreamValue uniform {nut:.8g};",
            # Wall-resolved (y+ < 1): low-Re wall treatment, not a log-law function.
            "        type nutLowReWallFunction;\n        value uniform 0;",
            f"{nut:.8g}",
            "nut",
            "volScalarField",
            "[0 2 -1 0 0 0 0]",
        ),
        "k": per_field(
            f"        type inletOutlet;\n        inletValue uniform {k:.8g};"
            f"\n        value uniform {k:.8g};",
            f"        type kqRWallFunction;\n        value uniform {k:.8g};",
            f"{k:.8g}",
            "k",
            "volScalarField",
            "[0 2 -2 0 0 0 0]",
        ),
        "omega": per_field(
            f"        type inletOutlet;\n        inletValue uniform {omega:.8g};"
            f"\n        value uniform {omega:.8g};",
            f"        type omegaWallFunction;\n        value uniform {omega:.8g};",
            f"{omega:.8g}",
            "omega",
            "volScalarField",
            "[0 0 -1 0 0 0 0]",
        ),
    }


# --- flat plate ---------------------------------------------------------------
def _flat_plate_blockmesh(spec: FlatPlateSpec) -> str:
    il, pl, h, span = spec.inlet_length, spec.plate_length, spec.domain_height, spec.span
    base = [
        (-il, 0.0),  # 0
        (0.0, 0.0),  # 1  leading edge
        (pl, 0.0),  # 2
        (-il, h),  # 3
        (0.0, h),  # 4
        (pl, h),  # 5
    ]
    verts = [pt(x, y, 0.0) for x, y in base] + [pt(x, y, span) for x, y in base]
    g_eta = expansion(h, spec.n_normal, spec.first_cell_height)
    nrm, ni, nsw = spec.n_normal, spec.n_inlet, spec.n_streamwise
    # Cluster the plate's streamwise cells toward the leading edge: Cf ~ x^-0.2
    # is steepest there, and a uniform spacing under-resolves it (Cf ran ~16%
    # high at x=0.05 with uniform cells). First cell ~ 1/8 of the uniform size.
    g_le = expansion(pl, nsw, pl / nsw / 8.0)
    blocks = [
        f"    hex (0 1 4 3 6 7 10 9) ({ni} {nrm} 1) simpleGrading (1 {g_eta:.8g} 1)",
        f"    hex (1 2 5 4 7 8 11 10) ({nsw} {nrm} 1) simpleGrading ({g_le:.8g} {g_eta:.8g} 1)",
    ]

    def face(a: int, b: int) -> str:
        return f"({a} {b} {b + 6} {a + 6})"

    boundary = f"""    wall
    {{
        type wall;
        faces ( {face(1, 2)} );
    }}
    symmetry
    {{
        type symmetryPlane;
        faces ( {face(0, 1)} );
    }}
    farfield
    {{
        type patch;
        faces ( {face(0, 3)} {face(2, 5)} {face(3, 4)} {face(4, 5)} );
    }}
    front
    {{
        type empty;
        faces ( (0 1 4 3) (1 2 5 4) );
    }}
    back
    {{
        type empty;
        faces ( (6 7 10 9) (7 8 11 10) );
    }}"""
    verts_block = "\n".join(f"    {v}" for v in verts)
    return (
        header("dictionary", "blockMeshDict")
        + "\nscale 1;\n\n"
        + f"vertices\n(\n{verts_block}\n);\n\n"
        + "blocks\n(\n"
        + "\n".join(blocks)
        + "\n);\n\n"
        + "edges\n(\n);\n\n"
        + f"boundary\n(\n{boundary}\n);\n\n"
        + "mergePatchPairs ( );\n"
    )


# --- 2D bump ------------------------------------------------------------------
def _bump_blockmesh(spec: Bump2DSpec) -> str:
    il, bl, ol = spec.inlet_length, spec.bump_length, spec.outlet_length
    h, span = spec.domain_height, spec.span
    base = [
        (-il, 0.0),  # 0
        (0.0, 0.0),  # 1  bump start
        (bl, 0.0),  # 2  bump end
        (bl + ol, 0.0),  # 3
        (-il, h),  # 4
        (0.0, h),  # 5
        (bl, h),  # 6
        (bl + ol, h),  # 7
    ]
    verts = [pt(x, y, 0.0) for x, y in base] + [pt(x, y, span) for x, y in base]
    g_eta = expansion(h, spec.n_normal, spec.first_cell_height)
    nrm = spec.n_normal
    blocks = [
        f"    hex (0 1 5 4 8 9 13 12) ({spec.n_inlet} {nrm} 1) simpleGrading (1 {g_eta:.8g} 1)",
        f"    hex (1 2 6 5 9 10 14 13) ({spec.n_bump} {nrm} 1) simpleGrading (1 {g_eta:.8g} 1)",
        f"    hex (2 3 7 6 10 11 15 14) ({spec.n_outlet} {nrm} 1) simpleGrading (1 {g_eta:.8g} 1)",
    ]

    # The bump lower wall is a polyLine edge (1, 2), interior points only.
    wall_pts = bump_lower_wall(
        spec.n_bump + 1,
        x_start=0.0,
        x_end=bl,
        height=spec.bump_height,
        bump_length=spec.bump_length,
    )

    def poly(v1: int, v2: int, pts: NDArray[np.float64], z: float) -> str:
        body = "\n".join(f"            {pt(float(x), float(y), z)}" for x, y in pts)
        return f"    polyLine {v1} {v2}\n        (\n{body}\n        )"

    edges = [
        poly(1, 2, wall_pts[1:-1], 0.0),
        poly(9, 10, wall_pts[1:-1], span),
    ]

    def face(a: int, b: int) -> str:
        return f"({a} {b} {b + 8} {a + 8})"

    boundary = f"""    wall
    {{
        type wall;
        faces ( {face(0, 1)} {face(1, 2)} {face(2, 3)} );
    }}
    topSym
    {{
        type symmetryPlane;
        faces ( {face(4, 5)} {face(5, 6)} {face(6, 7)} );
    }}
    farfield
    {{
        type patch;
        faces ( {face(0, 4)} {face(3, 7)} );
    }}
    front
    {{
        type empty;
        faces ( (0 1 5 4) (1 2 6 5) (2 3 7 6) );
    }}
    back
    {{
        type empty;
        faces ( (8 9 13 12) (9 10 14 13) (10 11 15 14) );
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


def write_tmr_case(spec: TMRCaseSpec, dest: Path) -> None:
    """Write a complete OpenFOAM case for a TMR geometry under `dest`."""
    system = dest / "system"
    constant = dest / "constant"
    zero = dest / "0"
    for d in (system, constant, zero):
        d.mkdir(parents=True, exist_ok=True)

    if spec.geometry == "flat_plate":
        blockmesh = _flat_plate_blockmesh(spec)
        ref_length = spec.plate_length
        fields = _tmr_fields(
            reynolds=spec.reynolds,
            ref_length=ref_length,
            turbulence_intensity=spec.turbulence_intensity,
            wall_patches=["wall"],
            slip_patch="symmetry",
            slip_type="symmetryPlane",
        )
    elif spec.geometry == "bump_2d":
        blockmesh = _bump_blockmesh(spec)
        ref_length = spec.ref_length
        fields = _tmr_fields(
            reynolds=spec.reynolds,
            ref_length=ref_length,
            turbulence_intensity=spec.turbulence_intensity,
            wall_patches=["wall"],
            slip_patch="topSym",
            slip_type="symmetryPlane",
        )
    else:  # pragma: no cover — the discriminated union forbids anything else
        raise ValueError(f"unknown TMR geometry: {spec.geometry!r}")

    nu = flow_state(
        reynolds=spec.reynolds,
        ref_length=ref_length,
        turbulence_intensity=spec.turbulence_intensity,
    )["nu"]
    (system / "blockMeshDict").write_text(blockmesh, encoding="utf-8")
    (system / "controlDict").write_text(_controldict(spec.end_time), encoding="utf-8")
    (system / "fvSchemes").write_text(fvschemes(), encoding="utf-8")
    (system / "fvSolution").write_text(fvsolution(), encoding="utf-8")
    (constant / "transportProperties").write_text(transport_properties(nu), encoding="utf-8")
    (constant / "turbulenceProperties").write_text(
        turbulence_properties(spec.turbulence_model), encoding="utf-8"
    )
    for name, text in fields.items():
        (zero / name).write_text(text, encoding="utf-8")
