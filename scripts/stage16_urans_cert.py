#!/usr/bin/env python
"""Stage-16 URANS certification: time-accurate matched-delta on the graded grid family.

The steady campaign (data/vv/stage16_grid_convergence.json) ended in an honest NO-GO: the
loaded optimum's resolved unsteadiness makes steady simpleFoam a violent two-iteration limit
cycle at the finest grid (cd sign-crossings — no meaningful iterative uncertainty). This
driver certifies the SAME optimum on the SAME graded family the honest way: `pimpleFoam`
time-accurate solves for baseline AND optimum at matched numerics, TIME-WEIGHTED window means
of the force coefficients over the statistically steady tail, a measured `u95_statistical`
per solve (NOBM on the window means), an observed-order GCI on the time-averaged delta, and
the ADR-029 independent-RSS composition (no cancellation claimed). The verdict is hard-gated
exactly like the steady driver: GO requires FULL-RSS significance AND stationary solves AND a
monotone delta AND a bounded observed order — finest grid included, k never relaxed.

    # cost probe (short fine-grid solve; measure s/step, extrapolate, no claim)
    python scripts/stage16_urans_cert.py --host aero-dev --opt-m ... --opt-p ... \
        --probe --end-time-convective 2.0

    # certification campaign (6 solves: 3 grids x baseline+optimum; hours-long, detached)
    python scripts/stage16_urans_cert.py --host aero-dev --opt-m ... --opt-p ...

Clean-tree provenance: commit first, then run without touching the repo.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import time
from pathlib import Path
from typing import Any

_REPO_ROOT = Path(__file__).resolve().parents[1]

_GRID_LABELS = ("fine", "medium", "coarse", "coarsest")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--host", default="aero-dev")
    ap.add_argument("--reynolds", type=float, default=5.0e5)
    ap.add_argument("--aoa", type=float, default=4.0)
    ap.add_argument("--ratio", type=float, default=1.7)
    ap.add_argument(
        "--finest-mult",
        type=float,
        default=1.0 / 1.7,
        help="Finest-grid multiplier (default 1/1.7 -> the 136² grid, finest INCLUDED).",
    )
    ap.add_argument("--n-grids", type=int, choices=(3, 4), default=3)
    ap.add_argument("--opt-m", type=float, required=True, help="Optimum max_camber (REQUIRED).")
    ap.add_argument(
        "--opt-p", type=float, required=True, help="Optimum camber_position (REQUIRED)."
    )
    ap.add_argument("--k", type=float, default=2.0)
    ap.add_argument(
        "--end-time-convective",
        type=float,
        default=100.0,
        help="Run length in convective times; the first --transient-fraction is discarded.",
    )
    ap.add_argument("--max-courant", type=float, default=4.0)
    ap.add_argument(
        "--transient-fraction",
        type=float,
        default=0.5,
        help="Leading fraction of the run discarded as startup transient.",
    )
    ap.add_argument(
        "--n-windows", type=int, default=16, help="Averaging windows over the retained tail."
    )
    ap.add_argument(
        "--probe",
        action="store_true",
        help="Cost probe: ONE short fine-grid optimum solve; measure wall-time/step and "
        "extrapolate the campaign cost. Writes stage16_urans_probe.json; composes NO claim.",
    )
    ap.add_argument("--n-candidates", type=int, default=14)
    ap.add_argument(
        "--concurrent",
        action="store_true",
        help="Run all campaign solves concurrently (independent serial jobs; 16-core box).",
    )
    ap.add_argument(
        "--extend",
        action="store_true",
        help="CONTINUATION mode: restart the existing g16u_* cases from latestTime, extend "
        "endTime to --extend-to convective times, and re-window on the settled tail — the "
        "honest remedy when the first segment's stationarity gates refuse a still-settling "
        "flow (the paid-for segment is reused, never discarded selectively).",
    )
    ap.add_argument(
        "--extend-to",
        type=float,
        default=100.0,
        help="Extension mode: new total run length in convective times.",
    )
    ap.add_argument(
        "--tail-start-convective",
        type=float,
        default=None,
        help="Absolute averaging-tail start (t*); default 0.6*extend-to in extension mode.",
    )
    ap.add_argument(
        "--grids",
        default=None,
        help="Comma-separated subset of grids to run (e.g. 'medium'); multipliers stay pinned "
        "to each grid's position in the full family. Default: all --n-grids grids.",
    )
    ap.add_argument("--timeout", type=int, default=129600, help="Per-solve ceiling, s (36 h).")
    ap.add_argument("--allow-dirty", action="store_true")
    ap.add_argument("--out", default=None)
    ap.add_argument("--diag-out", default=None)
    args = ap.parse_args()

    import threading

    import numpy as np
    from aero.adapters._base import build_apptainer_exec
    from aero.adapters.openfoam.solver import OpenFOAMSolver
    from aero.adapters.openfoam.transient_airfoil import TransientAirfoilSpec
    from aero.optimize.report import (
        MatchedGridDeltaTriplet,
        certification_gates,
        compose_independent_result,
        observed_order,
    )
    from aero.optimize.turbulent_airfoil import ShapedTurbulentAirfoil
    from aero.orchestration import LocalSSHExecutor
    from aero.postprocess.window_means import time_weighted_window_means
    from aero.provenance import compute_provenance
    from aero.vv._base import BenchmarkError
    from aero.vv.statistical_uncertainty import (
        StatisticalUncertaintyError,
        statistical_uncertainty_from_samples,
    )

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

    def analyze_series(
        row: dict[str, Any],
        t: tuple[float, ...],
        cd: tuple[float, ...],
        cl: tuple[float, ...],
        tail_start: float,
    ) -> None:
        """Window the force series, measure the sampling stats, apply the stationarity gate.

        Pre-registered gate: half-tail window-mean L/D averages agree within 2x the full-tail
        sampling half-width, the NOBM estimate is `reliable`, every window-mean cd positive.
        """
        row["n_samples"] = len(t)
        cd_w = time_weighted_window_means(t, cd, start_time=tail_start, n_windows=args.n_windows)
        cl_w = time_weighted_window_means(t, cl, start_time=tail_start, n_windows=args.n_windows)
        if min(cd_w) <= 0.0:
            row["error"] = f"non-physical window-mean cd (min {min(cd_w):.4g})"
            return
        ld_w = tuple(c / d for c, d in zip(cl_w, cd_w, strict=True))
        try:
            stat = statistical_uncertainty_from_samples(
                ld_w, amp_scale=max(ld_w) - min(ld_w), min_samples=8
            )
        except StatisticalUncertaintyError as exc:
            row["error"] = f"StatisticalUncertaintyError: {exc}"
            return
        half = args.n_windows // 2
        drift = abs(float(np.mean(ld_w[:half])) - float(np.mean(ld_w[half:])))
        stationary = drift <= 2.0 * stat.u95_statistical
        row.update(
            ld=float(stat.mean),
            cd=float(np.mean(cd_w)),
            cl=float(np.mean(cl_w)),
            u95_statistical=float(stat.u95_statistical),
            stat_reliable=bool(stat.reliable),
            drift=drift,
            converged=bool(stationary and stat.reliable),
            stat=stat.model_dump(mode="json"),
            ld_windows=list(ld_w),
            tail_start_convective=tail_start,
        )

    def solve(m: float, design: str, grid: str, mult: float) -> dict[str, Any]:
        """One time-accurate solve → window-mean L/D + measured sampling stats + provenance.

        Never raises on a solver failure — the signature is campaign evidence; the composer
        refuses an incomplete family.
        """
        row: dict[str, Any] = {
            "design": design,
            "grid": grid,
            "refine_mult": mult,
            "ld": None,
            "cd": None,
            "cl": None,
            "u95_statistical": None,
            "stat_reliable": None,
            "drift": None,
            "converged": False,
            "n_elements": None,
            "n_samples": None,
            "wall_s": None,
            "checkmesh": None,
            "error": None,
            "solver_log_tail": None,
            "stat": None,
            "provenance": None,
        }
        t0 = time.monotonic()
        try:
            name = f"g16u_{design}_{grid}"
            spec = make_spec(m, name, mult)
            with _prov_lock:  # git reads race under 6-way concurrency (index.lock)
                prov = compute_provenance(
                    repo_root=_REPO_ROOT,
                    container_sif="openfoam-esi.sif",
                    resolved_config=spec.model_dump(mode="json"),
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
            row["checkmesh"] = run_checkmesh(case_dir)
            result = solver.run(case_dir, executor)
            row["wall_s"] = time.monotonic() - t0
            if getattr(result, "returncode", 1) != 0:
                row["error"] = f"solver failed (rc={result.returncode})"
                row["solver_log_tail"] = (result.solver_log or "")[-4000:]
                print(f"SOLVE {design}/{grid} !! SOLVER FAILED rc={result.returncode}", flush=True)
                return row
            t, cd, cl = solver.load_force_series(result)
            start = t[0] + args.transient_fraction * (t[-1] - t[0])
            analyze_series(row, t, cd, cl, tail_start=start)
            if row["error"]:
                print(f"SOLVE {design}/{grid} !! {row['error']}", flush=True)
                return row
        except (BenchmarkError, ValueError, OSError) as exc:
            row["error"] = f"{type(exc).__name__}: {exc}"
            print(f"SOLVE {design}/{grid} !! {row['error']}", flush=True)
            return row
        flag = "OK" if row["converged"] else "!! NOT STATIONARY"
        print(
            f"SOLVE {design}/{grid} mult={mult:.4f} n_el={row['n_elements']} "
            f"L/D={row['ld']:.5f} u95_stat={row['u95_statistical']:.4f} "
            f"drift={row['drift']:.4f} reliable={row['stat_reliable']} "
            f"wall={row['wall_s']:.0f}s {flag}",
            flush=True,
        )
        return row

    # ------------------------------------------------------------------ probe mode
    if args.probe:
        row = solve(args.opt_m, "optimum", "probe-fine", args.finest_mult)
        wall = row.get("wall_s") or 0.0
        per_conv = wall / args.end_time_convective if wall else None
        est_full = per_conv * 100.0 if per_conv else None
        probe = {
            "purpose": "URANS cost probe (fine grid, optimum design) — no claim composed",
            "end_time_convective": args.end_time_convective,
            "wall_s": wall,
            "wall_s_per_convective_time": per_conv,
            "est_wall_s_full_run_100tc": est_full,
            "est_wall_h_campaign_6_solves": (
                # medium/coarse scale ~1/r^3 (cells x dt) per refinement step
                (est_full * (1 + 1 + 2 / args.ratio**3 + 2 / args.ratio**6) / 3600.0)
                if est_full
                else None
            ),
            "row": row,
        }
        out = Path(_REPO_ROOT / "data" / "vv" / "stage16_urans_probe.json")
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(probe, indent=2) + "\n")
        print(f"PROBE done -> {out}: {json.dumps({k: v for k, v in probe.items() if k != 'row'})}")
        return

    # ---------------------------------------------------------------- continuation mode
    def patch_controldict_for_restart(case_host: Path, end_time_s: float) -> None:
        p = case_host / "system" / "controlDict"
        txt = p.read_text(encoding="utf-8")
        txt = re.sub(r"startFrom\s+\w+;", "startFrom       latestTime;", txt, count=1)
        txt = re.sub(r"endTime\s+[0-9.eE+-]+;", f"endTime         {end_time_s:.8g};", txt, count=1)
        # Only the controlDict write interval (first occurrence) — the forceCoeffs FO's
        # per-timestep writeInterval further down must stay 1.
        txt = re.sub(
            r"writeInterval\s+[0-9.eE+-]+;", f"writeInterval   {end_time_s:.8g};", txt, count=1
        )
        p.write_text(txt, encoding="utf-8")

    def read_concat_series(
        case_host: Path,
    ) -> tuple[tuple[float, ...], tuple[float, ...], tuple[float, ...]]:
        """The forceCoeffs series concatenated across restart segments (duplicate times dropped)."""
        from aero.adapters.openfoam.solver import _read_coefficient_dat

        files = sorted(
            (case_host / "postProcessing" / "forceCoeffs1").glob("*/coefficient.dat"),
            key=lambda p: float(p.parent.name),
        )
        if not files:
            raise ValueError(f"no coefficient.dat under {case_host}")
        ts: list[Any] = []
        cds: list[Any] = []
        cls_: list[Any] = []
        last_t = -1.0
        for f in files:
            columns, data = _read_coefficient_dat(f)
            if data.ndim == 1:
                data = data.reshape(1, -1)
            t = data[:, columns.index("Time")]
            keep = t > last_t
            ts.append(t[keep])
            cds.append(data[keep, columns.index("Cd")])
            cls_.append(data[keep, columns.index("Cl")])
            if len(t):
                last_t = float(t[-1])
        t_all = np.concatenate(ts)
        cd_all = np.concatenate(cds)
        cl_all = np.concatenate(cls_)
        return (
            tuple(float(v) for v in t_all),
            tuple(float(v) for v in cd_all),
            tuple(float(v) for v in cl_all),
        )

    def extend_one(m: float, design: str, grid: str, mult: float) -> dict[str, Any]:
        """Restart an existing case from latestTime out to --extend-to; re-analyze the tail."""
        row: dict[str, Any] = {
            "design": design,
            "grid": grid,
            "refine_mult": mult,
            "ld": None,
            "cd": None,
            "cl": None,
            "u95_statistical": None,
            "stat_reliable": None,
            "drift": None,
            "converged": False,
            "n_elements": None,
            "n_samples": None,
            "wall_s": None,
            "checkmesh": None,
            "error": None,
            "solver_log_tail": None,
            "stat": None,
            "provenance": None,
        }
        t0 = time.monotonic()
        try:
            name = f"g16u_{design}_{grid}"
            spec = make_spec(m, name, mult)
            with _prov_lock:
                prov = compute_provenance(
                    repo_root=_REPO_ROOT,
                    container_sif="openfoam-esi.sif",
                    resolved_config={
                        **spec.model_dump(mode="json"),
                        "end_time_convective": args.extend_to,
                        "restart_continuation": True,
                    },
                    allow_dirty=args.allow_dirty,
                )
            row["provenance"] = prov.model_dump(mode="json")
            dirs = sorted((nfs / "runs").glob(f"{name}-*"))
            if not dirs:
                row["error"] = f"no existing case dir {name}-* to extend"
                print(f"SOLVE {design}/{grid} !! {row['error']}", flush=True)
                return row
            case_host = dirs[-1]
            row["run_id"] = case_host.name
            row["extended_to_convective"] = args.extend_to
            patch_controldict_for_restart(case_host, args.extend_to)
            remote = Path("/mnt/aero/runs") / case_host.name
            cmd = build_apptainer_exec(
                sif_path=solver.sif_path,
                case_bind_source=str(remote),
                command="pimpleFoam",
            )
            res = executor.run(cmd, long_running=True, session=f"ext-{case_host.name}")
            row["wall_s"] = time.monotonic() - t0
            if res.returncode != 0:
                row["error"] = f"extension solve failed (rc={res.returncode})"
                row["solver_log_tail"] = (res.stdout or "")[-4000:]
                print(f"SOLVE {design}/{grid} !! {row['error']}", flush=True)
                return row
            t, cd, cl = read_concat_series(case_host)
            tail_start = (
                args.tail_start_convective
                if args.tail_start_convective is not None
                else 0.6 * args.extend_to
            )
            analyze_series(row, t, cd, cl, tail_start=tail_start)
            if row["error"]:
                print(f"SOLVE {design}/{grid} !! {row['error']}", flush=True)
                return row
        except (BenchmarkError, ValueError, OSError) as exc:
            row["error"] = f"{type(exc).__name__}: {exc}"
            print(f"SOLVE {design}/{grid} !! {row['error']}", flush=True)
            return row
        flag = "OK" if row["converged"] else "!! NOT STATIONARY"
        print(
            f"SOLVE {design}/{grid} EXT->{args.extend_to:g}t* n_samples={row['n_samples']} "
            f"L/D={row['ld']:.5f} u95_stat={row['u95_statistical']:.4f} "
            f"drift={row['drift']:.4f} reliable={row['stat_reliable']} "
            f"wall={row['wall_s']:.0f}s {flag}",
            flush=True,
        )
        return row

    # ------------------------------------------------------------- certification campaign
    labels = _GRID_LABELS[: args.n_grids]
    mults = {lab: args.finest_mult * args.ratio**i for i, lab in enumerate(labels)}
    run_labels = [g.strip() for g in args.grids.split(",")] if args.grids else list(labels)
    unknown = [g for g in run_labels if g not in mults]
    if unknown:
        raise SystemExit(f"--grids: unknown grid label(s) {unknown}; family is {list(labels)}")
    jobs = [
        (m, design, grid)
        for grid in run_labels
        for m, design in ((0.0, "baseline"), (args.opt_m, "optimum"))
    ]
    worker = extend_one if args.extend else solve

    def safe_worker(j: tuple[float, str, str]) -> dict[str, Any]:
        """A per-solve failure must become an evidence row, never a hidden thread exception
        that surfaces hours later at pool collection (the first campaign lost its medium pair
        this way)."""
        m, design, grid = j
        try:
            return worker(m, design, grid, mults[grid])
        except Exception as exc:
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
        # Independent SERIAL jobs on the 16-core box (the platform's sanctioned concurrency);
        # each thread just blocks on its own detached remote job. Wall time ~= the fine solve.
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
        "(URANS pimpleFoam, time-weighted window means)"
    )
    diag: dict[str, Any] = {
        "case": "airfoil_opt_naca4",
        "regime": regime,
        "method": "ASME V&V 20 3-grid observed-order GCI on the TIME-AVERAGED matched delta; "
        "ADR-029 independent-RSS sampling term (no cancellation claimed); hard-gated verdict",
        "refinement_ratio": args.ratio,
        "finest_mult": args.finest_mult,
        "aoa_deg": args.aoa,
        "reynolds": args.reynolds,
        "end_time_convective": args.extend_to if args.extend else args.end_time_convective,
        "continuation": bool(args.extend),
        "tail_start_convective": args.tail_start_convective,
        "transient_fraction": args.transient_fraction,
        "n_windows": args.n_windows,
        "max_courant": args.max_courant,
        "design_optimum": {"max_camber": args.opt_m, "camber_position": args.opt_p},
        "k": args.k,
        "solves": rows,
        "family_complete": family_complete,
        "all_converged_claim_grids": claim_converged,
    }
    diag_out = Path(args.diag_out or _REPO_ROOT / "data" / "vv" / "stage16_urans_convergence.json")
    diag_out.parent.mkdir(parents=True, exist_ok=True)

    if not family_complete:
        failed = [f"{r['design']}/{r['grid']}: {r['error']}" for r in claim_rows if r["error"]]
        diag["verdict"] = "INCOMPLETE"
        diag["failed_solves"] = failed
        diag_out.write_text(json.dumps(diag, indent=2) + "\n")
        print(f"RESULT verdict=INCOMPLETE failed={failed} diag={diag_out}", flush=True)
        return

    triplet = MatchedGridDeltaTriplet(
        quantity="lift_to_drag",
        baseline_fine=base["fine"]["ld"],
        baseline_medium=base["medium"]["ld"],
        baseline_coarse=base["coarse"]["ld"],
        optimum_fine=opt["fine"]["ld"],
        optimum_medium=opt["medium"]["ld"],
        optimum_coarse=opt["coarse"]["ld"],
        refinement_ratio=args.ratio,
        u95_delta_iterative=0.0,  # time-accurate: sampling error carried by the ADR-029 term
    )
    gates = certification_gates(
        triplet, all_converged=claim_converged, higher_is_better=True, k=args.k
    )
    # `significant` in the gates uses the grid-only term; the CLAIM's significance is judged
    # on the FULL independent RSS inside compose_independent_result. Family gates here are
    # the non-significance gates (stationary + monotone + bounded order).
    family_gates_pass = (
        gates["all_converged"] and gates["delta_monotone"] and gates["order_in_asymptotic_range"]
    )

    from aero.vv.statistical_uncertainty import StatisticalUncertainty

    b_stat = StatisticalUncertainty.model_validate(base["fine"]["stat"])
    o_stat = StatisticalUncertainty.model_validate(opt["fine"]["stat"])
    heldout_prov = compute_provenance(
        repo_root=_REPO_ROOT,
        container_sif="openfoam-esi.sif",
        resolved_config=make_spec(args.opt_m, "g16u_optimum_fine", mults["fine"]).model_dump(
            mode="json"
        ),
        allow_dirty=args.allow_dirty,
    )
    result, is_go = compose_independent_result(
        case_name="airfoil_opt_naca4",
        objective=(
            f"maximize lift_to_drag at AoA={args.aoa} deg ({regime} NACA-4 camber); "
            "3-grid observed-order GCI on the time-averaged matched delta, graded family, "
            "finest grid included, ADR-029 independent sampling term, hard-gated"
        ),
        quantity="lift_to_drag",
        higher_is_better=True,
        design_variables={"max_camber": args.opt_m, "camber_position": args.opt_p},
        delta=triplet,
        baseline_stat=b_stat,
        optimum_stat=o_stat,
        family_gates_pass=family_gates_pass,
        cfd_verified=heldout_prov,
        n_candidates=args.n_candidates,
        k=args.k,
    )

    out = Path(args.out or _REPO_ROOT / "data" / "vv" / "stage16_urans_optimization.json")
    out.write_text(result.model_dump_json(indent=2) + "\n")

    u95_stat_delta = float((b_stat.u95_statistical**2 + o_stat.u95_statistical**2) ** 0.5)
    u95_full = float((triplet.u95_delta_grid**2 + u95_stat_delta**2) ** 0.5)
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
        u95_delta_statistical_independent=u95_stat_delta,
        u95_delta_full_rss=u95_full,
        delta_fine=triplet.delta_fine,
        required_margin=args.k * u95_full,
        gates=gates,
        family_gates_pass=family_gates_pass,
        demoted_by=[name for name, ok in gates.items() if not ok],
        is_go=is_go,
        validation_tag=result.validation_tag,
    )
    if args.n_grids == 4 and base["coarsest"]["ld"] is not None:
        d = [opt[g]["ld"] - base[g]["ld"] for g in ("medium", "coarse", "coarsest")]
        p_overlap, mono_overlap = observed_order(d[0], d[1], d[2], ratio=args.ratio)
        diag["overlapping_triplet"] = {
            "grids": ["medium", "coarse", "coarsest"],
            "delta_series": d,
            "observed_order_delta": p_overlap,
            "delta_monotone": mono_overlap,
            "note": "order-stability evidence only; the claim is the finest triplet",
        }
    diag_out.write_text(json.dumps(diag, indent=2) + "\n")

    print(
        f"RESULT verdict={'GO' if is_go else 'NO-GO'} tag={result.validation_tag} "
        f"gates={gates} family_gates_pass={family_gates_pass} "
        f"observed_order_delta={triplet.observed_order_delta:.3f} "
        f"monotone={triplet.delta_monotone} delta={triplet.delta_fine:.5f} "
        f"u95_full={u95_full:.5f} required={args.k * u95_full:.5f} "
        f"baseline_LD={triplet.baseline_fine:.5f} optimum_LD={triplet.optimum_fine:.5f} "
        f"out={out} diag={diag_out}",
        flush=True,
    )


if __name__ == "__main__":
    main()
