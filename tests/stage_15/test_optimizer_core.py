"""Stage 15 — the numpy optimizer core: design space, GP, EI, and the BO loop (no CFD).

Pins the correctness of the backend-free Bayesian optimizer: the design-space transforms + LHS,
the GP (exact interpolation + uncertainty growth), the EI limits, and that the loop actually
climbs an analytic objective. All host-side, deterministic, no cluster.
"""

from __future__ import annotations

import numpy as np
import pytest
from aero.optimize import (
    BayesianOptimizer,
    BOConfig,
    DesignSpace,
    DesignVariable,
    GaussianProcess,
    GPConfig,
    expected_improvement,
)
from pydantic import ValidationError

pytestmark = pytest.mark.stage_15


def _space() -> DesignSpace:
    return DesignSpace(
        variables=(
            DesignVariable(name="a", low=-2.0, high=2.0),
            DesignVariable(name="b", low=0.0, high=1.0),
        )
    )


# --- design space ---
def test_unit_cube_round_trip() -> None:
    sp = _space()
    x = np.array([1.0, 0.25])
    assert np.allclose(sp.from_unit(sp.to_unit(x)), x)
    assert np.allclose(sp.to_unit(np.array([-2.0, 0.0])), 0.0)
    assert np.allclose(sp.to_unit(np.array([2.0, 1.0])), 1.0)


def test_lhs_in_bounds_and_seeded() -> None:
    sp = _space()
    pts = sp.lhs(10, seed=7)
    assert pts.shape == (10, 2)
    b = sp.bounds()
    assert np.all(pts[:, 0] >= b[0, 0]) and np.all(pts[:, 0] <= b[0, 1])
    assert np.array_equal(pts, sp.lhs(10, seed=7))  # reproducible
    assert not np.array_equal(pts, sp.lhs(10, seed=8))


def test_as_named_and_bad_dim() -> None:
    sp = _space()
    assert sp.as_named(np.array([0.5, 0.5])) == {"a": 0.5, "b": 0.5}
    with pytest.raises(ValueError, match="shape"):
        sp.as_named(np.array([0.5]))


def test_design_variable_ordering() -> None:
    with pytest.raises(ValidationError):
        DesignVariable(name="x", low=1.0, high=0.0)
    with pytest.raises(ValidationError):  # duplicate names
        DesignSpace(
            variables=(
                DesignVariable(name="x", low=0, high=1),
                DesignVariable(name="x", low=0, high=1),
            )
        )


# --- GP ---
def test_gp_interpolates_and_grows_uncertainty() -> None:
    x = np.array([[0.2, 0.2], [0.8, 0.8]])
    y = np.array([1.0, -1.0])
    gp = GaussianProcess(GPConfig(length_scale=0.3)).fit(x, y)
    mean, std = gp.predict(np.array([[0.2, 0.2], [0.5, 0.5]]))
    assert mean[0] == pytest.approx(1.0, abs=1e-2)  # ~exact at a training point
    assert std[0] < 0.05  # ~zero uncertainty there
    assert std[1] > 0.3  # grows away from data


def test_gp_predict_before_fit_raises() -> None:
    with pytest.raises(RuntimeError, match="before fit"):
        GaussianProcess().predict(np.array([[0.5, 0.5]]))


# --- EI ---
def test_ei_deterministic_and_stochastic_limits() -> None:
    ei = expected_improvement(np.array([1.0, 0.0]), np.array([0.0, 1.0]), best=0.5)
    assert ei[0] == pytest.approx(0.5)  # std=0 -> max(mean-best, 0)
    assert ei[1] > 0.0  # stochastic EI positive
    assert np.all(ei >= 0.0)
    # minimization flips the sense
    ei_min = expected_improvement(np.array([0.0]), np.array([0.0]), best=0.5, maximize=False)
    assert ei_min[0] == pytest.approx(0.5)


# --- BO loop on an analytic objective ---
def test_bo_maximizes_analytic_objective() -> None:
    sp = _space()

    def f(v: np.ndarray) -> float:
        return -((v[0] - 0.7) ** 2 + (v[1] - 0.3) ** 2)  # max 0 at (0.7, 0.3)

    bo = BayesianOptimizer(sp, BOConfig(n_init=6, n_iter=18, seed=3), maximize=True)
    for _ in range(6 + 18):
        x = bo.ask()
        bo.tell(x, f(x))
    x_star, y_star = bo.incumbent
    assert y_star > -0.03  # climbed near the optimum
    assert bo.n_candidates == 24
    assert abs(x_star[0] - 0.7) < 0.2 and abs(x_star[1] - 0.3) < 0.2


def test_bo_incumbent_before_tell_raises() -> None:
    bo = BayesianOptimizer(_space(), BOConfig(n_init=2, n_iter=0))
    with pytest.raises(RuntimeError, match="before any tell"):
        _ = bo.incumbent
