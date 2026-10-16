"""The independent full-pagination read that cross-checks `aero vv report --latest` (Stage 22).

`scripts/vv_report_crosscheck.py` must reach its table by a different route than the report (one
pass over every run, no per-case query). Its pure parts are tested here; the live run is recorded
in the Stage-22 handoff.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest
from aero.vv.stacks import CASE_STACK, DEFERRED_CASES, STACKS

pytestmark = [pytest.mark.stage_22]

REPO = Path(__file__).resolve().parents[2]


def _load():  # type: ignore[no-untyped-def]
    spec = importlib.util.spec_from_file_location(
        "vv_report_crosscheck", REPO / "scripts" / "vv_report_crosscheck.py"
    )
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules["vv_report_crosscheck"] = mod
    spec.loader.exec_module(mod)
    return mod


xc = _load()
PREFIXES = {n: s.solver_version_prefixes for n, s in STACKS.items()}
FROZEN = {n for n, s in STACKS.items() if s.disposition == "frozen"}


def _run(
    run_id: str, case: str, t: int, status: str | None = "pass", solver: str = "OpenFOAM-ESI v2412"
):  # type: ignore[no-untyped-def]
    tags = {"validation_tag": case, "solver_version": solver}
    if status is not None:
        tags["vv_status"] = status
    return {"run_id": run_id, "start_time": t, "tags": tags}


def test_the_newest_on_stack_run_wins_and_off_stack_runs_are_noted() -> None:
    runs = [
        _run("old", "flat_plate_te", 1, "fail"),
        _run("new", "flat_plate_te", 5, "fail"),
        _run("su2", "flat_plate_te", 9, "pass", solver="SU2 v8"),
        _run("sw", "bump_2d-sweep", 3, None),
        {"run_id": "u", "start_time": 4, "tags": {}},
    ]
    on_stack, any_solver, census = xc.newest_by_case(runs, CASE_STACK, PREFIXES)
    assert on_stack["flat_plate_te"]["run_id"] == "new"
    assert any_solver["flat_plate_te"]["run_id"] == "su2"
    assert census == {"bump_2d-sweep": 1, "<no validation_tag>": 1}


@pytest.mark.parametrize(
    ("case", "run", "expected"),
    [
        ("bump_2d", None, "missing"),
        ("onera_m6", None, "frozen"),
        ("hg2007_flexible_foil", None, "deferred"),
        ("t3a_flat_plate_transition", _run("r", "t3a_flat_plate_transition", 1, None), "unknown"),
        ("turek_hron_cfd2", _run("r", "turek_hron_cfd2", 1, "pass"), "pass"),
    ],
)
def test_the_expected_status_is_derived_independently(case, run, expected) -> None:  # type: ignore[no-untyped-def]
    assert xc.expected_status(case, run, CASE_STACK, FROZEN, set(DEFERRED_CASES)) == expected


def test_compare_names_every_disagreement() -> None:
    expected = {"a": ("pass", "r1"), "b": ("fail", "r2"), "c": ("missing", "")}
    report = [
        {"case": "a", "status": "pass", "run_id": "r1"},
        {"case": "b", "status": "pass", "run_id": "r2"},
        {"case": "z", "status": "pass", "run_id": "r9"},
    ]
    problems = xc.compare(expected, report)
    assert len(problems) == 3
    assert any(p.startswith("b: report says") for p in problems)
    assert any(p.startswith("c: absent") for p in problems)
    assert any(p.startswith("z: in the report") for p in problems)
    assert (
        xc.compare(
            expected, [{"case": k, "status": s, "run_id": r} for k, (s, r) in expected.items()]
        )
        == []
    )
