"""Stage 17 — the additive gp_bootstrap basis rides end-to-end; ADR-025 defaults unchanged."""

from __future__ import annotations

import numpy as np
import pytest
from aero.optimize.gp import GPConfig
from aero.surrogates._common.base import Sample, SurrogatePrediction
from aero.surrogates._common.calibration import compute_uncertainty_calibration
from aero.surrogates._common.certificate import ApplicabilityEnvelope
from aero.surrogates._common.ensemble import EnsembleSurrogate
from aero.surrogates.gp_bootstrap import GPBootstrapMember

pytestmark = pytest.mark.stage_17

_HASH = "0" * 64
_ENVELOPE = ApplicabilityEnvelope(
    re_range=(5.0e5, 5.0e5),
    mach_range=(0.0, 0.0),
    aoa_range_deg=(4.0, 4.0),
    geometry_class="naca-4digit",
)


def _samples(n: int = 28) -> list[Sample]:
    rng = np.random.default_rng(11)
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
                data_origin="platform-validated",
            )
        )
    return out


def _ensemble(n_members: int = 5) -> EnsembleSurrogate:
    scales = (0.20, 0.25, 0.30, 0.35, 0.40)
    members = [
        GPBootstrapMember(
            gp_config=GPConfig(kernel="matern52", length_scale=scales[i]),
            training_dataset_dvc_hash=_HASH,
            dataset_id="stage17-naca4-ld",
            applicability_envelope=_ENVELOPE,
            metric_name="ld_mae",
        )
        for i in range(n_members)
    ]
    return EnsembleSurrogate(
        members,
        surrogate_name="stage17_ld_ensemble",
        training_dataset_dvc_hash=_HASH,
        dataset_id="stage17-naca4-ld",
        applicability_envelope=_ENVELOPE,
        basis="gp_bootstrap",
        metric_name="ld_mae",
    )


def test_prediction_model_accepts_gp_bootstrap() -> None:
    p = SurrogatePrediction(mean=(1.0,), epistemic_std=(0.1,), basis="gp_bootstrap", n_members=5)
    assert p.basis == "gp_bootstrap"


def test_calibration_accepts_gp_bootstrap() -> None:
    cal = compute_uncertainty_calibration(
        [1.0, 2.0, 3.0], [1.1, 1.9, 3.2], [0.2, 0.2, 0.3], basis="gp_bootstrap"
    )
    assert cal.basis == "gp_bootstrap"


def test_gp_bootstrap_ensemble_end_to_end() -> None:
    ens = _ensemble()
    ens.fit(_samples(), seed=17, calibration_fraction=0.25, interval_k=2.0)
    cert = ens.set_certificate()
    assert cert.model_architecture.startswith("gp_bootstrap(")
    assert "ld_mae" in cert.held_out_metrics
    assert cert.uncertainty_calibration is not None
    assert cert.uncertainty_calibration.basis == "gp_bootstrap"
    pred = ens.predict_with_uncertainty((0.6, 0.4))
    assert pred.basis == "gp_bootstrap"
    assert pred.n_members == 5
    assert pred.epistemic_std is not None and pred.epistemic_std[0] > 0.0


def test_adr025_defaults_unchanged() -> None:
    """A default-constructed ensemble still reads deep_ensemble/cd_mae (branch tests rely on it)."""
    members = [
        GPBootstrapMember(
            gp_config=GPConfig(),
            training_dataset_dvc_hash=_HASH,
            dataset_id="d",
            applicability_envelope=_ENVELOPE,
        )
        for _ in range(2)
    ]
    ens = EnsembleSurrogate(
        members,
        training_dataset_dvc_hash=_HASH,
        dataset_id="d",
        applicability_envelope=_ENVELOPE,
    )
    ens.fit(_samples(), seed=0)
    cert = ens.set_certificate()
    assert cert.model_architecture.startswith("deep_ensemble(")
    assert "cd_mae" in cert.held_out_metrics
    assert cert.uncertainty_calibration is not None
    assert cert.uncertainty_calibration.basis == "deep_ensemble"
