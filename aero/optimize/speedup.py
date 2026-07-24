"""The Stage-17 speed-up protocol — paired arms, pre-registered bar, honest accounting (ADR-032).

Pure composition, no I/O: the drivers produce one :class:`ArmTrace` per (arm, seed) and
this module evaluates the PRE-REGISTERED comparison rule (gates S1-S8, committed in the
driver docstring + ADR-032 before any campaign solve):

* the figure of merit is the MARGINAL ground-truth CFD evaluations to the first
  CFD-verified value at/past the bar (S4);
* the TOTAL-including-corpus accounting (marginal + training-corpus solves) is ALWAYS
  reported alongside — the corpus is the reusable flywheel asset, but hiding its cost
  would be the classic surrogate-speed-up sleight of hand (S4, honesty first);
* an arm that never reaches the bar within budget is censored, and a seed where
  NEITHER arm reaches it counts AGAINST GO (S5);
* GO on the speed-up axis ⇔ the surrogate arm wins strictly in >= ``min_wins`` of the
  seeds (S6). The certificate and verification gates (C*, V*) are combined by the
  report driver — this module owns only the eval-count comparison.

Failed solves are already inside each trace's rows/counts (S8: a failed solve is a
spent eval in both arms). Strict frozen pydantic; stdlib + pydantic only.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

_STRICT = ConfigDict(extra="forbid", frozen=True, validate_assignment=True, validate_default=True)


class EvalRow(BaseModel):
    """One ground-truth CFD evaluation in an arm's trajectory (budget order)."""

    model_config = _STRICT

    n: int = Field(..., ge=1, description="1-based cumulative ground-truth eval count.")
    design_named: dict[str, float] = Field(..., description="Physical design variables.")
    value: float | None = Field(
        default=None, description="CFD objective (L/D); None iff the solve failed (S8)."
    )
    mlflow_run_id: str | None = None


class ArmTrace(BaseModel):
    """One arm x seed trajectory: every ground-truth eval, in spend order."""

    model_config = _STRICT

    arm: Literal["direct", "surrogate"]
    seed: int
    baseline_value: float = Field(
        ..., description="The m=0 baseline L/D at the campaign grid (shared by both arms)."
    )
    rows: tuple[EvalRow, ...] = Field(..., min_length=1)

    @model_validator(mode="after")
    def _rows_ordered(self) -> ArmTrace:
        counts = [r.n for r in self.rows]
        if counts != sorted(counts) or len(set(counts)) != len(counts):
            raise ValueError(f"EvalRow.n must be strictly increasing; got {counts}")
        return self

    def reached_at(self, bar_delta: float, *, maximize: bool = True) -> int | None:
        """The eval count at which the arm FIRST cleared baseline + bar_delta; None = censored."""
        sign = 1.0 if maximize else -1.0
        for row in self.rows:
            if row.value is None:
                continue
            if sign * (row.value - self.baseline_value) >= bar_delta:
                return row.n
        return None


class SeedComparison(BaseModel):
    """One seed's paired outcome under the pre-registered rule."""

    model_config = _STRICT

    seed: int
    direct_reached_at: int | None
    surrogate_reached_at: int | None
    surrogate_marginal: int | None = Field(
        default=None, description="= surrogate_reached_at (S4 marginal accounting)."
    )
    surrogate_total_including_corpus: int | None = Field(
        default=None, description="surrogate_reached_at + corpus size (the honest second book)."
    )
    surrogate_wins: bool = Field(
        ...,
        description="Strict marginal win (S6). A censored surrogate arm never wins; a seed "
        "where neither arm reached the bar counts against GO (S5).",
    )


class SpeedupVerdict(BaseModel):
    """The speed-up axis of the Stage-17 GO decision (S-gates only)."""

    model_config = _STRICT

    bar_delta: float = Field(..., description="Pre-registered Δ* (S3).")
    corpus_size: int = Field(..., ge=0)
    min_wins: int = Field(..., ge=1)
    comparisons: tuple[SeedComparison, ...] = Field(..., min_length=1)
    wins: int = Field(..., ge=0)
    speedup_gate_pass: bool = Field(
        ...,
        description="wins >= min_wins. NOT the full GO — cert (C*) and verification "
        "(V*) gates are combined by the report driver.",
    )


def evaluate_speedup(
    direct: tuple[ArmTrace, ...],
    surrogate: tuple[ArmTrace, ...],
    *,
    bar_delta: float,
    corpus_size: int,
    min_wins: int = 2,
    maximize: bool = True,
) -> SpeedupVerdict:
    """Apply the pre-registered comparison rule to paired arm traces.

    ``direct`` and ``surrogate`` must cover the same seed set (S1); traces are
    paired by seed. Raises on mismatched seeds — a missing arm is a broken
    campaign, not a statistical outcome.
    """
    d_by_seed = {t.seed: t for t in direct}
    s_by_seed = {t.seed: t for t in surrogate}
    if len(d_by_seed) != len(direct) or len(s_by_seed) != len(surrogate):
        raise ValueError("duplicate seeds within an arm's traces")
    if set(d_by_seed) != set(s_by_seed):
        raise ValueError(
            f"arms cover different seed sets: direct={sorted(d_by_seed)} "
            f"surrogate={sorted(s_by_seed)} — the comparison is paired by seed (S1)"
        )
    for expected, traces in (("direct", direct), ("surrogate", surrogate)):
        for t in traces:
            if t.arm != expected:
                raise ValueError(
                    f"trace for seed {t.seed} carries arm label {t.arm!r}; expected {expected!r}"
                )

    comparisons: list[SeedComparison] = []
    for seed in sorted(d_by_seed):
        d_at = d_by_seed[seed].reached_at(bar_delta, maximize=maximize)
        s_at = s_by_seed[seed].reached_at(bar_delta, maximize=maximize)
        # S5/S6: a censored surrogate arm cannot win; if the direct arm is censored
        # too, the seed is inconclusive and counts AGAINST GO.
        wins = s_at is not None and (d_at is None or s_at < d_at)
        comparisons.append(
            SeedComparison(
                seed=seed,
                direct_reached_at=d_at,
                surrogate_reached_at=s_at,
                surrogate_marginal=s_at,
                surrogate_total_including_corpus=None if s_at is None else s_at + corpus_size,
                surrogate_wins=wins,
            )
        )
    n_wins = sum(1 for c in comparisons if c.surrogate_wins)
    return SpeedupVerdict(
        bar_delta=bar_delta,
        corpus_size=corpus_size,
        min_wins=min_wins,
        comparisons=tuple(comparisons),
        wins=n_wins,
        speedup_gate_pass=n_wins >= min_wins,
    )
