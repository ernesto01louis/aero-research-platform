"""The reportable schema refuses non-finite numbers and computes its U95s IEEE-exactly.

Stage 21, ADR-049 H-02 and H-03.

H-02 (FAIL-LOUD). ``allow_inf_nan`` was unset on the reportable, paired-difference and
statistical models, so NaN/inf were accepted wherever no bound blocked them. A NaN baseline built
a thesis-grade ``ReportableResult``, because ``delta <= required_margin`` is False for NaN (the
Invariant-10 gate, ``reportable.py``). The default ``ser_json_inf_nan='null'`` then wrote a record
that could not be read back. The one legitimate infinity,
``StatisticalUncertainty.crosscheck_ratio`` (+inf when ``u95_tau == 0``), opts back in per field
and travels as the string "Infinity".

H-03 (portability). The RSS computed fields used ``x**2`` and ``math.hypot``, which go through
the C library and can differ from ``x * x`` in the last bit, and between platforms. The result
crate (ADR-047) recomputes every U95 bit for bit on Linux, macOS and Windows, so the arithmetic is
now ``sqrt(a*a + b*b + c*c)``, added left to right. Every committed U95 still reproduces
bit-identically: the regression oracle is the committed ``data/vv`` records themselves.
"""

from __future__ import annotations

import json
import math
import random
from pathlib import Path
from typing import Any

import pytest
from aero.provenance.four_fold import ProvenanceTuple
from aero.vv.reportable import (
    ComposedDeltaU95,
    ImprovementClaim,
    ReportableQuantity,
    ReportableResult,
    SmallSignalError,
    _rss,
)
from aero.vv.statistical_uncertainty import StatisticalUncertainty
from pydantic import ValidationError

pytestmark = pytest.mark.stage_21

REPO = Path(__file__).resolve().parents[2]
NON_FINITE = (math.nan, math.inf, -math.inf)

_STAT_KW: dict[str, Any] = dict(
    n_samples=16,
    mean=1.0,
    std=0.1,
    n_batches=4,
    batch_size=4,
    dof=3,
    t_quantile=3.182446305284263,
    se=0.01,
    u95_statistical=0.03182446305284263,
    rel_half_width=0.03,
    autocorr_time=0.5,
    n_eff=16.0,
    crosscheck_ratio=1.0,
    reliable=True,
)


def _claim(**overrides: Any) -> ImprovementClaim:
    kw: dict[str, Any] = dict(
        quantity="L/D",
        kind="steady",
        baseline=20.0,
        improved=40.0,
        higher_is_better=True,
        delta_uncertainty=ComposedDeltaU95(u95_numerical=1.0),
        matched_conditions=True,
    )
    kw.update(overrides)
    return ImprovementClaim(**kw)


@pytest.mark.parametrize("bad", NON_FINITE)
@pytest.mark.parametrize("field", ["value", "u95_numerical", "u95_statistical"])
def test_reportable_quantity_refuses_non_finite(field: str, bad: float) -> None:
    kw: dict[str, Any] = dict(name="cd", value=0.1, u95_numerical=0.01, kind="time_averaged")
    kw[field] = bad
    with pytest.raises(ValidationError, match="finite"):
        ReportableQuantity(**kw)


@pytest.mark.parametrize("bad", NON_FINITE)
@pytest.mark.parametrize("field", ["baseline", "improved"])
def test_improvement_claim_refuses_non_finite(field: str, bad: float) -> None:
    with pytest.raises(ValidationError, match="finite"):
        _claim(**{field: bad})


def test_the_small_signal_gate_refuses_a_nan_delta_even_if_validation_is_bypassed() -> None:
    # model_construct skips field validation (the Stage-20 section 6.14 hazard); the gate itself
    # must still refuse a NaN delta rather than letting `nan <= margin` (False) wave it through.
    forged = ImprovementClaim.model_construct(
        quantity="L/D",
        kind="steady",
        baseline=math.nan,
        improved=40.0,
        higher_is_better=True,
        delta_uncertainty=ComposedDeltaU95(u95_numerical=1.0),
        k=2.0,
        matched_conditions=True,
    )
    with pytest.raises(SmallSignalError):
        forged._significant_and_matched()


@pytest.mark.parametrize("field", ["mean", "std", "se", "u95_statistical", "n_eff"])
def test_statistical_uncertainty_refuses_non_finite(field: str) -> None:
    with pytest.raises(ValidationError, match="finite"):
        StatisticalUncertainty(**{**_STAT_KW, field: math.inf})


def test_crosscheck_ratio_infinity_round_trips_as_a_string() -> None:
    stat = StatisticalUncertainty(**{**_STAT_KW, "crosscheck_ratio": math.inf, "reliable": False})
    text = stat.model_dump_json()
    assert '"crosscheck_ratio":"Infinity"' in text
    assert "null" not in text
    assert StatisticalUncertainty.model_validate_json(text) == stat
    assert StatisticalUncertainty.model_validate(json.loads(text)) == stat
    with pytest.raises(ValidationError):
        StatisticalUncertainty(**{**_STAT_KW, "crosscheck_ratio": math.nan})


def test_a_nested_crosscheck_infinity_round_trips_inside_a_reportable_result() -> None:
    # ser_json_inf_nan applies from the OUTERMOST model being serialized: the standalone
    # StatisticalUncertainty round trip above is not enough on its own.
    from aero.vv.reportable import ReportableResult
    from aero.vv.reportable_compose import compose_independent_improvement

    base = StatisticalUncertainty(**{**_STAT_KW, "mean": 28.0})
    cand = StatisticalUncertainty(
        **{**_STAT_KW, "mean": 50.0, "crosscheck_ratio": math.inf, "reliable": False}
    )
    claim = compose_independent_improvement(
        quantity="L/D",
        kind="time_averaged",
        higher_is_better=True,
        u95_delta_numerical=1.0,
        baseline_stat=base,
        candidate_stat=cand,
        baseline=28.0,
        improved=50.0,
    )
    result = ReportableResult(
        case_name="nested_inf",
        quantities=(
            ReportableQuantity(
                name="L/D",
                value=50.0,
                kind="time_averaged",
                u95_numerical=1.0,
                u95_statistical=0.03,
            ),
        ),
        provenance=ProvenanceTuple(
            git_sha="a" * 40,
            dvc_input_hash="b" * 64,
            container_sif_sha256="c" * 64,
            config_hash="d" * 64,
        ),
        improvement=claim,
        validation_tag="validated",
    )
    text = result.model_dump_json(round_trip=True)
    assert '"crosscheck_ratio":"Infinity"' in text
    assert '"crosscheck_ratio":null' not in text
    assert ReportableResult.model_validate_json(text) == result


def test_rss_is_ieee_exact_and_left_to_right() -> None:
    rng = random.Random(20261012)
    for _ in range(20_000):
        a, b, c = (rng.uniform(0.0, 50.0) * 10.0 ** rng.randint(-8, 3) for _ in range(3))
        assert _rss(a, b, c) == math.sqrt(a * a + b * b + c * c)
        assert _rss(a, b) == math.sqrt(a * a + b * b)
    assert _rss() == 0.0


def test_quantity_u95_total_uses_the_exact_rss() -> None:
    q = ReportableQuantity(
        name="cd", value=1.0, u95_numerical=0.1, u95_statistical=0.2, kind="time_averaged"
    )
    assert q.u95_total == math.sqrt(0.1 * 0.1 + 0.2 * 0.2)


_COMPUTED = {
    "u95_total",
    "delta",
    "u95_delta",
    "required_margin",
    "u95_delta_statistical",
    "mean_delta",
    "rss_independent",
    "variance_reduction",
    "cancellation_effective",
}


def _strip(obj: Any) -> Any:
    if isinstance(obj, dict):
        return {k: _strip(v) for k, v in obj.items() if k not in _COMPUTED}
    if isinstance(obj, list):
        return [_strip(v) for v in obj]
    return obj


def _leaves(obj: Any, path: str = "") -> dict[str, Any]:
    out: dict[str, Any] = {}
    if isinstance(obj, dict):
        for k, v in obj.items():
            out.update(_leaves(v, f"{path}/{k}"))
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            out.update(_leaves(v, f"{path}/{i}"))
    else:
        out[path] = obj
    return out


@pytest.mark.parametrize(
    "record",
    [
        "stage12_reportable_oscillating_cylinder_lockin",
        "stage15_optimization",
        "stage16_optimization",
        "stage16_relaxed_optimization",
        "stage17_optimization",
    ],
)
def test_committed_u95_values_recompute_bit_identically(record: str) -> None:
    raw = json.loads((REPO / "data" / "vv" / f"{record}.json").read_text())
    result = ReportableResult.model_validate(_strip(raw))
    recomputed = _leaves(json.loads(result.model_dump_json()))
    stored = {p: v for p, v in _leaves(raw).items() if p.rsplit("/", 1)[-1] in _COMPUTED}
    assert stored, "the record carries no computed values to check"
    for path, value in stored.items():
        assert isinstance(value, float)
        assert recomputed[path].hex() == value.hex(), path


def test_provenance_tuple_is_untouched_by_the_finite_rule() -> None:
    # Strings only; listed so a future float field there is a conscious decision.
    floats = [n for n, f in ProvenanceTuple.model_fields.items() if f.annotation is float]
    assert floats == []
