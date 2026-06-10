"""Stage 09 — DoMINO certificate generation + the smoke->validated gate."""

from __future__ import annotations

import pytest
from aero.surrogates._common.certificate import MetricQuantiles
from aero.surrogates.domino.certificate import (
    VALIDATED_CD_P95_THRESHOLD,
    build_domino_certificate,
    meets_validated_gate,
    quantiles_from_abs_errors,
)

from tests.stage_09._fakes import DRIVAER_ENVELOPE

pytestmark = pytest.mark.stage_09

_HASH = "b" * 64


def _metrics(cd_p95: float) -> dict[str, MetricQuantiles]:
    return {"cd_mae": MetricQuantiles(p50=cd_p95 / 2, p95=cd_p95, p99=cd_p95, n_held_out=20)}


def _build(metrics: dict[str, MetricQuantiles], *, upgrade: bool):
    return build_domino_certificate(
        surrogate_name="DominoSurrogate",
        training_dataset_dvc_hash=_HASH,
        dataset_id="drivaerml",
        held_out_metrics=metrics,
        applicability_envelope=DRIVAER_ENVELOPE,
        non_commercial=False,
        upgrade_to_validated=upgrade,
    )


def test_gate_passes_below_threshold() -> None:
    assert meets_validated_gate(_metrics(0.049)) is True


def test_gate_fails_at_exact_threshold() -> None:
    # strict `<`: exactly 5% must NOT pass (a tolerance is a contract).
    assert meets_validated_gate(_metrics(VALIDATED_CD_P95_THRESHOLD)) is False


def test_gate_fails_without_cd_metric() -> None:
    assert meets_validated_gate({}) is False


def test_build_defaults_to_smoke() -> None:
    assert _build(_metrics(0.01), upgrade=False).cert_status == "smoke"


def test_build_upgrades_when_gate_passes() -> None:
    assert _build(_metrics(0.01), upgrade=True).cert_status == "validated"


def test_build_stays_smoke_when_gate_fails_even_if_upgrade_requested() -> None:
    assert _build(_metrics(0.2), upgrade=True).cert_status == "smoke"


def test_quantiles_monotonic() -> None:
    q = quantiles_from_abs_errors((0.01, 0.02, 0.03, 0.5))
    assert q.p50 <= q.p95 <= q.p99
    assert q.n_held_out == 4


def test_quantiles_empty_raises() -> None:
    with pytest.raises(ValueError, match="empty"):
        quantiles_from_abs_errors(())
