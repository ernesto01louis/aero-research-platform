"""ADR-025 — trust-region policy: update law, geometry, fail-loud guards.

Table-driven pins of the ratio-test update law (expand / hold / shrink /
floor+distrust), the box-intersect-unit-cube geometry, maximize/minimize
symmetry, and the exploitation guard (a candidate whose *prediction* does not
improve on the incumbent must raise, not launder into a ratio).

Pure stdlib + pydantic — runs in the required CI unit job.
"""

from __future__ import annotations

import pytest
from aero.surrogates._common.trust_region import (
    TrustRegionConfig,
    TrustRegionError,
    TrustRegionPolicy,
    TrustRegionState,
)
from pydantic import ValidationError

_CFG = TrustRegionConfig()  # defaults: 0.25 initial, [1e-3, 0.5], x2 / x0.5, eta 0.25/0.75
_POLICY = TrustRegionPolicy(_CFG)


def _state(center: tuple[float, ...] = (0.5, 0.5), radius: float = 0.25) -> TrustRegionState:
    return TrustRegionState(center=center, radius=radius)


# --- config / state validators ---------------------------------------------------


def test_config_radius_ordering_enforced() -> None:
    with pytest.raises(ValidationError, match="min <= initial <= max"):
        TrustRegionConfig(initial_radius=0.6, max_radius=0.5)


def test_config_eta_ordering_enforced() -> None:
    with pytest.raises(ValidationError, match="eta_accept"):
        TrustRegionConfig(eta_accept=0.8, eta_expand=0.75)


def test_state_center_must_be_in_unit_cube() -> None:
    with pytest.raises(ValidationError, match="unit cube"):
        TrustRegionState(center=(1.5, 0.5), radius=0.1)
    with pytest.raises(ValidationError, match="unit cube"):
        TrustRegionState(center=(float("nan"),), radius=0.1)


# --- geometry --------------------------------------------------------------------


def test_bounds_intersect_unit_cube() -> None:
    state = _state(center=(0.1, 0.9), radius=0.25)
    assert _POLICY.bounds(state) == ((0.0, 0.35), (0.65, 1.0))


def test_clip_step_projects_onto_region() -> None:
    state = _state(center=(0.5, 0.5), radius=0.1)
    assert _POLICY.clip_step(state, (0.9, 0.55)) == (0.6, 0.55)


def test_clip_step_dimension_mismatch_raises() -> None:
    with pytest.raises(TrustRegionError, match="dimension"):
        _POLICY.clip_step(_state(), (0.5,))


def test_clip_step_non_finite_raises() -> None:
    with pytest.raises(TrustRegionError, match="non-finite"):
        _POLICY.clip_step(_state(), (float("inf"), 0.5))


def test_initial_state() -> None:
    state = _POLICY.initial_state((0.2, 0.8))
    assert state.center == (0.2, 0.8)
    assert state.radius == _CFG.initial_radius


# --- the update law (rho table) --------------------------------------------------
# maximize, best=1.0, predicted=2.0 → predicted_gain=1.0, so rho == cfd - 1.0.


@pytest.mark.parametrize(
    ("cfd", "verdict", "accepted"),
    [
        (1.9, "accept-expand", True),  # rho=0.9 >= eta_expand
        (1.5, "accept-hold", True),  # 0.25 <= rho=0.5 < 0.75
        (1.1, "reject-shrink", False),  # rho=0.1 < eta_accept
        (0.5, "reject-shrink", False),  # rho=-0.5 — CFD says it got WORSE
    ],
)
def test_update_law_verdicts(cfd: float, verdict: str, accepted: bool) -> None:
    update = _POLICY.update(
        _state(),
        candidate=(0.6, 0.5),
        predicted_objective=2.0,
        cfd_objective=cfd,
        best_objective=1.0,
        maximize=True,
    )
    assert update.verdict == verdict
    assert update.accepted is accepted
    assert update.rho == pytest.approx(cfd - 1.0)


def test_accept_expand_moves_center_and_doubles_radius() -> None:
    update = _POLICY.update(
        _state(radius=0.2),
        candidate=(0.6, 0.5),
        predicted_objective=2.0,
        cfd_objective=1.9,
        best_objective=1.0,
    )
    assert update.state.center == (0.6, 0.5)
    assert update.state.radius == pytest.approx(0.4)
    assert update.state.n_accepts == 1
    assert update.state.consecutive_rejects == 0
    assert update.surrogate_distrusted is False


def test_expand_caps_at_max_radius() -> None:
    update = _POLICY.update(
        _state(radius=0.4),
        candidate=(0.6, 0.5),
        predicted_objective=2.0,
        cfd_objective=2.0,
        best_objective=1.0,
    )
    assert update.state.radius == pytest.approx(_CFG.max_radius)


def test_accept_hold_keeps_radius() -> None:
    update = _POLICY.update(
        _state(radius=0.2),
        candidate=(0.6, 0.5),
        predicted_objective=2.0,
        cfd_objective=1.5,
        best_objective=1.0,
    )
    assert update.state.radius == pytest.approx(0.2)
    assert update.state.center == (0.6, 0.5)


def test_reject_shrinks_and_holds_center() -> None:
    prior = _state(radius=0.2)
    update = _POLICY.update(
        prior,
        candidate=(0.6, 0.5),
        predicted_objective=2.0,
        cfd_objective=1.0,
        best_objective=1.0,
    )
    assert update.state.center == prior.center
    assert update.state.radius == pytest.approx(0.1)
    assert update.state.n_rejects == 1
    assert update.state.consecutive_rejects == 1
    assert update.surrogate_distrusted is False


def test_reject_at_floor_flags_distrust() -> None:
    cfg = TrustRegionConfig(initial_radius=0.002, min_radius=1e-3)
    policy = TrustRegionPolicy(cfg)
    update = policy.update(
        TrustRegionState(center=(0.5,), radius=0.002),
        candidate=(0.501,),
        predicted_objective=2.0,
        cfd_objective=1.0,
        best_objective=1.0,
    )
    assert update.verdict == "reject-floor"
    assert update.surrogate_distrusted is True
    assert update.state.radius == pytest.approx(cfg.min_radius)


def test_accept_resets_reject_streak() -> None:
    streaky = TrustRegionState(center=(0.5, 0.5), radius=0.25, n_rejects=3, consecutive_rejects=3)
    update = _POLICY.update(
        streaky,
        candidate=(0.6, 0.5),
        predicted_objective=2.0,
        cfd_objective=1.9,
        best_objective=1.0,
    )
    assert update.state.consecutive_rejects == 0
    assert update.state.n_rejects == 3  # total is preserved


def test_minimize_symmetry() -> None:
    # Minimizing: predicted 0.5 vs best 1.0 is a gain of 0.5; CFD 0.6 → rho=0.8.
    update = _POLICY.update(
        _state(),
        candidate=(0.6, 0.5),
        predicted_objective=0.5,
        cfd_objective=0.6,
        best_objective=1.0,
        maximize=False,
    )
    assert update.verdict == "accept-expand"
    assert update.rho == pytest.approx(0.8)


def test_non_improving_prediction_raises() -> None:
    with pytest.raises(TrustRegionError, match="does not improve"):
        _POLICY.update(
            _state(),
            candidate=(0.6, 0.5),
            predicted_objective=0.9,  # predicted WORSE than incumbent (maximize)
            cfd_objective=1.5,
            best_objective=1.0,
        )


def test_non_finite_objective_raises() -> None:
    with pytest.raises(TrustRegionError, match="finite"):
        _POLICY.update(
            _state(),
            candidate=(0.6, 0.5),
            predicted_objective=float("nan"),
            cfd_objective=1.5,
            best_objective=1.0,
        )


def test_accepted_center_is_clipped_into_region() -> None:
    update = _POLICY.update(
        _state(center=(0.5, 0.5), radius=0.1),
        candidate=(0.9, 0.5),  # outside the region — clipped to 0.6
        predicted_objective=2.0,
        cfd_objective=1.9,
        best_objective=1.0,
    )
    assert update.state.center == (0.6, 0.5)
