#!/usr/bin/env python
"""Combined space+time GCI for any unsteady moving-body case — the ``u95_numerical`` term.

Generalized from ``scripts/stage12_cylinder_gci.py`` (which hard-wired the oscillating
cylinder). Computes the discretization uncertainty of a case's cycle-mean ``cd`` as
``u95_numerical = RSS(gci_space, gci_time)``. Each moving solve is ~30-84 min serial (MPI is
blocked in the LXC), so the **completed base (fine) grid is reused** (``--base-run-dir``) and
only the coarser grids are solved:

  * **spatial** — 2-grid GCI: base vs a coarser mesh (``refined(spatial_ratio)``);
  * **temporal** — 2-grid GCI: base vs a coarser Courant cap (``refined_dt(temporal_ratio)``).

ASME V&V 20 2-grid safety factor Fs=3.0 with assumed order p (2 spatial / 1 temporal). The
cycle-mean ``cd`` is the Richardson target (smooth, vs the frequency-quantized Strouhal); for
a plunging foil C_T = -cd so its fractional GCI is identical. The forcing period is derived
from the case spec's ``motion.frequency``. Launch detached; writes a JSON report + a RESULT line.

    python scripts/stage13_gci.py plunging_airfoil_hg2007_st02 --host aero-dev \\
        --base-run-dir /mnt/aero-nfs/runs/plunging_airfoil_hg2007_st02-<ts> --skip-temporal
"""

from __future__ import annotations

import argparse
import json
import math
import os
from pathlib import Path

import numpy as np

_REPO_ROOT = Path(__file__).resolve().parents[1]

_FS = 3.0  # ASME V&V 20 safety factor for a 2-grid GCI estimate
_P_SPACE = 2.0  # assumed spatial order (2nd-order FV)
_P_TIME = 1.0  # assumed temporal order (pimpleFoam ~1st order)


def _cycle_mean_cd(run_dir: Path, *, period: float) -> float:
    """Cycle-mean Cd over the converged tail of a completed moving-body run dir."""
    from aero.postprocess._base import Signal
    from aero.postprocess.cycle_detection import detect_cycle_convergence
    from aero.postprocess.phase_averaging import segment_cycles

    path = run_dir / "postProcessing" / "forceCoeffs1" / "0" / "coefficient.dat"
    rows = [
        (float(p[0]), float(p[1]))
        for p in (s.split() for s in path.read_text().splitlines() if s.strip() and s[0] != "#")
    ]
    a = np.asarray(rows, dtype=np.float64)
    # Dedupe non-monotone timestamps (moving-mesh adjustable-dt can re-emit a time).
    _, keep = np.unique(a[:, 0], return_index=True)
    a = a[np.sort(keep)]
    samples = segment_cycles(Signal.from_arrays(a[:, 0], a[:, 1], name="cd"), period=period)
    report = detect_cycle_convergence(samples)
    return float(np.mean(samples.per_cycle_mean[report.converged_from_cycle :]))


def _gci_2grid(cd_fine: float, cd_coarse: float, *, ratio: float, order: float) -> float:
    """2-grid GCI on the fine grid, as a fraction of |cd_fine| (ASME V&V 20, Fs=3.0)."""
    eps = abs(cd_coarse - cd_fine) / max(abs(cd_fine), 1.0e-12)
    return _FS * eps / (ratio**order - 1.0)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("case", help="UNSTEADY_CASES key (e.g. plunging_airfoil_hg2007_st02)")
    ap.add_argument("--host", default="aero-dev")
    ap.add_argument("--timeout", type=int, default=21600)
    ap.add_argument("--base-run-dir", type=Path, required=True, help="Completed base (fine) dir")
    ap.add_argument("--spatial-ratio", type=float, default=1.7)
    ap.add_argument("--temporal-ratio", type=float, default=2.0)
    ap.add_argument("--skip-temporal", action="store_true")
    ap.add_argument("--out", default=None)
    ap.add_argument("--no-mlflow", action="store_true")
    args = ap.parse_args()

    from aero.adapters.openfoam.solver import OpenFOAMSolver
    from aero.orchestration import LocalSSHExecutor
    from aero.provenance import compute_provenance
    from aero.provenance.db import resolve_dsn
    from aero.vv import BenchmarkRunner
    from aero.vv.unsteady import UNSTEADY_CASES

    if args.case not in UNSTEADY_CASES:
        raise SystemExit(f"unknown case {args.case!r}; known: {', '.join(UNSTEADY_CASES)}")
    base = UNSTEADY_CASES[args.case]
    spec = base.case_spec()
    motion = getattr(spec, "motion", None)
    if motion is None:
        raise SystemExit(f"{args.case}: no motion on the spec — GCI needs a forcing period")
    period = 1.0 / motion.frequency

    nfs = Path("/mnt/aero-nfs") if os.path.ismount("/mnt/aero-nfs") else Path("/mnt/aero")
    solver = OpenFOAMSolver(host_nfs_root=nfs, remote_nfs_root=Path("/mnt/aero"))
    executor = LocalSSHExecutor(
        host=args.host, ssh_user="root", repo_root=_REPO_ROOT, long_timeout_s=args.timeout
    )
    runner = BenchmarkRunner(
        solver=solver,
        executor=executor,
        tracking_uri="http://192.168.2.234:5000",
        experiment="aero-provenance",
        db_dsn=None if args.no_mlflow else resolve_dsn(),
        solver_version="OpenFOAM-ESI v2412",
        stage="13",
    )
    prov = compute_provenance(
        repo_root=_REPO_ROOT,
        container_sif="openfoam-esi.sif",
        resolved_config=spec.model_dump(mode="json"),
        allow_dirty=False,
    )

    cd_fine = _cycle_mean_cd(args.base_run_dir, period=period)  # reuse the completed base grid

    obs_s = runner.measure_scalar(
        base.refined(args.spatial_ratio), "cd", provenance=prov, repo_root=_REPO_ROOT
    )
    gci_space = _gci_2grid(cd_fine, obs_s.value, ratio=args.spatial_ratio, order=_P_SPACE)

    gci_time = 0.0
    cd_coarse_dt = None
    if not args.skip_temporal:
        obs_t = runner.measure_scalar(
            base.refined_dt(args.temporal_ratio), "cd", provenance=prov, repo_root=_REPO_ROOT
        )
        cd_coarse_dt = obs_t.value
        gci_time = _gci_2grid(cd_fine, cd_coarse_dt, ratio=args.temporal_ratio, order=_P_TIME)

    u95_num_frac = math.sqrt(gci_space**2 + gci_time**2)
    out = {
        "case": args.case,
        "metric": "cd",
        "method": "2-grid space+time GCI (base reused), ASME V&V 20 Fs=3.0",
        "git_sha": prov.git_sha,
        "cd_fine": cd_fine,
        "base_run_dir": str(args.base_run_dir),
        "spatial": {
            "ratio": args.spatial_ratio,
            "cd_coarse": obs_s.value,
            "order": _P_SPACE,
            "gci_fraction": gci_space,
        },
        "temporal": {
            "ratio": args.temporal_ratio,
            "cd_coarse": cd_coarse_dt,
            "order": _P_TIME,
            "gci_fraction": gci_time,
        },
        "u95_numerical_fraction": u95_num_frac,
        "u95_numerical_abs": u95_num_frac * abs(cd_fine),
    }
    out_path = (
        Path(args.out) if args.out else _REPO_ROOT / "data" / "vv" / f"stage13_gci_{args.case}.json"
    )
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(out, indent=2) + "\n")
    print(
        f"RESULT case={args.case} gci_space={gci_space:.5f} gci_time={gci_time:.5f} "
        f"u95_numerical_frac={u95_num_frac:.5f} cd_fine={cd_fine:.5f} out={out_path}"
    )


if __name__ == "__main__":
    main()
