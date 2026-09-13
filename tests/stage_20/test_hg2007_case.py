"""The Heathcote-Gursul V&V case: what it pre-registers, and what it refuses to guess.

The operating point is fixed from the reference ALONE, before any solve, so these are the
numbers the campaign is committed to. They are pinned as literals rather than recomputed,
because a test that re-derives them from the same constants they came from would pass
whatever they became.

The most important property here is a negative one: **there is no default time step**. It is
decided by the I7 max-Courant probe, and until ADR-039 B2 records it, `is_gated_configuration`
returns False for every configuration — so the campaign structurally cannot be launched
against an estimate.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from aero.adapters.precice.case import CoupledCaseSpec
from aero.vv._base import BenchmarkError, MetricSpec
from aero.vv.fsi import FSI_CASES
from aero.vv.fsi.hg2007_flexible_foil import (
    ARMS,
    BANDS,
    CHORD_M,
    CLAUSE_BANDS,
    CLAUSE_METRIC,
    FREQUENCY_HZ,
    PLUNGE_AMPLITUDE_M,
    PLUNGE_TO_CHORD,
    PREDICATES,
    REPORTED_ONLY,
    RUNGS,
    SPAN_M,
    STROUHAL,
    THICKNESS_RATIO,
    HeathcoteGursulFoil,
    evaluate_predicates,
    hg2007_case_spec,
    is_gated_configuration,
)

pytestmark = pytest.mark.stage_20

_REPO_ROOT = Path(__file__).resolve().parents[2]

DT = 1.0e-3
MAX_TIME = 1.0


def _spec(arm: str = "flexible", **overrides: object) -> CoupledCaseSpec:
    return hg2007_case_spec(
        **{
            "arm": arm,
            "time_window_size": DT,
            "max_time": MAX_TIME,
            "wall_clock_ceiling_s": 3600,
            **overrides,
        }  # type: ignore[arg-type]
    )


# --------------------------------------------------------------------------------------
# The operating point
# --------------------------------------------------------------------------------------


def test_the_plunge_amplitude_ratio_is_the_one_this_experiment_used() -> None:
    """h = 0.194, NOT 0.175.

    0.175 belongs to the other two Heathcote experiments — the NACA-0012 validation model
    and the SPANWISE-flexible wing — whose chord is 100 mm. Same shaker amplitude, different
    chord. The reference file itself had made that conflation once, and it propagates into
    the frequency-from-Strouhal conversion and therefore into every solve.
    """
    assert PLUNGE_AMPLITUDE_M == 0.0175
    assert CHORD_M == 0.090
    assert pytest.approx(0.1944, abs=5e-5) == PLUNGE_TO_CHORD


def test_the_frequency_follows_from_the_strouhal_number_and_the_rig_can_produce_it() -> None:
    st = 2.0 * FREQUENCY_HZ * PLUNGE_AMPLITUDE_M / 0.1
    assert st == pytest.approx(STROUHAL, rel=1e-12)
    # The rig's stated range is 0.3-2.5 Hz; a derived frequency outside it means the setup
    # is wrong rather than merely unusual.
    assert 0.3 <= FREQUENCY_HZ <= 2.5


def test_the_two_arms_differ_in_exactly_one_number() -> None:
    """The whole gated increment rests on this being true."""
    flexible = _spec("flexible").source
    rigid = _spec("rigid").source
    assert flexible.fluid.section.plate_half_thickness != rigid.fluid.section.plate_half_thickness
    for field in ("chord", "span", "u_inf", "rho", "nu", "time_window_size", "max_time"):
        assert getattr(flexible.fluid, field) == getattr(rigid.fluid, field)
    for field in ("nose_length", "max_half_thickness", "join_x"):
        assert getattr(flexible.fluid.section, field) == getattr(rigid.fluid.section, field)
    assert flexible.solid.plate == rigid.solid.plate
    assert flexible.solid.kinematics == rigid.solid.kinematics
    assert flexible.fluid.mesh_spec().n_surface == rigid.fluid.mesh_spec().n_surface


@pytest.mark.parametrize("arm", ARMS)
def test_the_plate_thickness_is_the_published_ratio(arm: str) -> None:
    spec = _spec(arm)
    b_over_c = 2.0 * spec.source.solid.plate_half_thickness / CHORD_M
    assert b_over_c == pytest.approx(THICKNESS_RATIO[arm], rel=1e-12)


@pytest.mark.parametrize("arm", ARMS)
def test_the_solid_slab_is_the_fluid_span_not_the_rig_span(arm: str) -> None:
    """A 1 m slab under a 2.5 mm fluid span is loaded 400x too little, and converges."""
    spec = _spec(arm)
    assert spec.source.solid.span == spec.source.fluid.span == SPAN_M


@pytest.mark.parametrize("arm", ARMS)
def test_the_pitch_is_never_prescribed(arm: str) -> None:
    """It ARISES from the flexibility; prescribing it models a different experiment."""
    kinematics = _spec(arm).source.solid.kinematics
    assert kinematics.pitch_amplitude_deg == 0.0
    assert kinematics.stroke_plane_deg == 90.0  # at the default 0, vy is identically zero


# --------------------------------------------------------------------------------------
# The campaign cannot be gated on an estimate
# --------------------------------------------------------------------------------------


def test_no_configuration_is_gated_until_the_pre_flight_has_measured_the_time_step() -> None:
    """ADR-039 B2's numbers come from I7 and I4. Until they land, nothing is gated.

    `gated` is DERIVED, never passed in, so this is what makes "pre-register before any
    campaign run" structural rather than a matter of discipline.
    """
    for rung in RUNGS:
        assert not is_gated_configuration(rung=rung, time_window_size=DT, max_time=MAX_TIME)
    for arm in ARMS:
        assert _spec(arm).gated is False


def test_building_a_case_without_a_time_step_refuses_rather_than_defaulting() -> None:
    with pytest.raises(TypeError):
        hg2007_case_spec(arm="flexible", max_time=1.0, wall_clock_ceiling_s=60)  # type: ignore[call-arg]


def test_the_default_case_spec_says_why_it_cannot_be_built_yet() -> None:
    with pytest.raises(BenchmarkError, match="I7 max-Courant probe"):
        HeathcoteGursulFoil("flexible").case_spec()


def test_an_unknown_rung_is_refused() -> None:
    with pytest.raises(BenchmarkError, match="unknown rung"):
        _spec("flexible", rung="finest")


def test_the_rung_ladder_is_self_similar() -> None:
    """A three-grid GCI needs one refinement ratio across both steps."""
    ordered = [RUNGS[name]["n_surface"] for name in ("coarse", "mid", "fine")]
    assert ordered == sorted(ordered)
    ratios = [ordered[1] / ordered[0], ordered[2] / ordered[1]]
    assert ratios[0] == pytest.approx(ratios[1], rel=0.03)
    assert ratios[0] == pytest.approx(1.30, rel=0.03)


# --------------------------------------------------------------------------------------
# The clause registry
# --------------------------------------------------------------------------------------


def test_every_clause_has_exactly_one_row_in_the_ordered_registry() -> None:
    clauses = [clause for clause, _ in CLAUSE_BANDS]
    assert clauses == sorted(clauses, key=lambda c: int(c[1:]))
    assert len(clauses) == len(set(clauses)) == 11


def test_a_band_less_clause_carries_a_literal_token_rather_than_being_omitted() -> None:
    """ADR-036's parity test omitted its band-less clauses, and that is exactly how D9 and
    D10 vanished from it silently. `(no band)` is a first-class value here."""
    band_less = {clause for clause, band in CLAUSE_BANDS if band == "(no band)"}
    assert band_less == {"D5", "D6", "D7", "D9"}
    assert band_less == {p.clause for p in PREDICATES} | set(REPORTED_ONLY)


def test_the_gated_and_reported_only_sets_are_disjoint_and_exhaustive() -> None:
    """Shape-7's property, checked against the registry the gate block will be parsed for."""
    metric_clauses = {clause for arm in ARMS for clause, _ in CLAUSE_METRIC[arm]}
    predicate_clauses = {p.clause for p in PREDICATES}
    increment_clauses = {"D3", "D4"}  # composed by the driver; both arms needed
    gated = metric_clauses | predicate_clauses | increment_clauses
    reported = set(REPORTED_ONLY)

    assert gated & reported == set()
    assert gated | reported == {clause for clause, _ in CLAUSE_BANDS}


def test_every_banded_clause_has_a_band_and_every_band_a_clause() -> None:
    banded = {clause for clause, band in CLAUSE_BANDS if band != "(no band)"}
    assert banded == set(BANDS)


@pytest.mark.parametrize("arm", ARMS)
def test_the_metrics_bands_match_the_registry_in_order(arm: str) -> None:
    case = HeathcoteGursulFoil(arm)  # type: ignore[arg-type]
    coded = [(m.name, m.tolerance, m.comparison) for m in case.metrics()]
    expected = [
        (metric, BANDS[clause], "absolute" if clause in {"D8", "D10"} else "relative")
        for clause, metric in CLAUSE_METRIC[arm]
    ]
    assert coded == expected


@pytest.mark.parametrize("arm", ARMS)
def test_every_metric_has_a_reference_row(arm: str) -> None:
    case = HeathcoteGursulFoil(arm)  # type: ignore[arg-type]
    reference = case.reference(_REPO_ROOT)
    for metric in case.metrics():
        assert metric.name in reference.scalars, f"{arm}: no reference for {metric.name}"


def test_the_declared_zeros_are_declared_as_such() -> None:
    """D8 and D10 compare against 0.0, and the reference file has no row for either."""
    reference = HeathcoteGursulFoil("rigid").reference(_REPO_ROOT)
    assert reference.scalars["d0_pitch_amplitude_deg"] == 0.0
    assert reference.scalars["p3_p2_closure"] == 0.0
    assert "DECLARED by construction" in reference.source


def test_the_flexible_bands_are_the_computed_ones() -> None:
    """Traceable to hg2007_recomputed.csv with the 4x rule floored at 0.25 (ADR-039)."""
    assert BANDS["D0"] == 0.25
    assert BANDS["D1"] == 0.25
    assert BANDS["D2"] == 0.40
    assert BANDS["D3"] == BANDS["D4"] == 0.25  # the floor binds; 0.25 is a policy number
    assert BANDS["D8"] == 2.0
    assert BANDS["D10"] == 0.02


def test_the_reference_values_are_the_published_ones() -> None:
    flexible = HeathcoteGursulFoil("flexible").reference(_REPO_ROOT).scalars
    rigid = HeathcoteGursulFoil("rigid").reference(_REPO_ROOT).scalars
    assert flexible["c_t"] == pytest.approx(1.00772, rel=1e-5)
    assert flexible["eta"] == pytest.approx(0.175279, rel=1e-5)
    assert flexible["d0_pitch_amplitude_deg"] == pytest.approx(5.34637, rel=1e-5)
    assert rigid["c_t"] == pytest.approx(0.398463, rel=1e-5)
    assert rigid["eta"] == pytest.approx(0.0887515, rel=1e-5)
    # The increment the driver gates on, from the same rows.
    assert flexible["c_t"] - rigid["c_t"] == pytest.approx(0.609257, rel=1e-4)
    assert flexible["eta"] - rigid["eta"] == pytest.approx(0.0865273, rel=1e-4)


# --------------------------------------------------------------------------------------
# The structural predicates
# --------------------------------------------------------------------------------------


class _Arm:
    """The two fields `evaluate_predicates` reads."""

    def __init__(self, arm: str, c_t: float, eta: float) -> None:
        self.arm, self.c_t, self.eta = arm, c_t, eta


def test_a_reproduced_increment_passes_d5_and_d6() -> None:
    results = evaluate_predicates(_Arm("flexible", 1.0, 0.18), _Arm("rigid", 0.4, 0.09))
    assert {r.clause: r.passed for r in results} == {"D5": True, "D6": True, "D7": True}


def test_a_negative_increment_is_a_result_not_an_error() -> None:
    """HG's headline finding failing to reproduce is a real physical NO-GO. It must be
    REPORTED clause by clause, not raised — the verdict has to be able to say
    "NO-GO on the increment, GO on the absolutes"."""
    results = evaluate_predicates(_Arm("flexible", 0.3, 0.05), _Arm("rigid", 0.4, 0.09))
    by_clause = {r.clause: r.passed for r in results}
    assert by_clause["D5"] is False
    assert by_clause["D6"] is False
    assert by_clause["D7"] is True


@pytest.mark.parametrize(
    ("c_t", "eta"),
    [(-0.1, 0.18), (1.0, -0.2), (1.0, 1.4)],
)
def test_an_inadmissible_arm_raises_because_the_record_is_broken(c_t: float, eta: float) -> None:
    """Net drag, or an efficiency outside (0, 1), is not a disagreement with the
    experiment — it is a readout that is wrong, and reporting it as a NO-GO would put a
    broken measurement on the record as evidence about the physics."""
    with pytest.raises(BenchmarkError, match="inadmissible"):
        evaluate_predicates(_Arm("flexible", c_t, eta), _Arm("rigid", 0.4, 0.09))


# --------------------------------------------------------------------------------------
# Registration
# --------------------------------------------------------------------------------------


def test_both_arms_are_registered_so_neither_can_go_quiet() -> None:
    """`aero vv report` is registry-driven: a registered case with no run reports `missing`,
    renders red and denies ALL GREEN. Before Stage 19 a case that went red and stopped being
    run vanished from the report entirely."""
    assert "hg2007_flexible_foil" in FSI_CASES
    assert "hg2007_rigid_foil" in FSI_CASES
    assert isinstance(FSI_CASES["hg2007_flexible_foil"], HeathcoteGursulFoil)


def test_a_mesh_sweep_is_refused_with_the_reason() -> None:
    """The ladder is real, but each rung is a multi-day coupled solve with its own ceiling.
    Running three inside `aero vv run` would silently exceed every declared budget."""
    with pytest.raises(NotImplementedError, match="CAMPAIGN"):
        HeathcoteGursulFoil("flexible").refined(1.3)


def test_the_case_is_driven_by_the_coupled_solver_only() -> None:
    class _NotACoupledSolver:
        def load(self, result: object) -> object:  # pragma: no cover - never reached
            raise AssertionError("must not be called")

    with pytest.raises(BenchmarkError, match="PreciceCoupledSolver only"):
        HeathcoteGursulFoil("flexible").evaluate(_NotACoupledSolver(), object())  # type: ignore[arg-type]


def test_metric_specs_are_well_formed() -> None:
    for case in (HeathcoteGursulFoil(arm) for arm in ARMS):
        for metric in case.metrics():
            assert isinstance(metric, MetricSpec)
            assert metric.tolerance > 0.0
