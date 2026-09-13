"""The bridge between what `--collect-probe` writes and what the sizing rule consumes.

`_n3_block` emits 22 keys; `N3Confirmation` has 16 and is ``extra='forbid'``. Until this
mapping existed there was no code joining them, so the B2 fill would have been assembled by
hand from a JSON file -- at exactly the moment hand-assembly is least acceptable, because
the numbers being assembled ARE the campaign's length and disk footprint.

Reconciling two shapes is also where a silent wrong number gets in, so the mapping does
three things this file pins:

* it DROPS the two quantities the model derives, and then checks the model's derivation
  against the block's stated value. Both sides run identical arithmetic on identical
  inputs, so they agree bitwise or the driver's projection and the rule's have drifted;
* it names the ``-1`` sentinel `--collect-probe` writes for an unread remote ``du`` /
  ``find``, rather than letting it surface as a pydantic complaint about a ``ge=0`` bound;
* it refuses an I7 probe that never reached the post-ramp window -- the state BOTH
  committed I4 bundles are in -- instead of reading a Courant maximum measured where the
  mesh barely moves.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import pytest
from aero.vv.fsi.hg2007_sizing import (
    I7Probe,
    N3Confirmation,
    SizingError,
    i7_probe_from_bundle,
    n3_confirmation_from_bundle,
)

pytestmark = pytest.mark.stage_20

_REPO_ROOT = Path(__file__).resolve().parents[2]

#: The campaign's own numbers, so the fixture exercises the arithmetic that will actually
#: run: dt 2e-5, T = 1/f, a (1-cos) ramp of one full cycle, quarter-cycles of 12681.
_DT = 2.0e-5
_PERIOD = 1.0144927536231882
_RAMP = 50725
_QUARTER = 12681
_MEASURED = 2 * _QUARTER


def _n3(**over: Any) -> dict[str, Any]:
    """A block shaped exactly as ``_n3_block``'s rate-bearing branch writes it."""
    wall = _MEASURED * 1.5
    block: dict[str, Any] = {
        "arm": "flexible",
        "rung": "mid",
        "dt": _DT,
        "period_s": _PERIOD,
        "numerics_label": "adr040-candidate",
        "mpi_ranks": 4,
        "windows_requested": 76090,
        "windows_completed": 76090,
        "stopped_by": "all-exited",
        "ramp_windows": _RAMP,
        "quarter_cycle_windows": _QUARTER,
        "post_ramp_windows_completed": 25365,
        "post_ramp_windows_measured": _MEASURED,
        "post_ramp_quarter_cycles": 2,
        "post_ramp_wall_clock_s": wall,
        "post_ramp_step_solves_measured": 124_000,
        "post_ramp_seconds_per_window": wall / _MEASURED,
        "max_courant_post_ramp": 0.55,
        "time_dir_count": 497,
        "du_bytes": 342_749_623,
        "concurrent_with": ["hg2007_rigid_foil-20260812-230109"],
        "rate_source": "fluid log ClockTime (NOT ExecutionTime: rank 0's CPU under mpirun)",
    }
    return block | over


def _n3_inside_the_ramp(**over: Any) -> dict[str, Any]:
    """The other branch: a run that has not completed one whole post-ramp quarter-cycle."""
    block = _n3()
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
                f"0 post-ramp window(s) is less than one quarter-cycle ({_QUARTER}); a rate "
                "over a fractional quarter-cycle is phase-weighted and ADR-040 W3 refuses it"
            ),
        }
        | over
    )


def _i7(**over: Any) -> dict[str, Any]:
    return {
        "arm": "flexible",
        "rung": "mid",
        "dt": _DT,
        "courant_lines": 400_000,
        "max_courant_anywhere": 0.61,
        "max_courant_post_ramp": 0.55,
        "post_ramp_window_starts_at": _PERIOD,
        "covers_post_ramp_window": True,
        "passed": True,
    } | over


def _i4(**over: Any) -> dict[str, Any]:
    return {
        "arm": "flexible",
        "rung": "mid",
        "dt": _DT,
        "windows_requested": 76090,
        "windows_completed": 76090,
        "stopped_by": "all-exited",
        "wall_clock_s": 312_000.0,
        "iterations_per_window_mean": 5.367,
        "du_bytes": 342_749_623,
        "time_dir_count": 497,
        "concurrent_with": ["hg2007_rigid_foil-20260812-230109"],
        "case_subdir": "hg2007_flexible_foil-20260812-230102",
    } | over


def _bundle(**over: Any) -> dict[str, Any]:
    return {"i7": _i7(), "i4": _i4(), "n3": _n3()} | over


# --------------------------------------------------------------------------------------
# The mapping itself
# --------------------------------------------------------------------------------------


def test_a_rate_bearing_block_becomes_a_confirmation_that_carries_the_rate() -> None:
    got = n3_confirmation_from_bundle(_bundle())
    assert isinstance(got, N3Confirmation)
    assert got.post_ramp_quarter_cycles == 2
    assert got.post_ramp_seconds_per_window == 1.5
    assert got.concurrent_with == ("hg2007_rigid_foil-20260812-230109",)


def test_a_ramp_phase_block_maps_and_reports_no_rate() -> None:
    """The state N3 is in today. Mapping it must SUCCEED and yield no rate.

    The refusal belongs to the rule, not to the mapping: `size_gated_campaign_040` says
    "a ramp-phase rate may not size a campaign (ADR-040 N3/W3)", which is the sentence the
    operator needs. A mapping that refused here would replace it with a shape complaint.
    """
    got = n3_confirmation_from_bundle(_bundle(n3=_n3_inside_the_ramp()))
    assert got.post_ramp_quarter_cycles == 0
    assert got.post_ramp_seconds_per_window is None


def test_the_blocks_extra_keys_would_have_been_refused_by_the_model() -> None:
    """The mapping is load-bearing, not ceremony: the model rejects the block as written."""
    with pytest.raises(Exception):  # noqa: B017 - pydantic ValidationError, extra='forbid'
        N3Confirmation(**_n3())
    assert set(_n3()) - set(N3Confirmation.model_fields) == {
        "quarter_cycle_windows",
        "post_ramp_windows_completed",
        "post_ramp_quarter_cycles",
        "post_ramp_seconds_per_window",
        "post_ramp_step_solves_measured",
        "rate_source",
    }


@pytest.mark.parametrize("key", sorted(N3Confirmation.model_fields))
def test_a_missing_field_is_named_rather_than_raised_on(key: str) -> None:
    block = _n3()
    if not N3Confirmation.model_fields[key].is_required():
        pytest.skip(f"{key} is optional on the model")
    block.pop(key)
    with pytest.raises(SizingError, match=f"missing.*{key}"):
        n3_confirmation_from_bundle(_bundle(n3=block))


# --------------------------------------------------------------------------------------
# The two checks that stop a silent wrong number
# --------------------------------------------------------------------------------------


def test_a_stated_rate_that_disagrees_with_the_derived_one_is_refused() -> None:
    """A drift between the driver's arithmetic and the rule's is a wrong campaign length."""
    block = _n3(post_ramp_seconds_per_window=1.4)
    with pytest.raises(SizingError, match="drifted apart"):
        n3_confirmation_from_bundle(_bundle(n3=block))


def test_a_stated_phase_coverage_that_disagrees_with_the_derived_one_is_refused() -> None:
    block = _n3(post_ramp_quarter_cycles=3)
    with pytest.raises(SizingError, match="drifted apart"):
        n3_confirmation_from_bundle(_bundle(n3=block))


@pytest.mark.parametrize("key", ["du_bytes", "time_dir_count"])
def test_the_unread_sentinel_is_named_for_what_it_is(key: str) -> None:
    """-1 means the remote read failed, not "a bound was violated"."""
    with pytest.raises(SizingError, match="remote read failed"):
        n3_confirmation_from_bundle(_bundle(n3=_n3(**{key: -1})))


# --------------------------------------------------------------------------------------
# The I7 side, which is split across two blocks
# --------------------------------------------------------------------------------------


def test_an_i7_probe_is_assembled_from_both_blocks() -> None:
    """`i7` has the Courant maximum; `i4` has the window counts and the stop reason."""
    got = i7_probe_from_bundle(_bundle())
    assert isinstance(got, I7Probe)
    assert (got.arm, got.rung, got.dt) == ("flexible", "mid", _DT)
    assert got.max_courant_post_ramp == 0.55
    assert (got.windows_completed, got.windows_requested) == (76090, 76090)
    assert got.stopped_by == "all-exited"


def test_a_probe_that_never_left_the_ramp_has_no_courant_bound_to_give() -> None:
    bundle = _bundle(i7=_i7(max_courant_post_ramp=None, covers_post_ramp_window=False, passed=None))
    with pytest.raises(SizingError, match="never reached the post-ramp window"):
        i7_probe_from_bundle(bundle)


@pytest.mark.parametrize("key", ["arm", "rung", "dt"])
def test_two_blocks_from_two_runs_are_refused(key: str) -> None:
    """They are written from one run; a disagreement means the bundle was stitched."""
    bundle = _bundle(
        i4=_i4(**{key: "coarse" if key == "rung" else 3.5e-4 if key == "dt" else "rigid"})
    )
    with pytest.raises(SizingError, match="disagree on"):
        i7_probe_from_bundle(bundle)


@pytest.mark.parametrize("block", ["i7", "i4", "n3"])
def test_an_absent_block_says_which_one(block: str) -> None:
    bundle = {k: v for k, v in _bundle().items() if k != block}
    fn = n3_confirmation_from_bundle if block == "n3" else i7_probe_from_bundle
    with pytest.raises(SizingError, match=f"no {block!r} block"):
        fn(bundle)


# --------------------------------------------------------------------------------------
# Against bytes this repo did not write for the test
# --------------------------------------------------------------------------------------


def test_the_committed_i4_bundles_refuse_for_the_reason_they_should() -> None:
    """Both surviving pre-flight bundles are inside the ramp, and say so (handoff §6.39).

    This is the real-record half of the two guards above: the fixtures assert the refusal
    fires, and this asserts the state that fires it is the state the campaign's own
    committed records are actually in.
    """
    record = json.loads((_REPO_ROOT / "data/vv/stage20_i4_calibration.json").read_text())
    for arm, bundle in record["collection_bundles"].items():
        assert bundle["i7"]["covers_post_ramp_window"] is False, arm
        with pytest.raises(SizingError, match="never reached the post-ramp window"):
            i7_probe_from_bundle(bundle)
        with pytest.raises(SizingError, match="no 'n3' block"):
            n3_confirmation_from_bundle(bundle)


# --------------------------------------------------------------------------------------
# Against the EMITTER, not against a second copy of its shape
# --------------------------------------------------------------------------------------

#: Everything `_n3_block` writes that `N3Confirmation` does not take. Two of them are the
#: model's own properties, dropped and then cross-checked; the rest are for a human reader.
#: `why_no_rate` and `post_ramp_step_solves_measured` are mutually exclusive branches.
_DESCRIPTIVE = {
    "quarter_cycle_windows",
    "post_ramp_windows_completed",
    "post_ramp_quarter_cycles",
    "post_ramp_seconds_per_window",
    "post_ramp_step_solves_measured",
    "why_no_rate",
    "rate_source",
}

#: A short fluid log at a coarse dt, so a whole ramp plus four post-ramp quarter-cycles fit
#: in ten steps. The shape is pimpleFoam's: a Courant line, then `Time =`, then the solves,
#: then the `ExecutionTime`/`ClockTime` pair that CLOSES the step. The first Courant line
#: precedes the first `Time =`, exactly as OpenFOAM prints the t=0 initialisation state.
_LOG_DT = 0.1
_LOG_PERIOD = 0.4
_LOG_STEPS = 10


def _fluid_log(path: Path) -> Path:
    lines: list[str] = []
    for step in range(1, _LOG_STEPS + 1):
        lines += [
            "Courant Number mean: 0.000243155834688 max: 0.114210411895",
            f"Time = {step * _LOG_DT:g}",
            "",
            "smoothSolver:  Solving for Ux, Initial residual = 4.8e-06, "
            "Final residual = 3.1e-11, No Iterations 1",
            f"ExecutionTime = {2.0 * step} s  ClockTime = {3 * step} s",
            "",
        ]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def _driver():  # type: ignore[no-untyped-def]
    sys.path.insert(0, str(_REPO_ROOT / "scripts"))
    import stage20_hg2007_flexible_foil  # type: ignore[import-not-found]

    return stage20_hg2007_flexible_foil


def _emit(tmp_path: Path, *, windows_completed: int) -> dict[str, Any]:
    submission = {
        "arm": "flexible",
        "rung": "mid",
        "spec_knobs": {
            "time_window_size": _LOG_DT,
            "numerics_label": "adr040-candidate",
            "mpi_ranks": 4,
        },
    }
    return dict(
        _driver()._n3_block(
            _fluid_log(tmp_path / "Fluid.log"),
            submission=submission,
            status_stopped_by="all-exited",
            windows_completed=windows_completed,
            windows_requested=_LOG_STEPS,
            period_s=_LOG_PERIOD,
            max_courant_post_ramp=0.55,
            du_bytes=1_024,
            time_dir_count=9,
            concurrent_with=["hg2007_rigid_foil-x"],
        )
    )


@pytest.mark.parametrize("windows_completed", [3, 8], ids=["inside-the-ramp", "past-the-ramp"])
def test_the_emitted_block_carries_exactly_the_keys_this_mapping_expects(
    tmp_path: Path, windows_completed: int
) -> None:
    """The contract, checked against the function that actually writes it.

    The fixtures above are hand-written, so on their own they pin only what this file
    BELIEVES `_n3_block` emits. Driving the real emitter over a real (if small) fluid log
    is what makes them a contract: if a field is added to the block or to the model and the
    other side is not updated, this fails by name rather than at the B2 fill.

    Both branches are driven, because they do not emit the same key set.
    """
    block = _emit(tmp_path, windows_completed=windows_completed)
    assert set(N3Confirmation.model_fields) <= set(block)
    assert set(block) - set(N3Confirmation.model_fields) <= _DESCRIPTIVE


def test_a_block_straight_from_the_emitter_maps_and_carries_its_rate(tmp_path: Path) -> None:
    """Past the ramp: four whole post-ramp quarter-cycles, and a rate both sides agree on."""
    block = _emit(tmp_path, windows_completed=8)
    assert block["ramp_windows"] == 4
    assert block["quarter_cycle_windows"] == 1
    assert block["post_ramp_windows_measured"] == 4

    got = n3_confirmation_from_bundle({"n3": block})
    assert got.post_ramp_quarter_cycles == 4
    # The mapper already cross-checks these two against the block; asserting the rate is a
    # real number here is what says the cross-check had something to compare.
    assert got.post_ramp_seconds_per_window == block["post_ramp_seconds_per_window"]
    assert got.post_ramp_seconds_per_window is not None


def test_a_block_from_inside_the_ramp_maps_and_carries_no_rate(tmp_path: Path) -> None:
    """The state N3 is in today, straight from the emitter rather than from a fixture."""
    block = _emit(tmp_path, windows_completed=3)
    assert block["post_ramp_windows_measured"] == 0
    assert "why_no_rate" in block

    got = n3_confirmation_from_bundle({"n3": block})
    assert got.post_ramp_quarter_cycles == 0
    assert got.post_ramp_seconds_per_window is None
