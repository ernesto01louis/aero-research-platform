"""ReportableResult — the thesis-grade output contract (CONSTITUTION Invariant 10).

This is the schema the platform's *product* is measured against: a reported quantity is
thesis-grade only if it carries the four-fold provenance, its experimental/DNS validation
anchors, and a combined 95% uncertainty composed from three independent contributions:

    U95 = sqrt( u95_numerical**2 + u95_statistical**2 + u95_input**2 )

GCI / ASME V&V 20 covers **only** ``u95_numerical`` (discretization). Unsteady / phase-
averaged quantities also need ``u95_statistical`` (the sampling error of a time-average —
batch-means / autocorrelation effective-sample-size, after a periodic-steady-state
cycle-convergence check); ``u95_input`` is parametric. All three are in the same units as
the value, so they root-sum-square cleanly.

An :class:`ImprovementClaim` (and an :class:`OptimizationResult`'s delta) is reportable
only if its CFD-verified delta exceeds ``k * U95`` (default ``k = 2``) — the
**IMPROVEMENT-EXCEEDS-UNCERTAINTY** invariant. For a delta, baseline and candidate are
evaluated at matched numerics/mesh-topology so correlated errors cancel; the delta's U95
is then below the RSS of the two absolute U95s (paired-comparison / common-random-numbers).
**CFD-VERIFIED-OPTIMUM-ONLY** (Hard Rule 14): an :class:`OptimizationResult` carries the
four-tuple of the ground-truth-CFD run that verified the reported optimum, and best-of-N
reporting records the pool size and requires held-out verification.

Stage 10 ships this schema (the contract + the validators). Stage 12 wires the full U95
composition (the batch-means statistical term) and the required ``small-signal-gate`` CI
job; Stage 15 exercises :class:`OptimizationResult` in the first CFD-in-the-loop
optimization. See ADR-013 / ADR-015, CONSTITUTION Invariants 10 (and CLAUDE.md Hard Rules
12 + 14), ``docs/vv/output-validity-bar.md``, and
``.claude/rules/optimization-integrity.md``.

Strict pydantic, frozen, ``extra="forbid"``. PLATFORM-NOT-HUB: stdlib + numpy + pydantic
only (imports only the core ``ProvenanceTuple``).
"""

from __future__ import annotations

import math
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, computed_field, model_validator

from aero.provenance.four_fold import ProvenanceTuple

_STRICT = ConfigDict(
    extra="forbid",
    frozen=True,
    str_strip_whitespace=True,
    validate_default=True,
)

# Default safety margin for IMPROVEMENT-EXCEEDS-UNCERTAINTY (CONSTITUTION Invariant 10).
# k >= 1 is enforced; k < 1 would let noise be reported as signal.
DEFAULT_K = 2.0

ValidationTag = Literal["smoke", "validated", "thesis-grade"]

# Whether a reported quantity is a steady value or an average over time. Non-steady
# quantities REQUIRE a positive statistical U95 to be thesis-grade (GCI alone is
# insufficient for unsteady flows) — see ReportableResult._thesis_grade_gate.
QuantityKind = Literal["steady", "time_averaged", "phase_averaged"]


class SmallSignalError(ValueError):
    """A claimed improvement did not clear ``k * U95`` (CONSTITUTION Invariant 10).

    A ``ValueError`` subclass so a failed construction surfaces as a pydantic
    ``ValidationError`` — fail-loud, never silently downgraded.
    """


class ValidationAnchor(BaseModel):
    """One experiment- or DNS-reference a reported quantity is validated against.

    VALIDATE-AGAINST-EXPERIMENT (CLAUDE.md Hard Rule 15): forward capabilities validate
    against measured/DNS data (the flapping ladder), not CFD-vs-CFD alone.
    """

    model_config = _STRICT

    reference: str = Field(
        ..., min_length=1, description="Reference dataset/source, e.g. 'Dickinson 1999 Robofly'."
    )
    citation: str = Field(..., min_length=1, description="Full citation or DOI.")
    tolerance: float = Field(
        ..., gt=0.0, description="Validation tolerance as a fraction (0.05 = 5%)."
    )
    observed_error: float = Field(
        ..., ge=0.0, description="Observed error vs the reference, as a fraction."
    )
    passed: bool = Field(..., description="True iff observed_error <= tolerance.")

    @model_validator(mode="after")
    def _passed_consistent(self) -> ValidationAnchor:
        if self.passed != (self.observed_error <= self.tolerance):
            raise ValueError(
                f"passed={self.passed} contradicts observed_error={self.observed_error} "
                f"vs tolerance={self.tolerance}"
            )
        return self


class ReportableQuantity(BaseModel):
    """A scalar result with its three independent U95 contributions (RSS-combined).

    ``kind`` records whether the quantity is steady or a time/phase-average. For a
    non-steady ``kind`` the thesis-grade gate REQUIRES a positive ``u95_statistical``
    (the sampling error of the average — GCI covers only discretization). This field
    is what makes that requirement expressible and enforceable; without it an unsteady
    flapping result could be tagged thesis-grade with ``u95_statistical = 0`` and nothing
    would catch it. ``u95_statistical`` defaults to 0, which is valid only for ``steady``.
    """

    model_config = _STRICT

    name: str = Field(
        ..., min_length=1, description="Quantity name, e.g. 'cd' or 'propulsive_efficiency'."
    )
    value: float = Field(..., description="The reported scalar value.")
    units: str = Field(default="", description="Physical units; '' for dimensionless coefficients.")
    kind: QuantityKind = Field(
        default="steady",
        description="Steady value, or a time-/phase-average. Non-steady kinds require a "
        "positive u95_statistical to be thesis-grade (enforced in the thesis-grade gate).",
    )
    u95_numerical: float = Field(
        ...,
        ge=0.0,
        description="Discretization U95 (GCI / ASME V&V 20), same units as value.",
    )
    u95_statistical: float = Field(
        default=0.0,
        ge=0.0,
        description="Sampling U95 of a time/phase-average (batch-means / N_eff). "
        "0 for steady quantities.",
    )
    u95_input: float = Field(
        default=0.0,
        ge=0.0,
        description="Parametric (input) U95. 0 if no input-UQ was performed.",
    )

    @computed_field  # type: ignore[prop-decorator]
    @property
    def u95_total(self) -> float:
        """Combined 95% uncertainty: root-sum-square of the independent contributions."""
        return math.sqrt(self.u95_numerical**2 + self.u95_statistical**2 + self.u95_input**2)


class ImprovementClaim(BaseModel):
    """A claimed improvement (delta) that clears ``k * U95`` by construction.

    IMPROVEMENT-EXCEEDS-UNCERTAINTY (CONSTITUTION Invariant 10). Constructing an
    ``ImprovementClaim`` *is* a claim that the improvement is real; the validator refuses
    to build one whose delta is within ``k * u95_delta`` (raises :class:`SmallSignalError`).
    To record a measured-but-insignificant delta, report the two values as plain
    :class:`ReportableQuantity` objects instead — that is not a claim.

    ``u95_delta`` is the combined U95 of the *delta*, which for a matched-condition
    comparison is below the RSS of the two absolute U95s (correlated errors cancel).
    """

    model_config = _STRICT

    quantity: str = Field(
        ..., min_length=1, description="Quantity improved, e.g. 'propulsive_efficiency'."
    )
    baseline: float = Field(..., description="Baseline value.")
    improved: float = Field(..., description="Improved (candidate) value.")
    higher_is_better: bool = Field(..., description="Direction of improvement for this quantity.")
    u95_delta: float = Field(
        ...,
        gt=0.0,
        description="Combined U95 of the DELTA (matched-condition; correlated errors cancelled). "
        "Strictly positive — a zero-uncertainty delta would trivially clear any margin.",
    )
    k: float = Field(default=DEFAULT_K, ge=1.0, description="Safety margin; never < 1. Default 2.")
    matched_conditions: bool = Field(
        ...,
        description="True iff baseline and candidate ran at matched numerics/mesh-topology "
        "(required for correlated-error cancellation).",
    )

    @computed_field  # type: ignore[prop-decorator]
    @property
    def delta(self) -> float:
        """Signed improvement: positive means better (sign-corrected for direction)."""
        signed = self.improved - self.baseline
        return signed if self.higher_is_better else -signed

    @computed_field  # type: ignore[prop-decorator]
    @property
    def required_margin(self) -> float:
        """The bar the delta must exceed: ``k * u95_delta``."""
        return self.k * self.u95_delta

    @model_validator(mode="after")
    def _significant_and_matched(self) -> ImprovementClaim:
        if not self.matched_conditions:
            raise ValueError(
                "matched_conditions must be True: a reportable optimization delta requires "
                "baseline and candidate at matched numerics/mesh so correlated errors cancel "
                "(.claude/rules/optimization-integrity.md)."
            )
        if self.delta <= self.required_margin:
            raise SmallSignalError(
                f"improvement on '{self.quantity}' is not thesis-grade: delta={self.delta:.6g} "
                f"<= k*U95={self.required_margin:.6g} (k={self.k}, u95_delta={self.u95_delta:.6g}). "
                "Report the values as plain ReportableQuantity objects — this is not a claim "
                "(CONSTITUTION Invariant 10)."
            )
        return self


class OptimizationResult(BaseModel):
    """A CFD-verified optimization outcome (CFD-VERIFIED-OPTIMUM-ONLY, Hard Rule 14).

    The reported optimum is verified by a ground-truth CFD run whose four-tuple is
    ``cfd_verified`` — never reported on a surrogate prediction alone. ``n_candidates``
    records the best-of-N pool the optimum was selected from; best-of-N (``> 1``) requires
    ``held_out_verification`` to guard the post-hoc selection-bias failure mode
    (Luo, Kasirzadeh & Shah, arXiv:2509.08713).
    """

    model_config = _STRICT

    objective: str = Field(
        ...,
        min_length=1,
        description="Optimized objective, e.g. 'maximize propulsive_efficiency at fixed thrust'.",
    )
    design_variables: dict[str, float] = Field(
        ..., description="The reported optimum's design-variable values."
    )
    improvement: ImprovementClaim = Field(
        ..., description="The CFD-verified improvement over baseline (clears k*U95)."
    )
    cfd_verified: ProvenanceTuple = Field(
        ...,
        description="Four-tuple of the ground-truth-CFD run that verified the reported "
        "optimum. CFD-VERIFIED-OPTIMUM-ONLY.",
    )
    surrogate_predicted: bool = Field(
        default=False,
        description="True if a surrogate proposed the optimum (still CFD-verified above).",
    )
    n_candidates: int = Field(
        ..., ge=1, description="Best-of-N pool size the optimum was selected from."
    )
    held_out_verification: bool = Field(
        ...,
        description="True iff cfd_verified is a held-out run not seen by the optimizer "
        "(guards post-hoc selection bias).",
    )

    @model_validator(mode="after")
    def _selection_bias_guard(self) -> OptimizationResult:
        if self.n_candidates > 1 and not self.held_out_verification:
            raise ValueError(
                f"best-of-N (n_candidates={self.n_candidates}) requires held_out_verification=True: "
                "the reported optimum must be verified on a held-out CFD run not seen by the "
                "optimizer (.claude/rules/optimization-integrity.md)."
            )
        return self


class ReportableResult(BaseModel):
    """The thesis-grade output contract: quantities + four-tuple + anchors (+ optional claim).

    ``validation_tag="thesis-grade"`` is issuable **only** through this schema and only if
    every quantity carries a positive numerical U95, every non-steady quantity also carries
    a positive *statistical* U95, and the result is anchored to experiment (a passing
    :class:`ValidationAnchor`) or to a CFD-verified :class:`OptimizationResult`. This is the
    MLflow gate for CONSTITUTION Invariant 10. ``smoke`` and ``validated`` tags carry no such
    gate (they are explicitly not publication-grade).

    **Scope note (schema + process, not schema alone):** a CFD-verified
    :class:`OptimizationResult` is accepted as thesis-grade anchoring on the strength of its
    ``cfd_verified`` four-tuple. That the *forward model* used to verify the optimum was
    itself experimentally validated is a **process guarantee** — the forward problem clears
    the validation ladder (Stage 14) before the optimizer runs on it (Stage 15) — not
    something this schema enforces. The schema enforces CFD-verification of the optimum;
    experimental anchoring of the forward model lives in the stage sequencing.
    """

    model_config = _STRICT

    case_name: str = Field(..., min_length=1)
    quantities: tuple[ReportableQuantity, ...] = Field(
        ..., min_length=1, description="The reported scalar quantities, each with its U95."
    )
    provenance: ProvenanceTuple = Field(..., description="The four-fold provenance tuple.")
    anchors: tuple[ValidationAnchor, ...] = Field(
        default=(), description="Experiment/DNS validation anchors for this result."
    )
    improvement: ImprovementClaim | None = Field(
        default=None, description="An improvement claim, if this result reports one."
    )
    optimization: OptimizationResult | None = Field(
        default=None, description="A CFD-verified optimization outcome, if any."
    )
    validation_tag: ValidationTag = Field(
        ..., description="MLflow validation_tag; 'thesis-grade' is gated by this schema."
    )

    @model_validator(mode="after")
    def _improvement_optimization_consistent(self) -> ReportableResult:
        # An OptimizationResult carries its own ImprovementClaim; a top-level one alongside
        # it could silently diverge. Require exactly one source of truth.
        if self.optimization is not None and self.improvement is not None:
            raise ValueError(
                "set either `improvement` or `optimization` (which carries its own "
                "`improvement`), not both — two improvement claims must not diverge."
            )
        return self

    @model_validator(mode="after")
    def _thesis_grade_gate(self) -> ReportableResult:
        if self.validation_tag != "thesis-grade":
            return self
        for q in self.quantities:
            if q.u95_numerical <= 0.0:
                raise ValueError(
                    "thesis-grade requires a positive numerical U95 (GCI) on every quantity; "
                    f"'{q.name}' has u95_numerical={q.u95_numerical}."
                )
            if q.kind != "steady" and q.u95_statistical <= 0.0:
                raise ValueError(
                    f"thesis-grade requires a positive statistical U95 for the {q.kind} "
                    f"quantity '{q.name}' (sampling error of a time/phase-average — batch-means "
                    "/ autocorrelation effective-sample-size); GCI alone is insufficient for "
                    f"unsteady flows. Got u95_statistical={q.u95_statistical}."
                )
        anchored = any(a.passed for a in self.anchors)
        cfd_verified_opt = self.optimization is not None
        if not (anchored or cfd_verified_opt):
            raise ValueError(
                "thesis-grade requires a passing validation anchor (VALIDATE-AGAINST-EXPERIMENT) "
                "or a CFD-verified optimization outcome."
            )
        return self
