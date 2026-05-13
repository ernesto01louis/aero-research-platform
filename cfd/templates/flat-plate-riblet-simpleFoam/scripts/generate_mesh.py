#!/usr/bin/env python3
"""Generate the flat-plate periodic-strip mesh files for this case.

Lays down ``constant/triSurface/riblets.stl`` (when ``--riblet-enabled``),
``system/blockMeshDict``, ``system/snappyHexMeshDict``,
``system/meshQualityDict`` based on
``aero_research_platform.meshing.periodic_riblet_strip``.

The pitch ``s`` is computed from the target ``s+`` via
``s+ = s * u_tau / nu``. We use a canonical Re_θ ≈ 1500 at the measurement
station which gives ``u_tau / U_infty ≈ 0.0535`` from the Schlichting
flat-plate correlation; the actual u_τ is measured post-hoc from
``wallShearStress`` in the converged tail and the achieved ``s+`` is
reported in the notebook.

The orchestrator-generated run.sh calls this script before running
``blockMesh`` + ``snappyHexMesh`` proper.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Canonical u_tau / U_infty from Schlichting flat-plate correlation at
# Re_theta ≈ 1500 (Tu < 0.1%). See Schlichting & Truckenbrodt 1969.
# Used as the pitch-sizing assumption — the achieved s+ is reported
# post-hoc from the measured wallShearStress.
DEFAULT_U_TAU_RATIO: float = 0.0535


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
        help="target wall-unit pitch s+ for this sub-run",
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
        help="generate the riblet STL + snappy refinement; omit for smooth baseline",
    )
    p.add_argument(
        "--u-tau-ratio",
        type=float,
        default=DEFAULT_U_TAU_RATIO,
        help="assumed u_tau/U_infty for pitch sizing (Schlichting Re_theta~1500)",
    )
    p.add_argument(
        "--nu",
        type=float,
        default=1.0e-6,
        help="kinematic viscosity (must match constant/transportProperties)",
    )
    p.add_argument("--plate-length", type=float, default=None)
    p.add_argument("--plate-height", type=float, default=None)
    p.add_argument("--n-pitches-spanwise", type=int, default=None)
    p.add_argument("--n-x", type=int, default=None)
    p.add_argument("--n-y-per-pitch", type=int, default=None)
    p.add_argument("--n-z", type=int, default=None)
    p.add_argument("--n-layers", type=int, default=None)
    p.add_argument("--first-layer-thickness", type=float, default=None)
    args = p.parse_args()

    _add_repo_to_path()
    from aero_research_platform.geometry.riblet import s_from_s_plus
    from aero_research_platform.meshing.periodic_riblet_strip import (
        FlatPlateRibletMeshSpec,
        write_all,
    )

    u_tau = args.u_tau_ratio  # U_infty = 1 (non-dim) so u_tau = ratio.
    pitch_s = s_from_s_plus(s_plus=args.s_plus, u_tau=u_tau, nu=args.nu)
    print(f"target s+ = {args.s_plus}  ->  pitch_s = {pitch_s:.6e} c")

    overrides = {
        k: v for k, v in {
            "plate_length": args.plate_length,
            "plate_height": args.plate_height,
            "n_pitches_spanwise": args.n_pitches_spanwise,
            "n_x": args.n_x,
            "n_y_per_pitch": args.n_y_per_pitch,
            "n_z": args.n_z,
            "n_layers": args.n_layers,
            "first_layer_thickness": args.first_layer_thickness,
        }.items()
        if v is not None
    }
    spec = FlatPlateRibletMeshSpec(
        pitch_s=pitch_s,
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
