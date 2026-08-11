"""The deforming screen refutes two hypotheses, and a refutation has to stay refuted.

Session 8's N2 sweep ran on a STATIC mesh, so `cacheAgglomeration` was untestable there --
a cached agglomeration had nothing to go stale against -- and the record attributed the
campaign's 3x-harder pressure solve to "the deforming mesh" without ever varying it. This
screen varies it. Both named leads died, and the value of the record is precisely that:
a future session must not re-open either one without new evidence, and must not read N2's
attribution as established.

The pins below are one-sided wherever the underlying number is a wall-clock ratio, because
the box is shared: what is being enforced is the DIRECTION of each finding (no reduction, no
help), never a timing to three digits.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

pytestmark = pytest.mark.stage_20

_REPO_ROOT = Path(__file__).resolve().parents[2]
_RECORD = _REPO_ROOT / "data/vv/stage20_n4_deforming_screen.json"
_N2 = _REPO_ROOT / "data/vv/stage20_n2_screening.json"


def _record() -> dict:
    return json.loads(_RECORD.read_text(encoding="utf-8"))


def test_the_record_says_it_cannot_size_anything() -> None:
    """Same standing as N2: a screen that may not size, saying so in the record itself."""
    record = _record()
    admissibility = record["admissibility"]
    assert "RANKS ONLY" in admissibility
    assert "may NOT size" in admissibility
    assert "COUPLED" in admissibility
    assert record["gated"] is False
    assert record["adr"] == "ADR-040"


def test_the_control_pair_isolates_motion_and_nothing_else() -> None:
    """`d0` and `d1` differ in ONE thing, and the record has to prove the mesh moved.

    Without this the whole screen is unfalsifiable: a "moving" case whose mesh sat still
    would refute the hypothesis for free. `cellDisplacement` iterations per step are the
    witness, and the campaign's own value is 1.00.
    """
    variants = _record()["variants"]
    assert variants["d0"]["moving_mesh"] is False
    assert variants["d1"]["moving_mesh"] is True
    assert variants["d0"]["cell_displacement_iterations_per_step"] == pytest.approx(0.0)
    assert variants["d1"]["cell_displacement_iterations_per_step"] == pytest.approx(1.0)
    assert variants["d0"]["numerics"] == variants["d1"]["numerics"]


def test_the_static_control_reproduces_the_n2_sweep() -> None:
    """`d0` is the harness check: a new harness that cannot re-derive N2 measures nothing."""
    d0 = _record()["variants"]["d0"]
    n2_control = json.loads(_N2.read_text(encoding="utf-8"))["candidates"]["s0_control"]
    assert d0["gamg_iterations_per_step"] == pytest.approx(
        n2_control["gamg_iterations_per_step"], rel=0.01
    )


def test_cache_agglomeration_is_refuted_on_a_mesh_that_moves() -> None:
    """N4 is dead: turning the cache off does not reduce the pressure solve, and costs time.

    This is the test that could only ever be run here. On N2's static screen `s10` measured
    `cacheAgglomeration no` as 8 % slower, which proves nothing either way -- a cache that
    cannot go stale should of course only cost. On a moving mesh it still does not help.
    """
    record = _record()
    assert record["n4_cache_agglomeration"]["refuted"] is True
    variants = record["variants"]
    # No reduction in the quantity the hypothesis predicted would collapse.
    assert variants["d2"]["p_iterations_per_solve"] >= variants["d1"]["p_iterations_per_solve"], (
        "cacheAgglomeration no reduced the pressure solve — N4 would need re-opening"
    )
    assert variants["d4"]["p_iterations_per_solve"] >= variants["d3"]["p_iterations_per_solve"]
    # And it is not free.
    assert variants["d2"]["seconds_per_step"] > variants["d1"]["seconds_per_step"]


def test_the_pressure_reference_level_is_refuted() -> None:
    """N5 is dead: the strongest possible form of the fix buys nothing.

    `d5` pins the WHOLE farfield to fixedValue. That is not a candidate boundary condition --
    it over-constrains the physics and reflects -- it is the upper bound on what any
    reference-level fix could be worth. It is worth about 3 percent, so the near-pure-Neumann
    conditioning is not the mechanism and the C-grid's farfield patch is not split.
    """
    record = _record()
    assert record["n5_pressure_reference"]["refuted"] is True
    variants = record["variants"]
    assert variants["d5"]["dirichlet_farfield"] is True
    assert variants["d5"]["p_iterations_per_solve"] == pytest.approx(
        variants["d1"]["p_iterations_per_solve"], rel=0.10
    )


def test_n2s_stated_attribution_is_corrected_not_carried_forward() -> None:
    """The record must say plainly that the earlier explanation was wrong.

    N2's `admissibility` says the campaign is three times harder "because the deforming mesh
    makes the pressure system about three times harder". Prescribed motion reproduces the
    campaign's cellDisplacement signature exactly and reproduces almost none of the gap.
    """
    record = _record()
    variants = record["variants"]
    motion_alone = variants["d1"]["p_solve_ratio_vs_d0_static"]
    campaign = record["campaign_reference"]["flexible"]["p_iterations_per_solve_all"]
    campaign_ratio = campaign / variants["d0"]["p_iterations_per_solve"]
    assert motion_alone < 1.5, "motion alone explained the gap after all — rewrite the record"
    assert campaign_ratio > 2.5
    assert "WRONG" in record["where_the_3x_actually_is"]


def test_the_residual_gap_is_present_from_the_first_solve() -> None:
    """It is not something the campaign accumulated, so no amount of settling explains it.

    The campaign's first five step-solves are the only like-for-like comparison against a
    20-step screen, and they already sit far above it. This is what makes the remaining
    factor coupling-specific rather than a transient.
    """
    record = _record()
    flexible = record["campaign_reference"]["flexible"]
    moving_control = record["variants"]["d1"]["p_iterations_per_solve"]
    assert flexible["p_iterations_per_solve_first_5"] > 1.8 * moving_control
    # Development over 2627 solves is the SMALLER effect of the two.
    development = (
        flexible["p_iterations_per_solve_all"] / flexible["p_iterations_per_solve_first_5"]
    )
    assert development < flexible["p_iterations_per_solve_first_5"] / moving_control


def test_the_candidate_stack_ratio_survives_the_moving_mesh() -> None:
    """What the ~2.00 s/window projection actually rests on.

    N2 measured the candidate stack at 3.73x on a static mesh and the projection was built on
    it. If that ratio collapsed once the mesh moved, the projection would be worthless. It
    does not: the moving-mesh ratio brackets it.
    """
    variants = _record()["variants"]
    against_moving = variants["d1"]["seconds_per_step"] / variants["d3"]["seconds_per_step"]
    against_static = variants["d0"]["seconds_per_step"] / variants["d3"]["seconds_per_step"]
    assert against_moving > 3.0
    assert against_static > 3.0
    assert "stands unchanged" in _record()["verdict"]


def test_the_refutation_is_a_fortiori_not_marginal() -> None:
    """The screen deformed the mesh FAR more than the campaign ever did, and still missed.

    This is what makes the refutation safe rather than a close call. Under ADR-024's (1-cos)
    ramp the campaign's foil had moved a fraction of one wall cell by its 0.01 s end time;
    the screen has no ramp and starts at maximum plunge velocity. If the screen had moved
    LESS, "the deforming mesh" would still be alive and the record would be overclaiming.
    """
    record = _record()
    campaign_m = record["campaign_reference"]["flexible"]["plunge_reached_m"]
    assert record["campaign_reference"]["flexible"]["plunge_reached_wall_cells"] < 0.05, (
        "the campaign's mesh deformed more than expected — re-argue the attribution"
    )
    assert record["screen_plunge_reached_m"] > 10.0 * campaign_m
    assert "a fortiori" in record["where_the_3x_actually_is"]


def test_the_mechanism_is_named_and_explicitly_not_acted_on() -> None:
    """A mechanism that lands in ADR-039 C1 territory must be reported, never quietly taken.

    The campaign's cost is the screen's STARTUP number sustained forever: every coupling
    iteration restores the window-start checkpoint, so the pressure solve is permanently
    cold-started where a marching solve warms up within five steps. The lever that implies
    is the coupling scheme, which ADR-040 carries over frozen.
    """
    record = _record()
    mechanism = record["mechanism"]
    assert "checkpoint" in mechanism
    assert "REPORTED" in mechanism
    assert "C1" in mechanism
    variants = record["variants"]
    campaign_first5 = record["campaign_reference"]["flexible"]["p_iterations_per_solve_first_5"]
    # The campaign's early cost sits nearer the screen's startup than its settled value.
    assert abs(campaign_first5 - variants["d1"]["p_iterations_per_solve_startup"]) < abs(
        campaign_first5 - variants["d1"]["p_iterations_per_solve"]
    )


def test_the_projection_is_conservative_in_the_regime_that_matters() -> None:
    """The candidate stack must not be WORSE cold-started than warm, or ~2.00 s/window lies.

    The campaign never leaves the cold-start regime, so a stack whose advantage evaporated
    there would make every projection built on the settled ratio optimistic. It does not.
    """
    variants = _record()["variants"]
    startup = (
        variants["d1"]["seconds_per_step_startup"] / variants["d3"]["seconds_per_step_startup"]
    )
    settled = variants["d1"]["seconds_per_step"] / variants["d3"]["seconds_per_step"]
    assert startup >= settled
    assert "may not size" in _record()["the_projection_is_conservative_not_optimistic"]


def test_neither_refuted_knob_may_enter_the_adr040_stack() -> None:
    """A refuted lead that quietly ships anyway is worse than one never probed."""
    record = _record()
    for name in ("d3",):
        gamg_controls = record["variants"][name]["numerics"]["gamg_controls"]
        assert gamg_controls == [], f"{name} carries GAMG controls a refuted probe argued for"
    assert record["variants"]["d3"]["dirichlet_farfield"] is False
