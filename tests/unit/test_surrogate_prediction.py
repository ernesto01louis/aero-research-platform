"""ADR-025 — SurrogatePrediction validators + the predict_with_uncertainty default.

Pins the additive uncertainty seam on the Surrogate ABC:

* ``SurrogatePrediction`` is internally consistent (basis ⟺ std shape rules;
  never a fabricated zero std on ``basis="none"``).
* The base-class ``predict_with_uncertainty`` default wraps ``predict`` and
  reports ``basis="none"`` — existing subclasses gain the method unchanged.
* The :class:`UncertifiedSurrogate` guard fires through the default path.
* ``Surrogate`` subclasses satisfy ``UncertaintyAwareSurrogateProtocol``
  structurally; the pre-existing ``SurrogateProtocol`` is untouched.

Pure stdlib + pydantic — runs in the required CI unit job.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

import pytest
from aero.surrogates._common.base import (
    Sample,
    Surrogate,
    SurrogatePrediction,
    SurrogateProtocol,
    TaintedSample,
    UncertaintyAwareSurrogateProtocol,
    UncertifiedSurrogate,
)
from aero.surrogates._common.certificate import (
    ApplicabilityEnvelope,
    CertificateOfValidity,
    MetricQuantiles,
)
from pydantic import ValidationError

_ENVELOPE = ApplicabilityEnvelope(
    re_range=(1e2, 1e4),
    mach_range=(0.0, 0.1),
    aoa_range_deg=(-5.0, 5.0),
    geometry_class="synthetic-fixture",
)
_HASH_A = "a" * 64


class _ConstantSurrogate(Surrogate):
    """Pure-python fixture: predicts a constant vector; no uncertainty override."""

    def __init__(self, output: tuple[float, ...] = (1.0, 2.0)) -> None:
        super().__init__()
        self._output = output

    def fit(self, data: Iterable[Sample | TaintedSample], /, **hparams: Any) -> None:
        for sample in data:
            self.ingest(sample)

    def _build_certificate(self) -> CertificateOfValidity:
        return CertificateOfValidity.new(
            surrogate_name=type(self).__name__,
            model_architecture="constant_fixture",
            training_dataset_dvc_hash=_HASH_A,
            dataset_id="synthetic",
            held_out_metrics={"cd_mae": MetricQuantiles(p50=0.0, p95=0.0, p99=0.0, n_held_out=1)},
            applicability_envelope=_ENVELOPE,
            cert_status="smoke",
            non_commercial=self._non_commercial,
        )

    def predict(self, features: tuple[float, ...], /) -> tuple[float, ...]:
        self.certificate()
        return self._output


# --- SurrogatePrediction validator matrix -------------------------------------


def test_basis_none_valid() -> None:
    pred = SurrogatePrediction(mean=(0.5,), basis="none")
    assert pred.epistemic_std is None
    assert pred.n_members == 1


def test_basis_none_forbids_std() -> None:
    with pytest.raises(ValidationError, match="forbids epistemic_std"):
        SurrogatePrediction(mean=(0.5,), epistemic_std=(0.0,), basis="none")


def test_basis_none_forbids_members() -> None:
    with pytest.raises(ValidationError, match="requires n_members=1"):
        SurrogatePrediction(mean=(0.5,), basis="none", n_members=3)


def test_deep_ensemble_valid() -> None:
    pred = SurrogatePrediction(
        mean=(0.5, 1.5), epistemic_std=(0.01, 0.02), basis="deep_ensemble", n_members=3
    )
    assert pred.epistemic_std == (0.01, 0.02)


def test_deep_ensemble_requires_std() -> None:
    with pytest.raises(ValidationError, match="requires epistemic_std"):
        SurrogatePrediction(mean=(0.5,), basis="deep_ensemble", n_members=3)


def test_deep_ensemble_requires_two_members() -> None:
    with pytest.raises(ValidationError, match="n_members >= 2"):
        SurrogatePrediction(mean=(0.5,), epistemic_std=(0.01,), basis="deep_ensemble", n_members=1)


def test_std_width_must_match_mean() -> None:
    with pytest.raises(ValidationError, match="width"):
        SurrogatePrediction(
            mean=(0.5, 1.5), epistemic_std=(0.01,), basis="deep_ensemble", n_members=3
        )


def test_negative_std_rejected() -> None:
    with pytest.raises(ValidationError, match="finite and >= 0"):
        SurrogatePrediction(mean=(0.5,), epistemic_std=(-0.01,), basis="deep_ensemble", n_members=3)


def test_non_finite_mean_rejected() -> None:
    with pytest.raises(ValidationError, match="non-finite"):
        SurrogatePrediction(mean=(float("nan"),), basis="none")


def test_empty_mean_rejected() -> None:
    with pytest.raises(ValidationError):
        SurrogatePrediction(mean=(), basis="none")


def test_prediction_is_frozen() -> None:
    pred = SurrogatePrediction(mean=(0.5,), basis="none")
    with pytest.raises(ValidationError):
        pred.mean = (1.0,)  # type: ignore[misc]


# --- the ABC default ------------------------------------------------------------


def test_default_wraps_predict() -> None:
    surrogate = _ConstantSurrogate(output=(3.0, 4.0))
    surrogate.fit([])
    surrogate.set_certificate()
    pred = surrogate.predict_with_uncertainty((0.0,))
    assert pred.mean == (3.0, 4.0)
    assert pred.basis == "none"
    assert pred.epistemic_std is None
    assert pred.n_members == 1


def test_uncertified_guard_fires_through_default() -> None:
    surrogate = _ConstantSurrogate()
    with pytest.raises(UncertifiedSurrogate):
        surrogate.predict_with_uncertainty((0.0,))


def test_protocols() -> None:
    surrogate = _ConstantSurrogate()
    # The ABC satisfies both the pre-existing and the new structural protocol.
    assert isinstance(surrogate, SurrogateProtocol)
    assert isinstance(surrogate, UncertaintyAwareSurrogateProtocol)
