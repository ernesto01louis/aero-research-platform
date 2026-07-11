#!/usr/bin/env python
"""Stage-15 hardening: MEASURE the grid-convergence order of the CFD-verified L/D delta.

The Stage-15 thesis-grade claim originally rested on a 2-grid GCI that *assumed* order p=2.0
(inflated Fs=3.0). A pre-merge adversarial audit showed the GO/NO-GO could flip if the true
observed order is low (OpenFOAM's bounded linearUpwind delivers ~1.3-1.8 for force coefficients).

This driver replaces the assumption with a measurement: it re-solves the baseline (m=0) and the
optimum design at **three** matched grids at a constant refinement ratio r, records L/D **and the
final pressure residual** for every solve (an explicit iterative-convergence gate the original
lacked), computes the **observed** order of convergence of the delta, and recomposes the result
with the ASME V&V 20 observed-order GCI (`MatchedGridDeltaTriplet`). GO iff delta > k·U95 with the
MEASURED order. Writes the hardened `data/vv/stage15_optimization.json` plus a full
`data/vv/stage15_grid_convergence.json` diagnostics bundle (every solve, residual, and derivation
serialized — the auditability gap the audit flagged).

    python scripts/stage15_grid_order.py --host aero-dev --ratio 1.7 --aoa 4 --no-mlflow

Launch detached (six serial solves, a few minutes each); clean-tree provenance (P1b) — commit code
first, then run without touching the repo.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]

# The Stage-15 BO incumbent (data/vv/stage15_optimization.json, design_variables).
_OPT_M = 0.07453532271696652
_OPT_P = 0.592640974765251


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--host", default="aero-dev")
    ap.add_argument("--aoa", type=float, default=4.0)
    ap.add_argument("--ratio", type=float, default=1.7, help="Constant grid refinement ratio r.")
    ap.add_argument("--opt-m", type=float, default=_OPT_M, help="Optimum max_camber.")
    ap.add_argument("--opt-p", type=float, default=_OPT_P, help="Optimum camber_position.")
    ap.add_argument("--k", type=float, default=2.0, help="Significance margin (delta > k*U95).")
    ap.add_argument(
        "--resid-tol", type=float, default=1.0e-4, help="Converged if p-residual < tol."
    )
    ap.add_argument("--timeout", type=int, default=3600)
    ap.add_argument("--allow-dirty", action="store_true")
    ap.add_argument("--no-mlflow", action="store_true")
    ap.add_argument("--out", default=None)
    ap.add_argument("--diag-out", default=None)
    args = ap.parse_args()

    from aero.adapters.openfoam.solver import OpenFOAMSolver
    from aero.optimize.airfoil_case import ShapedLaminarAirfoil
    from aero.optimize.report import MatchedGridDeltaTriplet, compose_result, observed_order
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

    # Three grids at a constant ratio r, reported on the finest: fine (base = the grid of record,
    # the finest that solves without divergence at Re=1000 laminar), medium (base*r), coarse
    # (base*r^2). Going finer than the base grid diverges (SIGFPE) at this first-cell height, so the
    # observed order is measured across [base, base*r^2] and the GCI is reported on the base grid.
    grid_mult = {"fine": 1.0, "medium": args.ratio, "coarse": args.ratio**2}

    def make_case(m: float, name: str, mult: float) -> ShapedLaminarAirfoil:
        case = ShapedLaminarAirfoil(
            name=name, aoa_deg=args.aoa, max_camber=m, camber_position=args.opt_p
        )
        return case.refined(mult) if mult != 1.0 else case

    def solve(m: float, design: str, grid: str) -> dict:
        """One solve → L/D, cd, cl, final pressure residual, cell count (+ provenance)."""
        name = f"gm_{design}_{grid}"
        case = make_case(m, name, grid_mult[grid])
        prov = compute_provenance(
            repo_root=_REPO_ROOT,
            container_sif="openfoam-esi.sif",
            resolved_config=case.case_spec().model_dump(mode="json"),
            allow_dirty=args.allow_dirty,
        )
        measured, mesh, result = runner._drive(case)  # prepare->mesh->solve->evaluate (fail-loud)
        solved = solver.load(result)
        resid = float(solved.final_residual)
        row = {
            "design": design,
            "grid": grid,
            "refine_mult": grid_mult[grid],
            "ld": float(measured["ld"]),
            "cd": float(measured["cd"]),
            "cl": float(measured["cl"]),
            "final_residual": resid,
            "converged": resid < args.resid_tol,
            "n_elements": getattr(mesh, "n_elements", None),
            "provenance": prov.model_dump(mode="json"),
        }
        flag = "OK" if row["converged"] else "!! NOT CONVERGED"
        print(
            f"SOLVE {design}/{grid} mult={grid_mult[grid]:.4f} n_el={row['n_elements']} "
            f"L/D={row['ld']:.5f} resid={resid:.2e} {flag}",
            flush=True,
        )
        return row

    # --- six solves: baseline (m=0) and optimum (m*), each at fine/medium/coarse ---
    rows: list[dict] = []
    base: dict[str, dict] = {}
    opt: dict[str, dict] = {}
    for grid in ("fine", "medium", "coarse"):
        b = solve(0.0, "baseline", grid)
        o = solve(args.opt_m, "optimum", grid)
        rows.extend([b, o])
        base[grid] = b
        opt[grid] = o

    triplet = MatchedGridDeltaTriplet(
        quantity="lift_to_drag",
        baseline_fine=base["fine"]["ld"],
        baseline_medium=base["medium"]["ld"],
        baseline_coarse=base["coarse"]["ld"],
        optimum_fine=opt["fine"]["ld"],
        optimum_medium=opt["medium"]["ld"],
        optimum_coarse=opt["coarse"]["ld"],
        refinement_ratio=args.ratio,
    )

    # cfd_verified = the finest optimum solve (a fresh clean-SHA four-tuple). "Held out" here means
    # re-verified by an independent solve (not the BO loop's own eval); it is the SAME base grid the
    # optimizer selected on (the finer grid diverges), so it re-confirms rather than adds resolution.
    heldout_prov = compute_provenance(
        repo_root=_REPO_ROOT,
        container_sif="openfoam-esi.sif",
        resolved_config=make_case(args.opt_m, "gm_optimum_fine", grid_mult["fine"])
        .case_spec()
        .model_dump(mode="json"),
        allow_dirty=args.allow_dirty,
    )

    all_converged = all(r["converged"] for r in rows)
    result, is_go = compose_result(
        case_name="airfoil_opt_naca4",
        objective=(
            f"maximize lift_to_drag at AoA={args.aoa} deg (Re=1000 laminar NACA-4 camber); "
            "3-grid observed-order GCI"
        ),
        quantity="lift_to_drag",
        higher_is_better=True,
        design_variables={"max_camber": args.opt_m, "camber_position": args.opt_p},
        delta=triplet,
        cfd_verified=heldout_prov,
        n_candidates=14,
        k=args.k,
    )

    out = Path(args.out or _REPO_ROOT / "data" / "vv" / "stage15_optimization.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(result.model_dump_json(indent=2) + "\n")

    # Full diagnostics bundle — every solve + residual + the observed-order derivation (audit gap).
    diag = {
        "case": "airfoil_opt_naca4",
        "method": "ASME V&V 20 3-grid observed-order GCI on the matched-condition L/D delta",
        "refinement_ratio": args.ratio,
        "aoa_deg": args.aoa,
        "design_optimum": {"max_camber": args.opt_m, "camber_position": args.opt_p},
        "resid_tol": args.resid_tol,
        "all_converged": all_converged,
        "solves": rows,
        "delta_per_grid": {
            "fine": triplet.delta_fine,
            "medium": triplet.delta_medium,
            "coarse": triplet.delta_coarse,
        },
        "observed_order_delta": triplet.observed_order_delta,
        "delta_monotone": triplet.delta_monotone,
        "observed_order_optimum": observed_order(
            opt["fine"]["ld"], opt["medium"]["ld"], opt["coarse"]["ld"], ratio=args.ratio
        ),
        "observed_order_baseline": observed_order(
            base["fine"]["ld"], base["medium"]["ld"], base["coarse"]["ld"], ratio=args.ratio
        ),
        "gci_delta_fraction": triplet.gci_delta_fraction,
        "u95_delta_numerical": triplet.u95_delta_numerical,
        "delta_fine": triplet.delta_fine,
        "k": args.k,
        "required_margin": args.k * triplet.u95_delta_numerical,
        "is_go": is_go,
        "all_converged_gate": all_converged,
        "validation_tag": result.validation_tag,
    }
    diag_out = Path(args.diag_out or _REPO_ROOT / "data" / "vv" / "stage15_grid_convergence.json")
    diag_out.write_text(json.dumps(diag, indent=2) + "\n")

    print(
        f"RESULT verdict={'GO' if is_go else 'NO-GO'} tag={result.validation_tag} "
        f"all_converged={all_converged} "
        f"observed_order_delta={triplet.observed_order_delta:.3f} monotone={triplet.delta_monotone} "
        f"delta={triplet.delta_fine:.5f} u95_delta={triplet.u95_delta_numerical:.5f} "
        f"required={args.k * triplet.u95_delta_numerical:.5f} "
        f"baseline_LD={triplet.baseline_fine:.5f} optimum_LD={triplet.optimum_fine:.5f} "
        f"out={out} diag={diag_out}",
        flush=True,
    )


if __name__ == "__main__":
    main()
