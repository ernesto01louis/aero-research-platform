"""Uncertainty-routed infill selection — which candidates earn a CFD evaluation (ADR-025).

The active-learning arm of the anti-surrogate-exploitation stack: given
candidate designs with ensemble predictions ``(mean, epistemic_std)``, rank the
ones worth spending ground-truth CFD on. Two routes, one ranked batch:

* ``"exploit"`` — highest Expected Improvement over the incumbent: candidates
  the surrogate believes are better, weighted by how uncertain it is.
* ``"explore"`` — highest epistemic std regardless of predicted value: the
  points the surrogate knows least about, which is where exploitation hides.
  ``explore_fraction`` of the batch is reserved for this route so a
  perfectly-confident-and-wrong surrogate still gets audited.

Every selected candidate goes to CFD (Hard Rule 14); the results are appended
to the training corpus and the surrogate retrains — the certificate data gate
(``assert_current``) then forces re-issue automatically because the corpus DVC
hash changed (Invariant 9 closes the loop by construction).

EI under a Gaussian predictive distribution, with Phi via ``math.erf`` — no
scipy in the platform core. Pure stdlib + numpy + pydantic.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from typing import Literal

import numpy as np
from pydantic import BaseModel, ConfigDict, Field


class InfillError(ValueError):
    """Infill inputs are degenerate or inconsistent.

    The load-bearing case: ALL candidate stds are zero — there is no
    uncertainty to route on, which means either the surrogate has no
    uncertainty model (``basis="none"`` — use direct CFD instead) or the
    ensemble collapsed. Silently falling back to mean-ranking would turn the
    exploration arm off exactly when it is needed most.
    """


class InfillCandidate(BaseModel):
    """One CFD-worthy candidate with its routing evidence (frozen, loggable)."""

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        validate_default=True,
    )

    design: tuple[float, ...] = Field(..., min_length=1, description="The design vector.")
    mean: float = Field(..., description="Ensemble predictive mean of the objective.")
    epistemic_std: float = Field(..., ge=0.0, description="Ensemble epistemic std.")
    ei: float = Field(..., ge=0.0, description="Expected Improvement over the incumbent.")
    route: Literal["exploit", "explore"] = Field(
        ..., description="'exploit' = top EI; 'explore' = top epistemic std (audit arm)."
    )
    rank: int = Field(..., ge=0, description="Position in the selected batch (0 = first).")


def _standard_normal_cdf(z: np.ndarray) -> np.ndarray:
    """Phi(z) via erf — vectorized through np.vectorize over math.erf (no scipy)."""
    erf = np.vectorize(math.erf, otypes=[np.float64])
    return np.asarray(0.5 * (1.0 + erf(z / math.sqrt(2.0))), dtype=np.float64)


def _standard_normal_pdf(z: np.ndarray) -> np.ndarray:
    return np.asarray(np.exp(-0.5 * z * z) / math.sqrt(2.0 * math.pi), dtype=np.float64)


def expected_improvement(
    means: Sequence[float],
    stds: Sequence[float],
    best: float,
    *,
    maximize: bool = True,
    xi: float = 0.0,
) -> np.ndarray:
    """Gaussian EI of each candidate over the incumbent ``best``.

    ``EI = g * Phi(g / std) + std * phi(g / std)`` with
    ``g = sign * (mean - best) - xi``; ``std = 0`` gives ``max(g, 0)`` (the
    deterministic limit). ``xi >= 0`` trades exploration for exploitation.
    """
    m = np.asarray(means, dtype=np.float64)
    s = np.asarray(stds, dtype=np.float64)
    if m.ndim != 1 or s.ndim != 1 or m.size != s.size:
        raise InfillError(
            f"means/stds must be 1-D and equal length; got shapes {m.shape} and {s.shape}"
        )
    if m.size == 0:
        raise InfillError("cannot compute EI over zero candidates")
    if not (np.all(np.isfinite(m)) and np.all(np.isfinite(s))):
        raise InfillError("means/stds contain non-finite values")
    if np.any(s < 0.0):
        raise InfillError(f"stds must be >= 0; min = {float(s.min())}")
    if not math.isfinite(best):
        raise InfillError(f"best must be finite; got {best}")
    if xi < 0.0:
        raise InfillError(f"xi must be >= 0; got {xi}")

    sign = 1.0 if maximize else -1.0
    gain = sign * (m - best) - xi
    ei = np.where(gain > 0.0, gain, 0.0)  # deterministic limit for std == 0
    positive = s > 0.0
    if np.any(positive):
        z = gain[positive] / s[positive]
        ei_pos = gain[positive] * _standard_normal_cdf(z) + s[positive] * _standard_normal_pdf(z)
        ei = ei.copy()
        ei[positive] = ei_pos
    # EI is analytically >= 0, but the closed form g*Phi(z)+std*phi(z) suffers
    # float cancellation for strongly-negative z (~ -8.3), producing a tiny
    # negative (~ -1e-16). Left unclamped it violates InfillCandidate.ei's ge=0
    # and crashes ranking of a high-std far-worse candidate (the explore queue
    # routes exactly those). Clamp to the analytic floor.
    return np.maximum(ei, 0.0)


def rank_infill_candidates(
    designs: Sequence[tuple[float, ...]],
    means: Sequence[float],
    stds: Sequence[float],
    *,
    current_best: float,
    n_select: int,
    maximize: bool = True,
    explore_fraction: float = 0.25,
    xi: float = 0.0,
) -> tuple[InfillCandidate, ...]:
    """Select the batch of candidates to route to ground-truth CFD.

    Dual-queue routing: ``ceil(explore_fraction * n_select)`` slots go to the
    highest-epistemic-std candidates (route ``"explore"``); the rest go to the
    highest-EI candidates (route ``"exploit"``). A candidate topping both
    queues appears once, under its first (exploit) assignment. The returned
    batch is ranked exploit-first, then explore, each by its own criterion.
    """
    if not (0.0 <= explore_fraction <= 1.0):
        raise InfillError(f"explore_fraction must be in [0, 1]; got {explore_fraction}")
    n_candidates = len(designs)
    if len(means) != n_candidates or len(stds) != n_candidates:
        raise InfillError(
            f"designs/means/stds must have equal length; got "
            f"({n_candidates}, {len(means)}, {len(stds)})"
        )
    if not (1 <= n_select <= n_candidates):
        raise InfillError(
            f"n_select must be in [1, {n_candidates} (candidate count)]; got {n_select}"
        )

    s = np.asarray(stds, dtype=np.float64)
    ei = expected_improvement(means, stds, current_best, maximize=maximize, xi=xi)
    if np.all(s == 0.0):
        raise InfillError(
            "all candidate epistemic stds are zero — cannot uncertainty-route: the surrogate "
            "either has no uncertainty model (use direct CFD) or the ensemble collapsed "
            "(re-seed / diversify members). Refusing to silently rank on mean alone (ADR-025)."
        )

    n_explore = math.ceil(explore_fraction * n_select)
    n_exploit = n_select - n_explore

    # Stable, deterministic orderings (ties broken by candidate index).
    exploit_order = sorted(range(n_candidates), key=lambda i: (-ei[i], i))
    explore_order = sorted(range(n_candidates), key=lambda i: (-s[i], i))

    selected: list[InfillCandidate] = []
    taken: set[int] = set()
    for i in exploit_order[:n_exploit]:
        selected.append(
            InfillCandidate(
                design=tuple(float(v) for v in designs[i]),
                mean=float(means[i]),
                epistemic_std=float(s[i]),
                ei=float(ei[i]),
                route="exploit",
                rank=len(selected),
            )
        )
        taken.add(i)
    for i in explore_order:
        if len(selected) >= n_select:
            break
        if i in taken:
            continue
        selected.append(
            InfillCandidate(
                design=tuple(float(v) for v in designs[i]),
                mean=float(means[i]),
                epistemic_std=float(s[i]),
                ei=float(ei[i]),
                route="explore",
                rank=len(selected),
            )
        )
        taken.add(i)
    return tuple(selected)
