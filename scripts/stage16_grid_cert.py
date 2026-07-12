#!/usr/bin/env python
"""Stage-16: certify the airfoil optimum's L/D delta on a GRADED (fixed-mapping) grid family.

Stage 15's matched-delta failed grid convergence: its `refined()` family pinned every first
cell while scaling counts, so the stretching mapping drifted grid-to-grid (the coarse grids
carry the STEEP cells — the Stage-15 handoff's "steepening" one-liner is directionally wrong;
ADR-028) and the base 80² grid was the finest that solved. This driver runs the baseline (m=0)
and the optimum design on the Stage-16 graded family (pinned end-to-end expansion; first cells
scale ~1/ratio; grids nest) with the FINEST grid INCLUDED, and composes the 3-grid
observed-order GCI on the matched delta (`MatchedGridDeltaTriplet`).

The verdict is HARD-GATED (`certification_gates`): GO requires significance (delta > k·U95)
AND every claim solve converged AND a monotone delta AND an observed order inside the
asymptotic range — the Stage-15 driver recorded `all_converged` but did not gate on it. A
demotion writes the honest NO-GO composition; nothing ever relaxes `k`, drops the finest grid,
or hand-enters a U95 term (Hard Rules 12/14; .claude/rules/optimization-integrity.md).

    # certification campaign (8 solves: 4 grids x baseline+optimum, finest 136² included)
    python scripts/stage16_grid_cert.py --host aero-dev --case turbulent \
        --opt-m 0.07273510933 --opt-p 0.20448957451 --no-mlflow

    # divergence diagnostic (old drifting-mapping family; evidence for ADR-028)
    python scripts/stage16_grid_cert.py --host aero-dev --case turbulent \
        --opt-m 0.07273510933 --opt-p 0.20448957451 --diag --no-mlflow

Launch detached (scripts/run_long.sh); clean-tree provenance — commit code first, then run
without touching the repo.
"""

from __future__ import annotations

import argparse
import json
import os
import re
from pathlib import Path
from typing import Any

_REPO_ROOT = Path(__file__).resolve().parents[1]

# The Stage-15 turbulent BO incumbent (data/vv/stage15_optimization.json, design_variables).
_GRID_LABELS = ("fine", "medium", "coarse", "coarsest")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--host", default="aero-dev")
    ap.add_argument("--case", choices=("laminar", "turbulent"), default="turbulent")
    ap.add_argument("--reynolds", type=float, default=5.0e5, help="Re for the turbulent case.")
    ap.add_argument("--aoa", type=float, default=4.0)
    ap.add_argument("--ratio", type=float, default=1.7, help="Constant grid refinement ratio r.")
    ap.add_argument(
        "--finest-mult",
        type=float,
        default=1.0 / 1.7,
        help="Coarsening multiplier of the FINEST grid (default 1/1.7: one refinement FINER than "
        "the base 80² grid — the family the Stage-15 audit demanded, finest grid included).",
    )
    ap.add_argument(
        "--n-grids",
        type=int,
        choices=(3, 4),
        default=4,
        help="3 = the claim triplet only; 4 adds a coarser 4th grid for an overlapping-triplet "
        "order-stability check (evidence only — the claim NEVER moves off the finest three).",
    )
    ap.add_argument("--opt-m", type=float, required=True, help="Optimum max_camber (REQUIRED).")
    ap.add_argument(
        "--opt-p", type=float, required=True, help="Optimum camber_position (REQUIRED)."
    )
    ap.add_argument("--k", type=float, default=2.0, help="Significance margin (delta > k*U95).")
    ap.add_argument("--end-time", type=int, default=6000, help="simpleFoam iteration budget.")
    ap.add_argument(
        "--resid-tol", type=float, default=1.0e-4, help="Laminar: converged if p-resid < tol."
    )
    ap.add_argument(
        "--no-graded",
        dest="graded",
        action="store_false",
        help="Use the Stage-15 count-only (drifting-mapping) family — diagnostics only.",
    )
    ap.add_argument(
        "--diag",
        action="store_true",
        help="Divergence diagnostic instead of the campaign: checkMesh the old-family 28²/136² "
        "and the graded 136², then solve the old-family 136² optimum and record the failure "
        "signature (ADR-028 evidence).",
    )
    ap.add_argument("--n-candidates", type=int, default=14, help="BO pool size (best-of-N).")
    ap.add_argument("--timeout", type=int, default=7200)
    ap.add_argument("--allow-dirty", action="store_true")
    ap.add_argument("--no-mlflow", action="store_true")
    ap.add_argument("--out", default=None)
    ap.add_argument("--diag-out", default=None)
    args = ap.parse_args()

    import numpy as np
    from aero.adapters._base import build_apptainer_exec
    from aero.adapters.openfoam._foam_common import cell_ratio, expansion
    from aero.adapters.openfoam.solver import OpenFOAMSolver
    from aero.optimize.airfoil_case import ShapedLaminarAirfoil
    from aero.optimize.report import (
        MatchedGridDeltaTriplet,
        certification_gates,
        compose_result,
        nogo_result,
        observed_order,
    )
    from aero.optimize.turbulent_airfoil import ShapedTurbulentAirfoil
    from aero.orchestration import LocalSSHExecutor
    from aero.provenance import compute_provenance
    from aero.vv._base import BenchmarkError

    def batch_means_sem(series: tuple[float, ...], n_batches: int = 20) -> float:
        """95% batch-means standard error of the mean of a (limit-cycling) tail series."""
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

    nfs = Path("/mnt/aero-nfs") if os.path.ismount("/mnt/aero-nfs") else Path("/mnt/aero")
    solver = OpenFOAMSolver(host_nfs_root=nfs, remote_nfs_root=Path("/mnt/aero"))
    executor = LocalSSHExecutor(
        host=args.host, ssh_user="root", repo_root=_REPO_ROOT, long_timeout_s=args.timeout
    )

    turbulent = args.case == "turbulent"

    def make_case(m: float, name: str, mult: float, *, graded: bool) -> Any:
        if turbulent:
            case: Any = ShapedTurbulentAirfoil(
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
            case = ShapedLaminarAirfoil(
                spec=base.case_spec().model_copy(update={"end_time": args.end_time}), name=name
            )
        return case.refined(mult, graded=graded) if mult != 1.0 else case

    def grading_of(spec: Any) -> dict[str, float]:
        """The family's mapping fingerprint — G-invariance evidence for the panel."""
        ext = float(spec.farfield_extent_chords)
        return {
            "n_normal": spec.n_normal,
            "first_cell_height": spec.first_cell_height,
            "r_wall": cell_ratio(ext, spec.n_normal, spec.first_cell_height),
            "g_eta": expansion(ext, spec.n_normal, spec.first_cell_height),
            "e_front": expansion(ext, spec.n_front, spec.first_cell_front),
            "e_wake": expansion(ext, spec.n_wake, spec.first_cell_wake),
            "y_plus_estimate": 25.0 * spec.first_cell_height / 1.0e-3,  # scaled from base y+~25
        }

    def run_checkmesh(case_dir: Any) -> dict[str, Any]:
        cmd = build_apptainer_exec(
            sif_path=solver.sif_path,
            case_bind_source=str(case_dir.remote_path),
            command="checkMesh",
        )
        res = executor.run(cmd, timeout_s=900)
        txt = res.stdout

        def _f(pattern: str) -> float | None:
            m = re.search(pattern, txt)
            return float(m.group(1)) if m else None

        failed = re.search(r"Failed (\d+) mesh checks", txt)
        return {
            "ok": bool(re.search(r"Mesh OK", txt)) and res.ok,
            "failed_checks": int(failed.group(1)) if failed else 0,
            "max_aspect_ratio": _f(r"Max aspect ratio = ([0-9.eE+*-]+)"),
            "max_non_orthogonality": _f(r"non-orthogonality Max: ([0-9.eE+*-]+)"),
            "max_skewness": _f(r"[Mm]ax skewness = ([0-9.eE+*-]+)"),
        }

    def solve(m: float, design: str, grid: str, mult: float) -> dict[str, Any]:
        """One solve → tail-mean L/D + convergence + checkMesh + provenance. NEVER raises on a
        solver failure — the failure signature IS campaign evidence (the composition step then
        refuses to compose a claim from an incomplete/failed family)."""
        name = f"g16_{design}_{grid}"
        case = make_case(m, name, mult, graded=args.graded)
        spec = case.case_spec()
        prov = compute_provenance(
            repo_root=_REPO_ROOT,
            container_sif="openfoam-esi.sif",
            resolved_config=spec.model_dump(mode="json"),
            allow_dirty=args.allow_dirty,
        )
        row: dict[str, Any] = {
            "design": design,
            "grid": grid,
            "refine_mult": mult,
            "graded": args.graded,
            "grading": grading_of(spec),
            "ld": None,
            "cd": None,
            "cl": None,
            "ld_sem": None,
            "final_residual": None,
            "converged": False,
            "n_elements": None,
            "checkmesh": None,
            "error": None,
            "solver_log_tail": None,
            "provenance": prov.model_dump(mode="json"),
        }
        try:
            case_dir = solver.prepare(spec)
            mesh = solver.mesh(case_dir, executor)
            row["n_elements"] = getattr(mesh, "n_elements", None)
            if not getattr(mesh, "ok", False):
                row["error"] = "blockMesh failed"
                print(f"SOLVE {design}/{grid} !! MESH FAILED", flush=True)
                return row
            row["checkmesh"] = run_checkmesh(case_dir)
            result = solver.run(case_dir, executor)
            if getattr(result, "returncode", 1) != 0:
                row["error"] = f"solver failed (rc={result.returncode})"
                row["solver_log_tail"] = (result.solver_log or "")[-4000:]
                print(f"SOLVE {design}/{grid} !! SOLVER FAILED rc={result.returncode}", flush=True)
                return row
            measured = case.evaluate(solver, result)
            row["final_residual"] = float(solver.load(result).final_residual)
            ld_sem = 0.0
            if turbulent:
                _solve, cd_tail, cl_tail = solver.load_time_averaged(result)
                ld_tail = tuple(
                    cl / cd for cl, cd in zip(cl_tail, cd_tail, strict=True) if cd > 0.0
                )
                ld_sem = batch_means_sem(ld_tail)
                converged = ld_sem < 0.02 * abs(float(measured["ld"]))  # SEM < 2% of L/D
            else:
                converged = row["final_residual"] < args.resid_tol
            row.update(
                ld=float(measured["ld"]),
                cd=float(measured["cd"]),
                cl=float(measured["cl"]),
                ld_sem=ld_sem,
                converged=converged,
            )
        except (BenchmarkError, ValueError, OSError) as exc:  # keep the campaign alive; evidence
            row["error"] = f"{type(exc).__name__}: {exc}"
            print(f"SOLVE {design}/{grid} !! {row['error']}", flush=True)
            return row
        flag = "OK" if row["converged"] else "!! NOT CONVERGED"
        print(
            f"SOLVE {design}/{grid} mult={mult:.4f} n_el={row['n_elements']} "
            f"L/D={row['ld']:.5f} sem={row['ld_sem']:.4f} resid={row['final_residual']:.2e} "
            f"checkMesh={'OK' if (row['checkmesh'] or {}).get('ok') else 'FAIL'} {flag}",
            flush=True,
        )
        return row

    # ------------------------------------------------------------------ diag mode
    if args.diag:
        diag_rows: list[dict[str, Any]] = []
        # checkMesh contrast: the OLD family's steep-graded 28² and gentle-graded 136² vs the
        # graded-family 136². If the old 136² mesh is GOOD, "bad cells" is refuted and the
        # divergence is resolved unsteadiness — the corrected ADR-028 mechanism.
        contrasts = (
            ("old-28", args.ratio**2, False),
            ("old-136", 1.0 / args.ratio, False),
            ("graded-136", 1.0 / args.ratio, True),
        )
        for label, mult, graded in contrasts:
            case = make_case(args.opt_m, f"g16diag_{label.replace('-', '_')}", mult, graded=graded)
            spec = case.case_spec()
            case_dir = solver.prepare(spec)
            mesh = solver.mesh(case_dir, executor)
            row = {
                "label": label,
                "graded": graded,
                "refine_mult": mult,
                "n_elements": getattr(mesh, "n_elements", None),
                "mesh_ok": getattr(mesh, "ok", False),
                "grading": grading_of(spec),
                "checkmesh": run_checkmesh(case_dir) if getattr(mesh, "ok", False) else None,
            }
            diag_rows.append(row)
            print(f"DIAG mesh {label}: n_el={row['n_elements']} checkmesh={row['checkmesh']}")
        # The divergence reproduction: solve the OLD-family 136² optimum, capture the signature.
        old_graded = args.graded
        args.graded = False
        solve_row = solve(args.opt_m, "optimum", "old-136", 1.0 / args.ratio)
        args.graded = old_graded
        diag = {
            "purpose": "Stage-16 divergence diagnostic (ADR-028 corrected-mechanism evidence)",
            "regime": f"turbulent k-omega SST Re={args.reynolds:.2g}"
            if turbulent
            else "Re=1000 laminar",
            "mesh_contrast": diag_rows,
            "old_136_optimum_solve": solve_row,
        }
        diag_out = Path(
            args.diag_out or _REPO_ROOT / "data" / "vv" / "stage16_divergence_diag.json"
        )
        diag_out.parent.mkdir(parents=True, exist_ok=True)
        diag_out.write_text(json.dumps(diag, indent=2) + "\n")
        print(f"DIAG done -> {diag_out}", flush=True)
        return

    # ------------------------------------------------------------- certification campaign
    labels = _GRID_LABELS[: args.n_grids]
    mults = {lab: args.finest_mult * args.ratio**i for i, lab in enumerate(labels)}

    rows: list[dict[str, Any]] = []
    base: dict[str, dict[str, Any]] = {}
    opt: dict[str, dict[str, Any]] = {}
    for grid in labels:
        b = solve(0.0, "baseline", grid, mults[grid])
        o = solve(args.opt_m, "optimum", grid, mults[grid])
        rows.extend([b, o])
        base[grid] = b
        opt[grid] = o

    claim_grids = labels[:3]
    claim_rows = [base[g] for g in claim_grids] + [opt[g] for g in claim_grids]
    family_complete = all(r["ld"] is not None for r in claim_rows)
    claim_converged = family_complete and all(r["converged"] for r in claim_rows)

    regime = (
        f"turbulent k-omega SST Re={args.reynolds:.2g} (wall-function, tail-averaged)"
        if turbulent
        else "Re=1000 laminar"
    )

    diag: dict[str, Any] = {
        "case": "airfoil_opt_naca4",
        "regime": regime,
        "method": "ASME V&V 20 3-grid observed-order GCI on the matched-condition L/D delta, "
        "GRADED (fixed-mapping) family, finest grid included, hard-gated verdict"
        + ("; tail-averaged forces + batch-means iterative U95" if turbulent else ""),
        "graded_family": args.graded,
        "refinement_ratio": args.ratio,
        "finest_mult": args.finest_mult,
        "aoa_deg": args.aoa,
        "reynolds": args.reynolds if turbulent else 1000.0,
        "design_optimum": {"max_camber": args.opt_m, "camber_position": args.opt_p},
        "resid_tol": args.resid_tol,
        "k": args.k,
        "solves": rows,
        "family_complete": family_complete,
        "all_converged_claim_grids": claim_converged,
    }
    diag_out = Path(args.diag_out or _REPO_ROOT / "data" / "vv" / "stage16_grid_convergence.json")
    diag_out.parent.mkdir(parents=True, exist_ok=True)

    if not family_complete:
        failed = [f"{r['design']}/{r['grid']}: {r['error']}" for r in claim_rows if r["error"]]
        diag["verdict"] = "INCOMPLETE"
        diag["failed_solves"] = failed
        diag_out.write_text(json.dumps(diag, indent=2) + "\n")
        print(
            f"RESULT verdict=INCOMPLETE (no claim composed) failed={failed} diag={diag_out}",
            flush=True,
        )
        return

    u95_iter = float(
        (base["fine"]["ld_sem"] ** 2 + opt["fine"]["ld_sem"] ** 2) ** 0.5
    )  # measured, never hand-entered
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
    gates = certification_gates(
        triplet, all_converged=claim_converged, higher_is_better=True, k=args.k
    )
    go = all(gates.values())

    heldout_prov = compute_provenance(
        repo_root=_REPO_ROOT,
        container_sif="openfoam-esi.sif",
        resolved_config=make_case(args.opt_m, "g16_optimum_fine", mults["fine"], graded=args.graded)
        .case_spec()
        .model_dump(mode="json"),
        allow_dirty=args.allow_dirty,
    )
    if go:
        result, is_go = compose_result(
            case_name="airfoil_opt_naca4",
            objective=(
                f"maximize lift_to_drag at AoA={args.aoa} deg ({regime} NACA-4 camber); "
                "3-grid observed-order GCI on the matched delta, graded (fixed-mapping) family, "
                "finest grid included, convergence-gated"
            ),
            quantity="lift_to_drag",
            higher_is_better=True,
            design_variables={"max_camber": args.opt_m, "camber_position": args.opt_p},
            delta=triplet,
            cfd_verified=heldout_prov,
            n_candidates=args.n_candidates,
            k=args.k,
        )
    else:
        result = nogo_result(
            case_name="airfoil_opt_naca4",
            quantity="lift_to_drag",
            delta=triplet,
            provenance=heldout_prov,
        )
        is_go = False

    out = Path(args.out or _REPO_ROOT / "data" / "vv" / "stage16_optimization.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(result.model_dump_json(indent=2) + "\n")

    diag.update(
        delta_per_grid={
            "fine": triplet.delta_fine,
            "medium": triplet.delta_medium,
            "coarse": triplet.delta_coarse,
        },
        observed_order_delta=triplet.observed_order_delta,
        delta_monotone=triplet.delta_monotone,
        observed_order_optimum=observed_order(
            opt["fine"]["ld"], opt["medium"]["ld"], opt["coarse"]["ld"], ratio=args.ratio
        ),
        observed_order_baseline=observed_order(
            base["fine"]["ld"], base["medium"]["ld"], base["coarse"]["ld"], ratio=args.ratio
        ),
        gci_delta_fraction=triplet.gci_delta_fraction,
        u95_delta_grid=triplet.u95_delta_grid,
        u95_delta_iterative=triplet.u95_delta_iterative,
        u95_delta_numerical=triplet.u95_delta_numerical,
        delta_fine=triplet.delta_fine,
        required_margin=args.k * triplet.u95_delta_numerical,
        gates=gates,
        demoted_by=[name for name, ok in gates.items() if not ok],
        is_go=is_go,
        validation_tag=result.validation_tag,
    )
    # Overlapping-triplet order stability (4-grid family): evidence ONLY — the claim never
    # moves off the finest three grids (no coarsen-until-it-passes).
    if (
        args.n_grids == 4
        and base["coarsest"]["ld"] is not None
        and opt["coarsest"]["ld"] is not None
    ):
        d_med = opt["medium"]["ld"] - base["medium"]["ld"]
        d_coarse = opt["coarse"]["ld"] - base["coarse"]["ld"]
        d_coarsest = opt["coarsest"]["ld"] - base["coarsest"]["ld"]
        p_overlap, mono_overlap = observed_order(d_med, d_coarse, d_coarsest, ratio=args.ratio)
        diag["overlapping_triplet"] = {
            "grids": ["medium", "coarse", "coarsest"],
            "delta_series": [d_med, d_coarse, d_coarsest],
            "observed_order_delta": p_overlap,
            "delta_monotone": mono_overlap,
            "note": "order-stability evidence only; the claim is the finest triplet",
        }
    diag_out.write_text(json.dumps(diag, indent=2) + "\n")

    print(
        f"RESULT verdict={'GO' if is_go else 'NO-GO'} tag={result.validation_tag} "
        f"gates={gates} "
        f"observed_order_delta={triplet.observed_order_delta:.3f} monotone={triplet.delta_monotone} "
        f"delta={triplet.delta_fine:.5f} u95_delta={triplet.u95_delta_numerical:.5f} "
        f"required={args.k * triplet.u95_delta_numerical:.5f} "
        f"baseline_LD={triplet.baseline_fine:.5f} optimum_LD={triplet.optimum_fine:.5f} "
        f"out={out} diag={diag_out}",
        flush=True,
    )


if __name__ == "__main__":
    main()
