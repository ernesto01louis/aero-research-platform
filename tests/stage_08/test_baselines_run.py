"""Stage 08 — baseline end-to-end run tests.

Each test runs one baseline on a small CPU subset (no GPU required), pins
that:

* `fit` completes without raising.
* `set_certificate` returns a `CertificateOfValidity` with
  `cert_status="smoke"`.
* `predict` returns a tuple of the expected width.
* The tainted-sample flow on MGN flips `non_commercial=True`.

Skips entirely when `aero[surrogate-smoke]` extras aren't installed
(torch + torch-geometric); mirrors the Stage-07 PyFR pattern of
extras-conditional skipping.
"""

from __future__ import annotations

import pytest
from aero.surrogates._common.base import Sample, TaintedSample
from aero.surrogates._common.certificate import ApplicabilityEnvelope

pytestmark = [pytest.mark.stage_08, pytest.mark.slow]

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


def test_mlp_baseline_fits_and_certifies(surrogate_smoke_extra_installed: bool) -> None:
    if not surrogate_smoke_extra_installed:
        pytest.skip("aero[surrogate-smoke] extras not installed")
    from aero.surrogates.baselines import MLPBaseline

    surrogate = MLPBaseline(
        training_dataset_dvc_hash=_HASH_A,
        dataset_id="ahmedml",
        applicability_envelope=_ENVELOPE,
    )
    samples = [_sample(i) for i in range(40)]
    surrogate.fit(samples, epochs=10, hidden_dim=16, seed=42)
    cert = surrogate.set_certificate()
    assert cert.cert_status == "smoke"
    assert cert.non_commercial is False
    assert "cd_mae" in cert.held_out_metrics
    pred = surrogate.predict(samples[0].features)
    assert len(pred) == 1


def test_fno_smoke_fits_and_certifies(surrogate_smoke_extra_installed: bool) -> None:
    if not surrogate_smoke_extra_installed:
        pytest.skip("aero[surrogate-smoke] extras not installed")
    from aero.surrogates.baselines import FNOSmoke

    surrogate = FNOSmoke(
        training_dataset_dvc_hash=_HASH_A,
        dataset_id="ahmedml",
        applicability_envelope=_ENVELOPE,
    )
    samples = [_sample(i) for i in range(30)]
    surrogate.fit(samples, epochs=10, modes=4, width=4, seed=42)
    cert = surrogate.set_certificate()
    assert cert.cert_status == "smoke"
    assert "field_l1" in cert.held_out_metrics
    pred = surrogate.predict(samples[0].features)
    assert len(pred) == 16  # _GRID


def test_mgn_smoke_taint_propagation(surrogate_smoke_extra_installed: bool) -> None:
    if not surrogate_smoke_extra_installed:
        pytest.skip("aero[surrogate-smoke] extras not installed")
    from aero.surrogates.baselines import MGNSmoke

    surrogate = MGNSmoke(
        training_dataset_dvc_hash=_HASH_A,
        dataset_id="ahmedml",
        applicability_envelope=_ENVELOPE,
    )
    # Mix one TaintedSample into the training stream — should flip the flag.
    clean = [_sample(i) for i in range(15)]
    tainted = TaintedSample(
        features=(20.0, 1.0, 0.05, 0.05),
        targets=(0.27,),
        case_id="dnpp-0001",
        dataset_id="drivaernet_plus_plus",
    )
    surrogate.fit([*clean, tainted, *clean], epochs=10, hidden=8, seed=42)
    cert = surrogate.set_certificate()
    assert cert.cert_status == "smoke"
    assert cert.non_commercial is True, "CC-BY-NC taint did not propagate"
    pred = surrogate.predict(clean[0].features)
    assert len(pred) == 1
