#!/usr/bin/env python
"""Stage-17 own-CFD corpus campaign — the (m, p) → L/D training sweep (ADR-032).

Generates the platform-own training corpus the Stage-17 surrogate certifies against:
a seeded Latin-hypercube sweep over the Stage-15 design space at the campaign grid
(``ShapedTurbulentAirfoil``, k-omega SST, Re=5e5, AoA 4 deg, base mesh), plus two anchor
solves — the m=0 baseline and the Stage-15 optimum — each a ground-truth serial OpenFOAM
solve on aero-dev with four-fold clean-tree provenance.

    python scripts/stage17_corpus.py --host aero-dev --n-lhs 40 --seed 170 --concurrent 4

Campaign constants (pre-registered; part of the ADR-032 protocol):
  design space   m in [0, 0.08], p in [0.2, 0.6]  (Stage-15 bounds, S1)
  LHS            n=40, seed=170
  anchors        baseline (0.0, 0.20448957451063046)
                 stage-15 optimum (0.07273510933006024, 0.20448957451063046)
  case           turbulent, Re=5e5, AoA=4.0, end_time=3000 (base grid)

Failed solves are recorded as evidence rows (failed=True + the failure signature),
never silently dropped (Stage-16 gotcha: worker exceptions must land in the bundle).
Writes the corpus bundle at END only (untracked files count as dirty for provenance —
commit code first, run, then commit + `dvc add` the artifact).
"""

from __future__ import annotations

import argparse
import os
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]

BASELINE_ANCHOR = {"max_camber": 0.0, "camber_position": 0.20448957451063046}
OPTIMUM_ANCHOR = {
    "max_camber": 0.07273510933006024,
    "camber_position": 0.20448957451063046,
}


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--host", default="aero-dev")
    ap.add_argument("--n-lhs", type=int, default=40)
    ap.add_argument("--seed", type=int, default=170)
    ap.add_argument("--concurrent", type=int, default=4, help="Independent serial solves.")
    ap.add_argument("--reynolds", type=float, default=5.0e5)
    ap.add_argument("--aoa", type=float, default=4.0)
    ap.add_argument("--end-time", type=int, default=3000)
    ap.add_argument("--camber-max", type=float, default=0.08)
    ap.add_argument("--timeout", type=int, default=14400)
    ap.add_argument(
        "--extend-tag",
        default=None,
        help="Suffix for a pre-registered corpus "
        "extension batch (contingency: extend BEFORE any speed-up arm runs).",
    )
    ap.add_argument("--allow-dirty", action="store_true")
    ap.add_argument("--no-mlflow", action="store_true")
    ap.add_argument("--out", default=None)
    args = ap.parse_args()

    import numpy as np
    from aero.adapters.openfoam.solver import OpenFOAMSolver
    from aero.optimize import DesignSpace, DesignVariable
    from aero.optimize.corpus import CorpusRow, Stage17Corpus, save_corpus
    from aero.optimize.turbulent_airfoil import ShapedTurbulentAirfoil
    from aero.orchestration import LocalSSHExecutor
    from aero.provenance import compute_provenance
    from aero.provenance.db import resolve_dsn
    from aero.vv._base import BenchmarkRunner

    log_mlflow = not args.no_mlflow
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
        db_dsn=resolve_dsn() if log_mlflow else "unused",
        solver_version="OpenFOAM-ESI v2412",
        stage="17",
    )

    space = DesignSpace(
        variables=(
            DesignVariable(name="max_camber", low=0.0, high=args.camber_max),
            DesignVariable(name="camber_position", low=0.2, high=0.6),
        )
    )

    tag = f"_{args.extend_tag}" if args.extend_tag else ""
    points: list[tuple[str, dict[str, float]]] = [
        (f"s17c{tag}_base", BASELINE_ANCHOR),
        (f"s17c{tag}_opt15", OPTIMUM_ANCHOR),
    ]
    for i, x in enumerate(space.lhs(args.n_lhs, seed=args.seed)):
        points.append((f"s17c{tag}_{i:02d}", space.as_named(np.asarray(x))))

    prov_lock = threading.Lock()  # serialize git reads (index.lock race — Stage-16 gotcha)

    def solve_one(job: tuple[str, dict[str, float]]) -> CorpusRow:
        name, dv = job
        x = np.asarray([dv[v] for v in space.names], dtype=np.float64)
        case = ShapedTurbulentAirfoil(
            name=name,
            aoa_deg=args.aoa,
            reynolds=args.reynolds,
            max_camber=dv["max_camber"],
            camber_position=dv["camber_position"],
            end_time=args.end_time,
        )
        t0 = time.monotonic()
        try:
            with prov_lock:
                prov = compute_provenance(
                    repo_root=_REPO_ROOT,
                    container_sif="openfoam-esi.sif",
                    resolved_config=case.case_spec().model_dump(mode="json"),
                    allow_dirty=args.allow_dirty,
                )
            obs = runner.measure_scalar(
                case, "ld", provenance=prov, repo_root=_REPO_ROOT, log_mlflow=log_mlflow
            )
            row = CorpusRow(
                case_name=name,
                design_named=dv,
                design_unit=tuple(float(v) for v in space.to_unit(x)),
                ld=float(obs.value),
                mlflow_run_id=obs.mlflow_run_id,
                provenance=prov,
                wall_s=time.monotonic() - t0,
            )
            print(f"SOLVE {name} dv={dv} L/D={obs.value:.4f} wall={row.wall_s:.0f}s", flush=True)
            return row
        except Exception as exc:
            with prov_lock:
                prov = compute_provenance(
                    repo_root=_REPO_ROOT,
                    container_sif="openfoam-esi.sif",
                    resolved_config=case.case_spec().model_dump(mode="json"),
                    allow_dirty=True,  # provenance of a failed row must never abort the campaign
                )
            print(f"FAIL  {name} dv={dv} error={type(exc).__name__}: {exc}", flush=True)
            return CorpusRow(
                case_name=name,
                design_named=dv,
                design_unit=tuple(float(v) for v in space.to_unit(x)),
                failed=True,
                error=f"{type(exc).__name__}: {exc}",
                provenance=prov,
                wall_s=time.monotonic() - t0,
            )

    with ThreadPoolExecutor(max_workers=args.concurrent) as pool:
        rows = list(pool.map(solve_one, points))

    corpus = Stage17Corpus(
        dataset_id="stage17-naca4-ld",
        space=space,
        reynolds=args.reynolds,
        aoa_deg=args.aoa,
        end_time=float(args.end_time),
        seed=args.seed,
        n_lhs=args.n_lhs,
        created_at=datetime.now(UTC).isoformat(),
        rows=tuple(rows),
    )
    out = Path(
        args.out or _REPO_ROOT / "data" / "datasets" / "stage17_naca4_ld" / f"corpus{tag}.json"
    )
    save_corpus(corpus, out)

    ok = corpus.ok_rows
    lds = sorted(r.ld for r in ok if r.ld is not None)
    print(
        f"RESULT n_solves={len(rows)} n_ok={len(ok)} n_failed={len(rows) - len(ok)} "
        f"ld_range=[{lds[0]:.3f}, {lds[-1]:.3f}] out={out}",
        flush=True,
    )
    print("NEXT: dvc add the artifact, commit, dvc push (clean tree before any arm runs).")


if __name__ == "__main__":
    main()
