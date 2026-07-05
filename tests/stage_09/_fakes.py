"""Shared host-side fakes for the Stage-09 DoMINO tests.

The DoMINO engine is injectable (``DominoSurrogate(engine=...)``) precisely so
the cert / taint / guard / Predictor-Corrector seams are exercised WITHOUT
PhysicsNeMo + a 30 GB CUDA environment. These fakes stand in for the GPU engine
and a trained surrogate.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from aero.surrogates._common.certificate import (
    ApplicabilityEnvelope,
    CertificateOfValidity,
    MetricQuantiles,
)

DRIVAER_ENVELOPE = ApplicabilityEnvelope(
    re_range=(8.0e6, 1.1e7),
    mach_range=(0.0, 0.12),
    aoa_range_deg=(0.0, 0.0),
    geometry_class="drivaer-notchback",
)

_OTHER_TARGETS = ("cl", "clf", "clr", "cs")


class FakeDominoEngine:
    """A DominoEngine that records calls and returns canned held-out errors.

    ``cd_errors`` drives the smoke->validated gate: tiny errors pass the
    Cd-p95<5% gate, large errors keep the cert at "smoke".
    """

    def __init__(
        self,
        *,
        cd_errors: tuple[float, ...] = (0.001,) * 10,
        prediction: tuple[float, ...] = (0.30, 0.05, 0.02, 0.03, 0.0),
    ) -> None:
        self.cd_errors = cd_errors
        self.prediction = prediction
        self.train_calls = 0
        self.pc_calls = 0
        self.saved_to: Path | None = None

    def train(self, *, train_cases: Any, val_cases: Any, cases_root: Path, hparams: Any) -> Any:
        self.train_calls += 1
        return {"trained": True, "n_train": len(train_cases), "n_val": len(val_cases)}

    def fine_tune_predictor_corrector(
        self, handle: Any, *, train_cases: Any, val_cases: Any, cases_root: Path, hparams: Any
    ) -> Any:
        self.pc_calls += 1
        return {**handle, "pc": True}

    def held_out_abs_errors(
        self, handle: Any, *, val_cases: Any, cases_root: Path
    ) -> dict[str, tuple[float, ...]]:
        out: dict[str, tuple[float, ...]] = {"cd_mae": tuple(self.cd_errors)}
        for name in _OTHER_TARGETS:
            out[f"{name}_mae"] = tuple(0.01 for _ in self.cd_errors)
        return out

    def predict_coefficients(self, handle: Any, surface: tuple[float, ...]) -> tuple[float, ...]:
        return self.prediction

    def save_checkpoint(self, handle: Any, path: Path) -> None:
        self.saved_to = Path(path)
        Path(path).write_text("fake-domino-checkpoint")


class FakeSurrogate:
    """Minimal SurrogateProtocol stand-in for the compare_surrogate_cfd tests."""

    def __init__(self, cert: CertificateOfValidity, prediction: tuple[float, ...]) -> None:
        self._cert = cert
        self._prediction = prediction

    def predict(self, features: tuple[float, ...], /) -> tuple[float, ...]:
        return self._prediction

    def certificate(self) -> CertificateOfValidity:
        return self._cert


def make_cert(*, status: str = "validated", non_commercial: bool = False) -> CertificateOfValidity:
    """A ready-made cert for the compare tests.

    Synthetic PLATFORM-VALIDATED data to isolate the surrogate-vs-CFD comparison machinery from
    Invariant 11 — a real DoMINO-on-DrivAerML (foreign) cert cannot be 'validated' (see
    tests/stage_12/test_data_origin.py).
    """
    name = "DominoSurrogate"
    return CertificateOfValidity.new(
        surrogate_name=name,
        model_architecture="domino",
        training_dataset_dvc_hash="0" * 64,
        dataset_id="platform_cfd_synth",
        held_out_metrics={"cd_mae": MetricQuantiles(p50=0.01, p95=0.03, p99=0.04, n_held_out=20)},
        applicability_envelope=DRIVAER_ENVELOPE,
        cert_status=status,  # type: ignore[arg-type]
        non_commercial=non_commercial,
        data_origin="platform-validated",
    )
