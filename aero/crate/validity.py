"""The validity context of a result crate: Hard Rule 16's "validity context", made concrete (ADR-047 D4).

A crate states what its content does and does not support. That covers:

- its **claim tier**;
- the **pre-registered gates** it was judged against, kept distinct from the **diagnostics** it
  merely reports;
- the **applicability bounds** of the result;
- the **limitations** its own content makes mandatory.

Every ``passed`` flag and every GO/NO-GO is re-derived on read, so a crate cannot carry a verdict
its own numbers contradict. The rules that span the envelope *and* the payload live in
:func:`check_validity`. The reader and the writer both run it.
"""

from __future__ import annotations

from typing import Literal

from pydantic import AwareDatetime, BaseModel, Field, model_validator

from aero.crate.model_base import CRATE_CONFIG, Reference

__all__ = [
    "Comparator",
    "GateVerdict",
    "Limitation",
    "LimitationId",
    "Unavailable",
    "ValidityContext",
    "Verdict",
]

Comparator = Literal["lt", "le", "gt", "ge", "within", "is-true"]

LimitationId = Literal[
    # Mandatory when the content triggers them (check_validity enforces):
    "input-uq-skipped",
    "no-experiment-anchor",
    "nogo",
    "diagnostic-not-gate",
    "provenance-unavailable",
    "provenance-sha-not-public",
    "dvc-input-hash-sync-state",
    "container-digest-by-lookup",
    "certificate-expiry",
    "not-flagship-domain",
    "no-claim",
    # Record-specific, stated where they apply:
    "certificate-data-gate-content-blind",
    "retracted-claim",
    "tier-capped",
    "speedup-nogo",
    "recorded-not-re-derivable",
    "attribution-leading-hypothesis",
    "uq-reference-outside-release-narrative",
    "record-provenance-is-spec-identity",
    "held-out-is-same-grid-re-solve",
    "surrogate-proposals-smoke-tier",
    "margin-inside-u95",
    "superseded-campaign",
]

# The sentence ADR-046 S3 requires in the body of every v0.1.0 artifact that reports an
# optimization outside the flagship domain. check_validity requires it verbatim.
FLAGSHIP_LIMITATION_SENTENCE = "No flapping optimization claim is made in v0.1.0."


class GateVerdict(BaseModel):
    """One criterion with its observed value. Either GATED (pre-registered) or a reported DIAGNOSTIC."""

    model_config = CRATE_CONFIG

    name: str = Field(..., pattern=r"^[a-z0-9][a-z0-9-]{0,62}$")
    gated: bool = Field(
        ...,
        description="True: a pre-registered gate that decides the verdict. False: a reported "
        "diagnostic -- never a gate, whatever its outcome.",
    )
    criterion: str = Field(..., min_length=1, description="The criterion, as recorded.")
    comparator: Comparator
    threshold: float | tuple[float, float] | None = Field(
        ..., description="A bound; (lo, hi) for 'within'; None only for 'is-true'."
    )
    observed: bool | float = Field(..., description="The observed value.")
    passed: bool = Field(..., description="Must equal the comparator applied to observed.")
    preregistered_in: Reference | None = Field(
        default=None, description="Where the gate was pre-registered. Required when gated."
    )

    @model_validator(mode="after")
    def _consistent(self) -> GateVerdict:
        if self.gated and self.preregistered_in is None:
            raise ValueError(f"gate {self.name!r} is gated but names no pre-registration")
        if self.comparator == "is-true":
            if self.threshold is not None or not isinstance(self.observed, bool):
                raise ValueError(f"gate {self.name!r}: 'is-true' takes a bool and no threshold")
            expected = self.observed is True
        else:
            if isinstance(self.observed, bool):
                raise ValueError(
                    f"gate {self.name!r}: comparator {self.comparator!r} needs a number"
                )
            x = self.observed
            if self.comparator == "within":
                if not isinstance(self.threshold, tuple):
                    raise ValueError(f"gate {self.name!r}: 'within' needs (lo, hi)")
                lo, hi = self.threshold
                if lo > hi:
                    raise ValueError(f"gate {self.name!r}: lo > hi")
                expected = lo <= x <= hi
            else:
                if not isinstance(self.threshold, float):
                    raise ValueError(f"gate {self.name!r}: {self.comparator!r} needs one bound")
                t = self.threshold
                expected = {
                    "lt": x < t,
                    "le": x <= t,
                    "gt": x > t,
                    "ge": x >= t,
                }[self.comparator]
        if self.passed is not expected:
            raise ValueError(
                f"gate {self.name!r}: passed={self.passed} contradicts its own numbers "
                f"({self.observed!r} {self.comparator} {self.threshold!r} is {expected})"
            )
        return self


class Verdict(BaseModel):
    """A GO / NO-GO over a set of gates. GO iff every GATED gate passed."""

    model_config = CRATE_CONFIG

    scope: Literal[
        "optimization-claim",
        "grid-certification",
        "surrogate-certificate",
        "speed-up",
        "forward-validation",
        "thesis-grade-gate",
    ]
    overall: Literal["GO", "NO-GO"]
    qualifier: Literal["degenerate"] | None = None
    gates: tuple[GateVerdict, ...] = Field(..., min_length=1)

    @model_validator(mode="after")
    def _overall_follows_the_gates(self) -> Verdict:
        gated = [g for g in self.gates if g.gated]
        if not gated:
            raise ValueError(f"verdict {self.scope!r} has no gated gate (diagnostics only)")
        names = [g.name for g in self.gates]
        if len(names) != len(set(names)):
            raise ValueError(f"verdict {self.scope!r} repeats a gate name")
        expected = "GO" if all(g.passed for g in gated) else "NO-GO"
        if self.overall != expected:
            raise ValueError(
                f"verdict {self.scope!r}: overall={self.overall} but gates say {expected}"
            )
        return self


class Limitation(BaseModel):
    """A stated limitation of the crate's content. A ``quote`` is verbatim from ``source``."""

    model_config = CRATE_CONFIG

    id: LimitationId
    kind: Literal["quote", "statement"]
    text: str = Field(..., min_length=1)
    source: Reference


class Unavailable(BaseModel):
    """A component a self-describing crate would carry, declared ABSENT, with the reason."""

    model_config = CRATE_CONFIG

    item: Literal[
        "four_tuple",
        "u95",
        "case_spec",
        "baseline_provenance",
        "grid_inputs",
        "raw_series",
        "mlflow_run",
    ]
    reason: str = Field(..., min_length=1)


CORE_UNAVAILABLE = frozenset({"four_tuple", "u95", "case_spec"})


class ValidityContext(BaseModel):
    """What the crate's content supports, and what it does not."""

    model_config = CRATE_CONFIG

    claim_tier: Literal["none", "smoke", "validated", "thesis-grade"]
    claim_scope: Literal["optimization", "forward-capability", "uq-reference"]
    flagship_domain: bool = Field(
        ..., description="True iff the result is in the flagship flapping-wing domain."
    )
    validated_against_experiment: bool = Field(
        ..., description="True iff an experiment/DNS anchor PASSED. Re-derived on read."
    )
    verdicts: tuple[Verdict, ...] = ()
    design_space: dict[str, tuple[float, float]] = Field(
        default_factory=dict, description="Applicability bounds of every design variable."
    )
    conditions: dict[str, float | str] = Field(
        default_factory=dict, description="Operating conditions (Re, AoA, model, …)."
    )
    certificate_expiry: AwareDatetime | None = Field(
        default=None, description="Expiry of a cited surrogate certificate."
    )
    limitations: tuple[Limitation, ...] = Field(..., min_length=1)

    @model_validator(mode="after")
    def _well_formed(self) -> ValidityContext:
        for name, (lo, hi) in self.design_space.items():
            if lo > hi:
                raise ValueError(f"design_space[{name!r}]: lo > hi")
        ids = [lim.id for lim in self.limitations]
        if len(ids) != len(set(ids)):
            raise ValueError("a limitation id appears twice")
        return self
