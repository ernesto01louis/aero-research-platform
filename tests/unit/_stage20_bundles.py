"""Collected-bundle builders shared by the mapping and the `--size-040` tests.

Shared rather than duplicated for the reason `tests/stage_20/_hg2007.py` gives about the
authored case: the blocks have to agree with each other (an `i7` and an `i4` from one run
share arm/rung/dt, an `n3` states quantities the model re-derives), and a second
hand-maintained copy of that agreement would drift. The first symptom of the drift would
be a test asserting the cross-checks work while building a bundle that never exercises them.

The numbers are the campaign's own, and match `tests/unit/test_adr040_sizing_function.py`:
dt 2e-5, T = 1/f, a (1-cos) ramp of one full cycle = 50725 windows, quarter-cycles of 12681.
"""

from __future__ import annotations

from typing import Any

DT = 2.0e-5
PERIOD = 1.0144927536231882
RAMP = 50725
QUARTER = 12681
MEASURED = 2 * QUARTER
WINDOWS = 76090
LABEL = "adr040-candidate"
RANKS = 4

#: The rate the fixtures size from. Chosen exact so `post_ramp_wall_clock_s / measured`
#: is representable and the mapper's bitwise cross-check has something real to compare.
SECONDS_PER_WINDOW = 1.5


def i7_block(**over: Any) -> dict[str, Any]:
    """The `i7` half: the Courant maximum and whether it was measured past the ramp."""
    return {
        "arm": "flexible",
        "rung": "mid",
        "dt": DT,
        "courant_lines": 400_000,
        "max_courant_anywhere": 0.61,
        "max_courant_post_ramp": 0.55,
        "post_ramp_window_starts_at": PERIOD,
        "covers_post_ramp_window": True,
        "passed": True,
    } | over


def i4_block(**over: Any) -> dict[str, Any]:
    """The `i4` half: the window counts, the stop reason and the disk footprint."""
    return {
        "arm": "flexible",
        "rung": "mid",
        "dt": DT,
        "windows_requested": WINDOWS,
        "windows_completed": WINDOWS,
        "stopped_by": "all-exited",
        "wall_clock_s": 312_000.0,
        "iterations_per_window_mean": 5.367,
        "du_bytes": 342_749_623,
        "time_dir_count": 497,
        "concurrent_with": ["hg2007_rigid_foil-x"],
        "case_subdir": "hg2007_flexible_foil-x",
        "coupling": {
            "Fluid": {"n_windows": WINDOWS, "mean_iterations": 5.367, "n_nonconverged": 0}
        },
    } | over


def n3_block(**over: Any) -> dict[str, Any]:
    """The `n3` block as `_n3_block`'s rate-bearing branch writes it — all 22 keys."""
    wall = MEASURED * SECONDS_PER_WINDOW
    return {
        "arm": "flexible",
        "rung": "mid",
        "dt": DT,
        "period_s": PERIOD,
        "numerics_label": LABEL,
        "mpi_ranks": RANKS,
        "windows_requested": WINDOWS,
        "windows_completed": WINDOWS,
        "stopped_by": "all-exited",
        "ramp_windows": RAMP,
        "quarter_cycle_windows": QUARTER,
        "post_ramp_windows_completed": WINDOWS - RAMP,
        "post_ramp_windows_measured": MEASURED,
        "post_ramp_quarter_cycles": 2,
        "post_ramp_wall_clock_s": wall,
        "post_ramp_step_solves_measured": 124_000,
        "post_ramp_seconds_per_window": wall / MEASURED,
        "max_courant_post_ramp": 0.55,
        "time_dir_count": 497,
        "du_bytes": 342_749_623,
        "concurrent_with": ["hg2007_rigid_foil-x"],
        "rate_source": "fluid log ClockTime (NOT ExecutionTime: rank 0's CPU under mpirun)",
    } | over


def n3_block_inside_the_ramp(**over: Any) -> dict[str, Any]:
    """The other branch: no whole post-ramp quarter-cycle, so no rate and a reason instead."""
    block = n3_block()
    for key in ("post_ramp_step_solves_measured", "post_ramp_seconds_per_window"):
        block.pop(key)
    return (
        block
        | {
            "windows_completed": 1400,
            "post_ramp_windows_completed": 0,
            "post_ramp_windows_measured": 0,
            "post_ramp_quarter_cycles": 0,
            "post_ramp_wall_clock_s": 0.0,
            "post_ramp_seconds_per_window": None,
            "why_no_rate": (
                f"0 post-ramp window(s) is less than one quarter-cycle ({QUARTER}); a rate "
                "over a fractional quarter-cycle is phase-weighted and ADR-040 W3 refuses it"
            ),
        }
        | over
    )


def bundle(
    *, arm: str = "flexible", rung: str = "mid", n3: bool = True, **over: Any
) -> dict[str, Any]:
    """One `--collect-probe` bundle: `i7` + `i4`, and `n3` when the run reached the state."""
    built: dict[str, Any] = {
        "kind": "preflight-probe",
        "adr": "ADR-040",
        "gated": False,
        "i7": i7_block(arm=arm, rung=rung),
        "i4": i4_block(arm=arm, rung=rung, concurrent_with=[f"hg2007_other_{arm}-x"]),
    }
    if n3:
        built["n3"] = n3_block(arm=arm, rung=rung, concurrent_with=[f"hg2007_other_{arm}-x"])
    return built | over


def admissible_record() -> list[dict[str, Any]]:
    """The three bundles `size_gated_campaign_040` needs before it will size anything.

    Both arms at the gated rung with a coupled confirmation, plus the FINE-rung I7 probe
    the rule requires on `arms[0]` — dt is fixed across rungs (ADR-039 B2, carried over by
    ADR-040 U3), so the fine rung's Courant bound must be measured rather than scaled.
    That third bundle does not exist yet for the real campaign, and cannot until N3 is done.
    """
    return [
        bundle(arm="flexible", rung="mid"),
        bundle(arm="rigid", rung="mid"),
        bundle(arm="flexible", rung="fine", n3=False),
    ]
