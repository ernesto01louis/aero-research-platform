"""Periodic-strip flat-plate mesh generator for the Bechert riblet replication.

Stage 5 domain: a rectangular box

    x ∈ [0, plate_length]            (streamwise; developing BL)
    y ∈ [0, n_pitches * pitch_s]     (spanwise; cyclic periodic)
    z ∈ [0, plate_height]            (wall-normal; bottom = wall, top = slip)

Two variants, dispatched by ``write_all`` on ``spec.riblet_enabled``:

* ``riblet_enabled=True``  — bottom wall is the Bechert blade-riblet surface,
  defined geometrically via a **structured multi-block** blockMeshDict (5
  blocks per pitch period). No STL, no snappyHexMesh. Three pilot iterations
  with the snappy + STL + addLayers approach (pilots v1-v3, 2026-05-14/15)
  produced 28k negative-volume cells regardless of where addLayers targeted:
  the cell-size mismatch between castellated cells around the STL (~1e-6 c
  at refinement level 4) and the absolute prism stack height (~2e-5 c) is
  topologically inconsistent. The structured writer sidesteps the issue
  entirely — blade walls are blockMesh patches, not STL surfaces.

* ``riblet_enabled=False`` — smooth flat plate, a single-block blockMesh
  with grading toward z=0. The legacy snappy + addLayers path is still
  available for matched wall resolution against an STL-based riblet
  reference if needed.
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
    """Configuration for the streamwise-periodic channel mesh (riblet or smooth).

    See STAGE-5-REDESIGN.md. Normalized on the channel half-height
    delta = plate_height = 1, friction velocity u_tau = 1, kinematic
    viscosity nu = 1/re_tau. The riblet pitch is s = s+ / re_tau, so at
    re_tau=180 a s+=17 riblet has pitch ~0.094 delta — isotropic cells,
    no aspect-ratio pathology (contrast the abandoned developing-BL
    domain where s ~ 3e-4 chord forced 4700:1 aspect ratios).
    """

    # Channel half-height (delta) — the wall-normal extent z in [0, delta].
    plate_height: float = 1.0
    # Streamwise periodic extent (delta units). ~3 delta is the canonical
    # minimal-channel length; riblets run streamwise so this is
    # independent of the riblet pitch.
    plate_length: float = 3.0
    # Friction Reynolds number Re_tau = u_tau * delta / nu. 180 is the
    # canonical low-Re channel (Kim-Moin-Moser 1987). nu = 1/re_tau.
    re_tau: float = 180.0
    # Riblet pitch (delta units). For the Bechert sweep this is computed
    # at runtime as s = s+ / re_tau (scripts/generate_mesh.py).
    pitch_s: float = 0.094
    n_pitches_spanwise: int = 4   # ≥ 4 per Stage-5 brief
    h_over_s: float = BECHERT_BLADE_H_OVER_S
    t_over_s: float = BECHERT_BLADE_T_OVER_S
    # Background hex grid. n_y_per_pitch ≥ 16 per Stage-5 brief
    # (Bechert tip-sharpness — under-resolved tips kill the DR).
    n_x: int = 200
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

    # ── structured multi-block (riblet_enabled=True) parameters ──────────
    # Per-pitch topology: 8 blocks per period, across THREE z-bands:
    #
    #   z-band 1  [0, h]          groove region (riblet height)
    #   z-band 2  [h, z_bl]       boundary-layer-resolved band above the tips
    #   z-band 3  [z_bl, Lz]      freestream
    #
    #   band 1: A (groove-L), B (groove-R)               — 2 blocks
    #   band 2: C (above-grL), D (blade-slot), E (above-grR) — 3 blocks
    #   band 3: F (above-grL), G (blade-slot), H (above-grR) — 3 blocks
    #
    # The blade solid material (y∈[blade_left, blade_right], z∈[0, h]) is
    # NOT a mesh block — blockMesh leaves that region empty. Its three
    # fluid-facing faces (two side walls + the tip) form the `riblets`
    # patch. The riblet tip is the z=h face of block D (band-2 blade-slot).
    #
    # Three z-bands keep cell sizes wall-resolved near z=0 and the riblet
    # tips while coarsening into the channel core. In the periodic channel
    # (delta=1, Re_tau=180) the bands are thin enough in absolute terms
    # that only mild grading is needed — contrast the abandoned
    # developing-BL domain that needed grading ~276.
    n_y_groove: int = 8         # cells per groove-half (one of two grooves per pitch)
    n_y_blade: int = 1          # cells across the blade slot above the tip
    n_z_groove: int = 16        # cells in z-band 1 [0, h]
    n_z_bl: int = 24            # cells in z-band 2 [h, z_bl]
    n_z_outer: int = 30         # cells in z-band 3 [z_bl, Lz]
    # z_bl: top of the near-wall resolved band, as a fraction of the
    # channel half-height. 0.1 delta sits just above the riblet tips
    # (h ~ 0.047 delta at s+=17) and inside the buffer layer.
    z_bl_fraction: float = 0.1
    # z-grading: simpleGrading X = last_cell / first_cell ratio.
    # Band 1 (groove, ~0.047 delta / 16 cells): uniform — y+~0.5 at the
    #   wall already (cell ~0.003 delta, Re_tau=180).
    # Band 2 (~0.053 delta / 24 cells): X=4 packs mildly toward z=h
    #   (the riblet tip + high-shear region); first cell ~0.0013 -> y+~0.23.
    # Band 3 (channel core, ~0.9 delta / 30 cells): X=20 grows cells from
    #   the band-2 match (~0.005) into the coarse core (~0.09). Keeps the
    #   z=z_bl interface jump small; core aspect ratio dx/dz ~ 0.16.
    grading_z_groove: float = 1.0
    grading_z_bl: float = 4.0
    grading_z_outer: float = 20.0

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


def write_block_mesh_dict_structured(spec: FlatPlateRibletMeshSpec, out_path: Path) -> Path:
    """Write a structured multi-block blockMeshDict for the riblet case.

    Topology (per pitch period k = 0..n_pitches-1):

        y columns (iy): k*s,  k*s+(s-t)/2,  k*s+(s+t)/2,  (k+1)*s
        z rows    (iz): 0,    h,            z_bl,         Lz

    Eight blocks per period, across three z-bands:
        band 1 [0, h]:      A (groove-L, iy 0->1), B (groove-R, iy 2->3)
        band 2 [h, z_bl]:   C (iy 0->1), D (blade-slot, iy 1->2), E (iy 2->3)
        band 3 [z_bl, Lz]:  F (iy 0->1), G (blade-slot, iy 1->2), H (iy 2->3)

    The blade solid material (iy 1->2, iz 0->1) is NOT a block — its
    three fluid-facing faces (two side walls + the tip) form the
    ``riblets`` patch (the tip is the z=h face of block D).

    Boundary patches (streamwise-periodic channel — see STAGE-5-REDESIGN.md):
        xMinCyclic / xMaxCyclic   cyclic pair at x=0 / x=Lx
        frontPeriodic / backPeriodic   cyclic pair at y=0 / y=Ly
        top                       symmetryPlane at z=Lz (channel centreline)
        bottomWall                wall on the groove floors at z=0
        riblets                   wall — blade side walls + tips
    """
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    if not spec.riblet_enabled:
        raise RuntimeError(
            "write_block_mesh_dict_structured called with riblet_enabled=False; "
            "use write_block_mesh_dict for the smooth baseline."
        )

    s = spec.pitch_s
    h = spec.blade_spec().height_h
    t = spec.blade_spec().thickness_t
    Lx = spec.plate_length
    Lz = spec.plate_height
    z_bl = spec.z_bl_fraction * Lz
    n_p = spec.n_pitches_spanwise

    # Build unique y-column coordinates: 1 + 3*n_p columns total.
    y_cols: list[float] = [0.0]
    for k in range(n_p):
        y_cols.extend([k * s + (s - t) / 2.0, k * s + (s + t) / 2.0, (k + 1) * s])
    n_y_cols = len(y_cols)
    z_rows = [0.0, h, z_bl, Lz]
    n_z_rows = len(z_rows)
    x_slabs = [0.0, Lx]
    n_x_slabs = len(x_slabs)

    def v(ix: int, iy: int, iz: int) -> int:
        return ix * n_y_cols * n_z_rows + iy * n_z_rows + iz

    # Vertex list emitted in (ix, iy, iz) order.
    vertex_lines: list[str] = []
    for ix in range(n_x_slabs):
        for iy in range(n_y_cols):
            for iz in range(n_z_rows):
                vidx = v(ix, iy, iz)
                vertex_lines.append(
                    f"    ( {x_slabs[ix]} {y_cols[iy]} {z_rows[iz]} )  // {vidx}"
                )

    # Hex corner order (per blockMesh convention):
    #   0: x_lo y_lo z_lo,  1: x_hi y_lo z_lo,  2: x_hi y_hi z_lo,  3: x_lo y_hi z_lo
    #   4: x_lo y_lo z_hi,  5: x_hi y_lo z_hi,  6: x_hi y_hi z_hi,  7: x_lo y_hi z_hi
    def hex_corners(iy_lo: int, iy_hi: int, iz_lo: int, iz_hi: int) -> tuple[int, ...]:
        return (
            v(0, iy_lo, iz_lo), v(1, iy_lo, iz_lo), v(1, iy_hi, iz_lo), v(0, iy_hi, iz_lo),
            v(0, iy_lo, iz_hi), v(1, iy_lo, iz_hi), v(1, iy_hi, iz_hi), v(0, iy_hi, iz_hi),
        )

    def block_line(iy_lo: int, iy_hi: int, iz_lo: int, iz_hi: int,
                   n_y: int, n_z: int, grading_z: float) -> str:
        c = hex_corners(iy_lo, iy_hi, iz_lo, iz_hi)
        return (
            f"    hex ({' '.join(str(i) for i in c)}) "
            f"( {spec.n_x} {n_y} {n_z} ) "
            f"simpleGrading ( {spec.grading_x} 1 {grading_z} )"
        )

    block_lines: list[str] = []
    for k in range(n_p):
        iy_left = 3 * k
        iy_bl = 3 * k + 1
        iy_br = 3 * k + 2
        iy_right = 3 * k + 3
        # band 1 [iz 0->1]: groove-L (A), groove-R (B)
        block_lines.append(block_line(iy_left, iy_bl, 0, 1,
                                      spec.n_y_groove, spec.n_z_groove, spec.grading_z_groove))
        block_lines.append(block_line(iy_br, iy_right, 0, 1,
                                      spec.n_y_groove, spec.n_z_groove, spec.grading_z_groove))
        # band 2 [iz 1->2]: above-groove-L (C), blade-slot (D), above-groove-R (E)
        block_lines.append(block_line(iy_left, iy_bl, 1, 2,
                                      spec.n_y_groove, spec.n_z_bl, spec.grading_z_bl))
        block_lines.append(block_line(iy_bl, iy_br, 1, 2,
                                      spec.n_y_blade, spec.n_z_bl, spec.grading_z_bl))
        block_lines.append(block_line(iy_br, iy_right, 1, 2,
                                      spec.n_y_groove, spec.n_z_bl, spec.grading_z_bl))
        # band 3 [iz 2->3]: above-groove-L (F), blade-slot (G), above-groove-R (H)
        block_lines.append(block_line(iy_left, iy_bl, 2, 3,
                                      spec.n_y_groove, spec.n_z_outer, spec.grading_z_outer))
        block_lines.append(block_line(iy_bl, iy_br, 2, 3,
                                      spec.n_y_blade, spec.n_z_outer, spec.grading_z_outer))
        block_lines.append(block_line(iy_br, iy_right, 2, 3,
                                      spec.n_y_groove, spec.n_z_outer, spec.grading_z_outer))

    # Patch faces. Each face is 4 vertex indices CCW viewed from outside.
    inlet_faces: list[str] = []
    outlet_faces: list[str] = []
    top_faces: list[str] = []
    bottom_faces: list[str] = []
    riblet_faces: list[str] = []
    front_faces: list[str] = []  # y = 0
    back_faces: list[str] = []   # y = Ly

    def face(a: int, b: int, c_: int, d: int) -> str:
        return f"            ( {a} {b} {c_} {d} )"

    # Generic block-face emitters (outward-normal CCW orderings).
    def x_lo_face(iy_lo: int, iy_hi: int, iz_lo: int, iz_hi: int) -> str:
        return face(v(0, iy_lo, iz_lo), v(0, iy_lo, iz_hi), v(0, iy_hi, iz_hi), v(0, iy_hi, iz_lo))

    def x_hi_face(iy_lo: int, iy_hi: int, iz_lo: int, iz_hi: int) -> str:
        return face(v(1, iy_lo, iz_lo), v(1, iy_hi, iz_lo), v(1, iy_hi, iz_hi), v(1, iy_lo, iz_hi))

    def z_lo_face(iy_lo: int, iy_hi: int, iz: int) -> str:
        return face(v(0, iy_lo, iz), v(0, iy_hi, iz), v(1, iy_hi, iz), v(1, iy_lo, iz))

    def z_hi_face(iy_lo: int, iy_hi: int, iz: int) -> str:
        return face(v(0, iy_lo, iz), v(1, iy_lo, iz), v(1, iy_hi, iz), v(0, iy_hi, iz))

    def y_lo_face(iy: int, iz_lo: int, iz_hi: int) -> str:
        return face(v(0, iy, iz_lo), v(1, iy, iz_lo), v(1, iy, iz_hi), v(0, iy, iz_hi))

    def y_hi_face(iy: int, iz_lo: int, iz_hi: int) -> str:
        return face(v(0, iy, iz_lo), v(0, iy, iz_hi), v(1, iy, iz_hi), v(1, iy, iz_lo))

    for k in range(n_p):
        iy_left = 3 * k
        iy_bl = 3 * k + 1
        iy_br = 3 * k + 2
        iy_right = 3 * k + 3
        is_first = k == 0
        is_last = k == n_p - 1

        # All 8 blocks as (iy_lo, iy_hi, iz_lo, iz_hi) tuples.
        groove_l_1 = (iy_left, iy_bl, 0, 1)
        groove_r_1 = (iy_br, iy_right, 0, 1)
        band2_l = (iy_left, iy_bl, 1, 2)
        band2_slot = (iy_bl, iy_br, 1, 2)
        band2_r = (iy_br, iy_right, 1, 2)
        band3_l = (iy_left, iy_bl, 2, 3)
        band3_slot = (iy_bl, iy_br, 2, 3)
        band3_r = (iy_br, iy_right, 2, 3)
        all_blocks = [groove_l_1, groove_r_1, band2_l, band2_slot,
                      band2_r, band3_l, band3_slot, band3_r]

        # inlet / outlet — every block.
        for (yl, yh, zl, zh) in all_blocks:
            inlet_faces.append(x_lo_face(yl, yh, zl, zh))
            outlet_faces.append(x_hi_face(yl, yh, zl, zh))

        # bottomWall — z=0 floors of band-1 groove blocks only.
        bottom_faces.append(z_lo_face(iy_left, iy_bl, 0))
        bottom_faces.append(z_lo_face(iy_br, iy_right, 0))

        # top — z=Lz faces of band-3 blocks.
        top_faces.append(z_hi_face(iy_left, iy_bl, 3))
        top_faces.append(z_hi_face(iy_bl, iy_br, 3))
        top_faces.append(z_hi_face(iy_br, iy_right, 3))

        # riblets — blade side walls (band-1) + blade tip (band-2 slot z=h floor).
        riblet_faces.append(y_hi_face(iy_bl, 0, 1))   # left blade side wall
        riblet_faces.append(y_lo_face(iy_br, 0, 1))   # right blade side wall
        riblet_faces.append(z_lo_face(iy_bl, iy_br, 1))  # blade tip at z=h

        # frontPeriodic (y=0) — y_lo faces of the leftmost period's L-stack.
        if is_first:
            front_faces.append(y_lo_face(iy_left, 0, 1))
            front_faces.append(y_lo_face(iy_left, 1, 2))
            front_faces.append(y_lo_face(iy_left, 2, 3))

        # backPeriodic (y=Ly) — y_hi faces of the rightmost period's R-stack.
        if is_last:
            back_faces.append(y_hi_face(iy_right, 0, 1))
            back_faces.append(y_hi_face(iy_right, 1, 2))
            back_faces.append(y_hi_face(iy_right, 2, 3))

    vertices_block = "\n".join(vertex_lines)
    blocks_block = "\n".join(block_lines)
    inlet_block = "\n".join(inlet_faces)
    outlet_block = "\n".join(outlet_faces)
    top_block = "\n".join(top_faces)
    bottom_block = "\n".join(bottom_faces)
    riblet_block = "\n".join(riblet_faces)
    front_block = "\n".join(front_faces)
    back_block = "\n".join(back_faces)

    body = (
        _of_header("dictionary", "blockMeshDict")
        + f"""
convertToMeters 1.0;

vertices
(
{vertices_block}
);

blocks
(
{blocks_block}
);

edges
(
);

boundary
(
    xMinCyclic
    {{
        type cyclic;
        neighbourPatch xMaxCyclic;
        faces
        (
{inlet_block}
        );
    }}
    xMaxCyclic
    {{
        type cyclic;
        neighbourPatch xMinCyclic;
        faces
        (
{outlet_block}
        );
    }}
    top
    {{
        type symmetryPlane;
        faces
        (
{top_block}
        );
    }}
    bottomWall
    {{
        type wall;
        faces
        (
{bottom_block}
        );
    }}
    riblets
    {{
        type wall;
        faces
        (
{riblet_block}
        );
    }}
    frontPeriodic
    {{
        type cyclic;
        neighbourPatch backPeriodic;
        faces
        (
{front_block}
        );
    }}
    backPeriodic
    {{
        type cyclic;
        neighbourPatch frontPeriodic;
        faces
        (
{back_block}
        );
    }}
);

mergePatchPairs
(
);
"""
    )
    out_path.write_text(body)
    n_blocks = 8 * n_p
    _LOG.info("Wrote structured periodic-channel blockMeshDict: %d blocks, %d vertices to %s",
              n_blocks, len(vertex_lines), out_path)
    return out_path


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
        # Prism layers go on bottomWall (the flat region between riblets),
        # NOT on the riblet STL surface. Pilot v2 (run 3a1eba19) showed
        # that targeting addLayers at `riblets` produces 28k negative-volume
        # cells: the prism stack height (2.4e-5 chord at first_layer=1e-6,
        # ratio=1.15, n=12) is ~19x bigger than the level-4 castellated
        # cells around the STL (1.25e-6 chord), so addLayers tries to
        # extrude prism layers into cells that are smaller than the stack
        # and produces topological inversions. The riblet patch gets y+<<1
        # from castellated refinement alone: cell_size * u_tau / nu =
        # 1.25e-6 * 53.5 ≈ 6.7e-5, well below 1.
        layers_target = "bottomWall"
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

    Dispatches on ``spec.riblet_enabled``:

    * Riblet case (True): structured multi-block blockMeshDict only. No
      STL, no snappyHexMeshDict. The blade geometry is baked into the
      block topology — see ``write_block_mesh_dict_structured``.

    * Smooth baseline (False): single-block blockMeshDict + the legacy
      snappy + addLayers stack for matched wall resolution.
    """
    case_dir = Path(case_dir)
    paths: dict[str, Path] = {}
    if spec.riblet_enabled:
        paths["blockMeshDict"] = write_block_mesh_dict_structured(
            spec, case_dir / "system" / "blockMeshDict"
        )
        paths["meshQualityDict"] = write_mesh_quality_dict(
            case_dir / "system" / "meshQualityDict"
        )
        return paths
    paths["blockMeshDict"] = write_block_mesh_dict(spec, case_dir / "system" / "blockMeshDict")
    paths["snappyHexMeshDict"] = write_snappy_hex_mesh_dict(
        spec, case_dir / "system" / "snappyHexMeshDict"
    )
    paths["meshQualityDict"] = write_mesh_quality_dict(case_dir / "system" / "meshQualityDict")
    return paths
