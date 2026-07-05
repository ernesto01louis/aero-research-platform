#!/usr/bin/env python
"""Oscillating-cylinder combined space+time GCI for the Stage-12 ``u95_numerical`` (clean-SHA).

Computes the discretization uncertainty of the cycle-mean drag ``Cd`` of the lock-in cylinder:

  * **spatial** — a 3-grid ASME V&V 20 GCI (mesh refinement 1.0/1.3/1.7 at fixed Courant), via
    :class:`aero.vv.mesh_sweep.MeshSweep` on ``metric="cd"``;
  * **temporal** — a 2-grid bound at the fine mesh (``max_courant`` 0.5 vs a coarser cap), since
    the moving-cylinder timestep is Courant-driven and :meth:`refined` cannot touch it
    (:meth:`OscillatingCylinderLockin.refined_dt`);

then RSS's the two into ``u95_numerical`` (a fraction of the fine-grid ``Cd``). Each moving solve
is ~30-84 min serial (MPI is blocked in the LXC), so this is meant to be launched DETACHED and
polled. Writes a JSON report and prints a single machine-parseable RESULT line.

    python scripts/stage12_cylinder_gci.py --host aero-dev

Clean-SHA provenance (``allow_dirty=False``): commit the tree before launching (the Stage-11
runs used ``--allow-dirty``; Stage 12 reconciles to a clean SHA).
"""

from __future__ import annotations

import argparse
import json
import math
import os
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]

# ASME V&V 20 safety factor for a 2-grid GCI estimate (3-grid would use 1.25); the temporal arm
# is a conservative 2-level bound. pimpleFoam time integration is treated as ~1st order.
_TEMPORAL_FS = 3.0
_TEMPORAL_ORDER = 1.0


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--host", default="aero-dev", help="SSH host alias (default aero-dev)")
    ap.add_argument("--timeout", type=int, default=14400, help="Per-solve poll ceiling, s (4h)")
    ap.add_argument(
        "--temporal-ratio", type=float, default=2.0, help="Coarse-dt Courant multiple (fine=1.0)"
    )
    ap.add_argument(
        "--out",
        default=str(_REPO_ROOT / "data" / "vv" / "stage12_cylinder_gci.json"),
        help="Where to write the GCI JSON report",
    )
    ap.add_argument("--no-mlflow", action="store_true")
    args = ap.parse_args()

    from aero.adapters.openfoam.solver import OpenFOAMSolver
    from aero.orchestration import LocalSSHExecutor
    from aero.provenance import compute_provenance
    from aero.provenance.db import resolve_dsn
    from aero.vv import BenchmarkRunner
    from aero.vv.mesh_sweep import MeshSweep
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

    # --- spatial 3-grid GCI on cycle-mean Cd -------------------------------------------------
    sweep = MeshSweep(base, metric="cd", refinement_ratios=(1.0, 1.3, 1.7))
    report = sweep.run(runner, provenance=prov, repo_root=_REPO_ROOT)
    cd_fine = report.grids[0].metric_value
    gci_space = report.apparent_uncertainty  # fraction on the fine grid

    # --- temporal 2-grid bound at the fine mesh ----------------------------------------------
    coarse_dt_case = base.refined_dt(args.temporal_ratio)  # larger max_courant -> coarser dt
    obs_t = runner.measure_scalar(coarse_dt_case, "cd", provenance=prov, repo_root=_REPO_ROOT)
    cd_coarse_dt = obs_t.value
    eps_t = abs(cd_coarse_dt - cd_fine) / max(abs(cd_fine), 1.0e-12)
    gci_time = _TEMPORAL_FS * eps_t / (args.temporal_ratio**_TEMPORAL_ORDER - 1.0)

    u95_num_frac = math.sqrt(gci_space**2 + gci_time**2)
    out = {
        "case": "oscillating_cylinder_lockin",
        "metric": "cd",
        "git_sha": prov.git_sha,
        "cd_fine": cd_fine,
        "spatial": {
            "gci_fraction": gci_space,
            "gci_pct": report.gci_fine_pct,
            "observed_order_p": report.observed_order_p,
            "extrapolated_value": report.extrapolated_value,
            "monotonic": report.monotonic,
            "grids": [
                {
                    "ratio": g.refinement_ratio,
                    "n_cells": g.n_cells,
                    "cd": g.metric_value,
                    "mlflow_run_id": g.mlflow_run_id,
                }
                for g in report.grids
            ],
        },
        "temporal": {
            "ratio": args.temporal_ratio,
            "cd_coarse_dt": cd_coarse_dt,
            "gci_fraction": gci_time,
            "fs": _TEMPORAL_FS,
            "assumed_order": _TEMPORAL_ORDER,
            "mlflow_run_id": obs_t.mlflow_run_id,
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
