"""Stage 17 — GPBootstrapMember: seeded diversity, cert guard, fail-loud hparams."""

from __future__ import annotations

import numpy as np
import pytest
from aero.optimize.gp import GPConfig
from aero.surrogates._common.base import Sample, UncertifiedSurrogate
from aero.surrogates._common.certificate import ApplicabilityEnvelope
from aero.surrogates.gp_bootstrap import GPBootstrapMember

pytestmark = pytest.mark.stage_17

_HASH = "0" * 64
_ENVELOPE = ApplicabilityEnvelope(
    re_range=(5.0e5, 5.0e5),
    mach_range=(0.0, 0.0),
    aoa_range_deg=(4.0, 4.0),
    geometry_class="naca-4digit",
)


def _samples(n: int = 24) -> list[Sample]:
    rng = np.random.default_rng(7)
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


def _member(length_scale: float = 0.3) -> GPBootstrapMember:
    return GPBootstrapMember(
        gp_config=GPConfig(kernel="matern52", length_scale=length_scale),
        training_dataset_dvc_hash=_HASH,
        dataset_id="stage17-naca4-ld",
        applicability_envelope=_ENVELOPE,
        metric_name="ld_mae",
    )


def test_seed_determinism() -> None:
    a, b = _member(), _member()
    a.fit(_samples(), seed=3)
    b.fit(_samples(), seed=3)
    a.set_certificate()
    b.set_certificate()
    q = (0.55, 0.45)
    assert a.predict(q) == b.predict(q)


def test_seed_diversity() -> None:
    a, b = _member(), _member()
    a.fit(_samples(), seed=0)
    b.fit(_samples(), seed=1)
    a.set_certificate()
    b.set_certificate()
    q = (0.55, 0.45)
    assert a.predict(q) != b.predict(q)  # different bootstrap draws => different fits


def test_predict_guard_fires_before_certificate() -> None:
    m = _member()
    m.fit(_samples(), seed=0)
    with pytest.raises(UncertifiedSurrogate):
        m.predict((0.5, 0.5))


def test_certificate_carries_ld_mae_and_origin() -> None:
    m = _member()
    m.fit(_samples(), seed=0)
    cert = m.set_certificate()
    assert "ld_mae" in cert.held_out_metrics
    assert cert.data_origin == "platform-validated"
    assert cert.cert_status == "smoke"
    assert cert.model_architecture.startswith("gp(matern52")


def test_unknown_hparam_fails_loud() -> None:
    m = _member()
    with pytest.raises(ValueError, match="unknown hyperparameters"):
        m.fit(_samples(), seed=0, learning_rate=0.1)


def test_too_few_samples_fails_loud() -> None:
    m = _member()
    with pytest.raises(ValueError, match=">= 3 samples"):
        m.fit(_samples(2), seed=0)
