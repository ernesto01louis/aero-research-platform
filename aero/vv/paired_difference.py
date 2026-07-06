"""Paired-difference statistical uncertainty of a matched-condition delta — ``u95_delta``.

CONSTITUTION Invariant 10 (IMPROVEMENT-EXCEEDS-UNCERTAINTY) requires an optimization delta to
exceed ``k * u95_delta``, where baseline and candidate run at **matched numerics/mesh-topology**
so correlated errors cancel. Until the 2026-07 external review (finding F1,
``docs/review/2026-07-external-review.md``), that cancellation was asserted in prose and
``u95_delta`` was a free input — nothing measured it. This module is the measurement.

**Method.** Form the per-cycle **difference series** ``candidate - baseline`` over the common
converged window and run the existing NOBM + tau_int machinery
(:func:`aero.vv.statistical_uncertainty.statistical_uncertainty_from_samples`) on it. The
difference series carries whatever cycle-to-cycle covariance the two runs share, so its
batch-means half-width *is* the measured post-cancellation statistical uncertainty of the delta
— no analytic ``u_b^2 + u_c^2 - 2*rho*u_b*u_c`` composition (rejected in ADR-023: fragile dof
bookkeeping, double-counts what NOBM already sees). The empirical baseline<->candidate Pearson
correlation and the ``variance_reduction`` ratio against the independent RSS are recorded so the
cancellation is **auditable**: a weakly/anti-correlated pair yields ``variance_reduction >= 1``
— surfaced, never hidden, and still an honest (wide) estimate.

**Alignment precondition (read this).** :class:`~aero.postprocess.phase_averaging.CycleSamples`
carries no time-origin metadata: index-``k`` pairing is valid **only** when both runs were
segmented from the same wall-clock origin with the same period and the same
``drop_initial_cycles`` — true by construction for the platform's paired drivers (one motion
spec, two physics/geometry variants; e.g. the Stage-13 laminar-vs-``kOmegaSSTLM`` same-mesh
study), but not machine-checkable today. Period equality IS checked (fail-loud); a
``CycleSamples.t0`` field is ledgered (ADR-023) to make origin equality checkable.

**Practical sample-size bar.** The hard floor is ``min_pairs = 8`` (the NOBM minimum), but at
N = 8 the ``reliable`` flag is almost never set: ``n_eff = N / (2*tau_int) >= 8`` requires
``tau_int = 0.5`` exactly (a perfectly IID tail). Since the thesis-grade gate demands a
*reliable* difference-series estimate, plan paired campaigns around **~16-20 common converged
cycles**, not 8 — an 8-cycle pair will construct but stay ``validated``.

References: ASME V&V 20-2009 §7; Roy & Oberkampf (2011) CMAME 200; common-random-numbers /
paired-comparison variance reduction (law of total variance for matched pairs); Fishman (1978) /
Schmeiser (1982) batch means; Sokal (1997) automatic windowing.

Strict pydantic, frozen, ``extra="forbid"``. PLATFORM-NOT-HUB: stdlib + numpy + pydantic only.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from typing import Literal

import numpy as np
from pydantic import BaseModel, ConfigDict, Field, ValidationError, computed_field, model_validator

from aero.postprocess.cycle_detection import CycleConvergenceReport
from aero.postprocess.phase_averaging import CycleSamples
from aero.vv.statistical_uncertainty import (
    DEFAULT_MIN_SAMPLES,
    StatisticalUncertainty,
    StatisticalUncertaintyError,
    statistical_uncertainty_from_samples,
)

_STRICT = ConfigDict(
    extra="forbid",
    frozen=True,
    str_strip_whitespace=True,
    validate_default=True,
)

# Consistency tolerance for mean(candidate) - mean(baseline) vs mean(candidate - baseline):
# mathematically identical, but numpy's pairwise summation rounds the two paths differently
# (relative error ~ n * eps ~ 1e-12 for any realistic tail).
_MEAN_CONSISTENCY_RTOL = 1.0e-9
_MEAN_CONSISTENCY_ATOL = 1.0e-12


class PairedDifferenceError(StatisticalUncertaintyError):
    """The paired baseline/candidate series cannot support a delta uncertainty.

    Subclasses :class:`~aero.vv.statistical_uncertainty.StatisticalUncertaintyError` (itself a
    ``ValueError``) so existing handlers catch pairing failures and a failure inside a pydantic
    model surfaces as a ``ValidationError`` — fail-loud, never a silent zero.
    """


class PairedDeltaUncertainty(BaseModel):
    """Measured statistical uncertainty of a matched-pair delta, with its audit trail.

    The three embedded :class:`StatisticalUncertainty` objects are all computed over the SAME
    paired window (``pair_start``, ``n_pairs``) — per-side stats on each run's tail restricted
    to that window, ``diff_stat`` on the difference series. That keeps
    ``u95_delta_statistical`` vs :attr:`rss_independent` an apples-to-apples comparison: a
    longer baseline tail must not fake extra cancellation. Cross-field validators pin the
    embedded objects to the window and to each other, so a hand-assembled instance must be
    internally consistent (high-friction, not unforgeable — ADR-023).
    """

    model_config = _STRICT

    method: Literal["paired_nobm"] = Field(
        default="paired_nobm", description="Estimator: NOBM + tau_int on the difference series."
    )
    period: float = Field(..., gt=0.0, description="The (matched) cycle period, time units.")
    n_pairs: int = Field(
        ...,
        ge=2,
        description="Length of the common paired window (schema floor 2 = Pearson ddof=1 "
        "minimum; the estimator functions enforce the NOBM minimum of 8).",
    )
    pair_start: int = Field(
        ...,
        ge=0,
        description="First paired cycle index = max of the two converged_from_cycle (audit trail).",
    )
    mean_baseline: float = Field(..., description="Baseline mean over the paired window.")
    mean_candidate: float = Field(..., description="Candidate mean over the paired window.")
    correlation: float = Field(
        ...,
        ge=-1.0,
        le=1.0,
        description="Empirical Pearson r(baseline, candidate) over the paired window — the "
        "auditable evidence for (or against) correlated-error cancellation.",
    )
    baseline_stat: StatisticalUncertainty = Field(
        ..., description="NOBM + tau_int of the baseline tail over the paired window."
    )
    candidate_stat: StatisticalUncertainty = Field(
        ..., description="NOBM + tau_int of the candidate tail over the paired window."
    )
    diff_stat: StatisticalUncertainty = Field(
        ...,
        description="NOBM + tau_int of the DIFFERENCE series (candidate - baseline) — the "
        "measured post-cancellation statistical uncertainty of the delta.",
    )

    @computed_field  # type: ignore[prop-decorator]
    @property
    def mean_delta(self) -> float:
        """Raw delta ``candidate - baseline`` (direction-agnostic; the claim sign-corrects)."""
        return self.mean_candidate - self.mean_baseline

    @computed_field  # type: ignore[prop-decorator]
    @property
    def u95_delta_statistical(self) -> float:
        """The measured statistical U95 of the delta (the difference-series half-width)."""
        return self.diff_stat.u95_statistical

    @computed_field  # type: ignore[prop-decorator]
    @property
    def rss_independent(self) -> float:
        """The no-cancellation reference bar: RSS of the two per-side absolute U95s."""
        return math.hypot(self.baseline_stat.u95_statistical, self.candidate_stat.u95_statistical)

    @computed_field  # type: ignore[prop-decorator]
    @property
    def variance_reduction(self) -> float:
        """``u95_delta_statistical / rss_independent`` — < 1 means cancellation worked.

        >= 1 means the matched-condition cancellation did NOT work (weak or negative
        correlation); the estimate is still honest (wide) — surfaced, never hidden.
        """
        return self.u95_delta_statistical / self.rss_independent

    @computed_field  # type: ignore[prop-decorator]
    @property
    def cancellation_effective(self) -> bool:
        """Soft audit flag (mirrors ``StatisticalUncertainty.reliable``): did pairing pay off?"""
        return self.correlation > 0.0 and self.variance_reduction < 1.0

    @model_validator(mode="after")
    def _embedded_stats_consistent(self) -> PairedDeltaUncertainty:
        # Anti-forgery cross-checks (ADR-023): every embedded stat must be pinned to the paired
        # window and internally consistent, so the diagnostics derived from them mean something.
        for name, stat in (
            ("baseline_stat", self.baseline_stat),
            ("candidate_stat", self.candidate_stat),
            ("diff_stat", self.diff_stat),
        ):
            if stat.n_samples != self.n_pairs:
                raise ValueError(
                    f"{name}.n_samples={stat.n_samples} != n_pairs={self.n_pairs}: all three "
                    "embedded estimates must cover the SAME paired window."
                )
            if stat.dof != stat.n_batches - 1:
                raise ValueError(f"{name}.dof={stat.dof} != n_batches-1={stat.n_batches - 1}.")
            if stat.u95_statistical != stat.t_quantile * stat.se:
                raise ValueError(
                    f"{name}.u95_statistical={stat.u95_statistical} != t_quantile*se="
                    f"{stat.t_quantile * stat.se}: the embedded estimate is not self-consistent."
                )
        if self.mean_baseline != self.baseline_stat.mean:
            raise ValueError(
                f"mean_baseline={self.mean_baseline} != baseline_stat.mean="
                f"{self.baseline_stat.mean}: the claimed mean must be the paired-window mean."
            )
        if self.mean_candidate != self.candidate_stat.mean:
            raise ValueError(
                f"mean_candidate={self.mean_candidate} != candidate_stat.mean="
                f"{self.candidate_stat.mean}: the claimed mean must be the paired-window mean."
            )
        scale = max(abs(self.mean_baseline), abs(self.mean_candidate))
        if abs(self.mean_delta - self.diff_stat.mean) > (
            _MEAN_CONSISTENCY_RTOL * scale + _MEAN_CONSISTENCY_ATOL
        ):
            raise ValueError(
                f"mean_delta={self.mean_delta} disagrees with diff_stat.mean="
                f"{self.diff_stat.mean} beyond float rounding: the difference series does not "
                "match the claimed means."
            )
        # Zero-division guard for variance_reduction: a per-side u95 of exactly 0 is reachable
        # through NOBM with a live signal (e.g. a period-2 alternating tail gives identical
        # batch means), so refuse it here with a typed error instead of ZeroDivision at first
        # computed-field access.
        if self.baseline_stat.u95_statistical <= 0.0 or self.candidate_stat.u95_statistical <= 0.0:
            raise ValueError(
                "a per-side u95_statistical is exactly 0 (degenerate batch means — e.g. a "
                "period-locked alternating tail); the paired comparison has no independent "
                "reference bar. Investigate the per-side series, not the estimator."
            )
        return self


def paired_delta_uncertainty_from_samples(
    baseline_tail: Sequence[float],
    candidate_tail: Sequence[float],
    *,
    period: float,
    pair_start: int = 0,
    amp_scale: float | None = None,
    min_pairs: int = DEFAULT_MIN_SAMPLES,
) -> PairedDeltaUncertainty:
    """Measure the paired-delta statistical uncertainty from two aligned per-cycle tails.

    The tails must be index-aligned (element ``k`` of both = the same physical forcing cycle)
    and equal length — see the module docstring's alignment precondition.
    :func:`paired_delta_uncertainty` derives them from ``CycleSamples`` + convergence reports;
    call this directly only when you already hold aligned tails.

    ``amp_scale`` is the oscillation amplitude of the UNDERLYING signals (max over both runs).
    The difference series' dead-signal guard is normalised by the **signal scale**
    ``max(amp_scale, |mean_b|, |mean_c|)``, not by the diff's own scale: per-cycle means are
    O(signal) floats with ~2e-16 relative precision, so a difference varying below ``1e-12 x``
    the signal is float-cancellation noise — reporting a u95 from it would fabricate precision.
    (Normalising by the diff's own scale would never fire; by the delta mean would spuriously
    kill small-mean/high-variance diffs.)

    RAISES :class:`PairedDifferenceError` on: unequal lengths, ``N < min_pairs``, non-finite
    values, bit-identical inputs (a self-comparison is not a measurement), or a difference
    series the NOBM estimator refuses.
    """
    b = np.asarray(baseline_tail, dtype=np.float64)
    c = np.asarray(candidate_tail, dtype=np.float64)
    if b.size != c.size:
        raise PairedDifferenceError(
            f"paired tails must be equal length (index-aligned cycles); got baseline N={b.size} "
            f"vs candidate N={c.size}. Trim to the common converged window first."
        )
    n = int(b.size)
    if n < min_pairs:
        raise PairedDifferenceError(
            f"only N={n} paired converged cycles (< {min_pairs}); too few for a stable "
            "paired batch-means u95_delta. Extend BOTH runs to widen the common converged "
            "window (and note the practical thesis bar is ~16-20 pairs — module docstring)."
        )
    if not (bool(np.all(np.isfinite(b))) and bool(np.all(np.isfinite(c)))):
        raise PairedDifferenceError(
            "non-finite value in a paired tail: NaN/inf would silently poison the correlation "
            "and the difference series. Investigate the run outputs."
        )
    if np.array_equal(b, c):
        raise PairedDifferenceError(
            "baseline and candidate tails are bit-identical — a self-comparison is not a "
            "measurement (delta is exactly 0 and the correlation is undefined)."
        )

    amp = float(amp_scale) if amp_scale is not None else 0.0

    # Per-side estimates over the SAME window (apples-to-apples vs the diff — see model docs).
    # Semantic estimator failures (dead signal, unconverged) pass through as
    # StatisticalUncertaintyError; a *degenerate* batch-means estimate (e.g. a period-locked
    # alternating tail -> identical batch means -> u95 = 0 -> the estimator's own
    # crosscheck_ratio > 0 bound fails at construction) is re-raised typed so the paired caller
    # is never handed a bare mid-construction ValidationError.
    def _per_side(side: str, tail: np.ndarray) -> StatisticalUncertainty:
        try:
            return statistical_uncertainty_from_samples(
                tail.tolist(), amp_scale=amp, min_samples=min_pairs
            )
        except ValidationError as exc:
            raise PairedDifferenceError(
                f"the {side} tail cannot support a per-side u95_statistical (degenerate batch "
                f"means — e.g. a period-locked alternating tail): {exc}"
            ) from exc

    baseline_stat = _per_side("baseline", b)
    candidate_stat = _per_side("candidate", c)

    diff = c - b
    signal_scale = max(amp, abs(baseline_stat.mean), abs(candidate_stat.mean))
    try:
        diff_stat = statistical_uncertainty_from_samples(
            diff.tolist(), amp_scale=signal_scale, min_samples=min_pairs
        )
    except StatisticalUncertaintyError as exc:
        raise PairedDifferenceError(
            f"the difference series cannot support a paired u95_delta_statistical: {exc} "
            "(a dead difference at signal scale means the two runs are numerically "
            "indistinguishable — there is no measurable delta)."
        ) from exc

    # Empirical Pearson r — the audit evidence for the cancellation. Per-side dead-signal
    # guards above make a zero-variance side unreachable; keep a defensive raise anyway.
    sb = float(b.std(ddof=1))
    sc = float(c.std(ddof=1))
    if sb <= 0.0 or sc <= 0.0:
        raise PairedDifferenceError(
            "zero-variance paired tail: the correlation coefficient is undefined."
        )
    correlation = float(np.clip(np.corrcoef(b, c)[0, 1], -1.0, 1.0))

    return PairedDeltaUncertainty(
        period=period,
        n_pairs=n,
        pair_start=pair_start,
        mean_baseline=baseline_stat.mean,
        mean_candidate=candidate_stat.mean,
        correlation=correlation,
        baseline_stat=baseline_stat,
        candidate_stat=candidate_stat,
        diff_stat=diff_stat,
    )


def paired_delta_uncertainty(
    baseline: CycleSamples,
    baseline_report: CycleConvergenceReport,
    candidate: CycleSamples,
    candidate_report: CycleConvergenceReport,
    *,
    period_rtol: float = 1.0e-9,
    min_pairs: int = DEFAULT_MIN_SAMPLES,
) -> PairedDeltaUncertainty:
    """Measure the paired-delta uncertainty over the common converged window of two runs.

    The paired window is the **intersection of the two converged tails**:
    ``[max(converged_from_cycle), min(n_cycles))``. Cycle ``k`` is the same physical forcing
    cycle in both runs (same origin + period — module-docstring precondition), so trimming each
    side's own tail to equal length instead would silently pair *different* forcing cycles.

    ``period_rtol`` is deliberately tight (1e-9): matched-condition runs share one motion spec,
    so the two periods should be bit-identical; the tolerance only absorbs serialization
    round-trips. Any real mismatch means the runs were not matched and index pairing is
    physically meaningless — RAISES :class:`PairedDifferenceError`.
    """
    for side, samples, report in (
        ("baseline", baseline, baseline_report),
        ("candidate", candidate, candidate_report),
    ):
        if report.n_cycles != samples.n_cycles:
            raise PairedDifferenceError(
                f"{side} report covers n_cycles={report.n_cycles} but its CycleSamples has "
                f"n_cycles={samples.n_cycles}: report/samples mismatch — wrong pairing of inputs."
            )
        if not report.converged:
            raise PairedDifferenceError(
                f"no converged tail on the {side} run: the limit cycle has not converged. "
                "Run more cycles and investigate cycle-convergence, not the estimator."
            )
    pb, pc = baseline.period, candidate.period
    if abs(pb - pc) > period_rtol * max(pb, pc):
        raise PairedDifferenceError(
            f"period mismatch: baseline {pb!r} vs candidate {pc!r} (rtol={period_rtol:g}). "
            "Matched-condition runs share one motion spec; index-k cycle pairing is "
            "physically meaningless across different periods."
        )
    start = max(baseline_report.converged_from_cycle, candidate_report.converged_from_cycle)
    end = min(baseline.n_cycles, candidate.n_cycles)
    n_pairs = end - start
    if n_pairs < min_pairs:
        raise PairedDifferenceError(
            f"common converged window has only {n_pairs} pairs (cycles [{start}, {end}); "
            f"< {min_pairs}). Extend BOTH runs to widen the overlap of their converged tails."
        )
    b_tail = baseline.per_cycle_mean[start:end]
    c_tail = candidate.per_cycle_mean[start:end]
    amp_window = np.abs(
        np.asarray(
            baseline.per_cycle_amplitude[start:end] + candidate.per_cycle_amplitude[start:end],
            dtype=np.float64,
        )
    )
    amp_scale = float(amp_window.max()) if amp_window.size else 0.0
    return paired_delta_uncertainty_from_samples(
        b_tail,
        c_tail,
        period=pb,
        pair_start=start,
        amp_scale=amp_scale,
        min_pairs=min_pairs,
    )
