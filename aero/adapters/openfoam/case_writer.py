"""Render an OpenFOAM case directory from an airfoil `CaseSpec`.

The case is written as plain string templates — no Jinja. The non-trivial part
is the `blockMeshDict`: a 2D **multi-block C-grid** around the airfoil.

Stage 05 replaced the Stage-03 four-block O-grid (a closed ring at a 20-chord
circular far field, whose sharp trailing edge was badly skewed and which biased
Cd ~+11 %). The C-grid is eight blocks with a rectangular far field at
`farfield_extent_chords` and an explicit **wake cut** running downstream from
the trailing edge — the wake cut gives the sharp TE a well-defined discrete
continuation instead of forcing the grid to wrap a singular point. See ADR-005.

Block layout (upper half; the lower half mirrors it about the chord line):

    UF  inlet  -> LE    (front block, no wall)
    UA1 LE     -> mid   (upper surface, wall)
    UA2 mid    -> TE    (upper surface, wall)
    UW  TE     -> outlet (wake-cut block, no wall)

The airfoil surface is split at mid-chord so the upper- and lower-surface
`polyLine` edges never share an edge key (a single edge `(LE, TE)` cannot carry
two different curves). The front line (inlet->LE) and the wake cut (TE->outlet)
are internal faces shared by the upper and lower blocks — every vertex is
distinct, every block is a positive-volume hexahedron, no `mergePatchPairs`.
"""

from __future__ import annotations

import math
from pathlib import Path

import numpy as np
from numpy.typing import NDArray

from aero.adapters.openfoam._foam_common import (
    RHO_INF,
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
from aero.adapters.openfoam.geometry import naca0012_coordinates
from aero.adapters.openfoam.schemas import CaseSpec


# --- airfoil surface, split at mid-chord --------------------------------------
def _surfaces(spec: CaseSpec) -> dict[str, NDArray[np.float64]]:
    """Upper and lower surface point arrays, each LE -> TE, with `2*n_surface+1`
    points so index `n_surface` is the exact mid-chord split point."""
    n = spec.n_surface
    blunt = spec.trailing_edge_thickness > 0.0
    upper = naca0012_coordinates(2 * n + 1, chord=spec.chord, blunt_te=blunt)  # LE -> TE, +y
    lower = upper.copy()
    lower[:, 1] *= -1.0
    return {"upper": np.asarray(upper, np.float64), "lower": np.asarray(lower, np.float64)}


# --- OpenFOAM dictionary rendering -------------------------------------------
def _blockmeshdict(spec: CaseSpec) -> str:
    c = spec.chord
    ext = spec.farfield_extent_chords * c  # rectangular far-field half-extent
    span = spec.span
    surf = _surfaces(spec)
    n = spec.n_surface
    umid = surf["upper"][n]
    xm, ym = float(umid[0]), float(umid[1])

    # Trailing edge: sharp closes to the single vertex 3 = (c, 0); blunt
    # (trailing_edge_thickness>0) splits it into 3u=(c,+h) and a new 3l=(c,-h),
    # adds a base wall (own patch) + a base-wake block carrying the constant base
    # height to the split outlet 5u/5l (ADR-012; Stage-10 made the base-wake a
    # proper quad — see the BW block below for the collapse it replaced).
    blunt = spec.trailing_edge_thickness > 0.0
    h = float(surf["upper"][-1][1])  # TE half-thickness (0 sharp, >0 blunt)
    nte = spec.n_te

    # --- base vertices at z=0 (duplicated at z=span as +nb) ---
    base = [
        (-ext, 0.0),  # 0  inlet point
        (0.0, 0.0),  # 1  leading edge
        (xm, ym),  # 2  upper mid-chord
        (c, h),  # 3  trailing edge (upper corner 3u; h=0 when sharp)
        (xm, -ym),  # 4  lower mid-chord
        (ext, 0.0),  # 5  outlet point
        (-ext, ext),  # 6  far field, above inlet
        (0.0, ext),  # 7  far field, above LE
        (xm, ext),  # 8  far field, above mid
        (c, ext),  # 9  far field, above TE
        (ext, ext),  # 10 far field, above outlet
        (-ext, -ext),  # 11 far field, below inlet
        (0.0, -ext),  # 12 far field, below LE
        (xm, -ext),  # 13 far field, below mid
        (c, -ext),  # 14 far field, below TE
        (ext, -ext),  # 15 far field, below outlet
    ]
    # Blunt TE: append the lower TE corner 3l=(c,-h); the lower surface + lower
    # wake terminate there instead of at the shared sharp-TE vertex 3. The single
    # outlet vertex 5 also splits into 5u=(ext,+h_wake) / 5l=(ext,-h_wake) so the
    # base-wake block is a proper quad instead of a prism collapsing to a point at
    # the outlet (the collapse gave a zero-area face + 1e150 skewness, failing
    # checkMesh). The outlet half-height h_wake > h TAPERS the base wake wider
    # downstream: a constant-h (~0.0013c) strip over the 100c wake produced
    # aspect ratios ~3e4 that made the pressure equation ill-conditioned and
    # diverged the solve; widening the outlet brings the far base-wake cells back
    # to ~the sharp-wake aspect ratio. Vertex 5 is then unused by the blunt
    # blocks (blockMesh ignores it). For the sharp TE, out_up == out_lo == 5.
    h_wake = max(h, 0.02 * c)  # base-wake outlet half-height (taper target)
    if blunt:
        base.append((c, -h))  # 16 trailing edge (lower corner 3l)
        base.append((ext, h_wake))  # 17 outlet, upper (5u)
        base.append((ext, -h_wake))  # 18 outlet, lower (5l)
        te_lo, out_up, out_lo = 16, 17, 18
    else:
        te_lo, out_up, out_lo = 3, 5, 5
    nb = len(base)
    verts = [pt(x, y, 0.0) for x, y in base] + [pt(x, y, span) for x, y in base]

    # --- grading ---
    g_eta = expansion(ext, spec.n_normal, spec.first_cell_height * c)
    e_front = expansion(ext, spec.n_front, 0.01 * c)
    e_wake = expansion(ext, spec.n_wake, 0.01 * c)
    ns, nn, nf, nw = spec.n_surface, spec.n_normal, spec.n_front, spec.n_wake

    # --- 8 blocks: z=0 face wound CCW-from-above, +16 for the z=span face ---
    # (v0 v1 v2 v3) at z=0 then (v0 v1 v2 v3)+16; counts along (v0->v1, v1->v2, z).
    def _verts(a: int, b: int, d: int, e: int) -> str:
        return " ".join(str(v) for v in (a, b, d, e, a + nb, b + nb, d + nb, e + nb))

    def hexb(a: int, b: int, d: int, e: int, n1: int, n2: int, gx: float, gy: float) -> str:
        """An airfoil-surface block — simpleGrading (both eta edges wall-clustered)."""
        return f"    hex ({_verts(a, b, d, e)}) ({n1} {n2} 1) simpleGrading ({gx:.8g} {gy:.8g} 1)"

    def edge_hexb(
        a: int, b: int, d: int, e: int, n1: int, gx: float, x2: tuple[float, float, float, float]
    ) -> str:
        """A front/wake block — edgeGrading so the boundary-layer clustering
        applies only on the airfoil-side eta edge, not on the inlet/outlet eta
        edge (which would otherwise put a ~1e-6 cell 100 chords from any wall
        and blow the cell aspect ratio up).

        12 edges: 4 x1 (streamwise), 4 x2 (eta), 4 x3 (span). `x2` is the
        eta 4-tuple in blockMesh edge order (v0->v3, v1->v2, v5->v6, v4->v7).
        """
        x1 = " ".join(f"{gx:.8g}" for _ in range(4))
        x2s = " ".join(f"{g:.8g}" for g in x2)
        return f"    hex ({_verts(a, b, d, e)}) ({n1} {nn} 1) edgeGrading ({x1} {x2s} 1 1 1 1)"

    gi = 1.0 / g_eta  # lower-block eta runs far field -> wall
    blocks = [
        # UF: airfoil eta edge is v1->v2 (above the LE); inlet edge v0->v3.
        edge_hexb(0, 1, 7, 6, nf, 1.0 / e_front, (1.0, g_eta, g_eta, 1.0)),
        hexb(1, 2, 8, 7, ns, nn, 1.0, g_eta),  # UA1
        hexb(2, 3, 9, 8, ns, nn, 1.0, g_eta),  # UA2
        # UW: airfoil eta edge is v0->v3 (above the TE); outlet edge v1->v2.
        edge_hexb(3, out_up, 10, 9, nw, e_wake, (g_eta, 1.0, 1.0, g_eta)),
        # LF: airfoil eta edge is v1->v2 (below the LE); inlet edge v0->v3.
        edge_hexb(11, 12, 1, 0, nf, 1.0 / e_front, (1.0, gi, gi, 1.0)),
        hexb(12, 13, 4, 1, ns, nn, 1.0, gi),  # LA1
        hexb(13, 14, te_lo, 4, ns, nn, 1.0, gi),  # LA2 (lower TE corner te_lo)
        # LW: airfoil eta edge is v0->v3 (below the TE); outlet edge v1->v2.
        edge_hexb(14, 15, out_lo, te_lo, nw, e_wake, (gi, 1.0, 1.0, gi)),
    ]
    if blunt:
        # BW: the base-wake block — a proper quad from the blunt base (3l->3u at
        # x=c, height 2h) to the split outlet (5l->5u at x=ext, height 2*h_wake);
        # it TAPERS wider downstream to keep the far cells off extreme aspect
        # ratio. nte cells span the base (v0->v3 = 3l->3u, the wall edge), nw
        # streamwise.
        # Its streamwise (x1) edges 3l->5l and 3u->5u are SHARED with LW (edge
        # 16->18) and UW (edge 3->17); all three grade x1 with `e_wake`, so the
        # shared internal faces have identical node distributions (no duplicate
        # unmerged points — there is no mergePatchPairs). The base (x2, nte) and
        # span stay uniform. (Stage-10: replaces the degenerate collapsed prism.)
        blocks.append(
            f"    hex ({_verts(te_lo, out_lo, out_up, 3)}) ({nw} {nte} 1) "
            f"simpleGrading ({e_wake:.8g} 1 1)"
        )

    # --- polyLine edges along the airfoil surface (interior points only) ---
    def poly(v1: int, v2: int, pts: NDArray[np.float64], z: float) -> str:
        body = "\n".join(f"            {pt(float(x), float(y), z)}" for x, y in pts)
        return f"    polyLine {v1} {v2}\n        (\n{body}\n        )"

    edges = []
    # (v1, v2, interior point slice) — LE->mid and mid->TE, upper then lower.
    specs = [
        (1, 2, surf["upper"][1:n]),
        (2, 3, surf["upper"][n + 1 : 2 * n]),
        (1, 4, surf["lower"][1:n]),
        (4, te_lo, surf["lower"][n + 1 : 2 * n]),
    ]
    for v1, v2, interior in specs:
        edges.append(poly(v1, v2, interior, 0.0))
        edges.append(poly(v1 + nb, v2 + nb, interior, span))

    # --- boundary patches ---
    def face(a: int, b: int) -> str:
        return f"({a} {b} {b + nb} {a + nb})"

    # airfoil wall: the inner edge of each surface block. The blunt-TE base is a
    # SEPARATE patch (`airfoil_te`) so it can carry an all-y+ wall function: the
    # base's wall-normal direction IS the streamwise wake axis (first cell ~0.01c
    # -> y+ ~ 1e3), where the surface's nutLowReWallFunction (y+<1) is invalid.
    # Both patches are integrated by the force objects, so base drag is counted.
    wall_faces = [(1, 2), (2, 3), (1, 4), (4, te_lo)]
    wall = " ".join(face(a, b) for a, b in wall_faces)
    te_base_face = face(3, te_lo) if blunt else ""  # the blunt TE base (3u -> 3l)
    # far field: every outer / inlet / outlet face (freestream BC handles in/out).
    # The outlet column runs top->bottom: (out_up,10) upper wake, the base-wake
    # exit (out_lo,out_up) when blunt, then (15,out_lo) lower wake. For the sharp
    # TE out_up==out_lo==5 and the base-wake face collapses out (h=0), recovering
    # the original two outlet faces (5,10) and (15,5).
    outer = [
        (0, 6),
        (0, 11),  # inlet (left)
        (out_up, 10),
        (15, out_lo),  # outlet (right): upper + lower wake
        (6, 7),
        (7, 8),
        (8, 9),
        (9, 10),  # top
        (11, 12),
        (12, 13),
        (13, 14),
        (14, 15),  # bottom
    ]
    if blunt:
        outer.append((out_lo, out_up))  # the base-wake strip's outlet face (5l->5u)
    farfield = " ".join(face(a, b) for a, b in outer)
    # 2D: every block's z=0 face is `front`, its z=span face is `back`.
    z_faces = [
        (0, 1, 7, 6),
        (1, 2, 8, 7),
        (2, 3, 9, 8),
        (3, out_up, 10, 9),
        (11, 12, 1, 0),
        (12, 13, 4, 1),
        (13, 14, te_lo, 4),
        (14, 15, out_lo, te_lo),
    ]
    if blunt:
        z_faces.append((te_lo, out_lo, out_up, 3))  # BW base-wake block front/back face
    front = " ".join(f"({a} {b} {d} {e})" for a, b, d, e in z_faces)
    back = " ".join(f"({a + nb} {b + nb} {d + nb} {e + nb})" for a, b, d, e in z_faces)

    te_base_patch = (
        f"""    airfoil_te
    {{
        type wall;
        faces ( {te_base_face} );
    }}
"""
        if blunt
        else ""
    )
    boundary = f"""    airfoil
    {{
        type wall;
        faces ( {wall} );
    }}
{te_base_patch}    farfield
    {{
        type patch;
        faces ( {farfield} );
    }}
    front
    {{
        type empty;
        faces ( {front} );
    }}
    back
    {{
        type empty;
        faces ( {back} );
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


def _controldict(spec: CaseSpec) -> str:
    aoa = math.radians(spec.aoa_deg)
    drag_dir = f"({math.cos(aoa):.8f} {math.sin(aoa):.8f} 0)"
    lift_dir = f"({-math.sin(aoa):.8f} {math.cos(aoa):.8f} 0)"
    a_ref = spec.chord * spec.span
    # Blunt TE adds the `airfoil_te` base patch; both force objects integrate it
    # so base drag is counted (and measurable on its own patch).
    blunt = spec.trailing_edge_thickness > 0.0
    force_patches = "(airfoil airfoil_te)" if blunt else "(airfoil)"
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
purgeWrite      2;
writeFormat     ascii;
writePrecision  8;
runTimeModifiable false;

functions
{{
    forceCoeffs1
    {{
        type            forceCoeffs;
        libs            (forces);
        writeControl    timeStep;
        writeInterval   1;
        patches         {force_patches};
        rho             rhoInf;
        rhoInf          {RHO_INF};
        magUInf         {U_INF};
        lRef            {spec.chord};
        Aref            {a_ref};
        dragDir         {drag_dir};
        liftDir         {lift_dir};
        CofR            (0.25 0 0);
        pitchAxis       (0 0 1);
    }}
    // Raw force breakdown -> force.dat carries the pressure/viscous split that
    // `forceCoeffs` does not. The loader projects these onto dragDir and
    // divides by 0.5*rhoInf*magUInf^2*Aref to recover Cd_pressure / Cd_viscous,
    // then asserts they reconstruct the total Cd (FAIL-LOUD). This is the
    // measurement the NACA 0012 V&V hypothesis (excess = pressure drag) needs.
    forces1
    {{
        type            forces;
        libs            (forces);
        writeControl    timeStep;
        writeInterval   1;
        patches         {force_patches};
        rho             rhoInf;
        rhoInf          {RHO_INF};
        CofR            (0.25 0 0);
    }}
}}
"""
    )


def _field(
    obj: str,
    cls: str,
    dims: str,
    internal: str,
    farfield: str,
    airfoil: str,
    te_base: str | None = None,
) -> str:
    # `te_base` (when given) is the BC for the blunt-TE `airfoil_te` patch; it
    # must be present in EVERY field's boundaryField when that patch exists.
    te_block = ""
    if te_base is not None:
        te_block = f"""    airfoil_te
    {{
{te_base}
    }}
"""
    return (
        header(cls, obj)
        + f"""
dimensions      {dims};
internalField   uniform {internal};

boundaryField
{{
    airfoil
    {{
{airfoil}
    }}
{te_block}    farfield
    {{
{farfield}
    }}
    front {{ type empty; }}
    back  {{ type empty; }}
}}
"""
    )


def _fields(spec: CaseSpec) -> dict[str, str]:
    st = flow_state(
        reynolds=spec.reynolds,
        ref_length=spec.chord,
        turbulence_intensity=spec.turbulence_intensity,
    )
    aoa = math.radians(spec.aoa_deg)
    u_vec = f"({U_INF * math.cos(aoa):.8f} {U_INF * math.sin(aoa):.8f} 0)"
    k, omega, nut = st["k"], st["omega"], st["nut"]
    blunt = spec.trailing_edge_thickness > 0.0
    # The blunt-TE base patch (`airfoil_te`) shares the airfoil wall BCs EXCEPT
    # nut: the coarse base (y+ ~ 1e3) needs nutUSpaldingWallFunction (valid for
    # all y+), not the surface's nutLowReWallFunction (y+<1). None => no patch
    # (sharp TE), so the field omits the airfoil_te entry entirely.
    te_u = "        type noSlip;" if blunt else None
    te_p = "        type zeroGradient;" if blunt else None
    te_nut = "        type nutUSpaldingWallFunction;\n        value uniform 0;" if blunt else None
    te_k = f"        type kqRWallFunction;\n        value uniform {k:.8g};" if blunt else None
    te_omega = (
        f"        type omegaWallFunction;\n        value uniform {omega:.8g};" if blunt else None
    )
    fields = {
        "U": _field(
            "U",
            "volVectorField",
            "[0 1 -1 0 0 0 0]",
            u_vec,
            f"        type freestream;\n        freestreamValue uniform {u_vec};",
            "        type noSlip;",
            te_base=te_u,
        ),
        "p": _field(
            "p",
            "volScalarField",
            "[0 2 -2 0 0 0 0]",
            "0",
            "        type freestreamPressure;\n        freestreamValue uniform 0;",
            "        type zeroGradient;",
            te_base=te_p,
        ),
    }
    # Laminar (forward-regime low-Re airfoil): no k/omega/nut transport.
    if spec.turbulence_model == "laminar":
        return fields
    fields["nut"] = _field(
        "nut",
        "volScalarField",
        "[0 2 -1 0 0 0 0]",
        f"{nut:.8g}",
        f"        type freestream;\n        freestreamValue uniform {nut:.8g};",
        # Wall-resolved (y+ < 1) — low-Re wall treatment, not a log-law
        # wall function (using nutkWallFunction here biased Cd ~+20%).
        "        type nutLowReWallFunction;\n        value uniform 0;",
        te_base=te_nut,
    )
    fields["k"] = _field(
        "k",
        "volScalarField",
        "[0 2 -2 0 0 0 0]",
        f"{k:.8g}",
        f"        type inletOutlet;\n        inletValue uniform {k:.8g};\n        value uniform {k:.8g};",
        f"        type kqRWallFunction;\n        value uniform {k:.8g};",
        te_base=te_k,
    )
    fields["omega"] = _field(
        "omega",
        "volScalarField",
        "[0 0 -1 0 0 0 0]",
        f"{omega:.8g}",
        f"        type inletOutlet;\n        inletValue uniform {omega:.8g};\n        value uniform {omega:.8g};",
        f"        type omegaWallFunction;\n        value uniform {omega:.8g};",
        te_base=te_omega,
    )
    return fields


def write_case(spec: CaseSpec, dest: Path) -> None:
    """Write a complete OpenFOAM case (`system/`, `constant/`, `0/`) under `dest`."""
    system = dest / "system"
    constant = dest / "constant"
    zero = dest / "0"
    for d in (system, constant, zero):
        d.mkdir(parents=True, exist_ok=True)

    nu = flow_state(
        reynolds=spec.reynolds,
        ref_length=spec.chord,
        turbulence_intensity=spec.turbulence_intensity,
    )["nu"]
    # The blunt-TE base wake is a harder mesh than the sharp airfoil: even
    # tapered it carries higher-aspect-ratio cells, so the blunt case uses the
    # PCG/DIC pressure solver (robust where GAMG coarsening stalls) and lower
    # momentum/turbulence under-relaxation (0.7/0.5 vs the airfoil 0.9/0.7) for
    # SIMPLE stability. Neither changes the converged solution — only the path
    # to it. (The default-relaxation blunt solve diverged; Stage-10.)
    blunt = spec.trailing_edge_thickness > 0.0
    (system / "blockMeshDict").write_text(_blockmeshdict(spec), encoding="utf-8")
    (system / "controlDict").write_text(_controldict(spec), encoding="utf-8")
    (system / "fvSchemes").write_text(fvschemes(), encoding="utf-8")
    (system / "fvSolution").write_text(
        fvsolution(
            pressure_solver="PCG" if blunt else "GAMG",
            u_relax=0.7 if blunt else 0.9,
            kw_relax=0.5 if blunt else 0.7,
        ),
        encoding="utf-8",
    )
    (constant / "transportProperties").write_text(transport_properties(nu), encoding="utf-8")
    (constant / "turbulenceProperties").write_text(
        turbulence_properties(spec.turbulence_model), encoding="utf-8"
    )
    for name, text in _fields(spec).items():
        (zero / name).write_text(text, encoding="utf-8")
