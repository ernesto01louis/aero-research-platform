"""Stage 16 — URANS composition: window means + `compose_independent_result` (ADR-029)."""

from __future__ import annotations

import numpy as np
import pytest
from aero.optimize.report import MatchedGridDeltaTriplet, compose_independent_result
from aero.postprocess.window_means import time_weighted_window_means
from aero.provenance.four_fold import ProvenanceTuple
from aero.vv.statistical_uncertainty import (
    StatisticalUncertainty,
    statistical_uncertainty_from_samples,
)

pytestmark = pytest.mark.stage_16


# --- time_weighted_window_means -------------------------------------------------------------


def test_window_means_constant_signal() -> None:
    t = np.linspace(0.0, 10.0, 501)
    x = np.full_like(t, 3.5)
    means = time_weighted_window_means(tuple(t), tuple(x), start_time=5.0, n_windows=5)
    assert len(means) == 5
    assert all(m == pytest.approx(3.5) for m in means)


def test_window_means_time_weighting_beats_sample_bias() -> None:
    # Irregular sampling: x=1 on [0,1) sampled densely, x=3 on [1,2] sampled sparsely.
    t1 = np.linspace(0.0, 1.0, 101, endpoint=False)
    t2 = np.linspace(1.0, 2.0, 6)
    t = np.concatenate([t1, t2])
    x = np.concatenate([np.ones_like(t1), 3.0 * np.ones_like(t2)])
    (mean,) = (time_weighted_window_means(tuple(t), tuple(x), start_time=0.0, n_windows=2)[0],)
    # First window [0,1]: exactly 1. A sample mean over the window would also be ~1; the
    # discriminating check is the FULL span done as two windows: second window must be ~3
    # despite only 6 of 107 samples lying there.
    means = time_weighted_window_means(tuple(t), tuple(x), start_time=0.0, n_windows=2)
    assert means[0] == pytest.approx(1.0, abs=0.05)
    assert means[1] == pytest.approx(3.0, abs=0.05)
    assert mean == pytest.approx(means[0])


def test_window_means_fail_loud() -> None:
    t = tuple(np.linspace(0.0, 1.0, 100))
    x = tuple(np.ones(100))
    with pytest.raises(ValueError, match="windows"):
        time_weighted_window_means(t, x, start_time=0.0, n_windows=1)
    with pytest.raises(ValueError, match="outside"):
        time_weighted_window_means(t, x, start_time=2.0, n_windows=4)
    with pytest.raises(ValueError, match="< 2"):
        time_weighted_window_means(t, x, start_time=0.0, n_windows=60)


# --- compose_independent_result -------------------------------------------------------------


def _prov() -> ProvenanceTuple:
    return ProvenanceTuple(
        git_sha="a" * 40,
        dvc_input_hash="0" * 64,
        container_sif_sha256="1" * 64,
        config_hash="2" * 64,
    )


def _stat(mean: float, scale: float, seed: int) -> StatisticalUncertainty:
    su = statistical_uncertainty_from_samples(
        np.random.default_rng(seed).normal(mean, scale, 35), amp_scale=5 * scale
    )
    assert su.reliable
    return su


def _triplet(b_stat: StatisticalUncertainty, o_stat: StatisticalUncertainty, *, p: float = 1.5):
    b, o = float(b_stat.mean), float(o_stat.mean)
    d_fine = o - b
    e21 = 0.4
    e32 = e21 * 1.7**p
    return MatchedGridDeltaTriplet(
        quantity="lift_to_drag",
        baseline_fine=b,
        baseline_medium=b,
        baseline_coarse=b,
        optimum_fine=o,
        optimum_medium=b + d_fine + e21,
        optimum_coarse=b + d_fine + e21 + e32,
        refinement_ratio=1.7,
    )


def _compose(*, gates: bool, b_mean: float = 20.0, o_mean: float = 45.0):
    b_stat = _stat(b_mean, 0.05, 0)
    o_stat = _stat(o_mean, 0.20, 1)
    return compose_independent_result(
        case_name="airfoil_opt_naca4",
        objective="maximize lift_to_drag (URANS time-averaged)",
        quantity="lift_to_drag",
        higher_is_better=True,
        design_variables={"max_camber": 0.0727, "camber_position": 0.2045},
        delta=_triplet(b_stat, o_stat),
        baseline_stat=b_stat,
        optimum_stat=o_stat,
        family_gates_pass=gates,
        cfd_verified=_prov(),
        n_candidates=14,
    )


def test_go_composes_thesis_grade() -> None:
    result, is_go = _compose(gates=True)
    assert is_go and result.validation_tag == "thesis-grade"
    assert result.optimization is not None
    assert result.optimization.improvement.kind == "time_averaged"
    assert result.quantities[0].u95_statistical > 0.0


def test_family_gate_demotes_even_when_significant() -> None:
    result, is_go = _compose(gates=False)
    assert not is_go and result.validation_tag == "validated"
    assert result.optimization is None
    assert {q.name for q in result.quantities} == {
        "lift_to_drag_baseline",
        "lift_to_drag_optimum",
    }


def test_insignificant_delta_is_validated() -> None:
    result, is_go = _compose(gates=True, b_mean=20.0, o_mean=20.2)  # delta << k*U95
    assert not is_go and result.validation_tag == "validated"


def test_stat_mean_mismatch_fails_loud() -> None:
    b_stat, o_stat = _stat(20.0, 0.05, 0), _stat(45.0, 0.2, 1)
    trip = _triplet(b_stat, o_stat)
    # NOT the triplet's fine value (reliability is irrelevant to this check).
    other = statistical_uncertainty_from_samples(
        np.random.default_rng(2).normal(21.5, 0.05, 35), amp_scale=0.25
    )
    with pytest.raises(ValueError, match="window means"):
        compose_independent_result(
            case_name="c",
            objective="o",
            quantity="lift_to_drag",
            higher_is_better=True,
            design_variables={},
            delta=trip,
            baseline_stat=other,
            optimum_stat=o_stat,
            family_gates_pass=True,
            cfd_verified=_prov(),
            n_candidates=14,
        )
