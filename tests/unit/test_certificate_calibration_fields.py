"""ADR-025 — backward compatibility of the two new optional certificate fields.

The load-bearing pin: a certificate dict WITHOUT ``ensemble_size`` /
``uncertainty_calibration`` (i.e. any pre-ADR-025 MLflow ``certificates/*.json``
artifact) must still validate, defaulting both to ``None`` — the schema change
is additive, existing artifacts are untouched.

Pure stdlib + pydantic — runs in the required CI unit job.
"""

from __future__ import annotations

import math
from datetime import UTC, datetime

import pytest
from aero.surrogates._common.certificate import (
    ApplicabilityEnvelope,
    CertificateOfValidity,
    MetricQuantiles,
    UncertaintyCalibration,
)
from pydantic import ValidationError

_ENVELOPE = ApplicabilityEnvelope(
    re_range=(1e2, 1e4),
    mach_range=(0.0, 0.1),
    aoa_range_deg=(-5.0, 5.0),
    geometry_class="synthetic-fixture",
)
_HASH_A = "a" * 64


def _calibration() -> UncertaintyCalibration:
    return UncertaintyCalibration(
        basis="deep_ensemble",
        n_held_out=8,
        interval_k=2.0,
        nominal_coverage=math.erf(2.0 / math.sqrt(2.0)),
        empirical_coverage=0.875,
        mean_abs_z=0.81,
        std_z=1.02,
    )


def _cert(**overrides: object) -> CertificateOfValidity:
    kwargs: dict[str, object] = {
        "surrogate_name": "fixture",
        "model_architecture": "fixture_arch",
        "training_dataset_dvc_hash": _HASH_A,
        "dataset_id": "synthetic",
        "held_out_metrics": {"cd_mae": MetricQuantiles(p50=0.01, p95=0.02, p99=0.03, n_held_out=8)},
        "applicability_envelope": _ENVELOPE,
        "cert_status": "smoke",
        "non_commercial": False,
        "now": datetime(2026, 7, 10, tzinfo=UTC),
    }
    kwargs.update(overrides)
    return CertificateOfValidity.new(**kwargs)  # type: ignore[arg-type]


def test_pre_adr025_cert_dict_still_parses() -> None:
    """A cert serialized before ADR-025 has neither new key — must validate to None."""
    dumped = _cert().model_dump(mode="json")
    del dumped["ensemble_size"]
    del dumped["uncertainty_calibration"]
    revalidated = CertificateOfValidity.model_validate(dumped)
    assert revalidated.ensemble_size is None
    assert revalidated.uncertainty_calibration is None


def test_new_fields_round_trip_json() -> None:
    cert = _cert(ensemble_size=3, uncertainty_calibration=_calibration())
    restored = CertificateOfValidity.model_validate_json(cert.model_dump_json())
    assert restored.ensemble_size == 3
    assert restored.uncertainty_calibration is not None
    assert restored.uncertainty_calibration.empirical_coverage == pytest.approx(0.875)


def test_ensemble_size_one_rejected() -> None:
    with pytest.raises(ValidationError):
        _cert(ensemble_size=1)


def test_inconsistent_nominal_coverage_rejected() -> None:
    with pytest.raises(ValidationError, match="inconsistent with"):
        UncertaintyCalibration(
            basis="deep_ensemble",
            n_held_out=8,
            interval_k=2.0,
            nominal_coverage=0.5,  # not erf(2/sqrt(2))
            empirical_coverage=0.9,
            mean_abs_z=0.8,
            std_z=1.0,
        )


def test_mlflow_tags_conditional() -> None:
    plain = _cert()
    tags = plain.as_mlflow_tags()
    assert "ensemble_size" not in tags
    assert "uq_calibration_coverage" not in tags

    rich = _cert(ensemble_size=5, uncertainty_calibration=_calibration())
    tags = rich.as_mlflow_tags()
    assert tags["ensemble_size"] == "5"
    assert tags["uq_calibration_basis"] == "deep_ensemble"
    assert tags["uq_calibration_coverage"] == "0.8750"
