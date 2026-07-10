"""Trust-region surrogate management — bound steps to where the surrogate is believed (ADR-025).

The standard defense against surrogate exploitation in surrogate-based
optimization: the optimizer may only propose candidates inside an L-infinity
box (the trust region) around the current best design, and the box grows or
shrinks based on how well the surrogate's *predicted* improvement matched the
*CFD-verified* outcome (Hard Rule 14 — every accepted step is ground-truth
verified; this policy consumes that verification).

Design space is **normalized to the unit cube** ``[0, 1]^d`` — callers map
physical design variables in and out. The policy object is stateless: every
``update`` returns a NEW frozen :class:`TrustRegionState`, so an optimization
loop's trajectory is a pure fold and trivially replayable/logged.

The update law is the classic ratio test:

    rho = (f_cfd - f_best) / (f_predicted - f_best)

(sign-normalized so "improvement" is positive for both maximize and minimize).
``rho ~ 1`` means the surrogate told the truth → accept, maybe expand;
``rho`` small or negative means the surrogate over-promised → reject, shrink.
Shrinking to the floor sets ``surrogate_distrusted`` — the Stage-16 loop's
signal to stop optimizing and route budget to uncertainty-routed infill +
retraining instead (``aero/surrogates/_common/infill.py``).

Pure stdlib + numpy + pydantic — PLATFORM-NOT-HUB clean.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class TrustRegionError(ValueError):
    """A trust-region invariant was violated by the caller.

    The load-bearing case: ``update`` called with a candidate whose *predicted*
    objective does not improve on the incumbent. Such a candidate should never
    have been proposed — an optimizer feeding non-improving predictions into
    the accept/reject test is already exploiting surrogate noise, and the
    condition is surfaced loudly instead of laundered into a ratio.
    """


class TrustRegionConfig(BaseModel):
    """Tunables of the trust-region update law (frozen; one per campaign)."""

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        validate_default=True,
    )

    initial_radius: float = Field(
        default=0.25, gt=0.0, le=1.0, description="Starting half-width, unit-cube units."
    )
    min_radius: float = Field(
        default=1e-3,
        gt=0.0,
        description="Floor; shrinking to it flags surrogate_distrusted (route to infill).",
    )
    max_radius: float = Field(
        default=0.5, gt=0.0, le=1.0, description="Ceiling the region may expand to."
    )
    expand_factor: float = Field(
        default=2.0, gt=1.0, description="Radius multiplier on a high-fidelity accept."
    )
    shrink_factor: float = Field(
        default=0.5, gt=0.0, lt=1.0, description="Radius multiplier on a reject."
    )
    eta_accept: float = Field(
        default=0.25,
        gt=0.0,
        lt=1.0,
        description="Minimum rho to accept the step (CFD confirmed enough of the prediction).",
    )
    eta_expand: float = Field(
        default=0.75,
        gt=0.0,
        lt=1.0,
        description="rho at or above which the region expands (surrogate locally trustworthy).",
    )

    @model_validator(mode="after")
    def _ordered(self) -> TrustRegionConfig:
        if not (self.min_radius <= self.initial_radius <= self.max_radius):
            raise ValueError(
                f"radii must satisfy min <= initial <= max; got "
                f"({self.min_radius}, {self.initial_radius}, {self.max_radius})"
            )
        if not (self.eta_accept < self.eta_expand):
            raise ValueError(
                f"eta_accept ({self.eta_accept}) must be < eta_expand ({self.eta_expand})"
            )
        return self


class TrustRegionState(BaseModel):
    """One point of the trust-region trajectory (frozen; updates return new states)."""

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        validate_default=True,
    )

    center: tuple[float, ...] = Field(
        ..., min_length=1, description="Current incumbent design, unit-cube coordinates."
    )
    radius: float = Field(..., gt=0.0, description="Current L-infinity half-width.")
    n_accepts: int = Field(default=0, ge=0, description="Accepted steps so far.")
    n_rejects: int = Field(default=0, ge=0, description="Rejected steps so far.")
    consecutive_rejects: int = Field(
        default=0, ge=0, description="Rejects since the last accept (distrust streak)."
    )

    @model_validator(mode="after")
    def _center_in_unit_cube(self) -> TrustRegionState:
        for v in self.center:
            if not math.isfinite(v) or not (0.0 <= v <= 1.0):
                raise ValueError(
                    f"center must lie in the unit cube [0, 1]^d; got component {v} — "
                    "map physical design variables to normalized coordinates first"
                )
        return self


class TrustRegionUpdate(BaseModel):
    """Outcome of one accept/reject test (frozen evidence, loggable as-is)."""

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        validate_default=True,
    )

    state: TrustRegionState = Field(..., description="The new trust-region state.")
    accepted: bool = Field(..., description="True iff the candidate becomes the new center.")
    rho: float = Field(
        ..., description="CFD-verified improvement / surrogate-predicted improvement."
    )
    verdict: Literal["accept-expand", "accept-hold", "reject-shrink", "reject-floor"] = Field(
        ..., description="Which branch of the update law fired."
    )
    surrogate_distrusted: bool = Field(
        ...,
        description="True iff the region hit min_radius on a reject — stop optimizing, "
        "route budget to uncertainty-routed infill + retraining (ADR-025).",
    )


class TrustRegionPolicy:
    """Stateless policy: holds only the (frozen) config; all state flows through."""

    def __init__(self, config: TrustRegionConfig) -> None:
        self._config = config

    @property
    def config(self) -> TrustRegionConfig:
        return self._config

    def initial_state(self, center: Sequence[float]) -> TrustRegionState:
        """The trajectory's starting point at the configured initial radius."""
        return TrustRegionState(
            center=tuple(float(v) for v in center), radius=self._config.initial_radius
        )

    def bounds(self, state: TrustRegionState) -> tuple[tuple[float, float], ...]:
        """Per-dimension (lo, hi) of the current region, intersected with [0, 1]."""
        return tuple((max(0.0, c - state.radius), min(1.0, c + state.radius)) for c in state.center)

    def clip_step(self, state: TrustRegionState, candidate: Sequence[float]) -> tuple[float, ...]:
        """Project a proposed candidate onto the current region (box ∩ unit cube)."""
        if len(candidate) != len(state.center):
            raise TrustRegionError(
                f"candidate dimension ({len(candidate)}) != center dimension ({len(state.center)})"
            )
        clipped: list[float] = []
        for value, (lo, hi) in zip(candidate, self.bounds(state), strict=True):
            v = float(value)
            if not math.isfinite(v):
                raise TrustRegionError(f"candidate contains a non-finite component ({v})")
            clipped.append(min(hi, max(lo, v)))
        return tuple(clipped)

    def update(
        self,
        state: TrustRegionState,
        *,
        candidate: Sequence[float],
        predicted_objective: float,
        cfd_objective: float,
        best_objective: float,
        maximize: bool = True,
    ) -> TrustRegionUpdate:
        """Accept/reject a CFD-verified candidate and resize the region.

        ``predicted_objective`` is the surrogate's claim for the candidate,
        ``cfd_objective`` the ground-truth CFD verification of the SAME
        candidate (Hard Rule 14), ``best_objective`` the incumbent's
        (CFD-evaluated) objective. Raises :class:`TrustRegionError` when the
        surrogate did not even predict an improvement — that candidate should
        never have reached the verification stage.
        """
        for name, value in (
            ("predicted_objective", predicted_objective),
            ("cfd_objective", cfd_objective),
            ("best_objective", best_objective),
        ):
            if not math.isfinite(value):
                raise TrustRegionError(f"{name} must be finite; got {value}")
        sign = 1.0 if maximize else -1.0
        predicted_gain = sign * (predicted_objective - best_objective)
        verified_gain = sign * (cfd_objective - best_objective)
        if predicted_gain <= 0.0:
            raise TrustRegionError(
                f"candidate's predicted objective ({predicted_objective}) does not improve on "
                f"the incumbent ({best_objective}, maximize={maximize}) — a non-improving "
                "prediction must not enter the accept/reject test (surrogate-exploitation "
                "symptom; ADR-025)"
            )
        rho = verified_gain / predicted_gain

        cfg = self._config
        if rho >= cfg.eta_accept:
            new_center = self.clip_step(state, candidate)
            if rho >= cfg.eta_expand:
                verdict: Literal[
                    "accept-expand", "accept-hold", "reject-shrink", "reject-floor"
                ] = "accept-expand"
                new_radius = min(cfg.max_radius, state.radius * cfg.expand_factor)
            else:
                verdict = "accept-hold"
                new_radius = state.radius
            new_state = TrustRegionState(
                center=new_center,
                radius=new_radius,
                n_accepts=state.n_accepts + 1,
                n_rejects=state.n_rejects,
                consecutive_rejects=0,
            )
            return TrustRegionUpdate(
                state=new_state,
                accepted=True,
                rho=rho,
                verdict=verdict,
                surrogate_distrusted=False,
            )

        # Reject: center holds, region shrinks (floored at min_radius).
        shrunk = state.radius * cfg.shrink_factor
        at_floor = shrunk <= cfg.min_radius
        new_state = TrustRegionState(
            center=state.center,
            radius=max(cfg.min_radius, shrunk),
            n_accepts=state.n_accepts,
            n_rejects=state.n_rejects + 1,
            consecutive_rejects=state.consecutive_rejects + 1,
        )
        return TrustRegionUpdate(
            state=new_state,
            accepted=False,
            rho=rho,
            verdict="reject-floor" if at_floor else "reject-shrink",
            surrogate_distrusted=at_floor,
        )
