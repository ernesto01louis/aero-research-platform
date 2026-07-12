"""Compose a CFD-verified optimization result from a finished BO campaign (Stage 15).

The delta-side glue that turns an optimizer incumbent into a thesis-grade (or honest NO-GO)
`ReportableResult`:

* **matched-condition delta-UQ** — the objective (L/D) is a STEADY scalar, so the whole delta
  uncertainty is the GCI-on-the-delta: solve baseline AND optimum at ≥2 matched grids, difference
  per-grid to a delta series, run a 2-grid Richardson on the DELTA (correlated discretisation error
  cancels), and scale to an absolute `u95_delta_numerical`. No paired-difference / cycle machinery
  (that is the unsteady flapping path).
* **CFD-verified optimum** — the fine optimum solve (a clean-SHA four-tuple NOT used to fit the GP)
  is the held-out verification (`cfd_verified`); `n_candidates` = the number of CFD evals.
* **compose** — `compose_improvement(kind="steady")` builds the claim (raising `SmallSignalError`
  if the delta is within `k·U95` — the honest NO-GO), wrapped in an `OptimizationResult` +
  `ReportableResult`. Hard Rules 12 + 14, `.claude/rules/optimization-integrity.md`.

stdlib + numpy + pydantic only.
"""

from __future__ import annotations

import math

from pydantic import BaseModel, ConfigDict, Field

from aero.provenance.four_fold import ProvenanceTuple
from aero.vv.reportable import (
    OptimizationResult,
    ReportableQuantity,
    ReportableResult,
    SmallSignalError,
)
from aero.vv.reportable_compose import compose_improvement

_STRICT = ConfigDict(extra="forbid", frozen=True, validate_assignment=True, validate_default=True)

_FS_2GRID = 3.0  # ASME V&V 20 safety factor for a 2-grid GCI estimate (assumed order; stage13)
_FS_3GRID = 1.25  # ASME V&V 20 safety factor when the order is OBSERVED and convergence is monotone


def gci_2grid_fraction(fine: float, coarse: float, *, ratio: float, order: float = 2.0) -> float:
    """2-grid GCI on the fine value, as a fraction of |fine| (Fs=3.0). Reuses the stage13 idiom.

    Uses an *assumed* order (default the formal 2.0) because two grids cannot observe the order —
    hence the inflated Fs=3.0. Prefer `gci_3grid_fraction` (a measured order) for a headline claim.
    """
    eps = abs(coarse - fine) / max(abs(fine), 1.0e-12)
    return float(_FS_2GRID * eps / (ratio**order - 1.0))


def observed_order(
    fine: float, medium: float, coarse: float, *, ratio: float
) -> tuple[float, bool]:
    """Observed order of convergence ``p`` from three grids at a constant refinement ``ratio`` r.

    ``fine``/``medium``/``coarse`` are the solutions at ``h``, ``r·h``, ``r²·h``. Returns
    ``(p, monotone)`` where ``p = ln|(coarse-medium)/(medium-fine)| / ln r`` for **monotone**
    convergence (the two grid-to-grid differences share a sign). Returns ``(0.0, False)`` when the
    differences are degenerate or **oscillatory** (a sign change → not in the asymptotic range, so
    the order is undefined; ASME V&V 20 §7.2). Measuring ``p`` replaces the 2-grid *assumption*
    that could silently flip a GO to a NO-GO.
    """
    e21 = medium - fine
    e32 = coarse - medium
    if e21 == 0.0 or e32 == 0.0:
        return 0.0, False
    rr = e32 / e21
    if rr <= 0.0:  # oscillatory — observed order undefined
        return 0.0, False
    return float(math.log(rr) / math.log(ratio)), True


def gci_3grid_fraction(
    fine: float, medium: float, coarse: float, *, ratio: float, formal_order: float = 2.0
) -> float:
    """GCI on the FINEST value as a fraction of |fine|, using the OBSERVED order (three grids).

    Monotone convergence with a sane observed order → ASME V&V 20 ``Fs=1.25`` with
    ``p = min(p_obs, formal_order)`` (never claim faster-than-formal convergence). Oscillatory or
    non-asymptotic behaviour → a conservative first-order fallback (``Fs=3.0``, ``p=1.0``), so a
    family that is NOT converging cannot manufacture a tight uncertainty band.
    """
    p_obs, monotone = observed_order(fine, medium, coarse, ratio=ratio)
    eps = abs(medium - fine) / max(abs(fine), 1.0e-12)
    if monotone and p_obs >= 0.5:
        p = min(p_obs, formal_order)
        fs = _FS_3GRID
    else:
        p = 1.0
        fs = _FS_2GRID
    return float(fs * eps / (ratio**p - 1.0))


class MatchedGridDelta(BaseModel):
    """The matched-grid baseline↔optimum objective values + the composed delta uncertainty."""

    model_config = _STRICT

    quantity: str
    baseline_fine: float
    baseline_coarse: float
    optimum_fine: float
    optimum_coarse: float
    refinement_ratio: float = Field(..., gt=1.0)
    order: float = Field(default=2.0, gt=0.0)

    @property
    def delta_fine(self) -> float:
        return self.optimum_fine - self.baseline_fine

    @property
    def delta_coarse(self) -> float:
        return self.optimum_coarse - self.baseline_coarse

    @property
    def gci_delta_fraction(self) -> float:
        """GCI on the DELTA (matched grids → correlated error cancels)."""
        return gci_2grid_fraction(
            self.delta_fine, self.delta_coarse, ratio=self.refinement_ratio, order=self.order
        )

    @property
    def u95_delta_numerical(self) -> float:
        """Absolute numerical U95 of the delta."""
        return self.gci_delta_fraction * abs(self.delta_fine)

    @property
    def gci_optimum_fraction(self) -> float:
        """GCI on the optimum's own objective value (for its ReportableQuantity)."""
        return gci_2grid_fraction(
            self.optimum_fine, self.optimum_coarse, ratio=self.refinement_ratio, order=self.order
        )

    @property
    def gci_baseline_fraction(self) -> float:
        """GCI on the baseline's own objective value (for the NO-GO plain quantity)."""
        return gci_2grid_fraction(
            self.baseline_fine, self.baseline_coarse, ratio=self.refinement_ratio, order=self.order
        )

    def is_significant(self, *, higher_is_better: bool, k: float = 2.0) -> bool:
        """True iff the improvement clears ``k·U95`` (the GO condition; Invariant 10).

        Checked BEFORE composing because the schema raises `SmallSignalError` inside a pydantic
        validator (surfacing as `ValidationError`), so a pre-check is the clean GO/NO-GO branch.
        """
        signed = self.delta_fine if higher_is_better else -self.delta_fine
        return signed > k * self.u95_delta_numerical


class MatchedGridDeltaTriplet(BaseModel):
    """Matched-grid baseline↔optimum values at THREE grids → **observed-order** GCI on the delta.

    The rigorous upgrade over the 2-grid `MatchedGridDelta`: with three grids at a constant
    refinement ratio the order of accuracy is **measured**, not assumed, so the delta's numerical
    U95 is the ASME V&V 20 observed-order GCI (`Fs=1.25` when the delta converges monotonically, a
    conservative first-order `Fs=3.0` fallback otherwise). Reported values are at the FINEST grid.
    Duck-compatible with `MatchedGridDelta` (same properties) so `compose_result` consumes either.
    """

    model_config = _STRICT

    quantity: str
    baseline_fine: float
    baseline_medium: float
    baseline_coarse: float
    optimum_fine: float
    optimum_medium: float
    optimum_coarse: float
    refinement_ratio: float = Field(..., gt=1.0)
    formal_order: float = Field(default=2.0, gt=0.0)
    # Absolute iterative-convergence uncertainty of the delta (RSS'd into u95_delta_numerical). For a
    # turbulent airfoil whose steady SIMPLE iteration limit-cycles, this is the batch-means spread of
    # the tail-averaged delta — an iterative (not physical/statistical) term, since the tail MEAN is
    # relaxation-independent (the flow is steady; only the iteration oscillates). Default 0 (a
    # cleanly-converged case adds nothing).
    u95_delta_iterative: float = Field(default=0.0, ge=0.0)

    @property
    def delta_fine(self) -> float:
        return self.optimum_fine - self.baseline_fine

    @property
    def delta_medium(self) -> float:
        return self.optimum_medium - self.baseline_medium

    @property
    def delta_coarse(self) -> float:
        return self.optimum_coarse - self.baseline_coarse

    @property
    def observed_order_delta(self) -> float:
        """Measured order of convergence of the DELTA (0.0 if oscillatory/degenerate)."""
        return observed_order(
            self.delta_fine, self.delta_medium, self.delta_coarse, ratio=self.refinement_ratio
        )[0]

    @property
    def delta_monotone(self) -> bool:
        """Whether the delta converges monotonically across the three grids (asymptotic-range gate)."""
        return observed_order(
            self.delta_fine, self.delta_medium, self.delta_coarse, ratio=self.refinement_ratio
        )[1]

    @property
    def gci_delta_fraction(self) -> float:
        return gci_3grid_fraction(
            self.delta_fine,
            self.delta_medium,
            self.delta_coarse,
            ratio=self.refinement_ratio,
            formal_order=self.formal_order,
        )

    @property
    def u95_delta_grid(self) -> float:
        """The grid-convergence (GCI-on-the-delta) arm of the numerical uncertainty."""
        return self.gci_delta_fraction * abs(self.delta_fine)

    @property
    def u95_delta_numerical(self) -> float:
        """RSS of the grid (GCI) and iterative (limit-cycle) convergence uncertainties."""
        return float((self.u95_delta_grid**2 + self.u95_delta_iterative**2) ** 0.5)

    @property
    def gci_optimum_fraction(self) -> float:
        return gci_3grid_fraction(
            self.optimum_fine,
            self.optimum_medium,
            self.optimum_coarse,
            ratio=self.refinement_ratio,
            formal_order=self.formal_order,
        )

    @property
    def gci_baseline_fraction(self) -> float:
        return gci_3grid_fraction(
            self.baseline_fine,
            self.baseline_medium,
            self.baseline_coarse,
            ratio=self.refinement_ratio,
            formal_order=self.formal_order,
        )

    def is_significant(self, *, higher_is_better: bool, k: float = 2.0) -> bool:
        signed = self.delta_fine if higher_is_better else -self.delta_fine
        return signed > k * self.u95_delta_numerical


def compose_result(
    *,
    case_name: str,
    objective: str,
    quantity: str,
    higher_is_better: bool,
    design_variables: dict[str, float],
    delta: MatchedGridDelta | MatchedGridDeltaTriplet,
    cfd_verified: ProvenanceTuple,
    n_candidates: int,
    surrogate_predicted: bool = True,
    k: float = 2.0,
) -> tuple[ReportableResult, bool]:
    """Compose the optimization result, branching on significance. Returns ``(result, is_go)``.

    GO (delta clears ``k·U95``) → a thesis-grade `ReportableResult` carrying an
    `OptimizationResult` with the CFD-verified, held-out optimum. NO-GO → a `validated`-tier result
    reporting baseline + optimum as plain quantities (the delta is noise, not a claim; Invariant 10,
    never a manufactured claim, never a relaxed `k`).
    """
    if not delta.is_significant(higher_is_better=higher_is_better, k=k):
        return nogo_result(
            case_name=case_name, quantity=quantity, delta=delta, provenance=cfd_verified
        ), False
    claim = compose_improvement(
        quantity=quantity,
        kind="steady",
        higher_is_better=higher_is_better,
        u95_delta_numerical=delta.u95_delta_numerical,
        baseline=delta.baseline_fine,
        improved=delta.optimum_fine,
        k=k,
        matched_conditions=True,
    )
    opt = OptimizationResult(
        objective=objective,
        design_variables=design_variables,
        improvement=claim,
        cfd_verified=cfd_verified,
        surrogate_predicted=surrogate_predicted,
        n_candidates=n_candidates,
        held_out_verification=True,
    )
    q = ReportableQuantity(
        name=quantity,
        value=delta.optimum_fine,
        kind="steady",
        u95_numerical=delta.gci_optimum_fraction * abs(delta.optimum_fine),
        u95_statistical=0.0,
        u95_input=0.0,
        u95_input_basis="skipped",
    )
    return ReportableResult(
        case_name=case_name,
        quantities=(q,),
        provenance=cfd_verified,
        optimization=opt,
        validation_tag="thesis-grade",
    ), True


def certification_gates(
    delta: MatchedGridDeltaTriplet,
    *,
    all_converged: bool,
    higher_is_better: bool,
    k: float = 2.0,
    min_order: float = 0.5,
) -> dict[str, bool]:
    """The Stage-16 hard GO gates — significance ALONE is not a GO.

    A delta measured on non-converged solves, a non-monotone family, or an observed order
    outside the asymptotic range (`[min_order, formal_order]`) is not a claim, however large it
    is. The Stage-15 driver recorded `all_converged` but did not gate the verdict on it — the
    audit gap this closes. The GO verdict is ``all(gates.values())``; a demotion never relaxes
    `k`, never drops a grid, never hand-edits a U95 term.
    """
    p = delta.observed_order_delta
    return {
        "significant": delta.is_significant(higher_is_better=higher_is_better, k=k),
        "all_converged": all_converged,
        "delta_monotone": delta.delta_monotone,
        "order_in_asymptotic_range": min_order <= p <= delta.formal_order,
    }


def nogo_result(
    *,
    case_name: str,
    quantity: str,
    delta: MatchedGridDelta | MatchedGridDeltaTriplet,
    provenance: ProvenanceTuple,
) -> ReportableResult:
    """A `validated`-tier result reporting the baseline + optimum as plain quantities (NO-GO).

    Used when the improvement does not clear `k·U95` — the delta is numerical noise, not a claim.
    """
    base_q = ReportableQuantity(
        name=f"{quantity}_baseline",
        value=delta.baseline_fine,
        kind="steady",
        u95_numerical=delta.gci_baseline_fraction * abs(delta.baseline_fine),
    )
    opt_q = ReportableQuantity(
        name=f"{quantity}_optimum",
        value=delta.optimum_fine,
        kind="steady",
        u95_numerical=delta.gci_optimum_fraction * abs(delta.optimum_fine),
    )
    return ReportableResult(
        case_name=case_name,
        quantities=(base_q, opt_q),
        provenance=provenance,
        validation_tag="validated",
    )


__all__ = [
    "MatchedGridDelta",
    "MatchedGridDeltaTriplet",
    "SmallSignalError",
    "certification_gates",
    "compose_result",
    "gci_2grid_fraction",
    "gci_3grid_fraction",
    "nogo_result",
    "observed_order",
]
