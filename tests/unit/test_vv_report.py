"""`aero vv report` reads the truth: a query per registered case, never a window (Stage 22).

Until Stage 22 the report read the newest 500 runs of the V&V experiment. `vv-smoke` logs four
cases per push, so those runs filled the window and every older run read as `missing`: three
failures and three passes were invisible (ADR-051 §1). These tests pin the replacement with a
fake MLflow client (no cluster in CI):

* a run older than any window is found;
* a case with zero runs is `missing` (or `frozen` / `deferred`, by its disposition);
* a failing case hidden behind newer runs of other cases is still `fail`;
* a run with no `vv_status` is `unknown`, never `pass`;
* unregistered tags (`-sweep`, `thesis-grade`, `validated`) never enter the verdict;
* the history listing pages explicitly and states its bound.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from aero.vv import report as rep
from aero.vv.report import (
    ReportError,
    case_filter,
    collect_history,
    collect_latest,
    render_history,
    render_latest,
    verdicts_of,
)
from aero.vv.stacks import CASE_STACK

from tests.unit._fake_mlflow import FakeClient, run

pytestmark = [pytest.mark.stage_22]

CASES = sorted(CASE_STACK)
SMOKE = (
    "flat_plate_te",
    "blasius_flat_plate",
    "laminar_airfoil_naca0012",
    "cylinder_strouhal_re100",
)


def _flood(n: int, t0: int) -> list:
    """`n` newer smoke runs, the pattern that filled the old 500-run window."""
    return [run(f"smoke{i}", SMOKE[i % 4], t0 + i) for i in range(n)]


def _row(rows: list, case: str):  # type: ignore[no-untyped-def]
    (only,) = [r for r in rows if r.case == case]
    return only


def test_a_run_older_than_any_window_is_found() -> None:
    old = run("old-cfd2", "turek_hron_cfd2", t=1_000, status="pass", cd_error=0.012)
    client = FakeClient([old, *_flood(1405, t0=10_000)])

    rows = collect_latest(client, "1", CASES)

    cfd2 = _row(rows, "turek_hron_cfd2")
    assert (cfd2.status, cfd2.run_id) == ("pass", "old-cfd2")
    assert cfd2.metric_errors == {"cd": pytest.approx(0.012)}
    # Every --latest query is a per-case filter returning ONE run: there is no window to fill.
    assert client.calls and all(c["filter_string"] and c["max_results"] == 1 for c in client.calls)


def test_a_case_with_zero_runs_is_missing_frozen_or_deferred_by_disposition() -> None:
    rows = collect_latest(FakeClient(_flood(8, t0=10)), "1", CASES)

    assert _row(rows, "bump_2d").status == "missing"
    assert _row(rows, "onera_m6").status == "frozen"
    assert _row(rows, "taylor_green_p3_32").status == "frozen"
    assert _row(rows, "hg2007_flexible_foil").status == "deferred"
    assert all(r.run_id == "" for r in rows if r.status in {"missing", "frozen", "deferred"})


def test_a_failing_case_hidden_behind_newer_runs_of_other_cases_is_still_fail() -> None:
    hidden = run("old-fail", "naca0012_verification", t=5, status="fail", cd_error=0.21)
    rows = collect_latest(FakeClient([hidden, *_flood(2000, t0=100)]), "1", CASES)

    assert _row(rows, "naca0012_verification").status == "fail"
    openfoam = verdicts_of(rows)["openfoam"]
    assert openfoam.verdict == "RED"
    assert ("naca0012_verification", "fail") in openfoam.not_passing


@pytest.mark.parametrize("vv_status", [None, "", "PASS", "ok", "skipped"])
def test_a_run_without_a_recognised_vv_status_is_unknown_never_pass(vv_status) -> None:  # type: ignore[no-untyped-def]
    r = run("r1", "t3a_flat_plate_transition", t=10, status=vv_status)
    rows = collect_latest(FakeClient([r]), "1", CASES)

    assert _row(rows, "t3a_flat_plate_transition").status == "unknown"
    assert verdicts_of(rows)["openfoam"].verdict == "RED"


def test_the_newest_run_on_the_case_s_own_stack_wins_not_a_newer_off_stack_run() -> None:
    of_fail = run("of-fail", "flat_plate_te", t=10, status="fail")
    su2_pass = run("su2-pass", "flat_plate_te", t=99, status="pass", solver="SU2 v8")
    rows = collect_latest(FakeClient([of_fail, su2_pass]), "1", CASES)

    assert (_row(rows, "flat_plate_te").status, _row(rows, "flat_plate_te").run_id) == (
        "fail",
        "of-fail",
    )


def test_a_precice_coupled_run_counts_for_the_openfoam_stack() -> None:
    fsi = run(
        "fsi", "turek_hron_fsi3", t=10, solver="preCICE 3.4.1 (OpenFOAM-ESI v2412 + Nutils 9.2)"
    )
    rows = collect_latest(FakeClient([fsi]), "1", CASES)

    assert (_row(rows, "turek_hron_fsi3").stack, _row(rows, "turek_hron_fsi3").status) == (
        "openfoam",
        "pass",
    )


def test_unregistered_tags_never_enter_the_report_or_the_verdict() -> None:
    noise = [
        run("s1", "bump_2d-sweep", t=50, status=None),
        run("s2", "thesis-grade", t=51, status=None),
        run("s3", "validated", t=52, status="pass"),
        run("s4", "s17c_00-sweep", t=53, status=None),
    ]
    rows = collect_latest(FakeClient(noise), "1", CASES)

    assert {r.case for r in rows} == set(CASE_STACK)
    assert _row(rows, "bump_2d").status == "missing"


def test_every_registered_case_gets_exactly_one_row() -> None:
    rows = collect_latest(FakeClient([]), "1", CASES)
    assert [r.case for r in rows].count("onera_m6") == 1
    assert len(rows) == len(CASE_STACK) == 25


def test_a_run_of_a_frozen_stack_shows_its_real_status() -> None:
    m6 = run("m6", "onera_m6", t=10, status="fail", solver="SU2 v8")
    rows = collect_latest(FakeClient([m6]), "1", CASES)

    assert _row(rows, "onera_m6").status == "fail"
    assert verdicts_of(rows)["su2"].verdict == "RED"


def test_the_latest_text_states_a_verdict_per_stack() -> None:
    rows = collect_latest(FakeClient(_flood(12, t0=1)), "1", CASES)
    text = render_latest(rows)

    assert "VERDICT openfoam: RED" in text
    assert "VERDICT su2: FROZEN" in text
    assert "VERDICT pyfr: FROZEN" in text
    assert "ADR-051 D2" in text
    assert "Stacks clear for production-tagged runs: none." in text


def test_history_pages_the_whole_experiment_and_states_its_bound(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(rep, "PAGE_SIZE", 7)
    runs = [
        *_flood(20, t0=100),
        run("sw", "bump_2d-sweep", t=1, status=None),
        run("tg", "thesis-grade", t=2, status=None),
    ]
    runs.append(run("untagged", "x", t=3))
    del runs[-1].tags["validation_tag"]
    client = FakeClient(runs)

    listing = collect_history(client, "1", limit=5)

    assert len(listing.rows) == 5 and listing.total_gated == 20 and listing.truncated
    assert (listing.sweep_runs, listing.unregistered, listing.untagged) == (
        1,
        {"thesis-grade": 1},
        1,
    )
    assert listing.total_runs == 23
    tokens = [c["page_token"] for c in client.calls]
    assert tokens == [None, "7", "14", "21"]  # every page was read, explicitly
    text = render_history(listing)
    assert "listed 5 of 20 gated run(s)" in text and "TRUNCATED" in text
    assert "NOT the production gate" in text


def test_history_refuses_a_repeated_page_token() -> None:
    class Looping(FakeClient):
        def search_runs(self, *a, **k):  # type: ignore[no-untyped-def]
            # A broken server: every page, including the next one, hands back the same token.
            page = super().search_runs(*a, **{**k, "page_token": None})
            page.token = "same"
            return page

    with pytest.raises(ReportError, match="page token twice"):
        collect_history(Looping(_flood(3, t0=1)), "1", limit=10)


@pytest.mark.parametrize("bad", ["a' OR '1'='1", "x y", "", "x;y"])
def test_the_filter_refuses_an_unsafe_case_name(bad: str) -> None:
    with pytest.raises(ReportError):
        case_filter(bad, "OpenFOAM-ESI")


def test_a_case_missing_from_the_stack_table_fails_loudly() -> None:
    with pytest.raises(Exception, match="not in CASE_STACK"):
        collect_latest(FakeClient([]), "1", [*CASES, "brand_new_case"])


# --- the CLI, in-process, with the fake client -----------------------------------------------


@pytest.fixture
def cli(monkeypatch: pytest.MonkeyPatch):  # type: ignore[no-untyped-def]
    import aero.cli as aero_cli
    from typer.testing import CliRunner

    client = FakeClient(
        [
            run("cfd2", "turek_hron_cfd2", t=1),
            run("fp", "flat_plate_te", t=9, status="fail", cf_error=0.126),
        ]
    )
    monkeypatch.setattr(aero_cli, "_vv_report_client", lambda: (client, "aero-provenance"))
    runner = CliRunner()
    return lambda *args: runner.invoke(aero_cli.app, ["vv", "report", *args])


def test_cli_latest_json_is_an_array_of_typed_rows(cli) -> None:  # type: ignore[no-untyped-def]
    result = cli("--latest", "--json")
    assert result.exit_code == 0, result.output
    rows = json.loads(result.output)
    assert isinstance(rows, list) and len(rows) == 25
    by_case = {r["case"]: r for r in rows}
    assert by_case["flat_plate_te"]["status"] == "fail"
    assert by_case["flat_plate_te"]["metric_errors"] == {"cf": pytest.approx(0.126)}
    assert by_case["turek_hron_cfd2"]["run_id"] == "cfd2"
    assert {"case", "status", "metric_errors", "stack", "disposition", "run_id"} <= set(rows[0])


def test_cli_latest_text_and_html(cli, tmp_path: Path) -> None:  # type: ignore[no-untyped-def]
    out = tmp_path / "dash.html"
    result = cli("--latest", "--html", str(out))
    assert result.exit_code == 0, result.output  # RED is reported, not an error exit
    assert "VERDICT openfoam: RED" in result.output
    html = out.read_text()
    assert "openfoam: ATTENTION NEEDED" in html and "su2: FROZEN" in html


def test_cli_html_needs_latest(cli) -> None:  # type: ignore[no-untyped-def]
    assert cli("--html", "x.html").exit_code == 2


def test_cli_history_states_its_bound(cli) -> None:  # type: ignore[no-untyped-def]
    result = cli("--limit", "1")
    assert result.exit_code == 0, result.output
    assert "listed 1 of 2 gated run(s)" in result.output
