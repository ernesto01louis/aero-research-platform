"""Stage 08 — Surrogate protocol + CertificateOfValidity contract tests.

Pure-Python; no SIF, no torch, no MLflow. The tests pin the three guards
the agent layer (Stage 14) gates on (CONSTITUTION Invariant 9):

* Predict-before-fit raises :class:`UncertifiedSurrogate`.
* Cert validates the time gate (expires_at).
* Cert validates the data gate (training-dataset DVC hash drift).
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from aero.surrogates._common.base import (
    Sample,
    Surrogate,
    TaintedSample,
    UncertifiedSurrogate,
)
from aero.surrogates._common.certificate import (
    DEFAULT_CERT_LIFETIME,
    ApplicabilityEnvelope,
    CertExpired,
    CertificateOfValidity,
    MetricQuantiles,
)
from pydantic import ValidationError

pytestmark = pytest.mark.stage_08

_ENVELOPE = ApplicabilityEnvelope(
    re_range=(1e5, 5e6),
    mach_range=(0.0, 0.3),
    aoa_range_deg=(-5.0, 15.0),
    geometry_class="ahmed-body",
)
_HASH_A = "a" * 64
_HASH_B = "b" * 64


class _StubSurrogate(Surrogate):
    """Minimal Surrogate subclass — exercises the base-class machinery."""

    def fit(self, data, /, **hparams):
        for s in data:
            self.ingest(s)

    def _build_certificate(self) -> CertificateOfValidity:
        return CertificateOfValidity.new(
            surrogate_name="stub",
            model_architecture="stub",
            training_dataset_dvc_hash=_HASH_A,
            dataset_id="stub-data",
            held_out_metrics={
                "metric": MetricQuantiles(p50=0.01, p95=0.04, p99=0.09, n_held_out=50)
            },
            applicability_envelope=_ENVELOPE,
            cert_status="smoke",
            non_commercial=False,
        )

    def predict(self, features, /):
        self.certificate()
        return (0.0,)


def test_default_lifetime_is_180_days() -> None:
    assert DEFAULT_CERT_LIFETIME.days == 180


def test_uncertified_predict_raises() -> None:
    s = _StubSurrogate()
    with pytest.raises(UncertifiedSurrogate):
        s.predict((1.0,))


def test_certificate_time_gate_raises_when_expired() -> None:
    issued = datetime.now(UTC)
    cert = CertificateOfValidity.new(
        surrogate_name="x",
        model_architecture="x",
        training_dataset_dvc_hash=_HASH_A,
        dataset_id="x",
        held_out_metrics={"m": MetricQuantiles(p50=0.0, p95=0.0, p99=0.0, n_held_out=1)},
        applicability_envelope=_ENVELOPE,
        cert_status="smoke",
        non_commercial=False,
        now=issued,
    )
    with pytest.raises(CertExpired) as excinfo:
        cert.assert_current(current_dataset_hash=_HASH_A, now=issued + timedelta(days=181))
    assert "expired at" in str(excinfo.value)


def test_certificate_data_gate_raises_on_hash_drift() -> None:
    cert = CertificateOfValidity.new(
        surrogate_name="x",
        model_architecture="x",
        training_dataset_dvc_hash=_HASH_A,
        dataset_id="x",
        held_out_metrics={"m": MetricQuantiles(p50=0.0, p95=0.0, p99=0.0, n_held_out=1)},
        applicability_envelope=_ENVELOPE,
        cert_status="smoke",
        non_commercial=False,
    )
    with pytest.raises(CertExpired) as excinfo:
        cert.assert_current(current_dataset_hash=_HASH_B)
    assert "dataset drifted" in str(excinfo.value)


def test_tainted_sample_propagates_into_certificate() -> None:
    s = _StubSurrogate()
    samples = [
        Sample(features=(1.0,), targets=(0.0,), case_id="a", dataset_id="x"),
        TaintedSample(features=(1.0,), targets=(0.0,), case_id="b", dataset_id="dnpp"),
    ]
    s.fit(samples)
    cert = s.set_certificate()
    # Subclass attempted non_commercial=False in _build_certificate; base
    # class must override to True.
    assert cert.non_commercial is True
    assert s.non_commercial is True


def test_quantile_monotonicity_validator() -> None:
    with pytest.raises(ValidationError):
        MetricQuantiles(p50=0.5, p95=0.2, p99=0.9, n_held_out=10)


def test_envelope_range_validator() -> None:
    with pytest.raises(ValidationError):
        ApplicabilityEnvelope(
            re_range=(1e6, 1e5),
            mach_range=(0.0, 0.3),
            aoa_range_deg=(-5.0, 15.0),
            geometry_class="ahmed-body",
        )
