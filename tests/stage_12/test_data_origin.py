"""CONSTITUTION Invariant 11 (NO-SURROGATE-ON-FOREIGN-DATA) — data_origin enforcement.

A surrogate that ingests any 'foreign' (automotive/aircraft) sample cannot be issued a
'validated'/'production' certificate — 'smoke' is exempt. The taint is write-once toward
'foreign', propagates into the cert, and a foreign+validated cert is unconstructible (the
schema validator refuses it on every path). Pure-host, no cluster.
"""

from __future__ import annotations

from typing import Any, Literal

import pytest
from aero.surrogates._common.base import Sample, Surrogate
from aero.surrogates._common.certificate import (
    ApplicabilityEnvelope,
    CertificateOfValidity,
    MetricQuantiles,
)
from pydantic import ValidationError

pytestmark = pytest.mark.stage_12

_ENVELOPE = ApplicabilityEnvelope(
    re_range=(1.0e2, 1.0e4),
    mach_range=(0.0, 0.1),
    aoa_range_deg=(0.0, 0.0),
    geometry_class="flapping-foil",
)
_METRICS = {"cd_mae": MetricQuantiles(p50=0.01, p95=0.02, p99=0.03, n_held_out=20)}


class _Stub(Surrogate):
    """Minimal Surrogate that issues a cert at a chosen status, carrying the ingested origin."""

    def __init__(self, status: Literal["smoke", "validated", "production"] = "smoke") -> None:
        super().__init__()
        self._status = status

    def fit(self, data: Any, /, **hparams: Any) -> None:
        for s in data:
            self.ingest(s)

    def _build_certificate(self) -> CertificateOfValidity:
        return CertificateOfValidity.new(
            surrogate_name="stub",
            model_architecture="stub",
            training_dataset_dvc_hash="0" * 64,
            dataset_id="d",
            held_out_metrics=_METRICS,
            applicability_envelope=_ENVELOPE,
            cert_status=self._status,
            non_commercial=False,
            data_origin=self._data_origin,
        )

    def predict(self, features: tuple[float, ...], /) -> tuple[float, ...]:
        return (0.0,)


def _sample(origin: Literal["platform-validated", "foreign"]) -> Sample:
    return Sample(features=(1.0,), targets=(0.1,), case_id="c", dataset_id="d", data_origin=origin)


def test_sample_defaults_foreign() -> None:
    """Fail-closed: an unmarked sample is 'foreign' so it cannot slip into a validated cert."""
    s = Sample(features=(1.0,), targets=(0.1,), case_id="c", dataset_id="d")
    assert s.data_origin == "foreign"


def test_platform_validated_stays_clean() -> None:
    s = _Stub("smoke")
    s.fit([_sample("platform-validated")] * 3)
    assert s.data_origin == "platform-validated"
    assert s.set_certificate().data_origin == "platform-validated"


def test_one_foreign_sample_taints_the_surrogate() -> None:
    s = _Stub("smoke")
    s.fit([_sample("platform-validated"), _sample("foreign"), _sample("platform-validated")])
    assert s.data_origin == "foreign"
    assert s.set_certificate().data_origin == "foreign"


def test_foreign_smoke_cert_is_allowed() -> None:
    """'smoke' is exempt — foreign data may seed pipeline-only experiments."""
    s = _Stub("smoke")
    s.fit([_sample("foreign")] * 3)
    assert s.set_certificate().cert_status == "smoke"


def test_foreign_validated_cert_is_unconstructible() -> None:
    with pytest.raises(ValidationError, match="foreign"):
        CertificateOfValidity.new(
            surrogate_name="stub",
            model_architecture="stub",
            training_dataset_dvc_hash="0" * 64,
            dataset_id="d",
            held_out_metrics=_METRICS,
            applicability_envelope=_ENVELOPE,
            cert_status="validated",
            non_commercial=False,
            data_origin="foreign",
        )


def test_foreign_surrogate_cannot_issue_validated_cert() -> None:
    s = _Stub("validated")
    s.fit([_sample("foreign")] * 3)
    with pytest.raises((ValidationError, ValueError), match="foreign"):
        s.set_certificate()  # foreign propagation into a validated cert -> validator refuses


def test_foreign_taint_is_write_once() -> None:
    cert = CertificateOfValidity.new(
        surrogate_name="stub",
        model_architecture="stub",
        training_dataset_dvc_hash="0" * 64,
        dataset_id="d",
        held_out_metrics=_METRICS,
        applicability_envelope=_ENVELOPE,
        cert_status="smoke",
        non_commercial=False,
        data_origin="foreign",
    )
    with pytest.raises(ValueError, match="write-once"):
        cert.model_copy(update={"data_origin": "platform-validated"})
