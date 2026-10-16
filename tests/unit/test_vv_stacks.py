"""The V&V stack table agrees with the case registries (ADR-051 D2 (b); Stage 22)."""

from __future__ import annotations

import pytest
from aero.vv.stacks import (
    CASE_STACK,
    DEFERRED_CASES,
    STACKS,
    StackMapError,
    case_disposition,
    check_stack_map,
    registered_cases,
)
from aero.vv.status import stack_verdicts

pytestmark = [pytest.mark.stage_22]


def test_every_registered_case_has_exactly_one_stack() -> None:
    assert set(registered_cases()) == set(CASE_STACK)
    assert len(CASE_STACK) == 25


def test_the_frozen_and_deferred_sets_are_the_ones_adr_051_d2_names() -> None:
    frozen = {c for c, s in CASE_STACK.items() if STACKS[s].disposition == "frozen"}
    assert frozen == {"naca0012_transonic", "onera_m6", "taylor_green_p3_32", "periodic_hill_2d"}
    assert set(DEFERRED_CASES) == {"hg2007_flexible_foil"}
    active = [c for c in CASE_STACK if case_disposition(c) == "active"]
    assert len(active) == 20  # ADR-051's Stage-24 arithmetic: 9 no-run + 4 failing + 7 passing


def test_the_scale_resolving_cases_are_pyfr_cases() -> None:
    cases = registered_cases()
    for name in ("taylor_green_p3_32", "periodic_hill_2d"):
        assert cases[name].solver_kind == "pyfr"  # type: ignore[attr-defined]
        assert CASE_STACK[name] == "pyfr"


def test_a_case_without_a_stack_or_a_stale_entry_fails_loudly() -> None:
    with pytest.raises(StackMapError, match="not in CASE_STACK: new_case"):
        check_stack_map([*CASE_STACK, "new_case"])
    with pytest.raises(StackMapError, match="not registered: onera_m6"):
        check_stack_map([c for c in CASE_STACK if c != "onera_m6"])


def test_green_needs_every_gating_case_to_pass() -> None:
    v = stack_verdicts(
        [
            ("a", "openfoam", "active", "pass"),
            ("b", "openfoam", "active", "pass"),
            ("d", "openfoam", "deferred", "deferred"),
        ]
    )
    assert v["openfoam"].verdict == "GREEN" and v["openfoam"].clear_for_production
    assert v["openfoam"].not_gating == (("d", "deferred"),)


@pytest.mark.parametrize("bad", ["fail", "regress", "missing", "unknown"])
def test_one_non_passing_gating_case_makes_the_stack_red(bad: str) -> None:
    v = stack_verdicts([("a", "openfoam", "active", "pass"), ("b", "openfoam", "active", bad)])
    assert v["openfoam"].verdict == "RED"


def test_a_frozen_stack_is_frozen_until_evaluated_and_red_on_a_failure() -> None:
    never = stack_verdicts([("m6", "su2", "frozen", "frozen"), ("t", "su2", "frozen", "frozen")])
    assert never["su2"].verdict == "FROZEN" and not never["su2"].clear_for_production
    failed = stack_verdicts([("m6", "su2", "frozen", "fail"), ("t", "su2", "frozen", "frozen")])
    assert failed["su2"].verdict == "RED"
    passed = stack_verdicts([("m6", "su2", "frozen", "pass"), ("t", "su2", "frozen", "pass")])
    assert passed["su2"].verdict == "GREEN"


def test_a_stack_with_only_deferred_cases_is_never_green() -> None:
    v = stack_verdicts([("d", "openfoam", "deferred", "pass")])
    assert v["openfoam"].verdict == "RED" and v["openfoam"].gating == ()


def test_stacks_absent_from_the_items_get_no_verdict() -> None:
    assert set(stack_verdicts([("a", "pyfr", "frozen", "frozen")])) == {"pyfr"}
