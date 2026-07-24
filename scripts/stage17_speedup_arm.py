#!/usr/bin/env python
"""Stage-17 speed-up campaign — one (arm, seed) run of the paired comparison (ADR-032).

    python scripts/stage17_speedup_arm.py --arm direct    --seed 0 --host aero-dev
    python scripts/stage17_speedup_arm.py --arm surrogate --seed 0 --host aero-dev

================================================================================
PRE-REGISTERED GATES — Stage 17 (committed BEFORE any campaign solve; NEVER
relaxed after data exists. The gates are the product.)
================================================================================

Certification (smoke -> validated), seeded 25% held-out split of the corpus:
 C1  empirical +/-2*std coverage in [0.85, 1.0]. (Amends the DRAFT band
     [0.85, 0.99] pre-campaign: at n_holdout ~ 10 a perfectly calibrated
     estimator hits coverage 1.0 with probability ~ 0.62, so the DRAFT's upper
     bound rejects calibrated models more often than not; the DRAFT itself
     marks the band "ratify or amend". Over-wide-sigma is guarded by C2 + D1.
     Recorded in ADR-031.)
 C2  held-out |L/D error| p95 <= 2.5 (~10% of the corpus objective span).
 C3  non-collapsed ensemble (CalibrationError-free build; structural, ADR-025).
 C4  every Sample data_origin == "platform-validated" (Invariant 11).
 D1  diagnostics reported, never gated: mean_abs_z, std_z, coverage.

Loop configuration (frozen):
 L1  TrustRegionConfig defaults (initial 0.25 / min 1e-3 / max 0.5,
     expand 2.0, shrink 0.5, eta_accept 0.25 / eta_expand 0.75); unit cube.
 L2  infill_batch = 4, explore_fraction = 0.25 (3 exploit + 1 explore).
 L3  candidate_pool = 2048 inside TrustRegionPolicy.bounds(state).
 L4  retrain + re-issue cert every iteration; assert_current once per iteration.
 L5  stop: bar reached | 16 ground-truth evals | 2 consecutive reject-floor
     events without incumbent improvement (-> NO-GO fallback: direct-CFD BO
     remains the loop of record).

Speed-up comparison (paired seeds):
 S1  seeds {0, 1, 2}; both arms share the DesignSpace (m in [0, 0.08],
     p in [0.2, 0.6]), base-grid ShapedTurbulentAirfoil (k-omega SST, Re 5e5,
     AoA 4 deg, end_time 3000), metric L/D.
 S2  direct arm = the Stage-15 configuration verbatim (n_init 6, n_iter 10,
     xi 0.01, candidate_pool 2048) on the UNTOUCHED BayesianOptimizer.
 S3  bar DELTA* = +22.20 L/D over the m=0 baseline at the campaign grid
     (90% of the Stage-15 recorded base-grid delta 24.66, rounded to 0.01;
     baseline reference value = the corpus baseline-anchor solve s17c_base).
 S4  figure of merit = MARGINAL ground-truth CFD evals to the first
     CFD-verified value >= baseline + DELTA*; the TOTAL-including-corpus
     accounting (marginal + corpus size) is ALWAYS reported alongside.
 S5  an arm not reaching DELTA* within 16 evals records "not reached"; a seed
     where neither arm reaches it is inconclusive and counts AGAINST GO.
 S6  GO <=> surrogate arm strictly fewer marginal evals in >= 2 of 3 seeds
     AND the cert of record is valid (C1-C4, in-window, data gate)
     AND the reported optimum passes V1-V3.
 S7  NO-GO fallback: direct-CFD BO remains the loop of record; document.
 S8  failed/diverged solves count as spent evals in BOTH arms (recorded with
     value=None; budget honesty). Within a surrogate batch, the within-batch
     eval order is the deterministic infill rank order.

Final-optimum verification (Invariant 12; the claim TIER is bounded by the
Stage-16 verdict — thesis-grade rests on the ledgered 393^2 rung, explicitly
out of Stage-17 scope; the GO-bar reading is recorded pre-campaign, ADR-031):
 V1  held-out fresh CFD re-solve of the reported optimum -> cfd_verified
     four-tuple; n_candidates = corpus + marginal evals; held_out_verification.
 V2  matched-grid pair (base + 1.7x coarse) vs the m=0 baseline via
     compose_result, k = 2; if significance fails the tag stays "validated"
     and is reported so.
 V3  surrogate_predicted = True on the OptimizationResult.

Contingency (pre-registered): the corpus may be EXTENDED by further seeded LHS
batches BEFORE any speed-up arm runs if C1/C2 fail on first training. The
gates themselves never move.
================================================================================

Writes data/vv/stage17_arm_<arm>_s<seed>.json at END only (clean-tree discipline).
"""

from __future__ import annotations

import argparse
import json
import os
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]

# --- pre-registered constants (ADR-032; duplicated from the gate block above) ---
BAR_DELTA = 22.20
MAX_EVALS = 16
DIRECT_N_INIT = 6
DIRECT_N_ITER = 10
MEMBER_LENGTH_SCALES = (0.20, 0.25, 0.30, 0.35, 0.40)
CORPUS_DVC_PATH = "data/datasets/stage17_naca4_ld"
# The Invariant-9 data gate targets the tracked corpus FILE (dvc tracks files, not the
# dataset dir; `dvc status -c <dir>` errors — ADR-032 sync-state-hash note).
CORPUS_HASH_PATH = f"{CORPUS_DVC_PATH}/corpus.json"
BASELINE_CASE = "s17c_base"


def main() -> None:
    ap = argparse.ArgumentParser(description="Run one (arm, seed) of the Stage-17 comparison.")
    ap.add_argument("--arm", choices=("direct", "surrogate"), required=True)
    ap.add_argument("--seed", type=int, required=True)
    ap.add_argument("--host", default="aero-dev")
    ap.add_argument("--concurrent", type=int, default=4, help="Surrogate-batch solve width.")
    ap.add_argument("--reynolds", type=float, default=5.0e5)
    ap.add_argument("--aoa", type=float, default=4.0)
    ap.add_argument("--end-time", type=int, default=3000)
    ap.add_argument("--timeout", type=int, default=14400)
    ap.add_argument("--allow-dirty", action="store_true")
    ap.add_argument("--no-mlflow", action="store_true")
    ap.add_argument("--out", default=None)
    args = ap.parse_args()

    import numpy as np
    from aero.adapters.openfoam.solver import OpenFOAMSolver
    from aero.optimize import (
        AcceleratedConfig,
        BayesianOptimizer,
        BOConfig,
        DesignSpace,
        DesignVariable,
        SurrogateAcceleratedOptimizer,
    )
    from aero.optimize.corpus import load_corpus, to_samples
    from aero.optimize.gp import GPConfig
    from aero.optimize.objective import ObjectiveEval
    from aero.optimize.speedup import ArmTrace, EvalRow
    from aero.optimize.turbulent_airfoil import ShapedTurbulentAirfoil
    from aero.orchestration import LocalSSHExecutor
    from aero.provenance import compute_provenance
    from aero.provenance.db import resolve_dsn
    from aero.surrogates._common.certificate import ApplicabilityEnvelope
    from aero.surrogates._common.loaders import dataset_hash
    from aero.surrogates.gp_bootstrap import GPBootstrapMember
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
            DesignVariable(name="max_camber", low=0.0, high=0.08),
            DesignVariable(name="camber_position", low=0.2, high=0.6),
        )
    )

    corpus = load_corpus(_REPO_ROOT / CORPUS_DVC_PATH / "corpus.json")
    baseline_rows = [r for r in corpus.rows if r.case_name == BASELINE_CASE and r.ld is not None]
    if not baseline_rows:
        raise SystemExit(f"corpus has no converged baseline anchor {BASELINE_CASE!r}")
    ld_val = baseline_rows[0].ld
    assert ld_val is not None
    baseline_value: float = ld_val
    target = baseline_value + BAR_DELTA
    print(
        f"ARM {args.arm} seed={args.seed} baseline={baseline_value:.4f} "
        f"bar=+{BAR_DELTA} target={target:.4f}",
        flush=True,
    )

    prov_lock = threading.Lock()  # serialize git reads (index.lock race — Stage-16 gotcha)
    eval_counter = {"n": 0}
    counter_lock = threading.Lock()

    def solve_design(x: np.ndarray) -> ObjectiveEval:
        """One ground-truth solve (raises on failure — callers decide the S8 policy)."""
        with counter_lock:
            eval_counter["n"] += 1
            idx = eval_counter["n"]
        dv = space.as_named(np.asarray(x, dtype=np.float64))
        case = ShapedTurbulentAirfoil(
            name=f"s17{args.arm[0]}{args.seed}_{idx:02d}",
            aoa_deg=args.aoa,
            reynolds=args.reynolds,
            max_camber=dv["max_camber"],
            camber_position=dv["camber_position"],
            end_time=args.end_time,
        )
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
        return ObjectiveEval(
            design=tuple(float(v) for v in np.asarray(x, dtype=np.float64)),
            value=float(obs.value),
            mlflow_run_id=obs.mlflow_run_id,
            provenance=prov,
        )

    rows: list[EvalRow] = []
    accelerated_dump: dict[str, object] | None = None

    if args.arm == "direct":
        # S2: Stage-15 configuration verbatim; serial ask/tell chain.
        bo = BayesianOptimizer(
            space, BOConfig(n_init=DIRECT_N_INIT, n_iter=DIRECT_N_ITER, seed=args.seed)
        )
        for i in range(MAX_EVALS):
            x = bo.ask()
            t0 = time.monotonic()
            try:
                ev = solve_design(x)
                bo.tell(x, ev.value, mlflow_run_id=ev.mlflow_run_id)
                value: float | None = ev.value
                run_id = ev.mlflow_run_id
            except Exception as exc:
                value, run_id = None, None
                print(f"FAIL eval {i + 1}: {type(exc).__name__}: {exc}", flush=True)
            rows.append(
                EvalRow(n=i + 1, design_named=space.as_named(x), value=value, mlflow_run_id=run_id)
            )
            shown = "failed" if value is None else f"{value:.4f}"
            print(
                f"EVAL {i + 1}/{MAX_EVALS} dv={space.as_named(x)} L/D={shown} "
                f"wall={time.monotonic() - t0:.0f}s",
                flush=True,
            )
            if value is not None and value - baseline_value >= BAR_DELTA:
                print(f"BAR reached at eval {i + 1}", flush=True)
                break
    else:
        samples = to_samples(corpus)
        envelope = ApplicabilityEnvelope(
            re_range=(args.reynolds, args.reynolds),
            mach_range=(0.0, 0.0),
            aoa_range_deg=(args.aoa, args.aoa),
            geometry_class="naca-4digit",
        )

        def dataset_hash_fn() -> str:
            return dataset_hash(_REPO_ROOT, CORPUS_HASH_PATH)

        def member_factory(i: int) -> GPBootstrapMember:
            return GPBootstrapMember(
                gp_config=GPConfig(kernel="matern52", length_scale=MEMBER_LENGTH_SCALES[i]),
                training_dataset_dvc_hash=dataset_hash_fn(),
                dataset_id=corpus.dataset_id,
                applicability_envelope=envelope,
                metric_name="ld_mae",
            )

        def evaluate_batch(designs: list[np.ndarray]) -> list[ObjectiveEval | None]:
            def one(x: np.ndarray) -> ObjectiveEval | None:
                try:
                    return solve_design(x)
                except Exception as exc:
                    print(f"FAIL batch solve: {type(exc).__name__}: {exc}", flush=True)
                    return None

            with ThreadPoolExecutor(max_workers=args.concurrent) as pool:
                return list(pool.map(one, designs))

        opt = SurrogateAcceleratedOptimizer(
            space=space,
            corpus=samples,
            member_factory=member_factory,
            envelope=envelope,
            dataset_id=corpus.dataset_id,
            dataset_hash_fn=dataset_hash_fn,
            evaluate_batch=evaluate_batch,
            config=AcceleratedConfig(
                target_value=target,
                max_cfd_evals=MAX_EVALS,
                seed=args.seed,
                n_members=len(MEMBER_LENGTH_SCALES),
            ),
            basis="gp_bootstrap",
            metric_name="ld_mae",
        )
        run = opt.run()
        accelerated_dump = json.loads(run.model_dump_json())
        n = 0
        for record in run.records:
            for candidate, result in zip(record.candidates, record.results, strict=True):
                n += 1
                dv = space.as_named(space.from_unit(np.asarray(candidate.design)))
                rows.append(
                    EvalRow(
                        n=n,
                        design_named=dv,
                        value=None if result is None else result.value,
                        mlflow_run_id=None if result is None else result.mlflow_run_id,
                    )
                )
        print(
            f"ACCEL stop={run.stop_reason} n_cfd={run.n_cfd_evals} "
            f"incumbent={run.incumbent_value:.4f} from_corpus={run.incumbent_from_corpus}",
            flush=True,
        )
        if not rows:
            # Corpus already at/past the bar: zero-marginal-eval run — still a trace
            # (a single synthetic row is NOT added; the report driver reads the
            # accelerated dump's stop_reason for this case).
            print("NOTE zero marginal evals (corpus already at bar)", flush=True)

    trace = (
        ArmTrace(
            arm=args.arm,
            seed=args.seed,
            baseline_value=baseline_value,
            rows=tuple(rows),
        )
        if rows
        else None
    )
    out = Path(args.out or _REPO_ROOT / "data" / "vv" / f"stage17_arm_{args.arm}_s{args.seed}.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    bundle = {
        "arm": args.arm,
        "seed": args.seed,
        "bar_delta": BAR_DELTA,
        "baseline_value": baseline_value,
        "max_evals": MAX_EVALS,
        "trace": None if trace is None else json.loads(trace.model_dump_json()),
        "accelerated": accelerated_dump,
    }
    out.write_text(json.dumps(bundle, indent=2) + "\n", encoding="utf-8")
    reached = None if trace is None else trace.reached_at(BAR_DELTA)
    print(f"RESULT arm={args.arm} seed={args.seed} reached_at={reached} out={out}", flush=True)


if __name__ == "__main__":
    main()
