#!/usr/bin/env python3
"""Generate the streamwise-periodic channel mesh files for this case.

Lays down ``system/blockMeshDict`` + ``system/meshQualityDict`` based on
``aero_research_platform.meshing.periodic_riblet_strip``. See
STAGE-5-REDESIGN.md for the periodic-channel rationale.

The mesh is normalized on the channel half-height delta=1, friction
velocity u_tau=1, kinematic viscosity nu=1/Re_tau. The riblet pitch is

    s = s+ / Re_tau          (s+ = s * u_tau / nu = s * Re_tau)

so a s+=17 riblet at Re_tau=180 has pitch ~0.094 delta — a sizeable
fraction of the domain, giving isotropic cells.

The orchestrator-generated run.sh calls this script before ``blockMesh``.
No snappyHexMesh — the riblet geometry is baked into the block topology.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Canonical low-Reynolds channel (Kim, Moin & Moser 1987). nu = 1/Re_tau.
DEFAULT_RE_TAU: float = 180.0


def _add_repo_to_path() -> None:
    """Ensure the aero_research_platform package is importable."""
    candidates = [
        Path("/opt/aero-research-platform"),  # orchestrator LXC
        Path.home() / "aero-research-platform",  # aero LXC clone
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
    p.add_argument(
        "--s-plus",
        type=float,
        required=True,
        help="target wall-unit riblet pitch s+ for this sub-run",
    )
    p.add_argument(
        "--h-over-s",
        type=float,
        default=0.5,
        help="blade height as fraction of pitch (Bechert: 0.5)",
    )
    p.add_argument(
        "--t-over-s",
        type=float,
        default=0.02,
        help="blade thickness as fraction of pitch (Bechert: 0.02)",
    )
    p.add_argument(
        "--riblet-enabled",
        action="store_true",
        help="generate the structured riblet blockMesh; omit for the smooth baseline",
    )
    p.add_argument(
        "--re-tau",
        type=float,
        default=DEFAULT_RE_TAU,
        help="friction Reynolds number; pitch s = s+/Re_tau, nu = 1/Re_tau",
    )
    p.add_argument("--plate-length", type=float, default=None)
    p.add_argument("--plate-height", type=float, default=None)
    p.add_argument("--n-pitches-spanwise", type=int, default=None)
    p.add_argument("--n-x", type=int, default=None)
    args = p.parse_args()

    _add_repo_to_path()
    from aero_research_platform.geometry.riblet import s_from_s_plus
    from aero_research_platform.meshing.periodic_riblet_strip import (
        FlatPlateRibletMeshSpec,
        write_all,
    )

    # delta = 1, u_tau = 1, nu = 1/Re_tau  ->  s = s+ / Re_tau.
    u_tau = 1.0
    nu = 1.0 / args.re_tau
    pitch_s = s_from_s_plus(s_plus=args.s_plus, u_tau=u_tau, nu=nu)
    print(f"target s+ = {args.s_plus}  Re_tau = {args.re_tau}  ->  pitch_s = {pitch_s:.6e} delta")

    overrides = {
        k: v for k, v in {
            "plate_length": args.plate_length,
            "plate_height": args.plate_height,
            "n_pitches_spanwise": args.n_pitches_spanwise,
            "n_x": args.n_x,
        }.items()
        if v is not None
    }
    spec = FlatPlateRibletMeshSpec(
        pitch_s=pitch_s,
        re_tau=args.re_tau,
        h_over_s=args.h_over_s,
        t_over_s=args.t_over_s,
        riblet_enabled=args.riblet_enabled,
        **overrides,
    )
    paths = write_all(spec, args.case_dir)
    print(
        f"Wrote {len(paths)} mesh files under {args.case_dir} "
        f"(riblet_enabled={spec.riblet_enabled}, s+={args.s_plus}):"
    )
    for name, path in paths.items():
        print(f"  {name}: {path}")


if __name__ == "__main__":
    _cli()
