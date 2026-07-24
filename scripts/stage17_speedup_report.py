#!/usr/bin/env python
"""Stage-17 verdict composition — speed-up comparison + cert of record + verification (ADR-032).

Two modes:

1. ``--assemble-v2`` (host-side, no CFD): collect the surrogate arms' infill evaluations
   from data/vv/stage17_arm_surrogate_s*.json into ``corpus_v2.json`` in the dataset dir
   (the flywheel grows). Then: ``dvc add`` + commit + ``dvc push`` BEFORE the finalize
   mode runs — the cert of record is issued against the COMMITTED corpus state.
   (Direct-arm evals are also own CFD but ride only in their bundles for now — EvalRow
   does not carry the four-fold tuple; ledgered.)

2. default (finalize; ~4 CFD solves): apply the PRE-REGISTERED comparison rule
   (S1-S8, see scripts/stage17_speedup_arm.py — the gate block of record), re-check the
   cert of record (in-window + data gate against the committed corpus), pick the
   reported optimum, run the V1/V2 verification solves, compose the OptimizationResult,
   and write:
     data/vv/stage17_speedup.json       (the comparison verdict, both accountings)
     data/vv/stage17_optimization.json  (the CFD-verified reported optimum)

Honest verdict handling: the pre-registered marginal metric (S6) is DEGENERATE when the
training corpus already contains designs past the bar — the surrogate-accelerated loop then
seeds its incumbent past the bar and does 0 marginal search, and scoring 0 < any-direct-count
as a "win" would be the exact corpus-cost-hiding sleight-of-hand the S4 total-cost gate exists
to expose. So a 0-marginal-from-corpus surrogate arm yields an honest NO-GO (never a hollow
GO), with both accountings reported. The reported optimum is the best CFD-verified design
across the WHOLE selection pool (corpus + every arm's evals + the exploratory loop), tagged by
origin, so surrogate_predicted reflects how the reported design was actually found; n_candidates
is the full pool size and V1 supplies the held-out verification (Invariant 12 selection-bias).
"""

from __future__ import annotations

import argparse
import json
import os
from datetime import UTC, datetime
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]

BAR_DELTA = 22.20
MIN_WINS = 2
SEEDS = (0, 1, 2)
CORPUS_DVC_PATH = "data/datasets/stage17_naca4_ld"
# Invariant-9 data-gate target: the tracked corpus FILE (ADR-032 sync-state-hash note).
CORPUS_HASH_PATH = f"{CORPUS_DVC_PATH}/corpus.json"
REFINE_RATIO = 1.7
K_MARGIN = 2.0


def assemble_v2() -> None:
    from aero.optimize.corpus import CorpusRow, Stage17Corpus, load_corpus, save_corpus
    from aero.provenance.four_fold import ProvenanceTuple

    base = load_corpus(_REPO_ROOT / CORPUS_DVC_PATH / "corpus.json")
    rows: list[CorpusRow] = []
    # The pre-registered surrogate arms are 0-marginal here (corpus already past bar), so the
    # flywheel growth comes from the exploratory loop's genuine infill evals. Include every
    # surrogate-loop bundle that actually searched.
    bundles = [
        (f"s{seed}", _REPO_ROOT / "data" / "vv" / f"stage17_arm_surrogate_s{seed}.json")
        for seed in SEEDS
    ] + [("explore", _REPO_ROOT / "data" / "vv" / "stage17_arm_surrogate_explore.json")]
    for label, bundle_path in bundles:
        if not bundle_path.exists():
            continue
        bundle = json.loads(bundle_path.read_text(encoding="utf-8"))
        accel = bundle.get("accelerated")
        if accel is None:
            continue
        for record in accel["records"]:
            for candidate, result in zip(record["candidates"], record["results"], strict=True):
                if result is None:
                    continue
                dv = dict(
                    zip(
                        base.space.names,
                        [float(v) for v in result["design"]],
                        strict=True,
                    )
                )
                rows.append(
                    CorpusRow(
                        case_name=f"s17{label}_it{record['iteration']:02d}_r{candidate['rank']}",
                        design_named=dv,
                        design_unit=tuple(float(v) for v in candidate["design"]),
                        ld=float(result["value"]),
                        mlflow_run_id=result.get("mlflow_run_id"),
                        provenance=ProvenanceTuple.model_validate(result["provenance"]),
                    )
                )
    v2 = Stage17Corpus(
        dataset_id=base.dataset_id,
        space=base.space,
        reynolds=base.reynolds,
        aoa_deg=base.aoa_deg,
        end_time=base.end_time,
        seed=base.seed,
        n_lhs=0,
        created_at=datetime.now(UTC).isoformat(),
        rows=tuple(rows),
    )
    out = _REPO_ROOT / CORPUS_DVC_PATH / "corpus_v2.json"
    save_corpus(v2, out)
    print(f"V2 n_infill_rows={len(rows)} out={out}")
    print("NEXT: dvc add + commit + dvc push, re-run stage17_train_cert.py, then finalize.")


def finalize(args: argparse.Namespace) -> None:

    from aero.adapters.openfoam.solver import OpenFOAMSolver
    from aero.optimize.corpus import load_corpus
    from aero.optimize.report import MatchedGridDelta, compose_result
    from aero.optimize.speedup import ArmTrace
    from aero.optimize.turbulent_airfoil import ShapedTurbulentAirfoil
    from aero.orchestration import LocalSSHExecutor
    from aero.provenance import compute_provenance
    from aero.provenance.db import resolve_dsn
    from aero.surrogates._common.certificate import CertificateOfValidity
    from aero.surrogates._common.loaders import dataset_hash
    from aero.vv._base import BenchmarkRunner

    # --- load the campaign evidence -------------------------------------------------
    corpus = load_corpus(_REPO_ROOT / CORPUS_DVC_PATH / "corpus.json")
    corpus_size = len(corpus.ok_rows)
    corpus_best = max(r.ld for r in corpus.ok_rows if r.ld is not None)
    baseline_ref = next(r.ld for r in corpus.ok_rows if r.case_name == "s17c_base")
    assert baseline_ref is not None
    bar_abs = baseline_ref + BAR_DELTA
    corpus_past_bar = sum(1 for r in corpus.ok_rows if r.ld is not None and r.ld >= bar_abs)

    # Every CFD-verified design the platform holds, tagged by how it was found — the honest
    # selection pool for the reported optimum (Invariant 12) and for the reported-optimum origin.
    pool: list[tuple[float, dict[str, float], str]] = [
        (r.ld, r.design_named, "corpus") for r in corpus.ok_rows if r.ld is not None
    ]

    direct_marginal: dict[int, int | None] = {}
    for seed in SEEDS:
        path = _REPO_ROOT / "data" / "vv" / f"stage17_arm_direct_s{seed}.json"
        bundle = json.loads(path.read_text(encoding="utf-8"))
        trace = ArmTrace.model_validate(bundle["trace"])
        direct_marginal[seed] = trace.reached_at(BAR_DELTA)
        pool += [(r.value, r.design_named, "direct") for r in trace.rows if r.value is not None]

    # Surrogate arms: the pre-registered comparison. A trace of None means the loop stopped at
    # 0 marginal evals because its incumbent (best corpus row) was already past the bar — the
    # corpus already solved the problem, so there was nothing to accelerate.
    surrogate_marginal: dict[int, int | None] = {}
    surrogate_from_corpus: dict[int, bool] = {}
    for seed in SEEDS:
        path = _REPO_ROOT / "data" / "vv" / f"stage17_arm_surrogate_s{seed}.json"
        bundle = json.loads(path.read_text(encoding="utf-8"))
        if bundle["trace"] is None:
            accel = bundle["accelerated"] or {}
            surrogate_marginal[seed] = 0
            surrogate_from_corpus[seed] = accel.get("incumbent_from_corpus", True)
        else:
            trace = ArmTrace.model_validate(bundle["trace"])
            surrogate_marginal[seed] = trace.reached_at(BAR_DELTA)
            surrogate_from_corpus[seed] = False
            pool += [
                (r.value, r.design_named, "surrogate") for r in trace.rows if r.value is not None
            ]

    # Exploratory loop (deliverable-2 machinery demonstration; never gates S) — fold its
    # CFD-verified candidates into the pool + corpus flywheel.
    explore_path = _REPO_ROOT / "data" / "vv" / "stage17_arm_surrogate_explore.json"
    explore: dict[str, object] | None = None
    if explore_path.exists():
        explore = json.loads(explore_path.read_text(encoding="utf-8"))
        etrace = explore["trace"]
        if etrace is not None:
            for r in ArmTrace.model_validate(etrace).rows:
                if r.value is not None:
                    pool.append((r.value, r.design_named, "surrogate-explore"))

    # Honest speed-up reading. The literal pre-registered marginal gate (S6) would score a
    # 0-marginal surrogate arm as a "win" (0 < any direct count), but that is the corpus, not
    # the surrogate: it performed no search. The S4 total-cost accounting exposes it, so the
    # honest verdict is NO-GO — a degenerate comparison, not a demonstrated acceleration.
    degenerate = all(surrogate_from_corpus[s] and surrogate_marginal[s] == 0 for s in SEEDS)
    literal_marginal_wins = sum(
        1
        for s in SEEDS
        if surrogate_marginal[s] is not None
        and (direct_marginal[s] is None or surrogate_marginal[s] < direct_marginal[s])
    )
    speedup_genuine_go = (not degenerate) and literal_marginal_wins >= MIN_WINS
    best_direct = min((v for v in direct_marginal.values() if v is not None), default=None)
    speedup = {
        "verdict": "GO" if speedup_genuine_go else "NO-GO",
        "degenerate": degenerate,
        "reason": (
            f"DEGENERATE: the {corpus_size}-solve training corpus already contains "
            f"{corpus_past_bar} designs past the bar (corpus best L/D {corpus_best:.3f} vs bar "
            f"{bar_abs:.3f}), so the surrogate-accelerated loop seeds its incumbent past the bar "
            f"and performs 0 marginal search in every seed. Direct-CFD BO reaches the bar from "
            f"scratch in {dict(direct_marginal)} marginal evals. Total-cost accounting: surrogate "
            f"= {corpus_size} corpus + 0 marginal; direct = {best_direct} from scratch — the "
            f"corpus cost dominates. No genuine single-run acceleration is demonstrated; fall "
            f"back to direct-CFD BO (S7). The bar is reachable by random LHS sampling (direct "
            f"arms cleared it during init), and surrogate acceleration's payoff is in "
            f"higher-dimensional / more expensive regimes and amortized across many runs — not "
            f"this cheap 2-D problem. See the handoff for the fair-test (reduced-prior) design."
            if degenerate
            else f"surrogate strictly fewer marginal evals in {literal_marginal_wins}/"
            f"{len(SEEDS)} seeds (>= {MIN_WINS})"
        ),
        "direct_marginal": {str(k): v for k, v in direct_marginal.items()},
        "surrogate_marginal": {str(k): v for k, v in surrogate_marginal.items()},
        "surrogate_from_corpus": {str(k): v for k, v in surrogate_from_corpus.items()},
        "literal_marginal_wins": literal_marginal_wins,
        "total_cost_surrogate_incl_corpus": corpus_size,
        "total_cost_direct_from_scratch": best_direct,
        "corpus_past_bar_designs": corpus_past_bar,
    }

    # --- cert of record: in-window + data gate against the committed corpus ---------
    cert_bundle = json.loads(
        (_REPO_ROOT / "data" / "vv" / "stage17_surrogate_cert.json").read_text(encoding="utf-8")
    )
    cert = CertificateOfValidity.model_validate(cert_bundle["certificate"])
    cert_valid = cert_bundle["verdict"] == "PROMOTED" and cert.cert_status == "validated"
    cert_gate_error: str | None = None
    try:
        cert.assert_current(current_dataset_hash=dataset_hash(_REPO_ROOT, CORPUS_HASH_PATH))
    except Exception as exc:
        cert_valid = False
        cert_gate_error = f"{type(exc).__name__}: {exc}"

    # --- reported optimum: the best CFD-verified design across the whole selection pool ------
    best_value, dv_star, opt_origin = max(pool, key=lambda t: t[0])
    n_candidates = len(pool)
    surrogate_predicted = opt_origin.startswith("surrogate")
    print(
        f"SPEEDUP verdict={speedup['verdict']} degenerate={degenerate} "
        f"direct_marginal={dict(direct_marginal)} surrogate_marginal={dict(surrogate_marginal)} "
        f"cert_valid={cert_valid} optimum_LD={best_value:.4f} origin={opt_origin} dv={dv_star}",
        flush=True,
    )

    # --- V1/V2 verification solves ---------------------------------------------------
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

    def solve_ld(dv: dict[str, float], name: str, ratio: float) -> tuple[float, object]:
        case = ShapedTurbulentAirfoil(
            name=name,
            aoa_deg=4.0,
            reynolds=corpus.reynolds,
            max_camber=dv["max_camber"],
            camber_position=dv["camber_position"],
            end_time=int(corpus.end_time),
        )
        refined = case.refined(ratio) if ratio != 1.0 else case
        prov = compute_provenance(
            repo_root=_REPO_ROOT,
            container_sif="openfoam-esi.sif",
            resolved_config=refined.case_spec().model_dump(mode="json"),
            allow_dirty=args.allow_dirty,
        )
        obs = runner.measure_scalar(
            refined, "ld", provenance=prov, repo_root=_REPO_ROOT, log_mlflow=log_mlflow
        )
        return float(obs.value), prov

    baseline_dv = {"max_camber": 0.0, "camber_position": dv_star["camber_position"]}
    ld_base_fine, _ = solve_ld(baseline_dv, "s17v_base_fine", 1.0)
    ld_base_coarse, _ = solve_ld(baseline_dv, "s17v_base_coarse", REFINE_RATIO)
    ld_opt_fine, heldout_prov = solve_ld(dv_star, "s17v_opt_fine", 1.0)  # V1 held-out re-solve
    ld_opt_coarse, _ = solve_ld(dv_star, "s17v_opt_coarse", REFINE_RATIO)

    delta = MatchedGridDelta(
        quantity="lift_to_drag",
        baseline_fine=ld_base_fine,
        baseline_coarse=ld_base_coarse,
        optimum_fine=ld_opt_fine,
        optimum_coarse=ld_opt_coarse,
        refinement_ratio=REFINE_RATIO,
    )
    from aero.provenance.four_fold import ProvenanceTuple

    assert isinstance(heldout_prov, ProvenanceTuple)
    result, delta_significant = compose_result(
        case_name="stage17_surrogate_accel_naca4",
        objective=(
            "maximize lift_to_drag at AoA=4 deg (Re=5e5 k-omega SST NACA-4 camber; "
            "surrogate-accelerated, every optimum CFD-verified)"
        ),
        quantity="lift_to_drag",
        higher_is_better=True,
        design_variables=dv_star,
        delta=delta,
        cfd_verified=heldout_prov,
        n_candidates=n_candidates,
        surrogate_predicted=surrogate_predicted,
        k=K_MARGIN,
    )

    bar_reached_verified = (ld_opt_fine - ld_base_fine) >= BAR_DELTA
    # Deliverables 1-3 (validated own-data surrogate + ADR-025-wired loop + CFD-verified optimum)
    # are established outside this driver; the speed-up axis (deliverable 4) is the honest NO-GO
    # here. overall_go tracks the speed-up axis only, and is never a hollow GO.
    overall_go = bool(speedup_genuine_go and cert_valid and bar_reached_verified)

    explore_summary = None
    if explore is not None and explore.get("accelerated") is not None:
        acc = explore["accelerated"]
        explore_summary = {
            "stop_reason": acc["stop_reason"],
            "n_cfd_evals": acc["n_cfd_evals"],
            "incumbent_value": acc["incumbent_value"],
            "incumbent_from_corpus": acc["incumbent_from_corpus"],
            "note": "exploratory deliverable-2 demonstration; never gates the speed-up S-gates",
        }

    out_speedup = _REPO_ROOT / "data" / "vv" / "stage17_speedup.json"
    out_speedup.write_text(
        json.dumps(
            {
                "verdict": "GO" if overall_go else "NO-GO",
                "speedup": speedup,
                "cert_of_record": {
                    "valid": cert_valid,
                    "error": cert_gate_error,
                    "status": cert.cert_status,
                    "coverage": (
                        None
                        if cert.uncertainty_calibration is None
                        else cert.uncertainty_calibration.empirical_coverage
                    ),
                },
                "verification": {
                    "V1_held_out_ld": ld_opt_fine,
                    "V2_delta_fine": delta.delta_fine,
                    "V2_significant_at_k2": delta_significant,
                    "V2_tag": result.validation_tag,
                    "bar_reached_on_verification": bar_reached_verified,
                },
                "reported_optimum": {
                    "origin": opt_origin,
                    "surrogate_predicted": surrogate_predicted,
                    "design": dv_star,
                    "loop_best_ld": best_value,
                },
                "exploratory_loop": explore_summary,
                "n_candidates": n_candidates,
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    out_opt = _REPO_ROOT / "data" / "vv" / "stage17_optimization.json"
    out_opt.write_text(result.model_dump_json(indent=2) + "\n", encoding="utf-8")
    print(
        f"RESULT speedup={speedup['verdict']} degenerate={degenerate} "
        f"reported_optimum_origin={opt_origin} surrogate_predicted={surrogate_predicted} "
        f"tag={result.validation_tag} baseline_LD={ld_base_fine:.4f} "
        f"optimum_LD={ld_opt_fine:.4f} delta={delta.delta_fine:.4f} "
        f"literal_marginal_wins={literal_marginal_wins}/{len(SEEDS)} out={out_speedup}",
        flush=True,
    )


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--assemble-v2", action="store_true")
    ap.add_argument("--host", default="aero-dev")
    ap.add_argument("--timeout", type=int, default=14400)
    ap.add_argument("--allow-dirty", action="store_true")
    ap.add_argument("--no-mlflow", action="store_true")
    args = ap.parse_args()
    if args.assemble_v2:
        assemble_v2()
    else:
        finalize(args)


if __name__ == "__main__":
    main()
