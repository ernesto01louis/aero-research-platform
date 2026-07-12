#!/usr/bin/env python
"""CFD-in-the-loop 2-D airfoil shape optimization — the ASO product (Stage 15).

Runs a direct-CFD Bayesian optimization of a laminar NACA-4 airfoil's shape (camber) to maximize
L/D at fixed AoA, then verifies the incumbent with a matched-grid, held-out CFD campaign and
composes a **CFD-verified improvement delta** (thesis-grade if it clears k*U95, else an honest
NO-GO). Every candidate is CFD-evaluated (Hard Rule 14); clean-tree provenance (P1b).

    python scripts/stage15_airfoil_opt.py --host aero-dev --n-init 6 --n-iter 10 --aoa 4

Launch detached (the BO loop is many minutes of serial solves); writes
data/vv/stage15_optimization_<ts>.json + a RESULT line.
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--host", default="aero-dev")
    ap.add_argument("--case", choices=("laminar", "turbulent"), default="laminar")
    ap.add_argument("--reynolds", type=float, default=5.0e5, help="Re for the turbulent case.")
    ap.add_argument("--end-time", type=int, default=3000, help="SIMPLE iterations per eval.")
    ap.add_argument("--n-init", type=int, default=6, help="Latin-hypercube initial design size.")
    ap.add_argument("--n-iter", type=int, default=10, help="EI-guided BO iterations.")
    ap.add_argument("--aoa", type=float, default=4.0, help="Fixed angle of attack (deg).")
    ap.add_argument("--camber-max", type=float, default=0.08, help="Upper bound on max_camber.")
    ap.add_argument(
        "--refine-ratio", type=float, default=1.7, help="Matched-grid GCI coarsen ratio."
    )
    ap.add_argument("--k", type=float, default=2.0, help="Significance margin (delta > k*U95).")
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--timeout", type=int, default=3600)
    ap.add_argument("--allow-dirty", action="store_true")
    ap.add_argument("--no-mlflow", action="store_true")
    ap.add_argument("--out", default=None)
    args = ap.parse_args()

    from aero.adapters.openfoam.solver import OpenFOAMSolver
    from aero.optimize import BayesianOptimizer, BOConfig, CFDObjective, DesignSpace, DesignVariable
    from aero.optimize.airfoil_case import ShapedLaminarAirfoil
    from aero.optimize.report import MatchedGridDelta, compose_result
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
        stage="15",
    )

    # 2-DV shape space: NACA-4 camber (m, p) on the trusted laminar NACA-0012 at fixed AoA.
    space = DesignSpace(
        variables=(
            DesignVariable(name="max_camber", low=0.0, high=args.camber_max),
            DesignVariable(name="camber_position", low=0.2, high=0.6),
        )
    )

    def make_case(dv: dict[str, float], *, name: str, ratio: float = 1.0) -> object:
        if args.case == "turbulent":
            case: object = ShapedTurbulentAirfoil(
                name=name,
                aoa_deg=args.aoa,
                reynolds=args.reynolds,
                max_camber=dv["max_camber"],
                camber_position=dv["camber_position"],
                end_time=args.end_time,
            )
        else:
            case = ShapedLaminarAirfoil(
                name=name,
                aoa_deg=args.aoa,
                max_camber=dv["max_camber"],
                camber_position=dv["camber_position"],
            )
        return case.refined(ratio) if ratio != 1.0 else case

    objective = CFDObjective(
        space=space,
        make_case=lambda dv: make_case(dv, name="airfoil_opt_eval"),
        runner=runner,
        repo_root=_REPO_ROOT,
        metric="ld",
        allow_dirty=args.allow_dirty,
        log_mlflow=log_mlflow,
    )
    bo = BayesianOptimizer(space, BOConfig(n_init=args.n_init, n_iter=args.n_iter, seed=args.seed))

    # --- BO campaign: every candidate CFD-evaluated (Hard Rule 14) ---
    n_total = args.n_init + args.n_iter
    for i in range(n_total):
        x = bo.ask()
        ev = objective(x)
        bo.tell(x, ev.value, mlflow_run_id=ev.mlflow_run_id)
        print(f"EVAL {i + 1}/{n_total} dv={space.as_named(x)} L/D={ev.value:.4f}", flush=True)
    x_star, ld_star = bo.incumbent
    dv_star = space.as_named(x_star)
    print(f"INCUMBENT dv={dv_star} L/D={ld_star:.4f} (best of {bo.n_candidates})", flush=True)

    # --- matched-grid delta-UQ: baseline (m=0) + optimum, each at fine + coarse ---
    def solve_ld(dv: dict[str, float], name: str, ratio: float) -> tuple[float, object]:
        case = make_case(dv, name=name, ratio=ratio)
        prov = compute_provenance(
            repo_root=_REPO_ROOT,
            container_sif="openfoam-esi.sif",
            resolved_config=case.case_spec().model_dump(mode="json"),
            allow_dirty=args.allow_dirty,
        )
        obs = runner.measure_scalar(
            case, "ld", provenance=prov, repo_root=_REPO_ROOT, log_mlflow=log_mlflow
        )
        return float(obs.value), prov

    baseline_dv = {"max_camber": 0.0, "camber_position": dv_star["camber_position"]}
    ld_base_fine, _ = solve_ld(baseline_dv, "airfoil_base_fine", 1.0)
    ld_base_coarse, _ = solve_ld(baseline_dv, "airfoil_base_coarse", args.refine_ratio)
    ld_opt_fine, heldout_prov = solve_ld(dv_star, "airfoil_opt_fine", 1.0)  # held-out verification
    ld_opt_coarse, _ = solve_ld(dv_star, "airfoil_opt_coarse", args.refine_ratio)

    delta = MatchedGridDelta(
        quantity="lift_to_drag",
        baseline_fine=ld_base_fine,
        baseline_coarse=ld_base_coarse,
        optimum_fine=ld_opt_fine,
        optimum_coarse=ld_opt_coarse,
        refinement_ratio=args.refine_ratio,
    )
    result, is_go = compose_result(
        case_name="airfoil_opt_naca4",
        objective=f"maximize lift_to_drag at AoA={args.aoa} deg (Re=1000 laminar NACA-4 camber)",
        quantity="lift_to_drag",
        higher_is_better=True,
        design_variables=dv_star,
        delta=delta,
        cfd_verified=heldout_prov,
        n_candidates=bo.n_candidates,
        k=args.k,
    )

    out = Path(args.out or _REPO_ROOT / "data" / "vv" / "stage15_optimization.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(result.model_dump_json(indent=2) + "\n")

    print(
        f"RESULT verdict={'GO' if is_go else 'NO-GO'} tag={result.validation_tag} "
        f"baseline_LD={ld_base_fine:.4f} optimum_LD={ld_opt_fine:.4f} "
        f"delta={delta.delta_fine:.4f} u95_delta={delta.u95_delta_numerical:.4f} "
        f"required={args.k * delta.u95_delta_numerical:.4f} "
        f"dv={dv_star} n_candidates={bo.n_candidates} out={out}",
        flush=True,
    )


if __name__ == "__main__":
    main()
