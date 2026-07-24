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
Since the 2026-07 review (finding F1; ADR-023) that cancellation is **measured, not
assumed**: the delta's U95 is carried by a :class:`DeltaU95` discriminated union, and only
the :class:`ComposedDeltaU95` arm — built from the paired-difference estimator
(:mod:`aero.vv.paired_difference`) plus a caller-supplied GCI-on-the-delta — can reach
``thesis-grade``. A :class:`HandEnteredDeltaU95` stays constructible for exploratory tiers
but is structurally refused a publication tag.
**CFD-VERIFIED-OPTIMUM-ONLY** (Hard Rule 14): an :class:`OptimizationResult` carries the
four-tuple of the ground-truth-CFD run that verified the reported optimum, and best-of-N
reporting records the pool size and requires held-out verification.

Stage 10 ships this schema (the contract + the validators). Stage 12 wires the full U95
composition (the batch-means statistical term) and the required ``small-signal-gate`` CI
job; Stage 15 exercises :class:`OptimizationResult` in the first CFD-in-the-loop
optimization. See ADR-013 / ADR-015 / ADR-023, CONSTITUTION Invariant 10 (and CLAUDE.md
Hard Rules 12 + 14), ``docs/vv/output-validity-bar.md``, and
``.claude/rules/optimization-integrity.md``.

Strict pydantic, frozen, ``extra="forbid"``. PLATFORM-NOT-HUB: stdlib + numpy + pydantic
only (imports the core ``ProvenanceTuple`` and the paired-difference estimator's model).
"""

from __future__ import annotations

import math
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, computed_field, model_validator

from aero.provenance.four_fold import ProvenanceTuple
from aero.vv.paired_difference import PairedDeltaUncertainty
from aero.vv.statistical_uncertainty import StatisticalUncertainty

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
        description="Parametric (input) U95. 0 if input-UQ found it negligible OR was skipped — "
        "which of those is recorded by u95_input_basis (review P1d).",
    )
    u95_input_basis: Literal["measured", "estimated", "skipped"] = Field(
        default="skipped",
        description="Provenance of u95_input, so 'performed and ~0' is distinguishable from "
        "'not performed' (review P1d): 'measured' = propagated from a parametric UQ study; "
        "'estimated' = a defensible bound (e.g. reference-digitization fraction); 'skipped' = "
        "no input-UQ performed (requires u95_input == 0).",
    )

    @computed_field  # type: ignore[prop-decorator]
    @property
    def u95_total(self) -> float:
        """Combined 95% uncertainty: root-sum-square of the independent contributions."""
        return math.sqrt(self.u95_numerical**2 + self.u95_statistical**2 + self.u95_input**2)

    @model_validator(mode="after")
    def _input_basis_consistent(self) -> ReportableQuantity:
        # 'skipped' asserts no input-UQ was performed, so the term must be exactly 0. A
        # 'measured'/'estimated' basis with u95_input == 0 is legitimate ("performed, found
        # negligible") — that is precisely the distinction P1d preserves.
        if self.u95_input_basis == "skipped" and self.u95_input != 0.0:
            raise ValueError(
                f"u95_input_basis='skipped' means no input-UQ was performed, so u95_input must "
                f"be 0; got {self.u95_input}. Use 'measured'/'estimated' for a performed "
                "input-UQ (even one that found the contribution negligible)."
            )
        return self


class HandEnteredDeltaU95(BaseModel):
    """A caller-asserted delta U95 — constructible, but NEVER thesis-grade (review F1).

    Kept for exploratory / ``smoke`` / ``validated``-tier claims where a defensible bound is
    known but not machine-measured. The thesis-grade gate on :class:`ReportableResult`
    structurally refuses it: a publication claim's delta uncertainty must be *composed* from
    the paired-difference measurement (:class:`ComposedDeltaU95`; ADR-023).
    """

    model_config = _STRICT

    source: Literal["hand-entered"] = "hand-entered"
    u95_delta: float = Field(
        ...,
        gt=0.0,
        description="Asserted combined U95 of the DELTA. Strictly positive — a "
        "zero-uncertainty delta would trivially clear any margin.",
    )


class ComposedDeltaU95(BaseModel):
    """A measured delta U95: ``RSS(paired numerical, paired statistical, input)`` (ADR-023).

    All terms are ABSOLUTE, in the delta's own units. ``u95_numerical`` is the paired
    discretization term (GCI on the delta / matched-grid Richardson — caller-supplied, same
    seam as :func:`aero.vv.reportable_compose.compose_reportable`); ``paired`` carries the
    paired-difference measurement of the statistical term (REQUIRED for non-steady claims —
    enforced by :class:`ImprovementClaim`); ``u95_input`` is the residual parametric term.
    The RSS lives here as a computed field, so any composed claim combines correctly by
    construction — there is no free total to mistype.
    """

    model_config = _STRICT

    source: Literal["composed"] = "composed"
    u95_numerical: float = Field(
        ...,
        ge=0.0,
        description="Paired discretization U95 of the delta, ABSOLUTE (GCI on the delta / "
        "matched-grid Richardson). Matched conditions reduce, never zero, this term.",
    )
    paired: PairedDeltaUncertainty | None = Field(
        default=None,
        description="The paired-difference measurement (statistical term + audit trail). "
        "Required for non-steady claims; forbidden for steady ones (no per-cycle series).",
    )
    u95_input: float = Field(
        default=0.0,
        ge=0.0,
        description="Residual parametric (input) U95 of the delta, ABSOLUTE.",
    )

    @computed_field  # type: ignore[prop-decorator]
    @property
    def u95_delta(self) -> float:
        """Combined delta U95: RSS of the paired numerical, paired statistical, input terms."""
        stat = self.paired.u95_delta_statistical if self.paired is not None else 0.0
        return math.sqrt(self.u95_numerical**2 + stat**2 + self.u95_input**2)

    @model_validator(mode="after")
    def _some_contribution(self) -> ComposedDeltaU95:
        if self.u95_delta <= 0.0:
            raise ValueError(
                "a composed delta U95 must have at least one positive contribution — a "
                "zero-uncertainty delta would trivially clear any margin."
            )
        return self


class IndependentDeltaU95(BaseModel):
    """A measured delta U95 with NO cancellation claimed: independent RSS (ADR-029).

    For a matched-condition delta whose baseline and candidate are BOTH time-averaged but
    share no common cycle basis (Stage 16: a steady baseline vs a candidate with resolved
    unsteadiness — no common period, so the paired-difference estimator of ADR-023 is
    category-inapplicable), the statistical term is the independent RSS of the two MEASURED
    sampling uncertainties. This claims no correlation benefit — it is conservative relative
    to any true paired estimate (matched runs correlate positively, and the paired estimator
    would subtract that shared variance) — and every term is machine-measured (NOBM window
    means), so it remains thesis-grade admissible, unlike :class:`HandEnteredDeltaU95`.
    """

    model_config = _STRICT

    source: Literal["independent"] = "independent"
    u95_numerical: float = Field(
        ...,
        ge=0.0,
        description="Paired discretization U95 of the delta, ABSOLUTE (GCI on the "
        "time-averaged delta over the matched grid family).",
    )
    baseline_stat: StatisticalUncertainty = Field(
        ..., description="Measured sampling U95 of the baseline time-average (NOBM windows)."
    )
    candidate_stat: StatisticalUncertainty = Field(
        ..., description="Measured sampling U95 of the candidate time-average (NOBM windows)."
    )
    u95_input: float = Field(
        default=0.0, ge=0.0, description="Residual parametric (input) U95 of the delta, ABSOLUTE."
    )

    @computed_field  # type: ignore[prop-decorator]
    @property
    def u95_delta_statistical(self) -> float:
        """Independent RSS of the two measured sampling terms (no cancellation claimed)."""
        return math.sqrt(
            self.baseline_stat.u95_statistical**2 + self.candidate_stat.u95_statistical**2
        )

    @computed_field  # type: ignore[prop-decorator]
    @property
    def u95_delta(self) -> float:
        """Combined delta U95: RSS of the numerical, independent-statistical, input terms."""
        return math.sqrt(self.u95_numerical**2 + self.u95_delta_statistical**2 + self.u95_input**2)

    @model_validator(mode="after")
    def _some_contribution(self) -> IndependentDeltaU95:
        if self.u95_delta <= 0.0:
            raise ValueError(
                "an independent delta U95 must have at least one positive contribution — a "
                "zero-uncertainty delta would trivially clear any margin."
            )
        return self


# Discriminated union: WHERE a claim's u95_delta comes from is part of the claim itself.
# Mirrors the platform's typed-union precedent (SolveResult.history, Sample/TaintedSample).
DeltaU95 = Annotated[
    HandEnteredDeltaU95 | ComposedDeltaU95 | IndependentDeltaU95, Field(discriminator="source")
]


class ImprovementClaim(BaseModel):
    """A claimed improvement (delta) that clears ``k * U95`` by construction.

    IMPROVEMENT-EXCEEDS-UNCERTAINTY (CONSTITUTION Invariant 10). Constructing an
    ``ImprovementClaim`` *is* a claim that the improvement is real; the validator refuses
    to build one whose delta is within ``k * u95_delta`` (raises :class:`SmallSignalError`).
    To record a measured-but-insignificant delta, report the two values as plain
    :class:`ReportableQuantity` objects instead — that is not a claim.

    ``delta_uncertainty`` states WHERE the delta's U95 comes from (review F1; ADR-023): a
    :class:`ComposedDeltaU95` measured via the paired-difference estimator, or a
    :class:`HandEnteredDeltaU95` (never thesis-grade). ``kind`` states what kind of delta
    this is — REQUIRED with no default, because a defaulted "steady" would let an unsteady
    delta silently skip the paired-measurement requirement (the F1 hole in new clothing).
    """

    model_config = _STRICT

    quantity: str = Field(
        ..., min_length=1, description="Quantity improved, e.g. 'propulsive_efficiency'."
    )
    kind: QuantityKind = Field(
        ...,
        description="Steady value or a time-/phase-average. Non-steady composed claims must "
        "carry the paired-difference measurement (no default — state what you claim).",
    )
    baseline: float = Field(..., description="Baseline value.")
    improved: float = Field(..., description="Improved (candidate) value.")
    higher_is_better: bool = Field(..., description="Direction of improvement for this quantity.")
    delta_uncertainty: DeltaU95 = Field(
        ...,
        description="The delta's U95 and its provenance (composed = measured; hand-entered = "
        "asserted, never thesis-grade).",
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
    def u95_delta(self) -> float:
        """Combined U95 of the DELTA (delegates to ``delta_uncertainty`` — key unchanged)."""
        return self.delta_uncertainty.u95_delta

    @computed_field  # type: ignore[prop-decorator]
    @property
    def required_margin(self) -> float:
        """The bar the delta must exceed: ``k * u95_delta``."""
        return self.k * self.u95_delta

    @model_validator(mode="after")
    def _delta_uncertainty_consistent(self) -> ImprovementClaim:
        du = self.delta_uncertainty
        if isinstance(du, IndependentDeltaU95) and self.kind == "steady":
            raise ValueError(
                "a steady claim has no sampling term; an independent (unsteady) delta U95 on "
                "a steady claim is a category error — check the claim's `kind` (ADR-029)."
            )
        if isinstance(du, ComposedDeltaU95):
            if self.kind != "steady" and du.paired is None:
                raise ValueError(
                    f"a composed {self.kind} claim requires the paired-difference measurement "
                    "(ComposedDeltaU95.paired): the statistical term of an unsteady delta must "
                    "be MEASURED on the difference series, not asserted (Invariant 10, ADR-023)."
                )
            if self.kind == "steady" and du.paired is not None:
                raise ValueError(
                    "a steady claim has no per-cycle series; supplying a paired-difference "
                    "measurement is a category error — check the claim's `kind`."
                )
            if du.paired is not None:
                scale = max(abs(self.baseline), abs(self.improved))
                tol = max(1.0e-9 * scale, 1.0e-12)
                if (
                    abs(self.baseline - du.paired.mean_baseline) > tol
                    or abs(self.improved - du.paired.mean_candidate) > tol
                ):
                    raise ValueError(
                        f"claimed values (baseline={self.baseline}, improved={self.improved}) "
                        f"disagree with the paired-window means ({du.paired.mean_baseline}, "
                        f"{du.paired.mean_candidate}): the uncertainty and the value must come "
                        "from the SAME window."
                    )
        return self

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
        # Review P1b: a `-dirty` SHA means the recorded provenance does not describe what
        # actually ran — the antithesis of thesis-grade. `git_sha(..., allow_dirty=True)`
        # annotates the SHA with `-dirty`; that annotation must bar the publication tag.
        if self.provenance.git_sha.endswith("-dirty"):
            raise ValueError(
                "thesis-grade forbids a dirty working tree: provenance.git_sha ends with "
                "'-dirty', so the recorded SHA does not describe what actually ran (review P1b). "
                "Commit the tree and re-run, or tag the result 'validated'."
            )
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
        # Review F1 / ADR-023: a thesis-grade claim's delta uncertainty must be COMPOSED from
        # the paired-difference measurement — a hand-entered u95_delta is not publication
        # evidence. Applies to a top-level claim and to one riding inside an OptimizationResult.
        claim = self.improvement
        if claim is None and self.optimization is not None:
            claim = self.optimization.improvement
        if claim is not None:
            du = claim.delta_uncertainty
            if not isinstance(du, ComposedDeltaU95 | IndependentDeltaU95):
                raise ValueError(
                    "thesis-grade requires a MEASURED delta uncertainty (composed paired-"
                    "difference per ADR-023, or independent-RSS per ADR-029); a hand-entered "
                    "u95_delta is not publication evidence (CONSTITUTION Invariant 10, review "
                    "F1)."
                )
            if du.u95_numerical <= 0.0:
                raise ValueError(
                    "thesis-grade improvement requires a positive paired-numerical U95 (GCI on "
                    "the delta / matched-grid Richardson): matched conditions reduce, never "
                    "zero, the discretization error."
                )
            if claim.kind != "steady":
                if isinstance(du, ComposedDeltaU95):
                    if du.paired is None:  # unreachable (claim validator) — fail-loud
                        raise ValueError(
                            f"composed {claim.kind} claim is missing its paired-difference "
                            "measurement."
                        )
                    if not du.paired.diff_stat.reliable:
                        raise ValueError(
                            "thesis-grade improvement requires a RELIABLE difference-series "
                            "statistical estimate (NOBM/tau_int agreement and N_eff above the "
                            "floor); extend the paired runs to tighten it."
                        )
                else:  # IndependentDeltaU95
                    if not (du.baseline_stat.reliable and du.candidate_stat.reliable):
                        raise ValueError(
                            "thesis-grade improvement requires RELIABLE sampling estimates on "
                            "BOTH time-averages (NOBM/tau_int agreement and N_eff above the "
                            "floor); extend the runs to tighten them (ADR-029)."
                        )
        return self
