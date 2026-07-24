"""ADR-025 — EnsembleSurrogate: aggregation math, seams, taint/origin propagation.

Uses deterministic pure-python affine members (no torch) so the ensemble mean
and ddof=1 spread are hand-checkable, and pins:

* member seeding (member ``i`` receives ``seed + i``) and member cert issue,
* CC-BY-NC taint + Invariant-11 data-origin propagation at the ensemble level,
* the predict-before-certificate guard,
* fail-loud paths: <2 members, heterogeneous widths, collapsed ensemble.

Runs in the required CI unit job.
"""

from __future__ import annotations

import math
from collections.abc import Iterable
from typing import Any

import pytest
from aero.surrogates._common.base import (
    Sample,
    Surrogate,
    TaintedSample,
    UncertifiedSurrogate,
)
from aero.surrogates._common.calibration import CalibrationError
from aero.surrogates._common.certificate import (
    ApplicabilityEnvelope,
    CertificateOfValidity,
    MetricQuantiles,
)
from aero.surrogates._common.ensemble import EnsembleSurrogate

_ENVELOPE = ApplicabilityEnvelope(
    re_range=(1e2, 1e4),
    mach_range=(0.0, 0.1),
    aoa_range_deg=(-5.0, 5.0),
    geometry_class="synthetic-fixture",
)
_HASH_A = "a" * 64


class _AffineMember(Surrogate):
    """Deterministic fixture: predicts ``features[0] + offset`` (width 1)."""

    def __init__(self, offset: float, *, width: int = 1) -> None:
        super().__init__()
        self._offset = offset
        self._width = width
        self.received_seed: int | None = None
        self.n_train_samples: int | None = None
        self.trained_case_ids: frozenset[str] = frozenset()

    def fit(self, data: Iterable[Sample | TaintedSample], /, **hparams: Any) -> None:
        samples = list(data)
        for sample in samples:
            self.ingest(sample)
        self.received_seed = int(hparams.get("seed", -1))
        self.n_train_samples = len(samples)
        self.trained_case_ids = frozenset(s.case_id for s in samples)

    def _build_certificate(self) -> CertificateOfValidity:
        return CertificateOfValidity.new(
            surrogate_name=type(self).__name__,
            model_architecture="affine_fixture",
            training_dataset_dvc_hash=_HASH_A,
            dataset_id="synthetic",
            held_out_metrics={"cd_mae": MetricQuantiles(p50=0.0, p95=0.0, p99=0.0, n_held_out=1)},
            applicability_envelope=_ENVELOPE,
            cert_status="smoke",
            non_commercial=self._non_commercial,
        )

    def predict(self, features: tuple[float, ...], /) -> tuple[float, ...]:
        self.certificate()
        return tuple(features[0] + self._offset for _ in range(self._width))


def _sample(i: int, *, origin: str = "foreign") -> Sample:
    return Sample(
        features=(float(i),),
        targets=(float(i) + 2.0,),  # truth = x + 2 — the offset-{1,2,3} ensemble's mean
        case_id=f"s-{i:04d}",
        dataset_id="synthetic",
        data_origin=origin,  # type: ignore[arg-type]
    )


def _ensemble(offsets: tuple[float, ...] = (1.0, 2.0, 3.0)) -> EnsembleSurrogate:
    return EnsembleSurrogate(
        [_AffineMember(o) for o in offsets],
        surrogate_name="test_ensemble",
        training_dataset_dvc_hash=_HASH_A,
        dataset_id="synthetic",
        applicability_envelope=_ENVELOPE,
    )


def test_fewer_than_two_members_raises() -> None:
    with pytest.raises(ValueError, match=">= 2 members"):
        EnsembleSurrogate(
            [_AffineMember(1.0)],
            training_dataset_dvc_hash=_HASH_A,
            dataset_id="synthetic",
            applicability_envelope=_ENVELOPE,
        )


def test_mean_and_std_hand_computed() -> None:
    ensemble = _ensemble((1.0, 2.0, 3.0))
    ensemble.fit([_sample(i) for i in range(10)], seed=0)
    cert = ensemble.set_certificate()
    # Members predict x+1, x+2, x+3 → mean = x+2, ddof=1 std of {1,2,3} = 1.0.
    assert ensemble.predict((5.0,)) == pytest.approx((7.0,))
    pred = ensemble.predict_with_uncertainty((5.0,))
    assert pred.mean == pytest.approx((7.0,))
    assert pred.epistemic_std is not None
    assert pred.epistemic_std == pytest.approx((1.0,))
    assert pred.basis == "deep_ensemble"
    assert pred.n_members == 3
    # Ensemble mean equals truth (x+2) → held-out cd_mae quantiles are all zero.
    assert cert.held_out_metrics["cd_mae"].p95 == pytest.approx(0.0)


def test_certificate_carries_ensemble_evidence() -> None:
    ensemble = _ensemble()
    ensemble.fit([_sample(i) for i in range(10)], seed=0)
    cert = ensemble.set_certificate()
    assert cert.cert_status == "smoke"
    assert cert.ensemble_size == 3
    assert cert.model_architecture == "deep_ensemble(affine_fixture, n=3)"
    assert cert.uncertainty_calibration is not None
    assert cert.uncertainty_calibration.basis == "deep_ensemble"
    assert cert.uncertainty_calibration.nominal_coverage == pytest.approx(
        math.erf(2.0 / math.sqrt(2.0))
    )
    # Truth sits exactly on the ensemble mean → every ±2·std interval covers.
    assert cert.uncertainty_calibration.empirical_coverage == pytest.approx(1.0)


def test_members_receive_shifted_seeds_and_certs() -> None:
    members = [_AffineMember(o) for o in (1.0, 2.0, 3.0)]
    ensemble = EnsembleSurrogate(
        members,
        training_dataset_dvc_hash=_HASH_A,
        dataset_id="synthetic",
        applicability_envelope=_ENVELOPE,
    )
    inputs = [_sample(i) for i in range(10)]
    ensemble.fit(inputs, seed=100)
    assert [m.received_seed for m in members] == [100, 101, 102]
    # Every member was certified during fit — certificate() must not raise.
    for member in members:
        assert member.certificate().cert_status == "smoke"
    # The calibration evidence was measured on cases NO member trained on —
    # the anti-exploitation honesty property ADR-025 protects. Pin it directly
    # against the calibration holdout ids (not merely inferred from the training
    # set's complement), so a refactor that computes the holdout independently
    # of the training split cannot leak silently.
    all_case_ids = frozenset(s.case_id for s in inputs)
    train_sets = {m.trained_case_ids for m in members}
    assert len(train_sets) == 1, "members trained on different splits"
    train_ids = next(iter(train_sets))
    holdout_ids = frozenset(ensemble.calibration_case_ids)
    assert len(train_ids) == 8
    assert len(holdout_ids) == 2
    assert train_ids.isdisjoint(holdout_ids)  # calibration measured out-of-sample
    assert train_ids | holdout_ids == all_case_ids  # exact partition, nothing dropped


def test_predict_before_certificate_raises() -> None:
    ensemble = _ensemble()
    ensemble.fit([_sample(i) for i in range(10)], seed=0)
    with pytest.raises(UncertifiedSurrogate):
        ensemble.predict((0.0,))
    with pytest.raises(UncertifiedSurrogate):
        ensemble.predict_with_uncertainty((0.0,))


def test_taint_propagates_to_ensemble_cert() -> None:
    ensemble = _ensemble()
    tainted = TaintedSample(
        features=(3.0,),
        targets=(5.0,),
        case_id="dnpp-0001",
        dataset_id="drivaernet_plus_plus",
    )
    ensemble.fit([*(_sample(i) for i in range(9)), tainted], seed=0)
    cert = ensemble.set_certificate()
    assert cert.non_commercial is True, "CC-BY-NC taint did not propagate"
    assert cert.surrogate_name.endswith("_nc")


def test_foreign_origin_default_propagates() -> None:
    ensemble = _ensemble()
    ensemble.fit([_sample(i) for i in range(10)], seed=0)  # data_origin defaults 'foreign'
    cert = ensemble.set_certificate()
    # Constructible only because the ensemble always issues smoke (Invariant 11 exemption).
    assert cert.data_origin == "foreign"
    assert cert.cert_status == "smoke"


def test_platform_validated_origin_recorded() -> None:
    ensemble = _ensemble()
    ensemble.fit([_sample(i, origin="platform-validated") for i in range(10)], seed=0)
    cert = ensemble.set_certificate()
    assert cert.data_origin == "platform-validated"


def test_heterogeneous_member_widths_raise() -> None:
    ensemble = EnsembleSurrogate(
        [_AffineMember(1.0, width=1), _AffineMember(2.0, width=2)],
        training_dataset_dvc_hash=_HASH_A,
        dataset_id="synthetic",
        applicability_envelope=_ENVELOPE,
    )
    with pytest.raises(ValueError, match="output width"):
        ensemble.fit([_sample(i) for i in range(10)], seed=0)


def test_collapsed_ensemble_refuses_certification() -> None:
    """Identical members → zero epistemic spread → CalibrationError, not a cert."""
    ensemble = _ensemble((2.0, 2.0, 2.0))
    with pytest.raises(CalibrationError, match="collapsed ensemble"):
        ensemble.fit([_sample(i) for i in range(10)], seed=0)


def test_empty_and_tiny_data_raise() -> None:
    ensemble = _ensemble()
    with pytest.raises(ValueError, match=">= 2 samples"):
        ensemble.fit([])
    with pytest.raises(ValueError, match=">= 2 samples"):
        ensemble.fit([_sample(0)])


def test_bad_calibration_fraction_raises() -> None:
    ensemble = _ensemble()
    with pytest.raises(ValueError, match="calibration_fraction"):
        ensemble.fit([_sample(i) for i in range(10)], calibration_fraction=1.0)
