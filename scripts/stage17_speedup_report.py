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
   reported optimum, run the V1/V2 verification solves, compose the OptimizationResult
   (V3: surrogate_predicted=True), and write:
     data/vv/stage17_speedup.json       (the comparison verdict, both accountings)
     data/vv/stage17_optimization.json  (the CFD-verified reported optimum)

Reported-optimum selection (pre-registered): if the speed-up gate passes, the best
CFD-verified incumbent across the SURROGATE arms; on the S7 fallback, the best across
the DIRECT arms. Either way n_candidates counts every ground-truth eval the selection
scanned (corpus + all marginal evals of the selected family) and V1 supplies the
held-out verification (Invariant 12 selection-bias guard).
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
REFINE_RATIO = 1.7
K_MARGIN = 2.0


def assemble_v2() -> None:
    from aero.optimize.corpus import CorpusRow, Stage17Corpus, load_corpus, save_corpus
    from aero.provenance.four_fold import ProvenanceTuple

    base = load_corpus(_REPO_ROOT / CORPUS_DVC_PATH / "corpus.json")
    rows: list[CorpusRow] = []
    for seed in SEEDS:
        bundle_path = _REPO_ROOT / "data" / "vv" / f"stage17_arm_surrogate_s{seed}.json"
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
                        case_name=f"s17s{seed}_it{record['iteration']:02d}_r{candidate['rank']}",
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
    from aero.optimize.speedup import ArmTrace, evaluate_speedup
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
    direct: list[ArmTrace] = []
    surrogate: list[ArmTrace] = []
    incumbents: dict[str, list[tuple[float, dict[str, float]]]] = {"direct": [], "surrogate": []}
    for arm, sink in (("direct", direct), ("surrogate", surrogate)):
        for seed in SEEDS:
            path = _REPO_ROOT / "data" / "vv" / f"stage17_arm_{arm}_s{seed}.json"
            bundle = json.loads(path.read_text(encoding="utf-8"))
            if bundle["trace"] is None:
                raise SystemExit(f"{path} has no trace — zero-marginal-eval runs need review")
            trace = ArmTrace.model_validate(bundle["trace"])
            sink.append(trace)
            converged = [(r.value, r.design_named) for r in trace.rows if r.value is not None]
            if converged:  # an arm-seed with every solve failed contributes no incumbent
                incumbents[arm].append(max(converged, key=lambda t: t[0]))
            else:
                print(f"WARN {path.name}: no converged solve — arm-seed contributes no incumbent")

    verdict = evaluate_speedup(
        tuple(direct),
        tuple(surrogate),
        bar_delta=BAR_DELTA,
        corpus_size=corpus_size,
        min_wins=MIN_WINS,
    )

    # --- cert of record: in-window + data gate against the committed corpus ---------
    cert_bundle = json.loads(
        (_REPO_ROOT / "data" / "vv" / "stage17_surrogate_cert.json").read_text(encoding="utf-8")
    )
    cert = CertificateOfValidity.model_validate(cert_bundle["certificate"])
    cert_valid = cert_bundle["verdict"] == "PROMOTED" and cert.cert_status == "validated"
    cert_gate_error: str | None = None
    try:
        cert.assert_current(current_dataset_hash=dataset_hash(_REPO_ROOT, CORPUS_DVC_PATH))
    except Exception as exc:
        cert_valid = False
        cert_gate_error = f"{type(exc).__name__}: {exc}"

    # --- reported optimum (pre-registered selection; S7 fallback) --------------------
    family = "surrogate" if (verdict.speedup_gate_pass and cert_valid) else "direct"
    if not incumbents[family]:
        raise SystemExit(f"no successful evals in the {family} arms — nothing to report")
    best_value, dv_star = max(incumbents[family], key=lambda t: t[0])
    marginal_scanned = sum(len(t.rows) for t in (surrogate if family == "surrogate" else direct))
    n_candidates = corpus_size + marginal_scanned
    print(
        f"SPEEDUP pass={verdict.speedup_gate_pass} wins={verdict.wins}/{len(SEEDS)} "
        f"cert_valid={cert_valid} family={family} optimum_LD={best_value:.4f} dv={dv_star}",
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
        surrogate_predicted=(family == "surrogate"),
        k=K_MARGIN,
    )

    bar_reached_verified = (ld_opt_fine - ld_base_fine) >= BAR_DELTA
    overall_go = bool(verdict.speedup_gate_pass and cert_valid and bar_reached_verified)

    out_speedup = _REPO_ROOT / "data" / "vv" / "stage17_speedup.json"
    out_speedup.write_text(
        json.dumps(
            {
                "verdict": "GO" if overall_go else "NO-GO",
                "speedup_gate": json.loads(verdict.model_dump_json()),
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
                "reported_family": family,
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
        f"RESULT verdict={'GO' if overall_go else 'NO-GO'} family={family} "
        f"tag={result.validation_tag} baseline_LD={ld_base_fine:.4f} "
        f"optimum_LD={ld_opt_fine:.4f} delta={delta.delta_fine:.4f} "
        f"wins={verdict.wins}/{len(SEEDS)} out={out_speedup}",
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
