"""Periodic-strip flat-plate mesh generator for the Bechert riblet replication.

Stage 5 domain: a rectangular box

    x ∈ [0, plate_length]            (streamwise; developing BL)
    y ∈ [0, n_pitches * pitch_s]     (spanwise; cyclic periodic)
    z ∈ [0, plate_height]            (wall-normal; bottom = wall, top = slip)

Two variants share the same writer:

* ``riblet_enabled=True``  — bottom wall is the Bechert blade-riblet surface
  built by extruding ``aero_research_platform.geometry.riblet.blade_strip_profile``
  along the streamwise axis. snappyHexMesh refines around it; addLayers grows
  prism layers tuned for y+ < 1 at the riblet tip.

* ``riblet_enabled=False`` — bottom wall is smooth (the blockMesh bottom face
  directly). snappyHexMeshDict is still written (with addLayers on the
  ``bottomWall`` patch) so the prism resolution matches the riblet case at
  identical Re_θ; ``write_all`` skips ``riblets.stl`` and the
  ``refinementSurfaces`` block.

The mesh-quality thresholds inherit Stage-4's proven SA-stable settings
(see ``meshing.airfoil_cmesh``).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from ..geometry.riblet import (
    BECHERT_BLADE_H_OVER_S,
    BECHERT_BLADE_T_OVER_S,
    BladeRibletSpec,
    blade_strip_profile,
)

_LOG = logging.getLogger(__name__)


@dataclass
class FlatPlateRibletMeshSpec:
    """Configuration for the periodic-strip flat-plate mesh (riblet or smooth)."""

    # Domain extents (chord units; chord=1 in the run).
    plate_length: float = 4.0
    plate_height: float = 1.0
    # Riblet pitch (chord units). For the Bechert sweep this is computed at
    # runtime from a target s+ via ``geometry.riblet.s_from_s_plus``.
    pitch_s: float = 0.002
    n_pitches_spanwise: int = 4   # ≥ 4 per Stage-5 brief
    h_over_s: float = BECHERT_BLADE_H_OVER_S
    t_over_s: float = BECHERT_BLADE_T_OVER_S
    # Background hex grid. n_y_per_pitch ≥ 16 per Stage-5 brief
    # (Bechert tip-sharpness — under-resolved tips kill the DR).
    n_x: int = 400
    n_y_per_pitch: int = 16
    n_z: int = 80
    grading_x: float = 1.0
    # z-grading > 1 packs cells toward the wall (z=0). With the spanwise
    # mesh already at O(2e-5) chord at n_y_per_pitch=16, grading_z=100
    # creates a first-cell-to-prism-stack jump of ~14x that addLayers
    # cannot bridge cleanly — yields max-aspect-ratio cells in the
    # thousands. 30 gives ~3e-3 chord at the wall, an order of magnitude
    # closer to the prism stack height (1.15^12 - 1)/0.15 * 1e-6 ≈ 4e-5.
    grading_z: float = 30.0
    # snappyHexMesh refinement around the riblet STL. At n_y_per_pitch=16
    # the BASE spanwise cell is already ~2e-5 chord (sub-pitch), so
    # surface refinement levels above ~4 over-refine: each level halves,
    # so level 4 = 1.25e-6 chord — well under the t/s=0.02 blade tip width.
    # Levels 7-8 (initial guess inherited from airfoil context) produced
    # a 17.3M-cell mesh that failed checkMesh with all cells under-determinant.
    surface_refinement_min: int = 3
    surface_refinement_max: int = 4
    # Prism inflation — flat plate has no STL+snappy degeneracy issues that
    # forced Stage-4's n_layers down to 5, so we run a fuller stack here.
    n_layers: int = 12
    first_layer_thickness: float = 1.0e-6
    expansion_ratio: float = 1.15
    # Drag-integration window (chord units). The BL develops over [0, ~1.5]
    # then statistics-stable; integrate Cd from [meas_window_x_start..end].
    meas_window_x_start: float = 2.0
    meas_window_x_end: float = 3.5
    # Toggle for the smooth-baseline twin run at matched Re_θ.
    riblet_enabled: bool = True
    expected_cells_lower_bound: int = 200_000

    @property
    def spanwise_extent(self) -> float:
        return self.n_pitches_spanwise * self.pitch_s

    def blade_spec(self) -> BladeRibletSpec:
        return BladeRibletSpec(
            pitch_s=self.pitch_s,
            h_over_s=self.h_over_s,
            t_over_s=self.t_over_s,
        )


def write_riblet_stl(spec: FlatPlateRibletMeshSpec, out_path: Path) -> Path:
    """Extrude the blade-riblet strip profile along x and write ASCII STL.

    The profile lives in the (y, z) plane and is extruded over the full
    streamwise extent ``[0, plate_length]``. Triangles wind CCW from outside.
    """
    if not spec.riblet_enabled:
        raise RuntimeError("write_riblet_stl called with riblet_enabled=False")
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    y, z = blade_strip_profile(spec.blade_spec(), n_pitches=spec.n_pitches_spanwise)
    x_lo = 0.0
    x_hi = spec.plate_length
    triangles: list[tuple[np.ndarray, np.ndarray, np.ndarray]] = []
    n = len(y)
    # Extrude side faces (each (y,z) segment becomes a quad → two triangles).
    for i in range(n - 1):
        p_lo_a = np.array([x_lo, y[i], z[i]])
        p_lo_b = np.array([x_lo, y[i + 1], z[i + 1]])
        p_hi_a = np.array([x_hi, y[i], z[i]])
        p_hi_b = np.array([x_hi, y[i + 1], z[i + 1]])
        triangles.append((p_lo_a, p_lo_b, p_hi_b))
        triangles.append((p_lo_a, p_hi_b, p_hi_a))
    lines = ["solid riblets"]
    for a, b, c in triangles:
        n_vec = np.cross(b - a, c - a)
        norm = float(np.linalg.norm(n_vec))
        if norm > 0:
            n_vec = n_vec / norm
        lines.append(f"  facet normal {n_vec[0]:.6e} {n_vec[1]:.6e} {n_vec[2]:.6e}")
        lines.append("    outer loop")
        lines.append(f"      vertex {a[0]:.6e} {a[1]:.6e} {a[2]:.6e}")
        lines.append(f"      vertex {b[0]:.6e} {b[1]:.6e} {b[2]:.6e}")
        lines.append(f"      vertex {c[0]:.6e} {c[1]:.6e} {c[2]:.6e}")
        lines.append("    endloop")
        lines.append("  endfacet")
    lines.append("endsolid riblets")
    out_path.write_text("\n".join(lines) + "\n")
    _LOG.info("Wrote riblet STL with %d triangles to %s", len(triangles), out_path)
    return out_path


def _of_header(class_name: str, obj_name: str) -> str:
    return (
        "FoamFile\n"
        "{\n"
        "    version     2.0;\n"
        "    format      ascii;\n"
        f"    class       {class_name};\n"
        f"    object      {obj_name};\n"
        "}\n"
    )


def write_block_mesh_dict(spec: FlatPlateRibletMeshSpec, out_path: Path) -> Path:
    """Write blockMeshDict with cyclic spanwise patches.

    Patches:
        inlet           (x = 0,  type patch)
        outlet          (x = Lx, type patch)
        top             (z = Lz, type patch)
        bottomWall      (z = 0,  type wall)
        frontPeriodic   (y = 0,  type cyclic, neighbourPatch backPeriodic)
        backPeriodic    (y = Ly, type cyclic, neighbourPatch frontPeriodic)
    """
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    Lx = spec.plate_length
    Ly = spec.spanwise_extent
    Lz = spec.plate_height
    n_y_total = spec.n_pitches_spanwise * spec.n_y_per_pitch
    body = (
        _of_header("dictionary", "blockMeshDict")
        + f"""
convertToMeters 1.0;

vertices
(
    ( 0    0   0   )    // 0
    ( {Lx} 0   0   )    // 1
    ( {Lx} {Ly} 0   )   // 2
    ( 0    {Ly} 0   )   // 3
    ( 0    0   {Lz} )   // 4
    ( {Lx} 0   {Lz} )   // 5
    ( {Lx} {Ly} {Lz} )  // 6
    ( 0    {Ly} {Lz} )  // 7
);

blocks
(
    hex (0 1 2 3 4 5 6 7)
    ( {spec.n_x} {n_y_total} {spec.n_z} )
    simpleGrading ( {spec.grading_x} 1 {spec.grading_z} )
);

edges
(
);

boundary
(
    inlet
    {{
        type patch;
        faces ( (0 4 7 3) );
    }}
    outlet
    {{
        type patch;
        faces ( (1 2 6 5) );
    }}
    top
    {{
        type patch;
        faces ( (4 5 6 7) );
    }}
    bottomWall
    {{
        type wall;
        faces ( (0 3 2 1) );
    }}
    frontPeriodic
    {{
        type cyclic;
        neighbourPatch backPeriodic;
        faces ( (0 1 5 4) );
    }}
    backPeriodic
    {{
        type cyclic;
        neighbourPatch frontPeriodic;
        faces ( (3 7 6 2) );
    }}
);

mergePatchPairs
(
);
"""
    )
    out_path.write_text(body)
    return out_path


def write_snappy_hex_mesh_dict(spec: FlatPlateRibletMeshSpec, out_path: Path) -> Path:
    """Write snappyHexMeshDict — riblet refinement + prism layers.

    When ``riblet_enabled=False`` the dict still emits addLayers on the
    ``bottomWall`` patch so the smooth baseline has matched wall resolution.
    """
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    if spec.riblet_enabled:
        geometry_block = """
geometry
{
    riblets
    {
        type triSurfaceMesh;
        file "riblets.stl";
    }
}
"""
        refinement_surfaces = f"""
    refinementSurfaces
    {{
        riblets
        {{
            level ( {spec.surface_refinement_min} {spec.surface_refinement_max} );
            patchInfo {{ type wall; }}
        }}
    }}
"""
        layers_target = "riblets"
        castellated_features = "    features ( );\n"
        location_in_mesh = f"( {spec.plate_length / 2.0} {spec.spanwise_extent / 2.0} {spec.plate_height / 2.0} )"
        castellated_mesh = "true"
        snap = "true"
    else:
        # Smooth baseline: no STL, but still add prism layers on bottomWall.
        geometry_block = "geometry { }\n"
        refinement_surfaces = "    refinementSurfaces { }\n"
        layers_target = "bottomWall"
        castellated_features = "    features ( );\n"
        location_in_mesh = f"( {spec.plate_length / 2.0} {spec.spanwise_extent / 2.0} {spec.plate_height / 2.0} )"
        castellated_mesh = "false"
        snap = "false"
    body = (
        _of_header("dictionary", "snappyHexMeshDict")
        + f"""
castellatedMesh {castellated_mesh};
snap            {snap};
addLayers       true;

{geometry_block}

castellatedMeshControls
{{
    maxLocalCells  4000000;
    maxGlobalCells 10000000;
    minRefinementCells 10;
    nCellsBetweenLevels 4;
    maxLoadUnbalance   0.10;
    resolveFeatureAngle 30;
    locationInMesh {location_in_mesh};
    allowFreeStandingZoneFaces true;
{castellated_features}{refinement_surfaces}
    refinementRegions {{ }}
}}

snapControls
{{
    nSmoothPatch   3;
    tolerance      2.0;
    nSolveIter     50;
    nRelaxIter     8;
    nFeatureSnapIter 10;
    explicitFeatureSnap true;
    implicitFeatureSnap false;
    multiRegionFeatureSnap false;
}}

addLayersControls
{{
    // Stage 4.x lesson: `relativeSizes true` reinterprets
    // firstLayerThickness as a fraction of the local face edge,
    // silently falling back to snappy defaults and yielding y+ >> 1.
    // `false` honors the absolute chord-units value in FlatPlateRibletMeshSpec.
    relativeSizes false;
    layers
    {{
        {layers_target}
        {{
            nSurfaceLayers {spec.n_layers};
        }}
    }}

    expansionRatio    {spec.expansion_ratio};
    firstLayerThickness {spec.first_layer_thickness};
    minThickness        {spec.first_layer_thickness * 0.5};
    nGrow               0;
    featureAngle        180;
    slipFeatureAngle    30;
    nRelaxIter          5;
    nSmoothSurfaceNormals 1;
    nSmoothNormals      3;
    nSmoothThickness    10;
    maxFaceThicknessRatio   0.5;
    maxThicknessToMedialRatio 0.3;
    minMedialAxisAngle      90;
    nBufferCellsNoExtrude   0;
    nLayerIter              50;
    nRelaxedIter            20;
}}

meshQualityControls
{{
    #include "meshQualityDict"
}}

writeFlatTriSurface false;
mergeTolerance 1e-6;
"""
    )
    out_path.write_text(body)
    return out_path


def write_mesh_quality_dict(out_path: Path) -> Path:
    """Conservative meshQualityDict — Stage-4 SA-stable thresholds."""
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    body = (
        _of_header("dictionary", "meshQualityDict")
        + """
maxNonOrtho         70;
maxBoundarySkewness 20;
maxInternalSkewness 4;
maxConcave          60;
minVol              1e-13;
minTetQuality       -1e30;
minArea             -1;
minTwist            0.02;
minDeterminant      1e-5;
minFaceWeight       0.05;
minVolRatio         0.01;
minTriangleTwist    -1;
nSmoothScale        4;
errorReduction      0.75;
"""
    )
    out_path.write_text(body)
    return out_path


def write_all(spec: FlatPlateRibletMeshSpec, case_dir: Path) -> dict[str, Path]:
    """Emit every mesh-related file for the flat-plate case.

    Layout written under ``case_dir`` (riblet_enabled):
        constant/triSurface/riblets.stl   (only when riblet_enabled)
        system/blockMeshDict
        system/snappyHexMeshDict
        system/meshQualityDict
    """
    case_dir = Path(case_dir)
    paths: dict[str, Path] = {}
    if spec.riblet_enabled:
        paths["stl"] = write_riblet_stl(spec, case_dir / "constant" / "triSurface" / "riblets.stl")
    paths["blockMeshDict"] = write_block_mesh_dict(spec, case_dir / "system" / "blockMeshDict")
    paths["snappyHexMeshDict"] = write_snappy_hex_mesh_dict(
        spec, case_dir / "system" / "snappyHexMeshDict"
    )
    paths["meshQualityDict"] = write_mesh_quality_dict(case_dir / "system" / "meshQualityDict")
    return paths
