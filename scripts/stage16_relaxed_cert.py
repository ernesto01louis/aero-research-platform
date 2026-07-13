#!/usr/bin/env python
"""Stage-16 relaxed certification: URANS-stabilized steady values on the graded family.

The Stage-16 evidence chain: steady SIMPLE limit-cycles violently for the loaded optimum at
the finest grid (honest NO-GO, `stage16_grid_convergence.json`); impulsive-start URANS at
maxCo 8 falls into a spurious high-circulation attractor at medium/fine resolution
(`stage16_urans_pathology.json`); at a SAFE Courant number, a steady-RANS-initialized
time-accurate solve STAYS on the physical steady solution (the Co-2 diagnostic). So the
physical flow is steady, the pseudo-time SIMPLE iteration is what's unstable — and the honest
certification route is TIME-ACCURATE RELAXATION: initialize each graded-family case from its
converged steady-RANS field, integrate pimpleFoam at a safe Co, and read the STEADY value from
the flat tail. Same family (finest grid INCLUDED), same physics, same hard gates and k — only
the route to the steady solution changes (a stabilized steady solve, the URANS path's
degenerate case; ADR-029 outcome).

Pre-registered per-solve gates (committed BEFORE the campaign):
- relaxation drift: |L/D(last 5 t*) - L/D(previous 5 t*)| ≤ 0.2% · |L/D(last 5 t*)|
- steadiness: the 0.5-t* window-mean L/D spread inside the last 5 t* ≤ the drift tolerance
  (a genuinely shedding flow fails this gate and the steady composition is refused — that
  regime needs the ADR-029 statistical path, not this one)
- physicality: window-mean cd > 0 everywhere in the tail
GO requires the family gates (all converged, monotone delta, bounded observed order) AND
significance at k=2 with u95_delta_iterative = RSS of the two fine-grid relaxation drifts.

    python scripts/stage16_relaxed_cert.py --host aero-dev --opt-m ... --opt-p ... \
        --max-courant 2 --end-time-convective 25 --concurrent

Clean-tree provenance: commit first, then run without touching the repo.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import time
from pathlib import Path
from typing import Any

_REPO_ROOT = Path(__file__).resolve().parents[1]
_GRID_LABELS = ("fine", "medium", "coarse", "coarsest")
_INIT_FIELDS = ("U", "p", "k", "omega", "nut", "phi")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--host", default="aero-dev")
    ap.add_argument("--reynolds", type=float, default=5.0e5)
    ap.add_argument("--aoa", type=float, default=4.0)
    ap.add_argument("--ratio", type=float, default=1.7)
    ap.add_argument("--finest-mult", type=float, default=1.0 / 1.7)
    ap.add_argument("--n-grids", type=int, choices=(3, 4), default=3)
    ap.add_argument("--opt-m", type=float, required=True)
    ap.add_argument("--opt-p", type=float, required=True)
    ap.add_argument("--k", type=float, default=2.0)
    ap.add_argument(
        "--max-courant",
        type=float,
        default=2.0,
        help="SAFE Courant cap (below the spurious-attractor threshold established by the "
        "medium-grid diagnostics; uniform across the family).",
    )
    ap.add_argument(
        "--end-time-convective",
        type=float,
        default=25.0,
        help="Relaxation length; the value is the last-5-t* time mean.",
    )
    ap.add_argument(
        "--drift-tol-frac",
        type=float,
        default=0.002,
        help="Pre-registered relaxation-drift gate as a fraction of |L/D|.",
    )
    ap.add_argument("--n-candidates", type=int, default=14)
    ap.add_argument(
        "--reuse-rows",
        default=None,
        help="Path to a previous relaxed-campaign diag JSON; converged rows matching a "
        "grid's refine_mult + design are REUSED instead of re-solved (deterministic serial "
        "solves; row-level provenance is preserved verbatim). Extends the family without "
        "re-paying for finished rungs.",
    )
    ap.add_argument(
        "--map-init-glob",
        default="g16r_{design}_fine-*",
        help="Fallback init source (mapFields grid-continuation) for a grid with no steady "
        "run; {design} is substituted.",
    )
    ap.add_argument("--concurrent", action="store_true")
    ap.add_argument("--timeout", type=int, default=259200, help="Per-solve ceiling, s (72 h).")
    ap.add_argument("--allow-dirty", action="store_true")
    ap.add_argument("--out", default=None)
    ap.add_argument("--diag-out", default=None)
    args = ap.parse_args()

    import threading

    from aero.adapters._base import build_apptainer_exec
    from aero.adapters.openfoam.solver import OpenFOAMSolver
    from aero.adapters.openfoam.transient_airfoil import TransientAirfoilSpec
    from aero.optimize.report import (
        MatchedGridDeltaTriplet,
        certification_gates,
        compose_result,
        nogo_result,
        observed_order,
    )
    from aero.optimize.turbulent_airfoil import ShapedTurbulentAirfoil
    from aero.orchestration import LocalSSHExecutor
    from aero.postprocess.window_means import time_weighted_window_means
    from aero.provenance import compute_provenance
    from aero.vv._base import BenchmarkError

    _prov_lock = threading.Lock()
    nfs = Path("/mnt/aero-nfs") if os.path.ismount("/mnt/aero-nfs") else Path("/mnt/aero")
    solver = OpenFOAMSolver(host_nfs_root=nfs, remote_nfs_root=Path("/mnt/aero"))
    executor = LocalSSHExecutor(
        host=args.host, ssh_user="root", repo_root=_REPO_ROOT, long_timeout_s=args.timeout
    )

    def make_spec(m: float, name: str, mult: float) -> TransientAirfoilSpec:
        steady = ShapedTurbulentAirfoil(
            name=name,
            aoa_deg=args.aoa,
            reynolds=args.reynolds,
            max_camber=m,
            camber_position=args.opt_p,
        )
        base = steady.refined(mult).case_spec() if mult != 1.0 else steady.case_spec()
        return TransientAirfoilSpec(
            base=base,
            end_time_convective=args.end_time_convective,
            max_courant=args.max_courant,
        )

    def _field_size(time_dir: Path) -> int | None:
        """The internalField length of `p` in a time directory (None if unparseable)."""
        p = time_dir / "p"
        if not p.exists():
            return None
        with p.open(encoding="utf-8") as fh:
            for i, line in enumerate(fh):
                s = line.strip()
                if s.isdigit():
                    return int(s)
                if i > 60:
                    return None
        return None

    def steady_init(design: str, grid: str, case_dir: Any, n_elements: int | None) -> str | None:
        """Copy the steady campaign's converged fields in as 0/ (standard RANS->URANS init).

        Returns the init source label, or None when no SIZE-MATCHED steady run exists for
        this grid — grid labels are positional within a family, so the same label can name a
        different resolution across campaigns (the 231² extension's 'fine' vs the steady
        campaign's 136² 'fine'); only an exact cell-count match is a valid direct copy. The
        caller then falls back to `mapfields_init` (grid continuation).
        """
        dirs = sorted((nfs / "runs").glob(f"g16_{design}_{grid}-*"))
        if not dirs:
            return None
        src_case = dirs[-1]
        times = sorted(
            (d for d in src_case.iterdir() if re.fullmatch(r"[0-9.]+", d.name)),
            key=lambda d: float(d.name),
        )
        if not times or float(times[-1].name) <= 0.0:
            raise ValueError(f"steady run {src_case.name} has no converged field directory")
        src = times[-1]
        if n_elements is None or _field_size(src) != n_elements:
            return None  # different resolution behind the same label -> mapFields instead
        for f in _INIT_FIELDS:
            if (src / f).exists():
                shutil.copy(src / f, case_dir.host_path / "0" / f)
        return f"{src_case.name}/{src.name}"

    def mapfields_init(design: str, case_dir: Any) -> str:
        """`mapFields -consistent` from the finest relaxed solution onto the (finer) target.

        Both cases live under the shared runs root, so ONE bind of that root serves source
        and target (same geometry + BCs -> -consistent). Runs AFTER blockMesh (mapFields
        needs the target mesh)."""
        if not args.map_init_glob:
            raise ValueError("no steady init source and --map-init-glob not set")
        pattern = args.map_init_glob.format(design=design)
        target = case_dir.remote_path.name
        # The target itself (and any sibling started this campaign) can match the glob —
        # source only from cases that already contain a written time directory > 0.
        dirs = [
            d
            for d in sorted((nfs / "runs").glob(pattern))
            if d.name != target
            and any(re.fullmatch(r"[0-9.]+", s.name) and float(s.name) > 0.0 for s in d.iterdir())
        ]
        if not dirs:
            raise ValueError(f"no relaxed source case matching {pattern} for mapFields init")
        src_case = dirs[-1]
        target = case_dir.remote_path.name
        cmd = build_apptainer_exec(
            sif_path=solver.sif_path,
            case_bind_source=str(case_dir.remote_path.parent),
            command=(
                f"cd /case/{target} && mapFields -consistent -sourceTime latestTime "
                f"../{src_case.name}"
            ),
        )
        res = executor.run(cmd, timeout_s=3600)
        if not res.ok:
            raise ValueError(f"mapFields failed (rc={res.returncode}): {res.stdout[-800:]}")
        return f"mapFields:{src_case.name}@latestTime"

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
            "max_non_orthogonality": _f(r"non-orthogonality Max: ([0-9.eE+*-]+)"),
            "max_skewness": _f(r"[Mm]ax skewness = ([0-9.eE+*-]+)"),
        }

    def solve(m: float, design: str, grid: str, mult: float) -> dict[str, Any]:
        row: dict[str, Any] = {
            "design": design,
            "grid": grid,
            "refine_mult": mult,
            "ld": None,
            "cd": None,
            "cl": None,
            "ld_prev5": None,
            "relax_drift": None,
            "osc_spread": None,
            "converged": False,
            "n_elements": None,
            "n_samples": None,
            "wall_s": None,
            "checkmesh": None,
            "init_from": None,
            "error": None,
            "solver_log_tail": None,
            "provenance": None,
        }
        t0 = time.monotonic()
        try:
            name = f"g16r_{design}_{grid}"
            spec = make_spec(m, name, mult)
            with _prov_lock:
                prov = compute_provenance(
                    repo_root=_REPO_ROOT,
                    container_sif="openfoam-esi.sif",
                    resolved_config={
                        **spec.model_dump(mode="json"),
                        "initialization": "steady-RANS fields (time-accurate relaxation)",
                    },
                    allow_dirty=args.allow_dirty,
                )
            row["provenance"] = prov.model_dump(mode="json")
            case_dir = solver.prepare(spec)
            row["run_id"] = case_dir.run_id
            mesh = solver.mesh(case_dir, executor)
            row["n_elements"] = getattr(mesh, "n_elements", None)
            if not getattr(mesh, "ok", False):
                row["error"] = "blockMesh failed"
                print(f"SOLVE {design}/{grid} !! MESH FAILED", flush=True)
                return row
            init_label = steady_init(design, grid, case_dir, row["n_elements"])
            if init_label is None:  # no size-matched steady run: grid-continuation init
                init_label = mapfields_init(design, case_dir)
            row["init_from"] = init_label
            row["checkmesh"] = run_checkmesh(case_dir)
            result = solver.run(case_dir, executor)
            row["wall_s"] = time.monotonic() - t0
            if getattr(result, "returncode", 1) != 0:
                row["error"] = f"solver failed (rc={result.returncode})"
                row["solver_log_tail"] = (result.solver_log or "")[-4000:]
                print(f"SOLVE {design}/{grid} !! {row['error']}", flush=True)
                return row
            t, cd, cl = solver.load_force_series(result)
            row["n_samples"] = len(t)
            t_end = t[-1]
            if t_end < 10.0:
                row["error"] = f"run too short (t*={t_end:.2f} < 10) for the two 5-t* windows"
                print(f"SOLVE {design}/{grid} !! {row['error']}", flush=True)
                return row

            # The last 10 t* as two equal 5-t* windows: [previous, last].
            cd2 = time_weighted_window_means(t, cd, start_time=t_end - 10.0, n_windows=2)
            cl2 = time_weighted_window_means(t, cl, start_time=t_end - 10.0, n_windows=2)
            cd_prev, cd_last = float(cd2[0]), float(cd2[1])
            cl_prev, cl_last = float(cl2[0]), float(cl2[1])
            if cd_last <= 0.0 or cd_prev <= 0.0:
                row["error"] = f"non-physical tail mean cd ({cd_last:.4g}/{cd_prev:.4g})"
                print(f"SOLVE {design}/{grid} !! {row['error']}", flush=True)
                return row
            ld_last = cl_last / cd_last
            ld_prev = cl_prev / cd_prev
            drift = abs(ld_last - ld_prev)
            # Oscillation spread: 0.5-t* window means of L/D inside the last 5 t*.
            n_osc = 10
            cdw = time_weighted_window_means(t, cd, start_time=t_end - 5.0, n_windows=n_osc)
            clw = time_weighted_window_means(t, cl, start_time=t_end - 5.0, n_windows=n_osc)
            if min(cdw) <= 0.0:
                row["error"] = f"non-physical 0.5-t* window cd (min {min(cdw):.4g})"
                print(f"SOLVE {design}/{grid} !! {row['error']}", flush=True)
                return row
            ldw = [c / d for c, d in zip(clw, cdw, strict=True)]
            osc = max(ldw) - min(ldw)
            tol = args.drift_tol_frac * abs(ld_last)
            row.update(
                ld=ld_last,
                cd=cd_last,
                cl=cl_last,
                ld_prev5=ld_prev,
                relax_drift=drift,
                osc_spread=osc,
                converged=bool(drift <= tol and osc <= tol),
            )
        except (BenchmarkError, ValueError, OSError) as exc:
            row["error"] = f"{type(exc).__name__}: {exc}"
            print(f"SOLVE {design}/{grid} !! {row['error']}", flush=True)
            return row
        flag = "OK" if row["converged"] else "!! NOT RELAXED/STEADY"
        print(
            f"SOLVE {design}/{grid} mult={mult:.4f} n_el={row['n_elements']} "
            f"L/D={row['ld']:.5f} drift={row['relax_drift']:.5f} osc={row['osc_spread']:.5f} "
            f"tol={args.drift_tol_frac * abs(row['ld']):.5f} wall={row['wall_s']:.0f}s {flag}",
            flush=True,
        )
        return row

    labels = _GRID_LABELS[: args.n_grids]
    mults = {lab: args.finest_mult * args.ratio**i for i, lab in enumerate(labels)}
    jobs = [
        (m, design, grid)
        for grid in labels
        for m, design in ((0.0, "baseline"), (args.opt_m, "optimum"))
    ]

    reuse_index: dict[tuple[str, float], dict[str, Any]] = {}
    if args.reuse_rows:
        prev = json.loads(Path(args.reuse_rows).read_text())
        for r in prev.get("solves", []):
            if r.get("converged") and r.get("ld") is not None:
                reuse_index[(r["design"], round(float(r["refine_mult"]), 9))] = r

    def safe_worker(j: tuple[float, str, str]) -> dict[str, Any]:
        m, design, grid = j
        reused = reuse_index.get((design, round(mults[grid], 9)))
        if reused is not None:
            row = dict(reused)
            row["grid"] = grid  # relabeled position in the extended family
            row["reused_from"] = args.reuse_rows
            print(
                f"SOLVE {design}/{grid} REUSED {row.get('run_id')} L/D={row['ld']:.5f}",
                flush=True,
            )
            return row
        try:
            return solve(m, design, grid, mults[grid])
        except Exception as exc:  # the campaign must survive any solve
            print(f"SOLVE {design}/{grid} !! UNHANDLED {type(exc).__name__}: {exc}", flush=True)
            return {
                "design": design,
                "grid": grid,
                "refine_mult": mults[grid],
                "ld": None,
                "converged": False,
                "error": f"UNHANDLED {type(exc).__name__}: {exc}",
            }

    if args.concurrent:
        from concurrent.futures import ThreadPoolExecutor

        with ThreadPoolExecutor(max_workers=len(jobs)) as pool:
            rows = list(pool.map(safe_worker, jobs))
    else:
        rows = [safe_worker(j) for j in jobs]
    base = {r["grid"]: r for r in rows if r["design"] == "baseline"}
    opt = {r["grid"]: r for r in rows if r["design"] == "optimum"}

    claim_grids = labels[:3]
    maybe_rows = [base.get(g) for g in claim_grids] + [opt.get(g) for g in claim_grids]
    family_complete = all(r is not None and r["ld"] is not None for r in maybe_rows)
    claim_rows = [r for r in maybe_rows if r is not None]
    claim_converged = family_complete and all(r["converged"] for r in claim_rows)

    regime = (
        f"turbulent k-omega SST Re={args.reynolds:.2g} "
        f"(time-accurate relaxation from steady-RANS init, maxCo {args.max_courant:g})"
    )
    diag: dict[str, Any] = {
        "case": "airfoil_opt_naca4",
        "regime": regime,
        "method": "ASME V&V 20 3-grid observed-order GCI on the matched STEADY delta; values "
        "from URANS-stabilized relaxation (last-5-t* time means); pre-registered drift + "
        "steadiness + physicality gates; hard-gated verdict",
        "refinement_ratio": args.ratio,
        "finest_mult": args.finest_mult,
        "aoa_deg": args.aoa,
        "reynolds": args.reynolds,
        "max_courant": args.max_courant,
        "end_time_convective": args.end_time_convective,
        "drift_tol_frac": args.drift_tol_frac,
        "design_optimum": {"max_camber": args.opt_m, "camber_position": args.opt_p},
        "k": args.k,
        "solves": rows,
        "family_complete": family_complete,
        "all_converged_claim_grids": claim_converged,
    }
    diag_out = Path(
        args.diag_out or _REPO_ROOT / "data" / "vv" / "stage16_relaxed_convergence.json"
    )
    diag_out.parent.mkdir(parents=True, exist_ok=True)
    if not family_complete:
        failed = [f"{r['design']}/{r['grid']}: {r['error']}" for r in claim_rows if r.get("error")]
        diag["verdict"] = "INCOMPLETE"
        diag["failed_solves"] = failed
        diag_out.write_text(json.dumps(diag, indent=2) + "\n")
        print(f"RESULT verdict=INCOMPLETE failed={failed} diag={diag_out}", flush=True)
        return

    u95_iter = float((base["fine"]["relax_drift"] ** 2 + opt["fine"]["relax_drift"] ** 2) ** 0.5)
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
    with _prov_lock:
        heldout_prov = compute_provenance(
            repo_root=_REPO_ROOT,
            container_sif="openfoam-esi.sif",
            resolved_config=make_spec(args.opt_m, "g16r_optimum_fine", mults["fine"]).model_dump(
                mode="json"
            ),
            allow_dirty=args.allow_dirty,
        )
    if go:
        result, is_go = compose_result(
            case_name="airfoil_opt_naca4",
            objective=(
                f"maximize lift_to_drag at AoA={args.aoa} deg ({regime} NACA-4 camber); "
                "3-grid observed-order GCI on the matched steady delta, graded family, finest "
                "grid included, URANS-stabilized values, convergence-gated"
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

    out = Path(args.out or _REPO_ROOT / "data" / "vv" / "stage16_relaxed_optimization.json")
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
    diag_out.write_text(json.dumps(diag, indent=2) + "\n")
    print(
        f"RESULT verdict={'GO' if is_go else 'NO-GO'} tag={result.validation_tag} gates={gates} "
        f"observed_order_delta={triplet.observed_order_delta:.3f} "
        f"monotone={triplet.delta_monotone} delta={triplet.delta_fine:.5f} "
        f"u95_delta={triplet.u95_delta_numerical:.5f} "
        f"required={args.k * triplet.u95_delta_numerical:.5f} "
        f"baseline_LD={triplet.baseline_fine:.5f} optimum_LD={triplet.optimum_fine:.5f} "
        f"out={out} diag={diag_out}",
        flush=True,
    )


if __name__ == "__main__":
    main()
