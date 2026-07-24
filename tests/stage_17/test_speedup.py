"""Stage 17 — the pre-registered speed-up rule: censoring, pairing, both accountings."""

from __future__ import annotations

import pytest
from aero.optimize.speedup import ArmTrace, EvalRow, evaluate_speedup

pytestmark = pytest.mark.stage_17

_BASE = 21.674
_BAR = 22.20


def _trace(arm: str, seed: int, values: list[float | None]) -> ArmTrace:
    return ArmTrace(
        arm=arm,  # type: ignore[arg-type]
        seed=seed,
        baseline_value=_BASE,
        rows=tuple(
            EvalRow(n=i + 1, design_named={"max_camber": 0.05, "camber_position": 0.3}, value=v)
            for i, v in enumerate(values)
        ),
    )


def _below() -> float:
    return _BASE + _BAR - 1.0


def _above() -> float:
    return _BASE + _BAR + 1.0


def test_reached_at_first_crossing_skips_failures() -> None:
    trace = _trace("direct", 0, [_below(), None, _above(), _above()])
    assert trace.reached_at(_BAR) == 3


def test_censored_when_never_reached() -> None:
    trace = _trace("direct", 0, [_below()] * 5)
    assert trace.reached_at(_BAR) is None


def test_go_on_two_of_three_wins_with_both_accountings() -> None:
    direct = tuple(
        _trace("direct", s, [_below()] * 9 + [_above()]) for s in (0, 1, 2)
    )  # reaches at 10
    surrogate = (
        _trace("surrogate", 0, [_below(), _above()]),  # wins at 2
        _trace("surrogate", 1, [_below()] * 3 + [_above()]),  # wins at 4
        _trace("surrogate", 2, [_below()] * 16),  # censored — loses
    )
    verdict = evaluate_speedup(direct, surrogate, bar_delta=_BAR, corpus_size=42, min_wins=2)
    assert verdict.speedup_gate_pass
    assert verdict.wins == 2
    by_seed = {c.seed: c for c in verdict.comparisons}
    assert by_seed[0].surrogate_marginal == 2
    assert by_seed[0].surrogate_total_including_corpus == 44  # honesty: +corpus
    assert by_seed[2].surrogate_total_including_corpus is None


def test_neither_arm_reaching_counts_against_go() -> None:
    direct = tuple(_trace("direct", s, [_below()] * 4) for s in (0, 1, 2))
    surrogate = tuple(_trace("surrogate", s, [_below()] * 4) for s in (0, 1, 2))
    verdict = evaluate_speedup(direct, surrogate, bar_delta=_BAR, corpus_size=42)
    assert verdict.wins == 0
    assert not verdict.speedup_gate_pass


def test_tie_is_not_a_win() -> None:
    direct = (_trace("direct", 0, [_below(), _above()]),)
    surrogate = (_trace("surrogate", 0, [_below(), _above()]),)
    verdict = evaluate_speedup(direct, surrogate, bar_delta=_BAR, corpus_size=0, min_wins=1)
    assert not verdict.speedup_gate_pass  # strictly fewer, never <=


def test_mismatched_seed_sets_raise() -> None:
    direct = (_trace("direct", 0, [_above()]),)
    surrogate = (_trace("surrogate", 1, [_above()]),)
    with pytest.raises(ValueError, match="different seed sets"):
        evaluate_speedup(direct, surrogate, bar_delta=_BAR, corpus_size=0)


def test_wrong_arm_label_raises() -> None:
    direct = (_trace("surrogate", 0, [_above()]),)
    surrogate = (_trace("surrogate", 0, [_above()]),)
    with pytest.raises(ValueError, match="arm label"):
        evaluate_speedup(direct, surrogate, bar_delta=_BAR, corpus_size=0)


def test_rows_must_be_strictly_ordered() -> None:
    with pytest.raises(ValueError, match="strictly increasing"):
        ArmTrace(
            arm="direct",
            seed=0,
            baseline_value=_BASE,
            rows=(
                EvalRow(n=2, design_named={"m": 0.0}, value=1.0),
                EvalRow(n=1, design_named={"m": 0.0}, value=1.0),
            ),
        )
