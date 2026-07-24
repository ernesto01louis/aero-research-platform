"""Stage 17 — gated promotion + Invariant-9 currency across the retrain lifecycle."""

from __future__ import annotations

import numpy as np
import pytest
from aero.optimize.gp import GPConfig
from aero.surrogates._common.base import Sample
from aero.surrogates._common.certificate import ApplicabilityEnvelope, CertExpired
from aero.surrogates._common.ensemble import EnsembleSurrogate, PromotionRefused
from aero.surrogates.gp_bootstrap import GPBootstrapMember

pytestmark = pytest.mark.stage_17

_HASH = "0" * 64
_ENVELOPE = ApplicabilityEnvelope(
    re_range=(5.0e5, 5.0e5),
    mach_range=(0.0, 0.0),
    aoa_range_deg=(4.0, 4.0),
    geometry_class="naca-4digit",
)


def _samples(n: int = 28, *, origin: str = "platform-validated") -> list[Sample]:
    rng = np.random.default_rng(23)
    out: list[Sample] = []
    for i in range(n):
        u = rng.random(2)
        y = 40.0 - 30.0 * ((u[0] - 0.7) ** 2 + (u[1] - 0.3) ** 2)
        out.append(
            Sample(
                features=(float(u[0]), float(u[1])),
                targets=(float(y),),
                case_id=f"c{i:02d}",
                dataset_id="stage17-naca4-ld",
                data_origin=origin,  # type: ignore[arg-type]
            )
        )
    return out


def _fitted(samples: list[Sample] | None = None) -> EnsembleSurrogate:
    scales = (0.20, 0.30, 0.40)
    members = [
        GPBootstrapMember(
            gp_config=GPConfig(kernel="matern52", length_scale=scales[i]),
            training_dataset_dvc_hash=_HASH,
            dataset_id="stage17-naca4-ld",
            applicability_envelope=_ENVELOPE,
            metric_name="ld_mae",
        )
        for i in range(3)
    ]
    ens = EnsembleSurrogate(
        members,
        surrogate_name="stage17_ld_ensemble",
        training_dataset_dvc_hash=_HASH,
        dataset_id="stage17-naca4-ld",
        applicability_envelope=_ENVELOPE,
        basis="gp_bootstrap",
        metric_name="ld_mae",
    )
    ens.fit(samples or _samples(), seed=17, calibration_fraction=0.25)
    ens.set_certificate()
    return ens


def test_promotion_pass() -> None:
    ens = _fitted()
    cert = ens.promote_to_validated(max_metric_p95=1e9, coverage_min=0.0, coverage_max=1.0)
    assert cert.cert_status == "validated"
    assert ens.certificate().cert_status == "validated"  # cached cert re-issued


def test_promotion_refuses_on_accuracy_gate() -> None:
    ens = _fitted()
    with pytest.raises(PromotionRefused, match="accuracy gate"):
        ens.promote_to_validated(max_metric_p95=0.0, coverage_min=0.0, coverage_max=1.0)


def test_promotion_refuses_on_coverage_gate() -> None:
    ens = _fitted()
    with pytest.raises(PromotionRefused, match="calibration gate"):
        ens.promote_to_validated(max_metric_p95=1e9, coverage_min=1.01)


def test_promotion_refuses_foreign_origin() -> None:
    ens = _fitted(_samples(origin="foreign"))
    with pytest.raises(PromotionRefused, match="Invariant 11"):
        ens.promote_to_validated(max_metric_p95=1e9, coverage_min=0.0)


def test_promotion_before_fit_is_runtime_error() -> None:
    member = GPBootstrapMember(
        gp_config=GPConfig(),
        training_dataset_dvc_hash=_HASH,
        dataset_id="d",
        applicability_envelope=_ENVELOPE,
    )
    ens = EnsembleSurrogate(
        [member, member],
        training_dataset_dvc_hash=_HASH,
        dataset_id="d",
        applicability_envelope=_ENVELOPE,
    )
    with pytest.raises(RuntimeError, match="before fit"):
        ens.promote_to_validated(max_metric_p95=1.0)


def test_data_gate_catches_corpus_drift() -> None:
    ens = _fitted()
    cert = ens.certificate()
    cert.assert_current(current_dataset_hash=_HASH)  # in sync — passes
    with pytest.raises(CertExpired, match="dataset drifted"):
        cert.assert_current(current_dataset_hash="1" * 64)
