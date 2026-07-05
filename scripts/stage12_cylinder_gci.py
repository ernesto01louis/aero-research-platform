#!/usr/bin/env python
"""Oscillating-cylinder combined space+time GCI for the Stage-12 ``u95_numerical`` (clean-SHA).

Computes the discretization uncertainty of the cycle-mean drag ``Cd`` of the lock-in cylinder as
``u95_numerical = RSS(gci_space, gci_time)``. To keep it tractable (each moving solve is ~30-84 min
serial — MPI is blocked in the LXC) the **completed base grid is reused** (``--base-run-dir``) and
only the coarser grids are solved:

  * **spatial** — a 2-grid GCI: base (fine) vs a coarser mesh (``refined(spatial_ratio)``);
  * **temporal** — a 2-grid GCI: base vs a coarser Courant cap (``refined_dt(temporal_ratio)``,
    since the moving timestep is Courant-driven and ``refined()`` cannot touch it).

Each 2-grid GCI uses ASME V&V 20's 2-grid safety factor (Fs=3.0) with an assumed order ``p``
(2 spatial / 1 temporal). ``Cd`` (not the frequency-locked Strouhal) is the Richardson target.
Launch detached; writes a JSON report + a machine-parseable RESULT line.

    python scripts/stage12_cylinder_gci.py --host aero-dev \\
        --base-run-dir /mnt/aero-nfs/runs/oscillating_cylinder_lockin-<ts>
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
_FORCING_ST = 1.1 * 0.165


def _cycle_mean_cd(run_dir: Path) -> float:
    """Cycle-mean Cd over the converged tail of a completed moving-cylinder run dir."""
    from aero.postprocess._base import Signal
    from aero.postprocess.cycle_detection import detect_cycle_convergence
    from aero.postprocess.phase_averaging import segment_cycles

    path = run_dir / "postProcessing" / "forceCoeffs1" / "0" / "coefficient.dat"
    rows = [
        (float(p[0]), float(p[1]))
        for p in (s.split() for s in path.read_text().splitlines() if s.strip() and s[0] != "#")
    ]
    a = np.asarray(rows, dtype=np.float64)
    samples = segment_cycles(
        Signal.from_arrays(a[:, 0], a[:, 1], name="cd"), period=1.0 / _FORCING_ST
    )
    report = detect_cycle_convergence(samples)
    return float(np.mean(samples.per_cycle_mean[report.converged_from_cycle :]))


def _gci_2grid(cd_fine: float, cd_coarse: float, *, ratio: float, order: float) -> float:
    """2-grid GCI on the fine grid, as a fraction of |cd_fine| (ASME V&V 20, Fs=3.0)."""
    eps = abs(cd_coarse - cd_fine) / max(abs(cd_fine), 1.0e-12)
    return _FS * eps / (ratio**order - 1.0)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--host", default="aero-dev")
    ap.add_argument("--timeout", type=int, default=14400)
    ap.add_argument(
        "--base-run-dir", type=Path, required=True, help="Completed base (fine) grid dir"
    )
    ap.add_argument("--spatial-ratio", type=float, default=1.7)
    ap.add_argument("--temporal-ratio", type=float, default=2.0)
    ap.add_argument("--skip-temporal", action="store_true")
    ap.add_argument("--out", default=str(_REPO_ROOT / "data" / "vv" / "stage12_cylinder_gci.json"))
    ap.add_argument("--no-mlflow", action="store_true")
    args = ap.parse_args()

    from aero.adapters.openfoam.solver import OpenFOAMSolver
    from aero.orchestration import LocalSSHExecutor
    from aero.provenance import compute_provenance
    from aero.provenance.db import resolve_dsn
    from aero.vv import BenchmarkRunner
    from aero.vv.unsteady import OscillatingCylinderLockin

    base = OscillatingCylinderLockin()
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
        stage="12",
    )
    prov = compute_provenance(
        repo_root=_REPO_ROOT,
        container_sif="openfoam-esi.sif",
        resolved_config=base.case_spec().model_dump(mode="json"),
        allow_dirty=False,
    )

    cd_fine = _cycle_mean_cd(args.base_run_dir)  # reuse the completed base grid

    # spatial coarse grid
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
        "case": "oscillating_cylinder_lockin",
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
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(out, indent=2) + "\n")
    print(
        f"RESULT gci_space={gci_space:.5f} gci_time={gci_time:.5f} "
        f"u95_numerical_frac={u95_num_frac:.5f} cd_fine={cd_fine:.5f} out={out_path}"
    )


if __name__ == "__main__":
    main()
