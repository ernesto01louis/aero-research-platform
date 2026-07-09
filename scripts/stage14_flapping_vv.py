#!/usr/bin/env python
"""Drive a moving-body / flapping V&V case end-to-end with a long executor timeout.

The Stage-14 generalisation of ``scripts/stage11_moving_vv.py``: it resolves the case from the
merged ``{**UNSTEADY_CASES, **FLAPPING_CASES}`` registry, so the flapping hover cases (which run
for hours — a 24-cycle solve is ~4-8 h serial, MPI being blocked in the LXC) run through the
same ``BenchmarkRunner`` (same four-fold provenance + MLflow) with a multi-hour poll ceiling.

Unlike the Stage-11 driver this defaults to **clean-tree provenance** (``allow_dirty=False``):
a thesis-grade flapping ReportableResult must not carry a ``-dirty`` SHA (review P1b), so the
campaign runs from a committed tree and fails loud at launch otherwise. ``--allow-dirty`` opts
into an explicit exploratory/smoke run.

Launch detached (``scripts/run_long.sh``) and poll ``/mnt/aero/runs``; prints one RESULT line.

    python scripts/stage14_flapping_vv.py flapping_wing_wbd2004 --host aero-dev --timeout 43200
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("case", help="FLAPPING_CASES or UNSTEADY_CASES key, e.g. flapping_wing_wbd2004")
    ap.add_argument(
        "--host", default="aero-dev", help="SSH host alias (default aero-dev, 16 cores)"
    )
    ap.add_argument("--timeout", type=int, default=43200, help="Long-job poll ceiling, s (12h)")
    ap.add_argument(
        "--allow-dirty",
        action="store_true",
        help="Permit a dirty-tree (-dirty) SHA — exploratory/smoke only, never thesis-grade.",
    )
    ap.add_argument("--no-mlflow", action="store_true", help="Skip MLflow logging (report only)")
    args = ap.parse_args()

    from aero.adapters.openfoam.solver import OpenFOAMSolver
    from aero.orchestration import LocalSSHExecutor
    from aero.provenance import compute_provenance
    from aero.provenance.db import resolve_dsn
    from aero.vv import BenchmarkRunner
    from aero.vv.flapping import FLAPPING_CASES
    from aero.vv.unsteady import UNSTEADY_CASES

    registry = {**UNSTEADY_CASES, **FLAPPING_CASES}
    if args.case not in registry:
        raise SystemExit(f"unknown case {args.case!r}; known: {', '.join(registry)}")
    case = registry[args.case]

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
        stage="14",
    )
    spec = case.case_spec()
    provenance = compute_provenance(
        repo_root=_REPO_ROOT,
        container_sif="openfoam-esi.sif",
        resolved_config=spec.model_dump(mode="json"),
        allow_dirty=args.allow_dirty,
    )
    result = runner.run(
        case, provenance=provenance, repo_root=_REPO_ROOT, log_mlflow=not args.no_mlflow
    )
    m = result.metrics[0]
    print(
        f"RESULT case={args.case} status={result.status} metric={m.name} "
        f"measured={m.measured} reference={m.reference} error={m.error:.4f} "
        f"tol={m.tolerance} mlflow_run={result.mlflow_run_id}"
    )


if __name__ == "__main__":
    main()
