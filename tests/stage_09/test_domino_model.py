"""Stage 09 — DoMINO surrogate seams (host-side, fake engine).

Exercises the platform contract WITHOUT PhysicsNeMo: that DoMINO is a real
``Surrogate``, the predict-before-fit guard fires, the CC-BY-NC taint
propagates, the Predictor-Corrector phase records a speedup, and the
smoke->validated gate is honored both ways.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from aero.surrogates._common.base import (
    Sample,
    Surrogate,
    SurrogateProtocol,
    TaintedSample,
    UncertifiedSurrogate,
)
from aero.surrogates.domino import DominoSurrogate

from tests.stage_09._fakes import DRIVAER_ENVELOPE, FakeDominoEngine

pytestmark = pytest.mark.stage_09

_HASH = "a" * 64


def _samples(n: int = 20) -> list[Sample]:
    return [
        Sample(
            features=tuple(float(i) for _ in range(16)),
            targets=(0.30 + 0.001 * i, 0.05, 0.02, 0.03, 0.0),
            case_id=f"drivaerml-{i}",
            dataset_id="drivaerml",
        )
        for i in range(n)
    ]


def _surrogate(engine: FakeDominoEngine, *, cases_root: Path) -> DominoSurrogate:
    return DominoSurrogate(
        training_dataset_dvc_hash=_HASH,
        dataset_id="drivaerml",
        applicability_envelope=DRIVAER_ENVELOPE,
        cases_root=cases_root,
        engine=engine,
    )


def test_domino_is_a_surrogate(tmp_path: Path) -> None:
    s = _surrogate(FakeDominoEngine(), cases_root=tmp_path)
    assert isinstance(s, Surrogate)
    assert isinstance(s, SurrogateProtocol)


def test_predict_before_fit_raises(tmp_path: Path) -> None:
    s = _surrogate(FakeDominoEngine(), cases_root=tmp_path)
    with pytest.raises(UncertifiedSurrogate):
        s.predict((0.0, 1.0, 2.0))


def test_fit_then_smoke_cert_then_predict(tmp_path: Path) -> None:
    engine = FakeDominoEngine()
    s = _surrogate(engine, cases_root=tmp_path)
    s.fit(iter(_samples()))
    assert engine.train_calls == 1
    cert = s.set_certificate()
    assert cert.cert_status == "smoke"
    assert cert.model_architecture == "domino"
    assert s.predict((0.1, 0.2, 0.3)) == engine.prediction


def test_fit_requires_cases_root() -> None:
    s = DominoSurrogate(
        training_dataset_dvc_hash=_HASH,
        dataset_id="drivaerml",
        applicability_envelope=DRIVAER_ENVELOPE,
        engine=FakeDominoEngine(),
    )
    with pytest.raises(ValueError, match="cases_root"):
        s.fit(iter(_samples()))


def test_fit_empty_raises(tmp_path: Path) -> None:
    s = _surrogate(FakeDominoEngine(), cases_root=tmp_path)
    with pytest.raises(ValueError, match="no samples"):
        s.fit(iter([]))


def test_predictor_corrector_records_speedup(tmp_path: Path) -> None:
    engine = FakeDominoEngine()
    s = _surrogate(engine, cases_root=tmp_path)
    s.fit(iter(_samples()))
    s.fine_tune_predictor_corrector()
    assert engine.pc_calls == 1
    assert s.baseline_seconds is not None
    assert s.pc_seconds is not None
    assert s.speedup_factor is not None


def test_promote_to_validated_passes_gate(tmp_path: Path) -> None:
    engine = FakeDominoEngine(cd_errors=(0.001,) * 20)  # p95 << 5%
    s = _surrogate(engine, cases_root=tmp_path)
    s.fit(iter(_samples()))
    cert = s.promote_to_validated()
    assert cert.cert_status == "validated"
    assert s.certificate().cert_status == "validated"


def test_promote_to_validated_fails_gate_stays_smoke(tmp_path: Path) -> None:
    engine = FakeDominoEngine(cd_errors=(0.2,) * 20)  # p95 >> 5%
    s = _surrogate(engine, cases_root=tmp_path)
    s.fit(iter(_samples()))
    cert = s.promote_to_validated()
    assert cert.cert_status == "smoke"


def test_taint_propagates_to_cert(tmp_path: Path) -> None:
    engine = FakeDominoEngine()
    s = _surrogate(engine, cases_root=tmp_path)
    tainted = TaintedSample(
        features=(0.0, 2.1, -3.0),
        targets=(0.30, 0.05, 0.02, 0.03, 0.0),
        case_id="npp-1",
        dataset_id="drivaernet_plus_plus",
    )
    s.fit(iter([*_samples(5), tainted]))
    cert = s.set_certificate()
    assert cert.non_commercial is True
    assert cert.surrogate_name.endswith("_nc")


def test_save_checkpoint(tmp_path: Path) -> None:
    engine = FakeDominoEngine()
    s = _surrogate(engine, cases_root=tmp_path)
    s.fit(iter(_samples()))
    ckpt = tmp_path / "domino.pt"
    s.save_checkpoint(ckpt)
    assert ckpt.is_file()
    assert engine.saved_to == ckpt
