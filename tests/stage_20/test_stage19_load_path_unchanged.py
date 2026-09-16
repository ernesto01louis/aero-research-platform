"""Non-regression pin on `PreciceCoupledSolver.load()`, ahead of the Stage-20 refactor.

Stage 20 reshapes `CoupledCaseSpec` around a `source` discriminated union, renames
`TutorialTree`, and extracts the K1/K2 gates so the solver and the Stage-19 driver share
one implementation. The FSI3 verdict (ADR-016, ADR-036, tag v0.0.19) rests on the numbers
the *current* load path produces, so the refactor has to reproduce them exactly.

**This file and its fixtures were committed BEFORE the refactor, and the golden was
captured by running the pre-refactor `load()`.** That ordering is the whole point — a
golden produced by post-refactor code records the refactor rather than testing it — and it
is provable after the fact:

    git log --oneline -- tests/stage_20/fixtures/stage19_load_path/   # one commit
    git merge-base --is-ancestor <that commit> <the refactor commit>  # true

Regenerate the fixtures and goldens with
``python scripts/stage20_capture_stage19_golden.py``. There is deliberately no
``--regenerate`` flag here: an escape hatch in the test is how a golden gets silently
rewritten to match a regression.

The record is synthetic but FSI3-shaped, and is built to exercise every branch of
`load()` — both admissible K2 endings, both refused ones, the `.within()` window scoping
(the two non-converged windows sit strictly below the analysis window's first index, so
removing `.within()` turns this red), gate C4's header prediction, and the S3/S5
periodic-steady-state path. See the capture script's docstring for the numerology.
"""

from __future__ import annotations

import json
import math
import sys
from pathlib import Path
from typing import Any

import pytest
from aero.adapters.precice.logs import (
    CouplingConvergenceError,
    assert_coupling_converged,
)
from aero.adapters.precice.solver import PreciceCoupledSolver, PreciceSolverError
from aero.adapters.precice.watchpoint import WatchpointError

pytestmark = pytest.mark.stage_20

_REPO_ROOT = Path(__file__).resolve().parents[2]
_FIXTURES = _REPO_ROOT / "tests" / "stage_20" / "fixtures" / "stage19_load_path"


def _capture_module() -> Any:
    """Import the capture script, which owns the fixture builder the test replays."""
    scripts = str(_REPO_ROOT / "scripts")
    if scripts not in sys.path:
        sys.path.insert(0, scripts)
    import stage20_capture_stage19_golden

    return stage20_capture_stage19_golden


#: Every key `load()` puts in `SolveResult.scalars`, as a literal.
#:
#: There are **23**, not the 20 the Stage-20 resume prompt states. Spelling them out here
#: rather than asserting a count is what makes an added or dropped scalar a named failure:
#: `scalars` is provenance-bearing (it is what the V&V case compares against the reference)
#: and a silently vanished key would show up as a `KeyError` days later in a driver.
_EXPECTED_SCALARS = frozenset(
    {
        # Gated (ADR-036 D1-D5), over the DERIVED analysis window.
        "tip_uy_amplitude",
        "tip_uy_frequency",
        "tip_ux_amplitude",
        "tip_ux_mean",
        "tip_ux_frequency",
        # Diagnostics (X) — reported, never gated.
        "tip_uy_mean",
        "analysis_t_start",
        "analysis_t_end",
        "analysis_n_settled_cycles",
        "analysis_cumulative_mean_drift",
        "analysis_cumulative_amplitude_drift",
        "coupling_first_window",
        "coupling_last_window",
        "analysis_mean_drift",
        "analysis_amplitude_drift",
        "t_end",
        "n_windows",
        "wall_clock_s",
        "stopped_by_ceiling",
        "coupling_mean_iterations",
        "coupling_max_iterations",
        "max_iterations_configured",
        "max_time_configured",
    }
)

#: Scalars whose value is an exact integer count or flag. Compared with `==`, never a
#: tolerance: a settled-cycle count or a gated window index that has moved by any amount
#: is a behaviour change, not numerical noise.
_EXACT_SCALARS = frozenset(
    {
        "analysis_n_settled_cycles",
        "coupling_first_window",
        "coupling_last_window",
        "coupling_max_iterations",
        "max_iterations_configured",
        "n_windows",
        "stopped_by_ceiling",
        "wall_clock_s",
    }
)

#: numpy's FFT dispatches on CPU SIMD width, so a bin-exact peak's parabolic correction can
#: differ in the last bits between this host and a CI runner. Comparison is therefore
#: `isclose`, not `==` — but at 1e-12, which is four orders tighter than any behaviour
#: change a refactor could introduce and still leaves the near-zero drift terms (~1e-15)
#: covered by `abs_tol`.
_REL_TOL = 1.0e-12
_ABS_TOL = 1.0e-12


def _golden(variant: str) -> dict[str, Any]:
    return json.loads((_FIXTURES / "golden" / f"solve_result.{variant}.json").read_text())


def _load(tmp_path: Path, *, variant: str, config: str | None = None) -> Any:
    capture = _capture_module()
    tutorial = capture.stage_fixture_tree(tmp_path, status=variant, config=config)
    return PreciceCoupledSolver().load(capture.fake_result(tutorial)), tutorial


def _assert_matches_golden(solve: Any, golden: dict[str, Any]) -> None:
    assert solve.case_name == golden["case_name"]
    assert solve.cd is None and solve.cl is None
    assert solve.cd_pressure is None and solve.cd_viscous is None
    assert solve.iterations_to_convergence == golden["iterations_to_convergence"]
    assert solve.final_residual == golden["final_residual"]

    assert set(solve.scalars) == _EXPECTED_SCALARS
    assert set(golden["scalars"]) == _EXPECTED_SCALARS
    for name in sorted(_EXPECTED_SCALARS):
        measured, expected = solve.scalars[name], golden["scalars"][name]
        if name in _EXACT_SCALARS:
            assert measured == expected, f"{name}: {measured!r} != golden {expected!r}"
        else:
            assert math.isclose(measured, expected, rel_tol=_REL_TOL, abs_tol=_ABS_TOL), (
                f"{name}: {measured!r} != golden {expected!r}"
            )

    history = golden["history"]
    assert solve.history.kind == "time"
    assert solve.history.monitor_name == history["monitor_name"]
    assert len(solve.history.t) == len(history["t"])
    assert len(solve.history.monitor) == len(history["monitor"])
    for got, want in zip(solve.history.t, history["t"], strict=True):
        assert math.isclose(got, want, rel_tol=_REL_TOL, abs_tol=_ABS_TOL)
    for got, want in zip(solve.history.monitor, history["monitor"], strict=True):
        assert math.isclose(got, want, rel_tol=_REL_TOL, abs_tol=_ABS_TOL)


class TestTheLoadPathIsUnchanged:
    def test_a_clean_run_reproduces_the_committed_golden(self, tmp_path: Path) -> None:
        solve, tutorial = _load(tmp_path, variant="all-exited")
        _assert_matches_golden(solve, _golden("all-exited"))
        assert solve.run_id == "turek_hron_fsi3-fixture"
        assert Path(solve.source) == (
            tutorial / "turek-hron-fsi3" / "solid-nutils" / "precice-Solid-watchpoint-Flap-Tip.log"
        )

    def test_a_ceiling_stop_with_everyone_still_running_is_admitted(self, tmp_path: Path) -> None:
        """ADR-036 K2's second admissible ending — a budget outcome, not a failure."""
        solve, _ = _load(tmp_path, variant="ceiling-ok")
        _assert_matches_golden(solve, _golden("ceiling-ok"))
        assert solve.scalars["stopped_by_ceiling"] == 1.0

    def test_the_two_endings_differ_only_in_the_status_derived_scalars(
        self, tmp_path: Path
    ) -> None:
        """The physics is one record; only how the run STOPPED differs between them.

        Pins that `load()` does not let the stopping reason leak into a measured value.
        """
        clean, ceiling = _golden("all-exited")["scalars"], _golden("ceiling-ok")["scalars"]
        differing = {k for k in clean if clean[k] != ceiling[k]}
        assert differing == {"wall_clock_s", "stopped_by_ceiling"}


class TestTheGateIsScopedToTheAnalysisWindow:
    def test_the_excluded_windows_really_are_non_converged(self, tmp_path: Path) -> None:
        """Without this the `.within()` scoping could be a no-op and nothing would notice.

        The fixture puts one capped window (5) and one flagged window (63) strictly below
        the analysis window's first index (64). Asserted over the WHOLE run the gate must
        fail; scoped to the analysis window it must pass. That difference is exactly what
        `load()`'s K1 placement buys, and it is what the Stage-19 driver's whole-run
        variant does not have.
        """
        capture = _capture_module()
        tutorial = capture.stage_fixture_tree(tmp_path, status="all-exited")
        solver = PreciceCoupledSolver()
        result = capture.fake_result(tutorial)

        whole_run = solver.coupling_report(result)
        assert len(whole_run) == 2
        for report in whole_run:
            offending = {w.time_window for w in report.nonconverged}
            assert offending == {capture.CAPPED_WINDOW, capture.FLAGGED_WINDOW}
            with pytest.raises(CouplingConvergenceError):
                assert_coupling_converged(report)

        golden = _golden("all-exited")["scalars"]
        first = int(golden["coupling_first_window"])
        last = int(golden["coupling_last_window"])
        assert first > capture.CAPPED_WINDOW and first > capture.FLAGGED_WINDOW
        for report in whole_run:
            assert_coupling_converged(report.within(first_window=first, last_window=last))

    def test_the_reported_iteration_maximum_is_the_in_window_one(self) -> None:
        """`coupling_max_iterations` is 9 (window 200), not 100 (the capped window 5)."""
        capture = _capture_module()
        golden = _golden("all-exited")["scalars"]
        assert golden["coupling_max_iterations"] == float(capture.PEAK_ITERATIONS)
        assert golden["max_iterations_configured"] == float(capture.MAX_ITERATIONS)


class TestTheHeaderIsVerifiedAgainstTheConfiguration:
    def test_a_reordered_use_data_declaration_is_refused(self, tmp_path: Path) -> None:
        """Gate C4. The watch-point header is PREDICTED from the config, not assumed.

        Swapping `Displacement` and `Stress` in the watched mesh's `use-data` order leaves
        a file that parses perfectly and whose columns would silently transpose the
        transverse displacement into a stress component.
        """
        with pytest.raises(WatchpointError, match="does not match the header predicted"):
            _load(tmp_path, variant="all-exited", config="precice-config.stress-first.xml")


class TestTheRefusalsStayLoud:
    def test_a_dead_participant_is_not_reportable(self, tmp_path: Path) -> None:
        with pytest.raises(PreciceSolverError, match="a participant died"):
            _load(tmp_path, variant="participant-died")

    def test_a_desynchronised_ceiling_stop_is_not_reportable(self, tmp_path: Path) -> None:
        """K2: a ceiling stop is admissible only with EVERY participant still running."""
        with pytest.raises(PreciceSolverError, match="had already exited"):
            _load(tmp_path, variant="ceiling-desync")


class TestTheHistoryIsTheWholeRecord:
    def test_the_time_history_is_not_truncated_to_the_analysis_window(self, tmp_path: Path) -> None:
        """`history` carries all 512 rows; only the SCALARS are window-scoped.

        A real invariant someone could plausibly "tidy" into the analysis window, which
        would silently change every downstream plot and every re-analysis.
        """
        capture = _capture_module()
        solve, _ = _load(tmp_path, variant="all-exited")
        assert len(solve.history.t) == capture.N_ROWS
        assert math.isclose(solve.history.t[0], capture.DT, rel_tol=_REL_TOL)
        assert solve.scalars["analysis_t_start"] > solve.history.t[0]
        assert solve.iterations_to_convergence == capture.N_ROWS
