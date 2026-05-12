#!/usr/bin/env python3
"""Generate the airfoil mesh files for this OpenFOAM case.

Lays down ``constant/triSurface/airfoil.stl``, ``system/blockMeshDict``,
``system/snappyHexMeshDict``, ``system/meshQualityDict`` based on the
in-tree ``aero_research_platform.meshing.airfoil_cmesh`` module.

The orchestrator-generated run.sh calls this script before running
``blockMesh`` + ``snappyHexMesh`` proper. Adjust ``--n-x`` / ``--n-y`` /
``--surface-refinement`` for coarse smoke runs.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


def _add_repo_to_path() -> None:
    """Ensure the aero_research_platform package is importable."""
    candidates = [
        Path("/opt/aero-research-platform"),  # orchestrator LXC
        Path.home() / "aero-research-platform",  # aero LXC clone fallback
        Path("/home/aero/aero-research-platform"),
    ]
    for cand in candidates:
        if (cand / "aero_research_platform" / "__init__.py").exists():
            sys.path.insert(0, str(cand))
            return
    raise RuntimeError(
        "Cannot find aero_research_platform package. Set PYTHONPATH or "
        "clone the repo to /opt/aero-research-platform."
    )


def _cli() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--case-dir", type=Path, default=Path("."))
    p.add_argument("--n-x", type=int, default=80, help="background hex cells in x")
    p.add_argument("--n-y", type=int, default=40, help="background hex cells in y")
    p.add_argument(
        "--surface-refinement-min",
        type=int,
        default=5,
        help="minimum snappyHexMesh refinement level on the airfoil",
    )
    p.add_argument(
        "--surface-refinement-max",
        type=int,
        default=6,
        help="maximum snappyHexMesh refinement level on the airfoil",
    )
    p.add_argument("--n-layers", type=int, default=30, help="prism boundary-layer count")
    p.add_argument(
        "--first-layer-thickness",
        type=float,
        default=1e-6,
        help="first prism cell wall distance (chord units)",
    )
    args = p.parse_args()

    _add_repo_to_path()
    from aero_research_platform.meshing.airfoil_cmesh import MeshSpec, write_all

    spec = MeshSpec(
        n_x=args.n_x,
        n_y=args.n_y,
        surface_refinement_min=args.surface_refinement_min,
        surface_refinement_max=args.surface_refinement_max,
        n_layers=args.n_layers,
        first_layer_thickness=args.first_layer_thickness,
    )
    paths = write_all(spec, args.case_dir)
    print(f"Wrote {len(paths)} mesh files under {args.case_dir}:")
    for name, path in paths.items():
        print(f"  {name}: {path}")


if __name__ == "__main__":
    _cli()
