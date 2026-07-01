"""Cycle segmentation + phase-averaging over the forcing / shedding period.

Two outputs:

* :class:`CycleSamples` — per-cycle mean / amplitude / min / max. ``per_cycle_mean``
  is the **first-class batch-means input** Stage 12's statistical-U95 (``u95_statistical``
  via batch-means / effective-sample-size) consumes, restricted to the converged tail
  reported by :mod:`aero.postprocess.cycle_detection`.
* :class:`PhaseAverage` — the value averaged over the stroke phase (0..1) with the
  cycle-to-cycle scatter at each phase, the classic phase-averaged load the flapping
  literature reports.

Solver-agnostic, stdlib + numpy + pydantic only.
"""

from __future__ import annotations

import math

import numpy as np
from pydantic import BaseModel, Field, model_validator

from aero.postprocess._base import _STRICT, Signal

_EPS = 1.0e-12


class CycleSamples(BaseModel):
    """Per-cycle statistics over an integer number of forcing/shedding periods."""

    model_config = _STRICT

    period: float = Field(..., gt=0.0, description="Cycle period (time units).")
    n_cycles: int = Field(..., ge=1, description="Number of full cycles segmented.")
    per_cycle_mean: tuple[float, ...] = Field(..., description="Mean value within each cycle.")
    per_cycle_amplitude: tuple[float, ...] = Field(
        ..., description="Half peak-to-peak (amplitude) within each cycle."
    )
    per_cycle_min: tuple[float, ...] = Field(..., description="Minimum within each cycle.")
    per_cycle_max: tuple[float, ...] = Field(..., description="Maximum within each cycle.")

    @model_validator(mode="after")
    def _lengths(self) -> CycleSamples:
        for field in ("per_cycle_mean", "per_cycle_amplitude", "per_cycle_min", "per_cycle_max"):
            if len(getattr(self, field)) != self.n_cycles:
                raise ValueError(
                    f"CycleSamples.{field} length {len(getattr(self, field))} != "
                    f"n_cycles {self.n_cycles}"
                )
        return self


class PhaseAverage(BaseModel):
    """Phase-averaged waveform over one period, with cycle-to-cycle scatter."""

    model_config = _STRICT

    period: float = Field(..., gt=0.0)
    n_cycles: int = Field(..., ge=1)
    phase: tuple[float, ...] = Field(..., description="Phase-bin centres in [0, 1).")
    mean: tuple[float, ...] = Field(..., description="Phase-averaged value per bin.")
    std: tuple[float, ...] = Field(..., description="Cycle-to-cycle std per bin.")

    @model_validator(mode="after")
    def _lengths(self) -> PhaseAverage:
        if not (len(self.phase) == len(self.mean) == len(self.std)):
            raise ValueError("PhaseAverage: phase/mean/std lengths differ")
        return self


def _cycle_bounds(sig: Signal, *, period: float, drop_initial_cycles: int) -> tuple[float, int]:
    """(start time, number of full cycles) for an integer-cycle window of ``sig``."""
    if period <= 0.0:
        raise ValueError(f"period must be positive, got {period}")
    t0 = sig.t[0] + drop_initial_cycles * period
    span = sig.t[-1] - t0
    n_full = math.floor(span / period + 1.0e-9)
    if n_full < 1:
        raise ValueError(
            f"signal {sig.name!r} spans < 1 cycle after dropping {drop_initial_cycles} "
            f"(period={period:g}, available span={span:g})"
        )
    return t0, n_full


def segment_cycles(
    sig: Signal,
    *,
    period: float,
    drop_initial_cycles: int = 0,
    min_samples_per_cycle: int = 4,
) -> CycleSamples:
    """Partition ``sig`` into consecutive full cycles and compute per-cycle statistics.

    Bins samples by time into half-open windows ``[t0 + k*period, t0 + (k+1)*period)``.
    Fails loud if any cycle is under-resolved (fewer than ``min_samples_per_cycle``
    samples) — an unreliable per-cycle statistic must not pass silently.
    """
    t = sig.t_array
    y = sig.y_array
    t0, n_full = _cycle_bounds(sig, period=period, drop_initial_cycles=drop_initial_cycles)

    means: list[float] = []
    amps: list[float] = []
    mins: list[float] = []
    maxs: list[float] = []
    for k in range(n_full):
        lo = t0 + k * period
        hi = lo + period
        mask = (t >= lo - _EPS) & (t < hi - _EPS)
        yk = y[mask]
        if yk.size < min_samples_per_cycle:
            raise ValueError(
                f"signal {sig.name!r} cycle {k} has {yk.size} samples "
                f"(< {min_samples_per_cycle}); increase the write frequency"
            )
        means.append(float(yk.mean()))
        amps.append(0.5 * float(yk.max() - yk.min()))
        mins.append(float(yk.min()))
        maxs.append(float(yk.max()))

    return CycleSamples(
        period=period,
        n_cycles=n_full,
        per_cycle_mean=tuple(means),
        per_cycle_amplitude=tuple(amps),
        per_cycle_min=tuple(mins),
        per_cycle_max=tuple(maxs),
    )


def phase_average(
    sig: Signal,
    *,
    period: float,
    n_bins: int = 64,
    drop_initial_cycles: int = 0,
) -> PhaseAverage:
    """Average ``sig`` over the stroke phase (0..1) across all full cycles.

    Each sample is assigned a cycle index and a phase bin ``((t - t0) mod period) /
    period``. For each phase bin the value is first averaged *within* each cycle, then
    the ``mean`` is the average of those per-cycle values and ``std`` is their
    scatter **across cycles** (the cycle-to-cycle spread at that phase — a pure
    diagnostic of periodic-steady-state, not the intra-bin waveform slope). Empty bins
    fail loud (too few samples for the requested resolution).
    """
    if n_bins < 2:
        raise ValueError(f"n_bins must be >= 2, got {n_bins}")
    t = sig.t_array
    y = sig.y_array
    t0, n_full = _cycle_bounds(sig, period=period, drop_initial_cycles=drop_initial_cycles)
    t_end = t0 + n_full * period
    mask = (t >= t0 - _EPS) & (t < t_end - _EPS)
    tw = t[mask]
    yw = y[mask]
    since = tw - t0
    cycle_idx = np.clip((since / period).astype(int), 0, n_full - 1)
    phase = np.mod(since, period) / period
    edges = np.linspace(0.0, 1.0, n_bins + 1)
    bin_idx = np.clip(np.digitize(phase, edges) - 1, 0, n_bins - 1)

    centres: list[float] = []
    means: list[float] = []
    stds: list[float] = []
    for b in range(n_bins):
        in_bin = bin_idx == b
        if not bool(np.any(in_bin)):
            raise ValueError(
                f"signal {sig.name!r}: phase bin {b}/{n_bins} is empty — reduce n_bins "
                "or increase the write frequency"
            )
        per_cycle = [
            float(yw[in_bin & (cycle_idx == k)].mean())
            for k in range(n_full)
            if bool(np.any(in_bin & (cycle_idx == k)))
        ]
        centres.append(0.5 * float(edges[b] + edges[b + 1]))
        means.append(float(np.mean(per_cycle)))
        stds.append(float(np.std(per_cycle)))

    return PhaseAverage(
        period=period,
        n_cycles=n_full,
        phase=tuple(centres),
        mean=tuple(means),
        std=tuple(stds),
    )
