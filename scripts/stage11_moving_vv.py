#!/usr/bin/env python
"""Drive a Stage-11 moving-body V&V case end-to-end with a long executor timeout.

The oscillating-cylinder / plunging-airfoil solves exceed the default 30-min executor
poll ceiling (`LocalSSHExecutor.long_timeout_s`), so `aero vv run` would time out. This
constructs the same `BenchmarkRunner` (same provenance four-tuple + MLflow logging) with a
multi-hour timeout and runs it. Intended to be launched as a detached background job and
polled; prints a single machine-parseable RESULT line at the end.

    python scripts/stage11_moving_vv.py oscillating_cylinder_lockin --host aero-dev

Uses `--allow-dirty` provenance (the in-flight Stage-11 branch); reconcile to a clean SHA in
the Stage-11 rigor follow-ups (the Stage-10 pattern).
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("case", help="UNSTEADY_CASES key, e.g. oscillating_cylinder_lockin")
    ap.add_argument(
        "--host", default="aero-dev", help="SSH host alias (default aero-dev, 16 cores)"
    )
    ap.add_argument("--timeout", type=int, default=14400, help="Long-job poll ceiling, s (4h)")
    ap.add_argument("--no-mlflow", action="store_true", help="Skip MLflow logging (report only)")
    args = ap.parse_args()

    from aero.adapters.openfoam.solver import OpenFOAMSolver
    from aero.orchestration import LocalSSHExecutor
    from aero.provenance import compute_provenance
    from aero.provenance.db import resolve_dsn
    from aero.vv import BenchmarkRunner
    from aero.vv.unsteady import UNSTEADY_CASES

    if args.case not in UNSTEADY_CASES:
        raise SystemExit(f"unknown case {args.case!r}; known: {', '.join(UNSTEADY_CASES)}")
    case = UNSTEADY_CASES[args.case]

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
        stage="11",
    )
    spec = case.case_spec()
    provenance = compute_provenance(
        repo_root=_REPO_ROOT,
        container_sif="openfoam-esi.sif",
        resolved_config=spec.model_dump(mode="json"),
        allow_dirty=True,
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
