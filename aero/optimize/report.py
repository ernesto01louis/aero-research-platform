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

_FS_2GRID = 3.0  # ASME V&V 20 safety factor for a 2-grid GCI estimate (stage13_gci precedent)


def gci_2grid_fraction(fine: float, coarse: float, *, ratio: float, order: float = 2.0) -> float:
    """2-grid GCI on the fine value, as a fraction of |fine| (Fs=3.0). Reuses the stage13 idiom."""
    eps = abs(coarse - fine) / max(abs(fine), 1.0e-12)
    return float(_FS_2GRID * eps / (ratio**order - 1.0))


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

    def is_significant(self, *, higher_is_better: bool, k: float = 2.0) -> bool:
        """True iff the improvement clears ``k·U95`` (the GO condition; Invariant 10).

        Checked BEFORE composing because the schema raises `SmallSignalError` inside a pydantic
        validator (surfacing as `ValidationError`), so a pre-check is the clean GO/NO-GO branch.
        """
        signed = self.delta_fine if higher_is_better else -self.delta_fine
        return signed > k * self.u95_delta_numerical


def compose_result(
    *,
    case_name: str,
    objective: str,
    quantity: str,
    higher_is_better: bool,
    design_variables: dict[str, float],
    delta: MatchedGridDelta,
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


def nogo_result(
    *,
    case_name: str,
    quantity: str,
    delta: MatchedGridDelta,
    provenance: ProvenanceTuple,
) -> ReportableResult:
    """A `validated`-tier result reporting the baseline + optimum as plain quantities (NO-GO).

    Used when the improvement does not clear `k·U95` — the delta is numerical noise, not a claim.
    """
    base_q = ReportableQuantity(
        name=f"{quantity}_baseline",
        value=delta.baseline_fine,
        kind="steady",
        u95_numerical=gci_2grid_fraction(
            delta.baseline_fine, delta.baseline_coarse, ratio=delta.refinement_ratio
        )
        * abs(delta.baseline_fine),
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
    "SmallSignalError",
    "compose_result",
    "gci_2grid_fraction",
    "nogo_result",
]
