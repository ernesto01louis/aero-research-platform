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
    ap.add_argument("--case", choices=("laminar", "turbulent"), default="laminar")
    ap.add_argument("--reynolds", type=float, default=5.0e5, help="Re for the turbulent case.")
    ap.add_argument("--aoa", type=float, default=4.0)
    ap.add_argument("--ratio", type=float, default=1.7, help="Constant grid refinement ratio r.")
    ap.add_argument(
        "--finest-mult",
        type=float,
        default=1.0,
        help="Coarsening multiplier of the FINEST grid of the family (1.0=base grid). Use >1 (e.g. "
        "1.7) to report on the finest grid that CONVERGES a loaded design, when the base grid's "
        "wake is mildly unsteady and floors the steady residual.",
    )
    ap.add_argument("--opt-m", type=float, default=_OPT_M, help="Optimum max_camber.")
    ap.add_argument("--opt-p", type=float, default=_OPT_P, help="Optimum camber_position.")
    ap.add_argument("--k", type=float, default=2.0, help="Significance margin (delta > k*U95).")
    ap.add_argument(
        "--end-time",
        type=int,
        default=6000,
        help="simpleFoam iterations; the base grid needs more than the case default to converge "
        "the cambered optimum below the residual tolerance.",
    )
    ap.add_argument(
        "--resid-tol", type=float, default=1.0e-4, help="Converged if p-residual < tol."
    )
    ap.add_argument("--timeout", type=int, default=3600)
    ap.add_argument("--allow-dirty", action="store_true")
    ap.add_argument("--no-mlflow", action="store_true")
    ap.add_argument("--out", default=None)
    ap.add_argument("--diag-out", default=None)
    args = ap.parse_args()

    import numpy as np
    from aero.adapters.openfoam.solver import OpenFOAMSolver
    from aero.optimize.airfoil_case import ShapedLaminarAirfoil
    from aero.optimize.report import MatchedGridDeltaTriplet, compose_result, observed_order
    from aero.optimize.turbulent_airfoil import ShapedTurbulentAirfoil
    from aero.orchestration import LocalSSHExecutor
    from aero.provenance import compute_provenance
    from aero.provenance.db import resolve_dsn
    from aero.vv._base import BenchmarkRunner

    def batch_means_sem(series: tuple[float, ...], n_batches: int = 20) -> float:
        """95% batch-means standard error of the mean of a (limit-cycling) tail series.

        Non-overlapping batch means decorrelate the per-iteration oscillation; the SEM of the batch
        means (x2 for ~95%) is the iterative-convergence uncertainty of the tail-averaged value.
        """
        x = np.asarray(series, dtype=np.float64)
        n = len(x)
        if n < 2 * n_batches:
            n_batches = max(2, n // 2)
        batch = n // n_batches
        if batch < 1:
            return 0.0
        trimmed = x[-batch * n_batches :].reshape(n_batches, batch)
        means = trimmed.mean(axis=1)
        return float(2.0 * means.std(ddof=1) / np.sqrt(n_batches))

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

    # Three grids at a constant ratio r, reported on the finest of the family: fine
    # (base*finest_mult), medium (fine*r), coarse (fine*r^2). finest_mult=1.0 puts the finest at the
    # base grid; finest_mult>1 shifts the whole family coarser so the finest grid is one that still
    # CONVERGES a loaded (mildly-unsteady-wake) design — the base grid floors the steady residual for
    # loaded airfoils, but the medium grid and coarser converge robustly.
    f = args.finest_mult
    grid_mult = {"fine": f, "medium": f * args.ratio, "coarse": f * args.ratio**2}

    turbulent = args.case == "turbulent"

    def make_case(m: float, name: str, mult: float) -> object:
        if turbulent:
            case: object = ShapedTurbulentAirfoil(
                name=name,
                aoa_deg=args.aoa,
                reynolds=args.reynolds,
                max_camber=m,
                camber_position=args.opt_p,
                end_time=args.end_time,
            )
        else:
            base = ShapedLaminarAirfoil(
                name=name, aoa_deg=args.aoa, max_camber=m, camber_position=args.opt_p
            )
            # Raise the iteration budget so the finer grids converge below --resid-tol.
            case = ShapedLaminarAirfoil(
                spec=base.case_spec().model_copy(update={"end_time": args.end_time}), name=name
            )
        return case.refined(mult) if mult != 1.0 else case

    def solve(m: float, design: str, grid: str) -> dict:
        """One solve → tail-mean L/D (turbulent) or steady L/D (laminar) + convergence + provenance."""
        name = f"gm_{design}_{grid}"
        case = make_case(m, name, grid_mult[grid])
        prov = compute_provenance(
            repo_root=_REPO_ROOT,
            container_sif="openfoam-esi.sif",
            resolved_config=case.case_spec().model_dump(mode="json"),
            allow_dirty=args.allow_dirty,
        )
        measured, mesh, result = runner._drive(case)  # prepare->mesh->solve->evaluate (fail-loud)
        resid = float(solver.load(result).final_residual)
        # Turbulent: the steady SIMPLE iteration limit-cycles; the tail-averaged L/D is the value and
        # its batch-means SEM is the iterative-convergence uncertainty. Convergence is judged on that
        # SEM (the mean being well-determined), not the pressure residual (which floors ~1e-3).
        ld_sem = 0.0
        if turbulent:
            _solve, cd_tail, cl_tail = solver.load_time_averaged(result)
            ld_tail = tuple(cl / cd for cl, cd in zip(cl_tail, cd_tail, strict=True) if cd > 0.0)
            ld_sem = batch_means_sem(ld_tail)
            converged = ld_sem < 0.02 * abs(float(measured["ld"]))  # SEM < 2% of L/D
        else:
            converged = resid < args.resid_tol
        row = {
            "design": design,
            "grid": grid,
            "refine_mult": grid_mult[grid],
            "ld": float(measured["ld"]),
            "cd": float(measured["cd"]),
            "cl": float(measured["cl"]),
            "ld_sem": ld_sem,
            "final_residual": resid,
            "converged": converged,
            "n_elements": getattr(mesh, "n_elements", None),
            "provenance": prov.model_dump(mode="json"),
        }
        flag = "OK" if converged else "!! NOT CONVERGED"
        print(
            f"SOLVE {design}/{grid} mult={grid_mult[grid]:.4f} n_el={row['n_elements']} "
            f"L/D={row['ld']:.5f} sem={ld_sem:.4f} resid={resid:.2e} {flag}",
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

    # Iterative-convergence uncertainty of the delta at the reported (finest) grid: RSS of the
    # baseline and optimum tail-mean SEMs (independent solves). Zero for the cleanly-steady laminar
    # case; the turbulent limit-cycle contributes here (folded into u95_delta_numerical, RSS'd with
    # the grid GCI). This is the honest Hard-Rule-12 term for a non-perfectly-converged quantity.
    u95_iter = float((base["fine"]["ld_sem"] ** 2 + opt["fine"]["ld_sem"] ** 2) ** 0.5)

    triplet = MatchedGridDeltaTriplet(
        quantity="lift_to_drag",
        baseline_fine=base["fine"]["ld"],
        baseline_medium=base["medium"]["ld"],
        baseline_coarse=base["coarse"]["ld"],
        optimum_fine=opt["fine"]["ld"],
        optimum_medium=opt["medium"]["ld"],
        optimum_coarse=opt["coarse"]["ld"],
        refinement_ratio=args.ratio,
        u95_delta_iterative=u95_iter,
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
    regime = (
        f"turbulent k-omega SST Re={args.reynolds:.2g} (wall-function, tail-averaged)"
        if turbulent
        else "Re=1000 laminar"
    )
    result, is_go = compose_result(
        case_name="airfoil_opt_naca4",
        objective=(
            f"maximize lift_to_drag at AoA={args.aoa} deg ({regime} NACA-4 camber); "
            "3-grid observed-order GCI on the matched delta"
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
        "regime": regime,
        "method": "ASME V&V 20 3-grid observed-order GCI on the matched-condition L/D delta"
        + ("; tail-averaged forces + batch-means iterative U95" if turbulent else ""),
        "refinement_ratio": args.ratio,
        "aoa_deg": args.aoa,
        "reynolds": args.reynolds if turbulent else 1000.0,
        "u95_delta_grid": triplet.u95_delta_grid,
        "u95_delta_iterative": triplet.u95_delta_iterative,
        "u95_delta_numerical_total": triplet.u95_delta_numerical,
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
