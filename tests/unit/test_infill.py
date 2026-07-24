"""ADR-025 — EI + uncertainty-routed infill: closed forms, routing, guards.

Pins the Gaussian-EI limits and one hand-computed value, the dual-queue
(exploit/explore) routing with dedupe, and the degenerate guard: an all-zero-std
candidate set cannot be uncertainty-routed and must raise, never silently rank
on mean alone.

Pure stdlib + numpy + pydantic — runs in the required CI unit job.
"""

from __future__ import annotations

import math

import numpy as np
import pytest
from aero.surrogates._common.infill import (
    InfillError,
    expected_improvement,
    rank_infill_candidates,
)

# --- expected_improvement ---------------------------------------------------------


def test_zero_std_is_deterministic_limit() -> None:
    ei = expected_improvement([2.0, 0.5], [0.0, 0.0], 1.0, maximize=True)
    assert ei[0] == pytest.approx(1.0)  # gain 1.0, no uncertainty
    assert ei[1] == pytest.approx(0.0)  # no improvement, no uncertainty


def test_large_gain_approaches_gain() -> None:
    ei = expected_improvement([100.0], [0.1], 0.0, maximize=True)
    assert ei[0] == pytest.approx(100.0, rel=1e-6)


def test_hand_computed_value() -> None:
    # mean=1, best=0, std=1: EI = 1*Phi(1) + 1*phi(1).
    phi_cdf = 0.5 * (1.0 + math.erf(1.0 / math.sqrt(2.0)))
    phi_pdf = math.exp(-0.5) / math.sqrt(2.0 * math.pi)
    ei = expected_improvement([1.0], [1.0], 0.0, maximize=True)
    assert ei[0] == pytest.approx(phi_cdf + phi_pdf)
    assert ei[0] == pytest.approx(1.0833, abs=1e-4)


def test_minimize_direction() -> None:
    # Minimizing: mean below best is the improvement.
    ei = expected_improvement([0.5, 1.5], [0.0, 0.0], 1.0, maximize=False)
    assert ei[0] == pytest.approx(0.5)
    assert ei[1] == pytest.approx(0.0)


def test_xi_shrinks_ei() -> None:
    plain = expected_improvement([1.0], [0.5], 0.0, maximize=True)
    margined = expected_improvement([1.0], [0.5], 0.0, maximize=True, xi=0.5)
    assert margined[0] < plain[0]


def test_ei_never_negative() -> None:
    ei = expected_improvement([-5.0, 0.0, 5.0], [0.3, 0.3, 0.3], 0.0, maximize=True)
    assert np.all(ei >= 0.0)


def test_ei_clamped_at_float_cancellation_boundary() -> None:
    # Around g/std ~ -8.3 the closed form g*Phi(z)+std*phi(z) cancels to a tiny
    # NEGATIVE float; unclamped this violates InfillCandidate.ei's ge=0 and
    # crashes ranking of a high-std far-worse candidate. Must clamp to >= 0.
    means = np.linspace(5.0, 12.0, 20000)  # minimize, best=0 -> gain in [-12, -5]
    ei = expected_improvement(means.tolist(), [1.0] * means.size, 0.0, maximize=False)
    assert np.all(ei >= 0.0)


def test_high_std_far_worse_candidate_ranks_without_crash() -> None:
    # The explore queue routes high-std candidates regardless of value; a ~8-sigma
    # worse one must not crash InfillCandidate construction (ge=0.0).
    batch = rank_infill_candidates(
        [(0.0,), (1.0,)],
        [8.37, 0.5],
        [1.0, 0.3],
        current_best=0.0,
        n_select=2,
        maximize=False,
    )
    assert len(batch) == 2
    assert all(c.ei >= 0.0 for c in batch)


@pytest.mark.parametrize(
    ("means", "stds", "best", "xi", "match"),
    [
        ([1.0, 2.0], [0.1], 0.0, 0.0, "equal length"),
        ([], [], 0.0, 0.0, "zero candidates"),
        ([float("nan")], [0.1], 0.0, 0.0, "non-finite"),
        ([1.0], [-0.1], 0.0, 0.0, ">= 0"),
        ([1.0], [0.1], float("inf"), 0.0, "best must be finite"),
        ([1.0], [0.1], 0.0, -0.5, "xi must be >= 0"),
    ],
)
def test_ei_guards(
    means: list[float], stds: list[float], best: float, xi: float, match: str
) -> None:
    with pytest.raises(InfillError, match=match):
        expected_improvement(means, stds, best, maximize=True, xi=xi)


# --- rank_infill_candidates -------------------------------------------------------

_DESIGNS = [(0.0,), (0.1,), (0.2,), (0.3,), (0.4,)]
_MEANS = [10.0, 9.0, 5.0, 4.0, 6.0]
_STDS = [0.1, 0.1, 5.0, 0.01, 0.5]
# maximize with best=5.0: EI order 0 > 1 > 2 > 4 > 3; std order 2 > 4 > 0 = 1 > 3.


def test_dual_queue_routing_and_dedupe() -> None:
    batch = rank_infill_candidates(
        _DESIGNS, _MEANS, _STDS, current_best=5.0, n_select=4, maximize=True
    )
    # n_explore = ceil(0.25*4) = 1, n_exploit = 3 → exploit picks EI-top {0, 1, 2};
    # explore's top-std candidate (2) is already taken → dedupe → next is 4.
    assert [c.design for c in batch] == [(0.0,), (0.1,), (0.2,), (0.4,)]
    assert [c.route for c in batch] == ["exploit", "exploit", "exploit", "explore"]
    assert [c.rank for c in batch] == [0, 1, 2, 3]
    # Exploit queue is EI-descending.
    assert batch[0].ei > batch[1].ei > batch[2].ei


def test_all_explore() -> None:
    batch = rank_infill_candidates(
        _DESIGNS, _MEANS, _STDS, current_best=5.0, n_select=2, explore_fraction=1.0
    )
    # Pure exploration: top-2 by std = candidates 2 and 4.
    assert [c.design for c in batch] == [(0.2,), (0.4,)]
    assert all(c.route == "explore" for c in batch)


def test_all_zero_std_refuses_to_route() -> None:
    with pytest.raises(InfillError, match="cannot uncertainty-route"):
        rank_infill_candidates(_DESIGNS, _MEANS, [0.0] * 5, current_best=5.0, n_select=2)


def test_n_select_bounds() -> None:
    with pytest.raises(InfillError, match="n_select"):
        rank_infill_candidates(_DESIGNS, _MEANS, _STDS, current_best=5.0, n_select=0)
    with pytest.raises(InfillError, match="n_select"):
        rank_infill_candidates(_DESIGNS, _MEANS, _STDS, current_best=5.0, n_select=6)


def test_explore_fraction_bounds() -> None:
    with pytest.raises(InfillError, match="explore_fraction"):
        rank_infill_candidates(
            _DESIGNS, _MEANS, _STDS, current_best=5.0, n_select=2, explore_fraction=1.5
        )


def test_length_mismatch_raises() -> None:
    with pytest.raises(InfillError, match="equal length"):
        rank_infill_candidates(_DESIGNS, _MEANS[:3], _STDS, current_best=5.0, n_select=2)


def test_deterministic_tie_break() -> None:
    """Equal EI/std ties break by candidate index — replayable batches."""
    designs = [(0.0,), (1.0,)]
    batch = rank_infill_candidates(
        designs, [1.0, 1.0], [0.2, 0.2], current_best=0.0, n_select=1, explore_fraction=0.0
    )
    assert batch[0].design == (0.0,)
