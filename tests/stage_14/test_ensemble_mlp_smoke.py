"""ADR-025 — end-to-end integration smoke: MLP deep ensemble → cert → infill routing.

Exercises the whole anti-surrogate-exploitation stack on real torch members:
3x MLPBaseline in an EnsembleSurrogate, fit on synthetic AhmedML-shaped
samples, certificate carrying ensemble_size + calibration evidence, epistemic
std > 0 somewhere, and a rank_infill_candidates pass over a small candidate
grid returning routed candidates.

Skips without the `aero[surrogate-smoke]` extras (torch); mirrors the
Stage-08 baseline-test conventions.
"""

from __future__ import annotations

import pytest
from aero.surrogates._common.base import Sample
from aero.surrogates._common.certificate import ApplicabilityEnvelope
from aero.surrogates._common.ensemble import EnsembleSurrogate
from aero.surrogates._common.infill import rank_infill_candidates

pytestmark = [pytest.mark.stage_14, pytest.mark.slow]

_ENVELOPE = ApplicabilityEnvelope(
    re_range=(1e5, 5e6),
    mach_range=(0.0, 0.3),
    aoa_range_deg=(-5.0, 15.0),
    geometry_class="ahmed-body",
)
_HASH_A = "a" * 64


def _sample(i: int) -> Sample:
    return Sample(
        features=(float(i % 10) * 4.5, 1.0 + 0.01 * i, 0.05, 0.05),
        targets=(0.28 + 0.001 * i,),
        case_id=f"a-{i:04d}",
        dataset_id="ahmedml",
    )


def test_ensemble_mlp_end_to_end(surrogate_smoke_extra_installed: bool) -> None:
    if not surrogate_smoke_extra_installed:
        pytest.skip("aero[surrogate-smoke] extras not installed")
    from aero.surrogates.baselines import MLPBaseline

    members = [
        MLPBaseline(
            training_dataset_dvc_hash=_HASH_A,
            dataset_id="ahmedml",
            applicability_envelope=_ENVELOPE,
        )
        for _ in range(3)
    ]
    ensemble = EnsembleSurrogate(
        members,
        surrogate_name="mlp_ensemble_smoke",
        training_dataset_dvc_hash=_HASH_A,
        dataset_id="ahmedml",
        applicability_envelope=_ENVELOPE,
    )
    samples = [_sample(i) for i in range(40)]
    ensemble.fit(samples, epochs=10, hidden_dim=16, seed=42)
    cert = ensemble.set_certificate()

    # Certificate carries the ADR-025 evidence.
    assert cert.cert_status == "smoke"
    assert cert.ensemble_size == 3
    assert cert.model_architecture == "deep_ensemble(mlp_baseline, n=3)"
    assert cert.uncertainty_calibration is not None
    assert cert.uncertainty_calibration.basis == "deep_ensemble"
    assert cert.uncertainty_calibration.n_held_out == 8  # 20% of 40
    tags = cert.as_mlflow_tags()
    assert tags["ensemble_size"] == "3"
    assert "uq_calibration_coverage" in tags

    # Differently-seeded torch members disagree somewhere → epistemic std > 0.
    prediction = ensemble.predict_with_uncertainty(samples[0].features)
    assert prediction.basis == "deep_ensemble"
    assert prediction.n_members == 3
    assert prediction.epistemic_std is not None
    assert any(s > 0.0 for s in prediction.epistemic_std)

    # End-to-end infill routing over a small candidate grid (minimize Cd).
    grid = [(float(a) * 4.5, 1.0, 0.05, 0.05) for a in range(8)]
    predictions = [ensemble.predict_with_uncertainty(g) for g in grid]
    batch = rank_infill_candidates(
        grid,
        [p.mean[0] for p in predictions],
        [p.epistemic_std[0] for p in predictions if p.epistemic_std is not None],
        current_best=0.30,
        n_select=4,
        maximize=False,
    )
    assert len(batch) == 4
    assert {c.route for c in batch} <= {"exploit", "explore"}
    assert any(c.route == "explore" for c in batch)
    assert [c.rank for c in batch] == [0, 1, 2, 3]
