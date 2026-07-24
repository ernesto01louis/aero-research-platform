#!/usr/bin/env python
"""Stage-17 surrogate training + gated certification — own-data ensemble (ADR-031/032).

Trains the gp_bootstrap ensemble on the COMMITTED own-CFD corpus and attempts the gated
promotion to a ``validated`` certificate. CPU-light, host-side, seconds.

    python scripts/stage17_train_cert.py

PRE-REGISTERED CERTIFICATION GATES (committed before any campaign; NEVER relaxed):
  C1  held-out +/-2*std empirical coverage in [0.85, 1.0]
      (amends the DRAFT band [0.85, 0.99] — recorded pre-campaign in ADR-031: at
      holdout n~10 a perfectly calibrated estimator lands coverage 1.0 with p~0.62,
      so the DRAFT's upper bound rejects calibrated models more often than not;
      the over-wide-sigma pathology stays guarded by C2 + the D1 z-diagnostics)
  C2  held-out |L/D error| p95 <= 2.5
  C3  non-collapsed ensemble (structural: CalibrationError aborts fit — ADR-025)
  C4  every sample data_origin == "platform-validated" (Invariant 11; the corpus
      builder asserts it explicitly and a foreign+validated cert is unconstructible)
  D1  mean_abs_z / std_z / coverage reported as diagnostics, never gated

MEMBER FAMILY (frozen): 5 x GPBootstrapMember, matern52, length_scale in
{0.20, 0.25, 0.30, 0.35, 0.40} (model-form diversity), GPConfig defaults otherwise.
ENSEMBLE FIT (frozen): seed=17, calibration_fraction=0.25, interval_k=2.0.

Exit code 0 = promoted (validated cert written); 1 = PromotionRefused (the refusal is
itself campaign evidence — the pre-registered contingency is to EXTEND the corpus with
further seeded LHS batches BEFORE any speed-up arm runs; the gates never move).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]

MEMBER_LENGTH_SCALES = (0.20, 0.25, 0.30, 0.35, 0.40)
FIT_SEED = 17
CALIBRATION_FRACTION = 0.25
INTERVAL_K = 2.0
GATE_C1_COVERAGE = (0.85, 1.0)
GATE_C2_P95 = 2.5


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--corpus-dir", default=None, help="Dir holding corpus*.json bundles.")
    ap.add_argument("--out", default=None)
    args = ap.parse_args()

    from aero.optimize.corpus import load_corpus, to_samples
    from aero.optimize.gp import GPConfig
    from aero.surrogates._common.certificate import ApplicabilityEnvelope
    from aero.surrogates._common.ensemble import EnsembleSurrogate, PromotionRefused
    from aero.surrogates._common.loaders import dataset_hash
    from aero.surrogates.gp_bootstrap import GPBootstrapMember

    corpus_dir = Path(args.corpus_dir or _REPO_ROOT / "data" / "datasets" / "stage17_naca4_ld")
    corpus_files = sorted(corpus_dir.glob("corpus*.json"))
    if not corpus_files:
        raise SystemExit(f"no corpus*.json under {corpus_dir} — run stage17_corpus.py first")
    samples = []
    for f in corpus_files:
        samples.extend(to_samples(load_corpus(f)))
    print(f"CORPUS files={[f.name for f in corpus_files]} n_samples={len(samples)}", flush=True)

    # The Invariant-9 data gate targets the tracked corpus FILE (dvc tracks files, not the
    # dataset dir — `dvc status -c <dir>` errors; ADR-032 sync-state-hash note).
    dvc_hash = dataset_hash(_REPO_ROOT, corpus_dir.relative_to(_REPO_ROOT) / "corpus.json")
    envelope = ApplicabilityEnvelope(
        re_range=(5.0e5, 5.0e5),
        mach_range=(0.0, 0.0),
        aoa_range_deg=(4.0, 4.0),
        geometry_class="naca-4digit",
    )

    def member(i: int) -> GPBootstrapMember:
        return GPBootstrapMember(
            gp_config=GPConfig(kernel="matern52", length_scale=MEMBER_LENGTH_SCALES[i]),
            training_dataset_dvc_hash=dvc_hash,
            dataset_id="stage17-naca4-ld",
            applicability_envelope=envelope,
            metric_name="ld_mae",
        )

    ensemble = EnsembleSurrogate(
        [member(i) for i in range(len(MEMBER_LENGTH_SCALES))],
        surrogate_name="stage17_ld_ensemble",
        training_dataset_dvc_hash=dvc_hash,
        dataset_id="stage17-naca4-ld",
        applicability_envelope=envelope,
        basis="gp_bootstrap",
        metric_name="ld_mae",
    )
    # C3 fires structurally here (CalibrationError on a collapsed ensemble).
    ensemble.fit(
        samples,
        seed=FIT_SEED,
        calibration_fraction=CALIBRATION_FRACTION,
        interval_k=INTERVAL_K,
    )
    smoke = ensemble.set_certificate()
    cal = smoke.uncertainty_calibration
    quantiles = smoke.held_out_metrics["ld_mae"]
    assert cal is not None  # ensemble certs always carry calibration evidence

    print(
        f"D1 coverage={cal.empirical_coverage:.4f} (nominal {cal.nominal_coverage:.4f}) "
        f"mean_abs_z={cal.mean_abs_z:.3f} std_z={cal.std_z:.3f} n_held_out={cal.n_held_out}",
        flush=True,
    )
    print(
        f"C2 ld_mae p50={quantiles.p50:.4f} p95={quantiles.p95:.4f} p99={quantiles.p99:.4f} "
        f"(bar p95 <= {GATE_C2_P95})",
        flush=True,
    )

    verdict = "PROMOTED"
    refusal: str | None = None
    try:
        cert = ensemble.promote_to_validated(
            max_metric_p95=GATE_C2_P95,
            coverage_min=GATE_C1_COVERAGE[0],
            coverage_max=GATE_C1_COVERAGE[1],
        )
    except PromotionRefused as exc:
        verdict = "REFUSED"
        refusal = str(exc)
        cert = smoke

    out = Path(args.out or _REPO_ROOT / "data" / "vv" / "stage17_surrogate_cert.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    bundle = {
        "verdict": verdict,
        "refusal": refusal,
        "gates": {
            "C1_coverage_band": list(GATE_C1_COVERAGE),
            "C1_empirical_coverage": cal.empirical_coverage,
            "C2_p95_bar": GATE_C2_P95,
            "C2_p95": quantiles.p95,
            "C3_non_collapsed": True,
            "C4_data_origin": cert.data_origin,
        },
        "member_length_scales": list(MEMBER_LENGTH_SCALES),
        "fit": {
            "seed": FIT_SEED,
            "calibration_fraction": CALIBRATION_FRACTION,
            "interval_k": INTERVAL_K,
            "n_samples": len(samples),
        },
        "corpus_files": [f.name for f in corpus_files],
        "calibration_case_ids": list(ensemble.calibration_case_ids),
        "certificate": json.loads(cert.model_dump_json()),
    }
    out.write_text(json.dumps(bundle, indent=2) + "\n", encoding="utf-8")
    print(f"CERT verdict={verdict} status={cert.cert_status} out={out}", flush=True)
    if verdict == "REFUSED":
        print(f"REFUSAL {refusal}", flush=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
