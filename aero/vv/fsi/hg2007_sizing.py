"""ADR-039 B2's pre-registered sizing rule — pure, so the numbers are an output.

The gate block pre-registers the sizing RULE while its B2 clause carries the
``<<B2-PENDING-I4>>`` marker; the I7/I4 pre-flight record lands next with its own
four-fold tuple; a third commit fills the marker with numbers that a required unit test
re-derives from the record THROUGH THIS MODULE. The numbers are therefore an output of
the measurement, never a decision (handoff §6.11, operator decision 2).

Three rules are structural rather than advisory, because each one closes a measured
failure mode:

- **No rate from a transient.** A record whose run did not complete every requested
  window, or did not end ``all-exited``, is refused outright — Stage 19's projections
  were off by 3.5-9.6x in one direction and the B3 diagnostic by ~1.8x in the other when
  a rate was read off a partial run.
- **The campaign dt IS a passing probe's dt, verbatim.** Courant scales with dt only
  under a dt-independent velocity field, which a coupled FSI solve does not guarantee.
  On a failed probe this module may *suggest* a smaller candidate
  (:func:`suggest_next_dt`), but it refuses to size a campaign around any dt that was
  not itself measured at ``Co <= courant_bound``.
- **The projection uses the contention-measured rate.** Wave 1 runs both arms
  concurrently on one box; an uncontended seconds-per-window understates the wave. The
  gated rung's calibrations must therefore have been measured in the wave-1 shape (each
  arm's record naming the other run as concurrent).

ADR-040 adds a second entry point, :func:`size_gated_campaign_040`, and a second record
type, :class:`N3Confirmation`. It exists because the ADR-039 rule reads its rate as
``wall_clock_s / windows_completed``, and under the campaign's own ``(1-cos)`` ramp that
is the wrong number by construction: the ramp spans one full cycle -- 50 725 windows at
dt = 2e-5 -- so a run long enough to reach the post-ramp regime spends about two thirds of
itself at near-zero plunge. Averaging those in produces a comfortable rate and an
unaffordable campaign. The ADR-039 rule and :class:`I4Calibration` are left UNTOUCHED, so
every test and record written against them still holds.

One pre-registered difference beyond the rate (ADR-040 W3): an N3 confirmation that
stopped at its ceiling may still size, PROVIDED it cleared the ramp and completed a whole
number of post-ramp quarter-cycles. ADR-039's ``_require_complete`` refuses a ceiling stop
outright, which is right for a fixed-length calibration and wrong for a measurement whose
whole purpose is to run until the rate is known. What may never size is a rate read from
inside the ramp -- that is refused, and it is the reason this function exists.

Everything here is stdlib + pydantic (Invariant 1); no filesystem, no clocks.
"""

from __future__ import annotations

import math
from collections.abc import Sequence

from pydantic import BaseModel, ConfigDict, Field, model_validator

__all__ = [
    "I4Calibration",
    "I7Probe",
    "N3Confirmation",
    "SizedCampaign",
    "SizingError",
    "size_gated_campaign",
    "size_gated_campaign_040",
    "suggest_next_dt",
]

_STRICT = ConfigDict(
    extra="forbid",
    frozen=True,
    str_strip_whitespace=True,
    validate_assignment=True,
    validate_default=True,
)

#: CalculiX reads numeric fields as ``(1:20)`` characters (handoff §6.17): a chosen value
#: must survive a ``%.13e`` round trip or the deck writer refuses it. The sizing rule
#: applies the same bar to dt and max_time so the solid deck's "dt equals the coupling
#: window" assertion stays exact.
_ROUND_TRIP_FORMAT = ".13e"


def _round_trips(value: float) -> bool:
    return float(format(value, _ROUND_TRIP_FORMAT)) == value


class SizingError(Exception):
    """The record cannot honestly size a campaign; the reason is the message."""


class I7Probe(BaseModel):
    """One measured max-Courant probe (gate I7) — a completed short coupled run."""

    model_config = _STRICT

    arm: str = Field(..., min_length=1)
    rung: str = Field(..., min_length=1)
    dt: float = Field(..., gt=0.0, description="Coupling window the probe ran at [s]")
    max_courant_post_ramp: float = Field(
        ...,
        ge=0.0,
        description="Max Courant number over the post-ramp window (t >= one period)",
    )
    windows_requested: int = Field(..., ge=1)
    windows_completed: int = Field(..., ge=0)
    stopped_by: str = Field(..., min_length=1)


class I4Calibration(BaseModel):
    """One completed calibration (gate I4) — the only admissible source of a rate."""

    model_config = _STRICT

    arm: str = Field(..., min_length=1)
    rung: str = Field(..., min_length=1)
    dt: float = Field(..., gt=0.0)
    windows_requested: int = Field(..., ge=1)
    windows_completed: int = Field(..., ge=0)
    stopped_by: str = Field(..., min_length=1)
    wall_clock_s: float = Field(..., gt=0.0)
    iterations_per_window_mean: float = Field(..., gt=0.0)
    time_dir_count: int = Field(..., ge=0, description="Time directories after the run (F4)")
    du_bytes: int = Field(..., ge=0, description="du of the case dir after the run (F4)")
    concurrent_with: tuple[str, ...] = Field(
        default=(),
        description="Run ids that were executing on the same box while this one ran",
    )

    @property
    def seconds_per_window(self) -> float | None:
        """The measured rate — ``None`` unless the run completed and exited cleanly."""
        if self.windows_completed < self.windows_requested:
            return None
        if self.stopped_by != "all-exited":
            return None
        return self.wall_clock_s / self.windows_completed


class N3Confirmation(BaseModel):
    """One coupled, contended confirmation (ADR-040 N3) — the only source of a B2 rate.

    Everything here except ``post_ramp_windows_measured`` and its wall clock exists in
    :class:`I4Calibration` too. What makes this a different model rather than three more
    optional fields on that one is the RATE: ``I4Calibration.seconds_per_window`` averages
    the whole run, and for a run that spends two thirds of itself inside the ramp that is
    not the campaign's rate. Two models with two rates is honest; one model with a rate
    that means different things depending on which fields are set is the silent-wrong-
    number shape this stage keeps finding.

    ``post_ramp_quarter_cycles`` is DERIVED, never supplied: a record that states its own
    phase coverage can state it wrongly.
    """

    model_config = _STRICT

    arm: str = Field(..., min_length=1)
    rung: str = Field(..., min_length=1)
    dt: float = Field(..., gt=0.0)
    period_s: float = Field(..., gt=0.0)
    numerics_label: str = Field(..., min_length=1)
    mpi_ranks: int = Field(..., ge=1)
    windows_requested: int = Field(..., ge=1)
    windows_completed: int = Field(..., ge=0)
    stopped_by: str = Field(..., min_length=1)
    ramp_windows: int = Field(
        ...,
        ge=1,
        description="Windows the (1-cos) ramp spans; the first post-ramp window is the next",
    )
    post_ramp_windows_measured: int = Field(
        ...,
        ge=0,
        description="Post-ramp windows the wall clock below was measured over",
    )
    post_ramp_wall_clock_s: float = Field(
        ...,
        ge=0.0,
        description="Wall clock over EXACTLY those windows, from the fluid log's ClockTime",
    )
    max_courant_post_ramp: float | None = Field(
        default=None,
        ge=0.0,
        description="Feeds ADR-040 W5's conditional dt re-probe; None if never measured",
    )
    time_dir_count: int = Field(..., ge=0, description="Rank-AWARE: processor*/<time> too")
    du_bytes: int = Field(..., ge=0)
    concurrent_with: tuple[str, ...] = Field(default=())

    @model_validator(mode="after")
    def _the_measured_span_is_whole_quarter_cycles(self) -> N3Confirmation:
        """The span the rate is read over must be whole quarter-cycles of plunge.

        A rate averaged over 1.3 quarter-cycles over-weights whichever part of the stroke
        the extra 0.3 landed in. Whole quarter-cycles is the coarsest slicing for which
        that cannot happen, and ADR-040 W3 makes it the fallback when a run stops at its
        ceiling mid-stroke.
        """
        if self.post_ramp_windows_measured == 0:
            return self
        quarter_s = self.period_s / 4.0
        spans = self.post_ramp_windows_measured * self.dt / quarter_s
        if abs(spans - round(spans)) > 0.5 * self.dt / quarter_s:
            raise ValueError(
                f"post_ramp_windows_measured={self.post_ramp_windows_measured} spans "
                f"{spans:.4f} quarter-cycles, not a whole number of them - a rate read "
                "over a fractional quarter-cycle is phase-weighted (ADR-040 W3)"
            )
        return self

    @property
    def post_ramp_quarter_cycles(self) -> int:
        """Derived, so a record cannot overstate its own phase coverage."""
        if self.post_ramp_windows_measured == 0:
            return 0
        return round(self.post_ramp_windows_measured * self.dt / (self.period_s / 4.0))

    @property
    def post_ramp_seconds_per_window(self) -> float | None:
        """The ONE rate B2 may be sized from — ``None`` when the record cannot supply it.

        A ceiling stop is admissible here and is not in :class:`I4Calibration` (ADR-040
        W3): the point of this run is to measure a rate, and it is allowed to be stopped
        once it has. ``participant-died`` is not admissible at any length -- an
        infrastructure death carries no honest wall clock -- and neither is a run that
        never cleared the ramp, whatever it stopped for.
        """
        if self.stopped_by not in ("all-exited", "ceiling"):
            return None
        if self.windows_completed <= self.ramp_windows:
            return None
        if self.post_ramp_quarter_cycles < 1 or self.post_ramp_wall_clock_s <= 0.0:
            return None
        return self.post_ramp_wall_clock_s / self.post_ramp_windows_measured


class SizedCampaign(BaseModel):
    """B2's numbers, derived. ``time_window_size``/``max_time`` fill the sentinels."""

    model_config = _STRICT

    rung: str
    time_window_size: float = Field(..., gt=0.0)
    max_time: float = Field(..., gt=0.0)
    n_windows: int = Field(..., ge=1)
    settled_cycles: int = Field(..., ge=1)
    discard_s: float = Field(..., ge=0.0)
    period_s: float = Field(..., gt=0.0)
    projected_wall_s_by_arm: dict[str, float]
    projected_du_bytes_by_arm: dict[str, int]
    ceiling_s: int = Field(..., ge=1)


def _require_complete(record: I7Probe | I4Calibration, kind: str) -> None:
    if record.windows_completed < record.windows_requested:
        raise SizingError(
            f"{kind} for arm={record.arm!r} rung={record.rung!r} completed "
            f"{record.windows_completed}/{record.windows_requested} windows - no rate "
            "and no Courant maximum may be read from a transient"
        )
    if record.stopped_by != "all-exited":
        raise SizingError(
            f"{kind} for arm={record.arm!r} rung={record.rung!r} ended "
            f"stopped_by={record.stopped_by!r}, not 'all-exited' - a run that was killed "
            "or died is not a measurement of the quantity this rule needs"
        )


def suggest_next_dt(probe: I7Probe, *, courant_bound: float = 1.0, headroom: float = 0.8) -> float:
    """A smaller candidate dt after a failed probe — a SUGGESTION, never a sizing.

    Applies the linear-in-dt Courant assumption (valid only for a dt-independent
    velocity field, which is why the result must be re-probed, ADR-039 I7), then rounds
    DOWN to one significant digit so the candidate is a clean decimal that survives the
    CalculiX field-width round trip.
    """
    if probe.max_courant_post_ramp <= courant_bound:
        raise SizingError(
            "suggest_next_dt called on a passing probe - the campaign dt is that "
            "probe's dt verbatim, not a rescaling of it"
        )
    target = probe.dt * headroom * courant_bound / probe.max_courant_post_ramp
    exponent = math.floor(math.log10(target))
    mantissa = math.floor(target / 10.0**exponent)
    candidate = mantissa * 10.0**exponent
    if not _round_trips(candidate):  # pragma: no cover - one-digit decimals round-trip
        raise SizingError(f"suggested dt {candidate!r} does not round-trip")
    return candidate


def size_gated_campaign(
    *,
    probes: Sequence[I7Probe],
    calibrations: Sequence[I4Calibration],
    rung: str = "mid",
    fine_rung: str = "fine",
    arms: tuple[str, ...] = ("flexible", "rigid"),
    settled_cycles: int = 20,
    discard_s: float,
    period_s: float,
    ceiling_s: int = 14 * 24 * 3600,
    courant_bound: float = 1.0,
) -> SizedCampaign:
    """Derive B2's numbers from the pre-flight record. Raises loud, never adjusts."""
    for probe in probes:
        _require_complete(probe, "I7 probe")
    for calibration in calibrations:
        _require_complete(calibration, "I4 calibration")

    dts = {probe.dt for probe in probes}
    if len(dts) != 1:
        raise SizingError(
            f"the probes disagree on dt ({sorted(dts)}) - the rule sizes ONE candidate; "
            "re-probe at a single dt"
        )
    (dt,) = dts
    if not _round_trips(dt):
        raise SizingError(
            f"dt={dt!r} does not survive the {_ROUND_TRIP_FORMAT} round trip the "
            "CalculiX field width requires (handoff 6.17)"
        )

    required = [(arm, rung) for arm in arms] + [(arms[0], fine_rung)]
    for want_arm, want_rung in required:
        matches = [p for p in probes if p.arm == want_arm and p.rung == want_rung]
        if not matches:
            raise SizingError(
                f"no I7 probe for arm={want_arm!r} rung={want_rung!r} - dt is fixed "
                "across rungs (ADR-039 B2), so the fine rung's Courant bound must be "
                "measured, not assumed from the refinement ratio"
            )
        for probe in matches:
            if probe.max_courant_post_ramp > courant_bound:
                raise SizingError(
                    f"I7 FAILED for arm={probe.arm!r} rung={probe.rung!r}: measured max "
                    f"Courant {probe.max_courant_post_ramp} > {courant_bound}. The "
                    "pre-flight never adjusts; re-probe at a smaller dt (see "
                    "suggest_next_dt) and record the failure"
                )

    n_windows = math.ceil((discard_s + settled_cycles * period_s) / dt)
    for _ in range(1000):
        if _round_trips(n_windows * dt):
            break
        n_windows += 1
    else:  # pragma: no cover - decimal dt values terminate immediately
        raise SizingError(f"no window count near the target makes n*dt round-trip at dt={dt!r}")
    max_time = n_windows * dt

    projected_wall: dict[str, float] = {}
    projected_du: dict[str, int] = {}
    for arm in arms:
        candidates = [
            c
            for c in calibrations
            if c.arm == arm and c.rung == rung and c.dt == dt and c.seconds_per_window
        ]
        if not candidates:
            raise SizingError(
                f"no completed I4 calibration for arm={arm!r} at the gated rung "
                f"{rung!r} and dt={dt!r}"
            )
        contended = [c for c in candidates if c.concurrent_with]
        if not contended:
            raise SizingError(
                f"the gated-rung calibration for arm={arm!r} was measured alone - B2's "
                "projection must use the wave-1 contention shape (both arms running "
                "concurrently), or it understates the wave"
            )
        rate = max(c.seconds_per_window for c in contended if c.seconds_per_window)
        projected_wall[arm] = n_windows * rate
        worst = max(contended, key=lambda c: c.du_bytes)
        projected_du[arm] = math.ceil(worst.du_bytes / worst.windows_completed * n_windows)

    over = {arm: wall for arm, wall in projected_wall.items() if wall > ceiling_s}
    if over:
        raise SizingError(
            "the sized campaign does not fit the per-wave ceiling: "
            + ", ".join(f"{arm} projects {wall:.0f}s > {ceiling_s}s" for arm, wall in over.items())
            + " - a budget NO-GO is a recorded outcome (ADR-039 B4), not a band change"
        )

    return SizedCampaign(
        rung=rung,
        time_window_size=dt,
        max_time=max_time,
        n_windows=n_windows,
        settled_cycles=settled_cycles,
        discard_s=discard_s,
        period_s=period_s,
        projected_wall_s_by_arm=projected_wall,
        projected_du_bytes_by_arm=projected_du,
        ceiling_s=ceiling_s,
    )


def size_gated_campaign_040(
    *,
    probes: Sequence[I7Probe],
    confirmations: Sequence[N3Confirmation],
    numerics_label: str,
    mpi_ranks: int,
    rung: str = "mid",
    fine_rung: str = "fine",
    arms: tuple[str, ...] = ("flexible", "rigid"),
    settled_cycles: int = 20,
    discard_s: float,
    period_s: float,
    ceiling_s: int,
    courant_bound: float = 1.0,
) -> SizedCampaign:
    """ADR-040 B2's numbers, derived from the N3 record. Raises loud, never adjusts.

    Differs from :func:`size_gated_campaign` in exactly four ways, each pre-registered:

    * the rate is :attr:`N3Confirmation.post_ramp_seconds_per_window`, never a whole-run
      average -- the reason this function exists;
    * the confirmation must carry the pre-registered ``numerics_label`` and ``mpi_ranks``,
      because a rate measured on another stack or another rank count is another campaign's
      rate (ADR-040 L5);
    * ``ceiling_s`` is REQUIRED and has no default. ADR-039's default was 14 days, which
      ADR-040 B3 records as measured out of reach at any settled-cycle count; a default
      here would be a ceiling nobody chose;
    * a ceiling-stopped confirmation is admissible if it cleared the ramp (ADR-040 W3).

    Everything else -- the dt round-trip bar, the fine-rung Courant requirement, the
    contention requirement, the window-count bump, the disk projection, and the refusal
    when the projection exceeds the ceiling -- is ADR-039's rule unchanged, because none of
    it was what made the campaign infeasible.
    """
    for probe in probes:
        _require_complete(probe, "I7 probe")

    dts = {probe.dt for probe in probes}
    if len(dts) != 1:
        raise SizingError(
            f"the probes disagree on dt ({sorted(dts)}) - the rule sizes ONE candidate; "
            "re-probe at a single dt"
        )
    (dt,) = dts
    if not _round_trips(dt):
        raise SizingError(
            f"dt={dt!r} does not survive the {_ROUND_TRIP_FORMAT} round trip the "
            "CalculiX field width requires (handoff 6.17)"
        )

    required = [(arm, rung) for arm in arms] + [(arms[0], fine_rung)]
    for want_arm, want_rung in required:
        matches = [p for p in probes if p.arm == want_arm and p.rung == want_rung]
        if not matches:
            raise SizingError(
                f"no I7 probe for arm={want_arm!r} rung={want_rung!r} - dt is fixed "
                "across rungs (ADR-039 B2, carried over by ADR-040 U3), so the fine "
                "rung's Courant bound must be measured, not assumed from the ratio"
            )
        for probe in matches:
            if probe.max_courant_post_ramp > courant_bound:
                raise SizingError(
                    f"I7 FAILED for arm={probe.arm!r} rung={probe.rung!r}: measured max "
                    f"Courant {probe.max_courant_post_ramp} > {courant_bound}. The "
                    "pre-flight never adjusts; re-probe at a smaller dt (see "
                    "suggest_next_dt) and record the failure"
                )

    n_windows = math.ceil((discard_s + settled_cycles * period_s) / dt)
    for _ in range(1000):
        if _round_trips(n_windows * dt):
            break
        n_windows += 1
    else:  # pragma: no cover - decimal dt values terminate immediately
        raise SizingError(f"no window count near the target makes n*dt round-trip at dt={dt!r}")
    max_time = n_windows * dt

    projected_wall: dict[str, float] = {}
    projected_du: dict[str, int] = {}
    for arm in arms:
        for_arm = [c for c in confirmations if c.arm == arm and c.rung == rung and c.dt == dt]
        if not for_arm:
            raise SizingError(
                f"no N3 confirmation for arm={arm!r} at the gated rung {rung!r} and "
                f"dt={dt!r} - only a coupled confirmation may size (ADR-040 N3)"
            )
        wrong_stack = [
            c for c in for_arm if c.numerics_label != numerics_label or c.mpi_ranks != mpi_ranks
        ]
        if wrong_stack and len(wrong_stack) == len(for_arm):
            got = sorted({(c.numerics_label, c.mpi_ranks) for c in wrong_stack})
            raise SizingError(
                f"the N3 confirmations for arm={arm!r} were measured at {got}, not at the "
                f"pre-registered ({numerics_label!r}, {mpi_ranks} ranks) - a rate measured "
                "on another stack or another rank count is another campaign's rate"
            )
        on_stack = [c for c in for_arm if c not in wrong_stack]
        contended = [c for c in on_stack if c.concurrent_with]
        if not contended:
            raise SizingError(
                f"the N3 confirmation for arm={arm!r} was measured alone - B2's projection "
                "must use the wave-1 contention shape (both arms running concurrently), "
                "or it understates the wave"
            )
        rates = [c.post_ramp_seconds_per_window for c in contended]
        usable = [(c, r) for c, r in zip(contended, rates, strict=True) if r is not None]
        if not usable:
            raise SizingError(
                f"no N3 confirmation for arm={arm!r} yields a POST-RAMP rate: "
                + "; ".join(
                    f"stopped_by={c.stopped_by!r}, {c.windows_completed} windows against a "
                    f"{c.ramp_windows}-window ramp, {c.post_ramp_quarter_cycles} post-ramp "
                    "quarter-cycles"
                    for c in contended
                )
                + " - a ramp-phase rate may not size a campaign (ADR-040 N3/W3)"
            )
        rate = max(r for _, r in usable)
        projected_wall[arm] = n_windows * rate
        worst = max((c for c, _ in usable), key=lambda c: c.du_bytes)
        projected_du[arm] = math.ceil(worst.du_bytes / worst.windows_completed * n_windows)

    over = {arm: wall for arm, wall in projected_wall.items() if wall > ceiling_s}
    if over:
        raise SizingError(
            "the sized campaign does not fit the per-wave ceiling: "
            + ", ".join(f"{arm} projects {wall:.0f}s > {ceiling_s}s" for arm, wall in over.items())
            + " - a budget NO-GO is a recorded outcome (ADR-039 B4, carried over by "
            "ADR-040 U11), not a band change"
        )

    return SizedCampaign(
        rung=rung,
        time_window_size=dt,
        max_time=max_time,
        n_windows=n_windows,
        settled_cycles=settled_cycles,
        discard_s=discard_s,
        period_s=period_s,
        projected_wall_s_by_arm=projected_wall,
        projected_du_bytes_by_arm=projected_du,
        ceiling_s=ceiling_s,
    )
