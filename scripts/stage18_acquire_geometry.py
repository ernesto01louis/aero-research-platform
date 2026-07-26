"""Stage-18 acquisition: close the extracted Turek-Hron band into a watertight STL.

Input: the open prismatic band `surfaceMeshExtract -patches "(cylinder|flap)"` pulled
off the THIRD-PARTY-authored preCICE tutorial mesh (github.com/precice/tutorials,
LGPL-3.0, pinned commit — the x-y profile is 100 % upstream-authored; ADR-033 §7).
This script applies ONLY the declared shape-preserving closure: ear-clip caps over the
two planar boundary loops at the band's z extremes, using the same
`aero.geometry.repair` machinery as ingestion but with EXPLICIT acquisition bounds
(the loops are ~334 edges — far past the campaign R2 repair bound of 32, which exists
to stop silent hole patching, not to limit a declared acquisition transform). Every
action is printed as the ledger for reference.md.

The output STL must then pass the STRICT default ingestion gate with ZERO repairs —
verified here, fail-loud — and its V1 extents are printed for the metrology record.

Usage:
  python scripts/stage18_acquire_geometry.py --band <extracted band.stl> \
      --out data/references/fsi/turek_hron_fsi3/cylinder_flag.stl
"""

from __future__ import annotations

import argparse
import hashlib
from pathlib import Path

from aero.geometry import (
    IngestConfig,
    RepairConfig,
    compute_quality,
    ingest,
    read_stl,
    repair,
    write_stl,
)

_REPO_ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--band", type=Path, required=True, help="Extracted open band STL.")
    parser.add_argument(
        "--out",
        type=Path,
        default=_REPO_ROOT
        / "data"
        / "references"
        / "fsi"
        / "turek_hron_fsi3"
        / "cylinder_flag.stl",
    )
    args = parser.parse_args()

    band = read_stl(args.band)
    band_quality = compute_quality(band)
    print(
        f"[band] {band.n_faces} faces, {band.n_vertices} vertices, "
        f"boundary edges: {band_quality.n_boundary_edges} (expect two open loops)"
    )
    if band_quality.watertight:
        print("[band] already watertight — no closure needed")
        closed, actions = band, ()
    else:
        # Declared acquisition closure: cap the two planar z-extreme loops.
        closed, actions = repair(band, RepairConfig(max_hole_edges=100000, max_holes=2))
    print("[closure ledger] (record verbatim in reference.md):")
    for a in actions:
        print(f"  - {a.kind} (x{a.count}): {a.detail}")
    if not actions:
        print("  (none)")

    args.out.parent.mkdir(parents=True, exist_ok=True)
    write_stl(closed, args.out, binary=True)
    sha = hashlib.sha256(args.out.read_bytes()).hexdigest()
    args.out.with_suffix(args.out.suffix + ".sha256").write_text(sha + "\n", encoding="utf-8")
    print(f"[out] {args.out} sha256={sha}")

    # The shipped artifact must clear the STRICT campaign gate with ZERO repairs.
    record = ingest(args.out, config=IngestConfig())
    assert record.repairs == (), "shipped STL needed repairs — acquisition is not clean"
    q = record.quality
    print(
        f"[verify] strict ingestion gate PASSED with zero repairs: "
        f"{record.n_faces} faces, watertight={q.watertight}, manifold={q.manifold}, "
        f"intersections={q.n_intersecting_pairs}"
    )
    print(
        f"[V1 extents] x: [{q.bbox_min[0]:.6f}, {q.bbox_max[0]:.6f}]  "
        f"y: [{q.bbox_min[1]:.6f}, {q.bbox_max[1]:.6f}]  "
        f"z: [{q.bbox_min[2]:.6f}, {q.bbox_max[2]:.6f}]"
    )
    print("[V1 expected] x: [0.15, 0.60]  y: [0.15, 0.25]  (tol 0.001)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
