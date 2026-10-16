"""The V&V job summary says what was measured and what was not, in words (Stage 22, ADR-051)."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

pytestmark = [pytest.mark.stage_22]

REPO = Path(__file__).resolve().parents[2]
_spec = importlib.util.spec_from_file_location(
    "vv_ci_summary", REPO / "scripts" / "vv_ci_summary.py"
)
assert _spec and _spec.loader
summ = importlib.util.module_from_spec(_spec)
sys.modules["vv_ci_summary"] = summ
_spec.loader.exec_module(summ)

JUNIT = """<?xml version="1.0" encoding="utf-8"?>
<testsuites><testsuite name="pytest" tests="4">
  <testcase classname="tests.vv.test_forward_regime_blasius" name="test_blasius" time="60"/>
  <testcase classname="tests.vv.test_tmr_flat_plate" name="test_flat_plate" time="80">
    <skipped type="pytest.xfail" message="measured Cf ~12.6% off the TMR data"/>
  </testcase>
  <testcase classname="tests.vv.test_tmr_naca0012" name="test_naca" time="35">
    <failure message="BenchmarkError: naca0012_verification: solver failed (rc=1)">trace</failure>
  </testcase>
  <testcase classname="tests.vv.test_x" name="test_skip" time="0">
    <skipped type="pytest.skip" message="V&amp;V cluster not ready"/>
  </testcase>
</testsuite></testsuites>
"""


def _deselected(tmp_path: Path) -> Path:
    recs = [
        {
            "nodeid": "tests/vv/test_transonic_onera_m6.py::test_m6",
            "markers": ["slow", "su2", "vv"],
            "reason": "",
        },
        {
            "nodeid": "tests/vv/test_tmr_naca0012.py::test_sweep",
            "markers": ["mesh_sweep", "unmeasurable", "vv"],
            "reason": "ADR-017: diverges",
        },
        {
            "nodeid": "tests/vv/test_unsteady_plunging_airfoil.py::test_p",
            "markers": ["moving", "vv"],
            "reason": "",
        },
        {"nodeid": "tests/vv/test_gci.py::test_unit", "markers": ["stage_05"], "reason": ""},
        {"nodeid": "tests/vv/test_gci.py::test_unit", "markers": ["stage_05"], "reason": ""},
    ]
    p = tmp_path / "d.jsonl"
    p.write_text("".join(json.dumps(r) + "\n" for r in recs))
    return p


def test_every_outcome_is_named_with_its_reason(tmp_path: Path) -> None:
    junit = tmp_path / "j.xml"
    junit.write_text(JUNIT)
    md = summ.render("V&V smoke", "vv and slow", junit, _deselected(tmp_path))

    assert "| passed |" in md and "| xfailed | measured Cf" in md
    assert "| FAILED | BenchmarkError: naca0012_verification: solver failed (rc=1)" in md
    assert "| SKIPPED | V&V cluster not ready" in md
    assert "**Totals:** 1 FAILED, 1 SKIPPED, 1 passed, 1 xfailed" in md
    # Deselected solves are grouped by WHY; the documented NO-GO carries its reason.
    assert "documented NO-GO" in md and "ADR-017: diverges" in md
    assert "frozen-optional SU2 stack" in md and "test_transonic_onera_m6.py::test_m6" in md
    assert "moving-mesh" in md
    assert "1 other test(s) outside this selection" in md  # de-duplicated


def test_a_missing_report_is_never_an_empty_green_table(tmp_path: Path) -> None:
    md = summ.render("vv-required", "x", tmp_path / "absent.xml", None)
    assert "pytest produced no report" in md


def test_a_report_with_no_test_says_nothing_was_measured(tmp_path: Path) -> None:
    junit = tmp_path / "j.xml"
    junit.write_text('<testsuites><testsuite name="pytest" tests="0"/></testsuites>')
    assert "No test ran" in summ.render("t", "", junit, None)
