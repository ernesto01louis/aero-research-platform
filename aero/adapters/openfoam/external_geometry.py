"""External-geometry (ingested STL) case writer — quasi-2D snappyHexMesh (Stage 18).

Composes a complete OpenFOAM case for an ingested external surface in a rectangular
channel: a uniform one-cell-thick background `blockMeshDict` (cubic cells, `empty`
front/back), the STL under `constant/triSurface/`, `surfaceFeatureExtractDict`,
`snappyHexMeshDict` (castellate + snap at background resolution, optional layers), and
laminar steady (`simpleFoam`) or transient (`pimpleFoam`) controls with a `forceCoeffs`
function object on the carved body patch.

The quasi-2D approach (ADR-034, F-gates): snappy cannot anisotropically refine, so the
background is generated at TARGET resolution and snappy does **no volumetric
refinement** — the slab stays exactly one cell thick and, after `flattenMesh` restores
front/back planarity, the `empty` patches make the case genuinely 2D. The fallback
ladder therefore steps the *background cell size* and the *layer count*, never the
mesh-quality thresholds.

Provenance: the spec's `surface_sha256` (from `IngestedGeometry`) enters `config_hash`;
`write_external_geometry_case` verifies the referenced STL's actual digest against it
and fails loud on mismatch — a case can never silently mesh a different surface than
the one that passed the ingestion gate.
"""

from __future__ import annotations

import hashlib
import shutil
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from aero.adapters.openfoam._foam_common import (
    fvschemes,
    fvsolution,
    header,
    pt,
    transient_fvschemes,
    transient_fvsolution,
    transport_properties,
    turbulence_properties,
)
from aero.geometry import GeometryError

_STRICT = ConfigDict(
    extra="forbid",
    frozen=True,
    str_strip_whitespace=True,
    validate_assignment=True,
    validate_default=True,
)

__all__ = ["ExternalGeometrySpec", "write_external_geometry_case"]

_SHA256_RE = r"^[0-9a-f]{64}$"


class ExternalGeometrySpec(BaseModel):
    """A quasi-2D channel-flow case around an ingested external surface.

    Defaults are the Turek-Hron benchmark fluid setup (channel 2.5 x 0.41,
    parabolic inlet, rho=1000, nu=1e-3); the geometry itself always comes from the
    referenced STL — nothing here analytically generates a shape.
    """

    model_config = _STRICT

    geometry: Literal["external"] = "external"
    name: str = Field(..., min_length=1, description="Case name.")

    # --- the ingested surface -------------------------------------------------
    surface_source: str = Field(
        ...,
        min_length=1,
        description="Host path of the ingestion-gated STL (DVC-tracked).",
    )
    surface_name: str = Field(
        default="body",
        min_length=1,
        pattern=r"^[A-Za-z][A-Za-z0-9_]*$",
        description="triSurface base name = the carved wall patch name.",
    )
    surface_sha256: str = Field(
        ...,
        pattern=_SHA256_RE,
        description="SHA-256 of the STL bytes (from IngestedGeometry) — provenance-bearing.",
    )

    # --- domain + background mesh (quasi-2D slab) -----------------------------
    domain_min: tuple[float, float] = Field(
        default=(0.0, 0.0), description="Channel (x, y) lower corner."
    )
    domain_max: tuple[float, float] = Field(
        default=(2.5, 0.41), description="Channel (x, y) upper corner."
    )
    base_cell_size: float = Field(
        default=0.005,
        gt=0.0,
        description="Uniform background cell size h (cubic cells; slab is one h thick).",
    )
    location_in_mesh: tuple[float, float] = Field(
        default=(2.2, 0.2),
        description="(x, y) point inside the flow region, outside the body.",
    )

    # --- snappy controls ------------------------------------------------------
    n_surface_layers: int = Field(
        default=0, ge=0, description="Prism layers on the body patch (0 = none)."
    )
    layer_expansion: float = Field(default=1.2, gt=1.0)
    final_layer_thickness_rel: float = Field(
        default=0.4, gt=0.0, le=1.0, description="Final layer thickness relative to h."
    )
    resolve_feature_angle_deg: float = Field(default=30.0, gt=0.0)
    feature_included_angle_deg: float = Field(
        default=150.0, gt=0.0, description="surfaceFeatureExtract includedAngle."
    )

    # --- flow (Turek-Hron fluid defaults) -------------------------------------
    u_mean: float = Field(default=1.0, gt=0.0, description="Mean inlet speed U-bar.")
    inlet_profile: Literal["parabolic", "uniform"] = Field(default="parabolic")
    inlet_bc: Literal["expr", "mapped"] = Field(
        default="expr",
        description="Parabolic-profile mechanism: exprFixedValue or "
        "timeVaryingMappedFixedValue boundaryData (no-compiler fallback).",
    )
    nu: float = Field(default=1e-3, gt=0.0, description="Kinematic viscosity.")
    rho: float = Field(default=1000.0, gt=0.0, description="Density (forceCoeffs rhoInf).")
    ref_length: float = Field(
        default=0.1, gt=0.0, description="forceCoeffs lRef (cylinder diameter)."
    )

    # --- solve controls -------------------------------------------------------
    transient: bool = Field(default=False)
    steady_iterations: int = Field(default=5000, gt=0)
    end_time: float = Field(default=15.0, gt=0.0, description="Transient end time [s].")
    write_interval: float = Field(
        default=0.005, gt=0.0, description="Force-sample / field-write interval [s]."
    )
    max_courant: float = Field(default=0.8, gt=0.0)

    @model_validator(mode="after")
    def _domain_ordered(self) -> ExternalGeometrySpec:
        if not (
            self.domain_min[0] < self.domain_max[0] and self.domain_min[1] < self.domain_max[1]
        ):
            raise ValueError("domain_min must be strictly below domain_max componentwise")
        return self

    @property
    def slab_thickness(self) -> float:
        """One background cell — the quasi-2D slab depth."""
        return self.base_cell_size

    def n_cells_background(self) -> tuple[int, int]:
        """(nx, ny) background cell counts at `base_cell_size`."""
        nx = max(1, round((self.domain_max[0] - self.domain_min[0]) / self.base_cell_size))
        ny = max(1, round((self.domain_max[1] - self.domain_min[1]) / self.base_cell_size))
        return nx, ny


# --- blockMesh background slab ------------------------------------------------
def _blockmesh(spec: ExternalGeometrySpec) -> str:
    (x0, y0), (x1, y1) = spec.domain_min, spec.domain_max
    dz = spec.slab_thickness
    nx, ny = spec.n_cells_background()
    verts = [
        pt(x0, y0, 0.0),
        pt(x1, y0, 0.0),
        pt(x1, y1, 0.0),
        pt(x0, y1, 0.0),
        pt(x0, y0, dz),
        pt(x1, y0, dz),
        pt(x1, y1, dz),
        pt(x0, y1, dz),
    ]
    verts_block = "\n".join(f"    {v}" for v in verts)
    return (
        header("dictionary", "blockMeshDict")
        + "\nscale 1;\n\n"
        + f"vertices\n(\n{verts_block}\n);\n\n"
        + f"blocks\n(\n    hex (0 1 2 3 4 5 6 7) ({nx} {ny} 1) simpleGrading (1 1 1)\n);\n\n"
        + "edges\n(\n);\n\n"
        + """boundary
(
    inlet
    {
        type patch;
        faces ( (0 4 7 3) );
    }
    outlet
    {
        type patch;
        faces ( (1 2 6 5) );
    }
    walls
    {
        type wall;
        faces ( (0 1 5 4) (3 7 6 2) );
    }
    frontAndBack
    {
        type empty;
        faces ( (0 3 2 1) (4 5 6 7) );
    }
);

mergePatchPairs ( );
"""
    )


# --- surfaceFeatureExtract + snappy -------------------------------------------
def _surface_feature_extract(spec: ExternalGeometrySpec) -> str:
    return (
        header("dictionary", "surfaceFeatureExtractDict")
        + f"""
{spec.surface_name}.stl
{{
    extractionMethod    extractFromSurface;
    includedAngle       {spec.feature_included_angle_deg:.8g};
    writeObj            no;
}}
"""
    )


def _snappy(spec: ExternalGeometrySpec) -> str:
    dz = spec.slab_thickness
    loc = f"({spec.location_in_mesh[0]:.8g} {spec.location_in_mesh[1]:.8g} {0.5 * dz:.8g})"
    add_layers = spec.n_surface_layers > 0
    layers_block = ""
    if add_layers:
        layers_block = f"""
    layers
    {{
        {spec.surface_name}
        {{
            nSurfaceLayers {spec.n_surface_layers};
        }}
    }}
    relativeSizes       true;
    expansionRatio      {spec.layer_expansion:.8g};
    finalLayerThickness {spec.final_layer_thickness_rel:.8g};
    minThickness        0.1;
    nGrow               0;
    featureAngle        130;
    slipFeatureAngle    30;
    nRelaxIter          5;
    nSmoothSurfaceNormals 1;
    nSmoothNormals      3;
    nSmoothThickness    10;
    maxFaceThicknessRatio 0.5;
    maxThicknessToMedialRatio 0.3;
    minMedianAxisAngle  90;
    nBufferCellsNoExtrude 0;
    nLayerIter          50;
"""
    return (
        header("dictionary", "snappyHexMeshDict")
        + f"""
castellatedMesh true;
snap            true;
addLayers       {"true" if add_layers else "false"};

geometry
{{
    {spec.surface_name}.stl
    {{
        type triSurfaceMesh;
        name {spec.surface_name};
    }}
}}

castellatedMeshControls
{{
    maxLocalCells       2000000;
    maxGlobalCells      4000000;
    minRefinementCells  0;
    nCellsBetweenLevels 3;

    features
    (
        {{
            file "{spec.surface_name}.eMesh";
            level 0;
        }}
    );

    // No volumetric refinement: the background is already at target resolution,
    // which is what keeps the slab one cell thick (quasi-2D — module docstring).
    refinementSurfaces
    {{
        {spec.surface_name}
        {{
            level (0 0);
            patchInfo
            {{
                type wall;
            }}
        }}
    }}
    resolveFeatureAngle {spec.resolve_feature_angle_deg:.8g};
    refinementRegions   {{ }}
    locationInMesh      {loc};
    allowFreeStandingZoneFaces true;
}}

snapControls
{{
    nSmoothPatch        3;
    tolerance           2.0;
    nSolveIter          30;
    nRelaxIter          5;
    nFeatureSnapIter    10;
    implicitFeatureSnap false;
    explicitFeatureSnap true;
    multiRegionFeatureSnap false;
}}

addLayersControls
{{{layers_block}
}}

meshQualityControls
{{
    maxNonOrtho         65;
    maxBoundarySkewness 20;
    maxInternalSkewness 4;
    maxConcave          80;
    minVol              1e-13;
    minTetQuality       1e-15;
    minArea             -1;
    minTwist            0.02;
    minDeterminant      0.001;
    minFaceWeight       0.02;
    minVolRatio         0.01;
    minTriangleTwist    -1;
    nSmoothScale        4;
    errorReduction      0.75;
    relaxed
    {{
        maxNonOrtho     75;
    }}
}}

writeFlags          ( scalarLevels );
mergeTolerance      1e-6;
"""
    )


# --- controls ------------------------------------------------------------------
def _force_coeffs_fo(spec: ExternalGeometrySpec) -> str:
    a_ref = spec.ref_length * spec.slab_thickness  # 2D: dz cancels vs the slab forces
    return f"""
functions
{{
    forceCoeffs1
    {{
        type            forceCoeffs;
        libs            (forces);
        writeControl    timeStep;
        writeInterval   1;
        patches         ({spec.surface_name});
        rho             rhoInf;
        rhoInf          {spec.rho:.8g};
        magUInf         {spec.u_mean:.8g};
        lRef            {spec.ref_length:.8g};
        Aref            {a_ref:.8g};
        dragDir         (1 0 0);
        liftDir         (0 1 0);
        CofR            (0 0 0);
        pitchAxis       (0 0 1);
    }}
}}
"""


def _controldict(spec: ExternalGeometrySpec) -> str:
    if spec.transient:
        body = f"""
application     pimpleFoam;
startFrom       startTime;
startTime       0;
stopAt          endTime;
endTime         {spec.end_time:.8g};
deltaT          {0.1 * spec.write_interval:.8g};
writeControl    adjustableRunTime;
writeInterval   {max(0.5, spec.end_time / 10.0):.8g};
purgeWrite      3;
writeFormat     ascii;
writePrecision  8;
runTimeModifiable false;
adjustTimeStep  yes;
maxCo           {spec.max_courant:.8g};
maxDeltaT       {spec.write_interval:.8g};
"""
    else:
        body = f"""
application     simpleFoam;
startFrom       startTime;
startTime       0;
stopAt          endTime;
endTime         {spec.steady_iterations};
deltaT          1;
writeControl    timeStep;
writeInterval   {spec.steady_iterations};
purgeWrite      2;
writeFormat     ascii;
writePrecision  8;
runTimeModifiable false;
"""
    return header("dictionary", "controlDict") + body + _force_coeffs_fo(spec)


# --- 0/ fields ------------------------------------------------------------------
def _parabolic_expr(spec: ExternalGeometrySpec) -> str:
    (_, y0), (_, y1) = spec.domain_min, spec.domain_max
    h = y1 - y0
    # U(y) = 6 U-bar (y-y0)(y1-y) / H^2  — max 1.5 U-bar at mid-channel (Turek-Hron eq. 10).
    return (
        f'"vector(6*{spec.u_mean:.8g}*(pos().y()-{y0:.8g})*({y1:.8g}-pos().y())'
        f'/({h:.8g}*{h:.8g}), 0, 0)"'
    )


def _inlet_u_bc(spec: ExternalGeometrySpec) -> str:
    if spec.inlet_profile == "uniform":
        return f"        type fixedValue;\n        value uniform ({spec.u_mean:.8g} 0 0);"
    if spec.inlet_bc == "expr":
        return (
            "        type exprFixedValue;\n"
            f"        valueExpr {_parabolic_expr(spec)};\n"
            "        value uniform (0 0 0);"
        )
    return (
        "        type timeVaryingMappedFixedValue;\n"
        "        offset (0 0 0);\n"
        "        setAverage off;\n"
        "        value uniform (0 0 0);"
    )


def _fields(spec: ExternalGeometrySpec) -> dict[str, str]:
    def field(obj: str, cls: str, dims: str, internal: str, inlet: str, outlet: str) -> str:
        return (
            header(cls, obj)
            + f"""
dimensions      {dims};
internalField   uniform {internal};

boundaryField
{{
    inlet
    {{
{inlet}
    }}
    outlet
    {{
{outlet}
    }}
    walls
    {{
{{WALL}}
    }}
    {spec.surface_name}
    {{
{{WALL}}
    }}
    frontAndBack {{ type empty; }}
}}
"""
        )

    u = field(
        "U",
        "volVectorField",
        "[0 1 -1 0 0 0 0]",
        "(0 0 0)",
        _inlet_u_bc(spec),
        "        type inletOutlet;\n        inletValue uniform (0 0 0);\n"
        "        value uniform (0 0 0);",
    ).replace("{WALL}", "        type noSlip;")
    p = field(
        "p",
        "volScalarField",
        "[0 2 -2 0 0 0 0]",
        "0",
        "        type zeroGradient;",
        "        type fixedValue;\n        value uniform 0;",
    ).replace("{WALL}", "        type zeroGradient;")
    return {"U": u, "p": p}


def _mapped_inlet_boundary_data(spec: ExternalGeometrySpec, constant: Path) -> None:
    """Discretized parabolic profile for the no-compiler fallback BC."""
    (x0, y0), (_, y1) = spec.domain_min, spec.domain_max
    h = y1 - y0
    _, ny = spec.n_cells_background()
    n_samples = 4 * ny  # oversampled; the BC maps by position
    bd = constant / "boundaryData" / "inlet"
    t0 = bd / "0"
    t0.mkdir(parents=True, exist_ok=True)
    zc = 0.5 * spec.slab_thickness
    pts, vals = [], []
    for j in range(n_samples + 1):
        y = y0 + h * j / n_samples
        u = 6.0 * spec.u_mean * (y - y0) * (y1 - y) / (h * h)
        pts.append(f"({x0:.10g} {y:.10g} {zc:.10g})")
        vals.append(f"({u:.10g} 0 0)")
    (bd / "points").write_text(f"{len(pts)}\n(\n" + "\n".join(pts) + "\n)\n", encoding="utf-8")
    (t0 / "U").write_text(f"{len(vals)}\n(\n" + "\n".join(vals) + "\n)\n", encoding="utf-8")


# --- the writer ------------------------------------------------------------------
def write_external_geometry_case(spec: ExternalGeometrySpec, dest: Path) -> None:
    """Write the complete case under `dest` (system/, constant/, 0/).

    Fails loud (`GeometryError`) if the referenced STL is missing or its SHA-256
    does not match `spec.surface_sha256` — the meshed surface must be byte-identical
    to the one that passed the ingestion gate.
    """
    source = Path(spec.surface_source)
    if not source.is_file():
        raise GeometryError(f"{source}: surface STL not found (did you `dvc pull`?)")
    actual = hashlib.sha256(source.read_bytes()).hexdigest()
    if actual != spec.surface_sha256:
        raise GeometryError(
            f"{source}: SHA-256 {actual[:12]}... does not match the ingestion-gated "
            f"digest {spec.surface_sha256[:12]}... — refusing to mesh a different surface"
        )

    system = dest / "system"
    constant = dest / "constant"
    zero = dest / "0"
    tri = constant / "triSurface"
    for d in (system, constant, zero, tri):
        d.mkdir(parents=True, exist_ok=True)

    shutil.copyfile(source, tri / f"{spec.surface_name}.stl")

    (system / "blockMeshDict").write_text(_blockmesh(spec), encoding="utf-8")
    (system / "surfaceFeatureExtractDict").write_text(
        _surface_feature_extract(spec), encoding="utf-8"
    )
    (system / "snappyHexMeshDict").write_text(_snappy(spec), encoding="utf-8")
    (system / "controlDict").write_text(_controldict(spec), encoding="utf-8")
    if spec.transient:
        (system / "fvSchemes").write_text(transient_fvschemes(), encoding="utf-8")
        (system / "fvSolution").write_text(transient_fvsolution(), encoding="utf-8")
    else:
        (system / "fvSchemes").write_text(fvschemes(), encoding="utf-8")
        (system / "fvSolution").write_text(fvsolution(), encoding="utf-8")
    (constant / "transportProperties").write_text(transport_properties(spec.nu), encoding="utf-8")
    (constant / "turbulenceProperties").write_text(
        turbulence_properties("laminar"), encoding="utf-8"
    )
    for name, text in _fields(spec).items():
        (zero / name).write_text(text, encoding="utf-8")
    if spec.inlet_profile == "parabolic" and spec.inlet_bc == "mapped":
        _mapped_inlet_boundary_data(spec, constant)
