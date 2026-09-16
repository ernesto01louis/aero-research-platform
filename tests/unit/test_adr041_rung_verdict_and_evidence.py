"""ADR-041 V1/V2: the rung verdict is derived, and the evidence lands beside the run.

The ladder's whole value is that the rule was fixed before the data existed. Two things
have to hold for that to survive contact with a real probe:

**The verdict is computed, never typed in.** V1's vocabulary is closed —
ELIMINATED / RECURRENCE-DETECTED / DIED-UNDIAGNOSED / INCONCLUSIVE — and the mapping from
(detector report, run outcome) onto it is code, so a rung cannot end in a state the
pre-registration failed to name, and "we'll decide when we see it" is unreachable.

**A later reader can re-derive the decision without this driver.** The per-window series
(the same five columns session 12's `minerB_parse.awk` emits, so the two diff cleanly),
the verdict, and the bounds that produced it are all written next to the run.

The ordering inside the mapping is the pre-registration's and is the subject of the first
three tests: a fired prong wins even if the probe then died, and a probe that dies with
nothing fired is terminal for its rung rather than re-probable — otherwise "it crashed
before the detector saw anything" would buy the retry V1 exists to refuse.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import pytest
from aero.adapters.precice.logs import DivergenceFinding, DivergenceReport
from aero.vv.fsi.hg2007_flexible_foil import adr041_rung_verdict

pytestmark = pytest.mark.stage_20

_REPO_ROOT = Path(__file__).resolve().parents[2]


def _driver():  # type: ignore[no-untyped-def]
    sys.path.insert(0, str(_REPO_ROOT / "scripts"))
    import stage20_hg2007_flexible_foil  # type: ignore[import-not-found]

    return stage20_hg2007_flexible_foil


def _report(verdict: str, *, fired: bool = False, **kw: Any) -> DivergenceReport:
    findings = (
        (
            DivergenceFinding(
                prong="parity",
                fired_at_window=1660,
                value=10.14,
                limit=4.0,
                detail="two consecutive active chunks over the limit",
            ),
        )
        if fired
        else ()
    )
    defaults: dict[str, Any] = {
        "n_windows": 8000,
        "complete_chunks": 395,
        "active_chunks": 390,
        "active_fraction": 0.987,
        "reason": "reason",
    }
    defaults.update(kw)
    return DivergenceReport(verdict=verdict, findings=findings, **defaults)


def test_a_fired_prong_wins_even_when_the_probe_then_died() -> None:
    """The signature is what the ladder tests; a death on top of it adds nothing."""
    verdict, _ = adr041_rung_verdict(_report("precursor", fired=True), completed=False)
    assert verdict == "recurrence-detected"


def test_a_death_with_nothing_fired_is_terminal_not_re_probable() -> None:
    """Otherwise an early crash buys the retry V1 exists to refuse.

    Attempt 1 died; determinism is divergent; MALLOC_CHECK_ may abort earlier at a
    different site. This is the most likely D-A outcome and it must not be a free re-roll.
    """
    verdict, why = adr041_rung_verdict(_report("clean"), completed=False)
    assert verdict == "died-undiagnosed"
    assert "V1(a)" in why


def test_a_completed_clean_probe_eliminates() -> None:
    verdict, _ = adr041_rung_verdict(_report("clean"), completed=True)
    assert verdict == "eliminated"


def test_an_inert_detector_is_inconclusive_not_elimination() -> None:
    """The rigid arm's shape: healthy-looking because nothing was measurable."""
    verdict, _ = adr041_rung_verdict(
        _report("inconclusive", active_chunks=182, active_fraction=0.048), completed=True
    )
    assert verdict == "inconclusive"


def test_a_short_or_truncated_probe_is_inconclusive() -> None:
    verdict, _ = adr041_rung_verdict(
        _report("no-data", complete_chunks=0, active_chunks=0, active_fraction=0.0), completed=True
    )
    assert verdict == "inconclusive"


def _rung_case(tmp_path: Path, *, per_window: dict[int, float], rung: str | None = "D-A") -> Path:
    """A submission record plus the case tree its Solid.log lives in."""
    driver = _driver()
    case_host = tmp_path / "run"
    case_root = case_host / "tutorial"
    case_root.mkdir(parents=True)
    marker = (
        "---[precice] \x1b[0m it 1 (min: 1, max: 50), time-window {w}, "
        "t {t} (max: 0.16), Dt 2e-05, max-dt 2e-05\n"
    )
    lines = []
    for window in sorted(per_window):
        lines.append(marker.format(w=window, t=window * 2e-5))
        lines.append(f" largest residual force= {per_window[window]:.6f} in node 2030 and dof 2\n")
    (case_root / "Solid.log").write_text("".join(lines), encoding="utf-8")

    submission = {
        "schema": driver.SUBMISSION_SCHEMA,
        "adr": "ADR-041",
        "adr041_rung": rung,
        "note": driver.ADR041_PROBE_NOTE,
        "observability": {"core_dumps": True, "malloc_check": True},
        "run_id": "hg2007_flexible_foil-fake",
        "session": "fsi-hg2007_flexible_foil-fake",
        "host": "aero-dev",
        "arm": "flexible",
        "rung": "mid",
        "spec_knobs": {"max_time": max(per_window) * 2e-5, "time_window_size": 2e-05},
        "case_host_path": str(case_host),
    }
    if rung is None:
        del submission["adr041_rung"]
    path = tmp_path / "submission.json"
    path.write_text(json.dumps(submission), encoding="utf-8")
    return path


class _Status:
    def __init__(self, returncode: int, text: str) -> None:
        self.returncode = returncode
        self.stdout = text
        self.stderr = ""


def test_evaluating_a_rung_writes_the_series_the_verdict_and_the_bounds(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    driver = _driver()
    values = {w: 5.0 for w in range(1, 301)}
    submission = _rung_case(tmp_path, per_window=values)
    monkeypatch.setattr(driver, "_run_long", lambda *a, **k: _Status(0, "session: done"))

    rc = driver._adr041_evaluate(driver.argparse.Namespace(adr041_evaluate=submission))

    assert rc == 0
    record = json.loads((tmp_path / "run" / "adr041-D-A-verdict.json").read_text(encoding="utf-8"))
    assert record["verdict"] == "eliminated"
    assert record["rung"] == "D-A"
    assert record["note"] == driver.ADR041_PROBE_NOTE
    assert record["observability"] == {"core_dumps": True, "malloc_check": True}
    # the bounds ride with the verdict, so the decision is re-derivable without the driver
    assert record["bounds"]["parity_ratio_limit"] == 4.0
    assert record["bounds"]["activation_floor_n"] == 1.0
    assert record["bounds"]["grid_start_window"] == 101

    tsv = (tmp_path / "run" / "adr041-D-A-solid-residuals.tsv").read_text(encoding="utf-8")
    header, first = tsv.splitlines()[0], tsv.splitlines()[1]
    assert header.split("\t") == ["window", "n_resid", "max_abs_resid", "argmax_node", "n_noconv"]
    assert first.split("\t")[0] == "1"


def test_a_running_probe_has_no_verdict_yet(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """V1 spends the rung's one verdict when it is taken; taking it early spends it wrong."""
    driver = _driver()
    submission = _rung_case(tmp_path, per_window={w: 5.0 for w in range(1, 301)})
    monkeypatch.setattr(driver, "_run_long", lambda *a, **k: _Status(2, "session: running"))

    with pytest.raises(SystemExit, match="still running"):
        driver._adr041_evaluate(driver.argparse.Namespace(adr041_evaluate=submission))


def test_an_ordinary_probe_is_refused_by_the_ladder_rule(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A verdict belongs only to a run the pre-registration scoped as a rung."""
    driver = _driver()
    submission = _rung_case(tmp_path, per_window={w: 5.0 for w in range(1, 301)}, rung=None)
    monkeypatch.setattr(driver, "_run_long", lambda *a, **k: _Status(0, "session: done"))

    with pytest.raises(SystemExit, match="not an ADR-041 ladder rung"):
        driver._adr041_evaluate(driver.argparse.Namespace(adr041_evaluate=submission))


def test_a_short_run_is_died_undiagnosed_not_eliminated(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Reaching fewer windows than were requested is not completing the span."""
    driver = _driver()
    values = {w: 5.0 for w in range(1, 301)}
    submission = _rung_case(tmp_path, per_window=values)
    record = json.loads(submission.read_text(encoding="utf-8"))
    record["spec_knobs"]["max_time"] = 8000 * 2e-5  # requested far more than it reached
    submission.write_text(json.dumps(record), encoding="utf-8")
    monkeypatch.setattr(driver, "_run_long", lambda *a, **k: _Status(0, "session: done"))

    driver._adr041_evaluate(driver.argparse.Namespace(adr041_evaluate=submission))

    written = json.loads((tmp_path / "run" / "adr041-D-A-verdict.json").read_text(encoding="utf-8"))
    assert written["verdict"] == "died-undiagnosed"
    assert written["windows_reached"] == 300
    assert written["windows_requested"] == 8000


# --- ADR-041 V7: the template-of-record fence ------------------------------------------


def test_the_fence_can_only_refuse_never_gate() -> None:
    """V7 adds a conjunct to ADR-040 L5, and a conjunct cannot promote anything.

    The five inputs stay necessary and none is replaced: with the sentinels unfilled the
    derivation is False whatever the template says, and that is the property ADR-039's P4
    mechanism rests on.
    """
    from aero.adapters.precice.template import template_sha256
    from aero.vv.fsi.hg2007_flexible_foil import (
        hg2007_case_spec,
        is_gated_configuration_040,
        is_template_of_record,
    )

    spec = hg2007_case_spec(
        arm="flexible",
        rung="mid",
        time_window_size=2e-05,
        max_time=0.16,
        wall_clock_ceiling_s=43200,
        numerics_label="adr040-candidate",
        mpi_ranks=4,
    )

    assert is_template_of_record(spec.source.template_sha256)
    assert is_template_of_record(template_sha256())
    assert not is_template_of_record("0" * 64)
    # the sentinels are unfilled, so the five-input predicate is False and so is `gated` --
    # the fence has not made anything gated, and cannot.
    assert not is_gated_configuration_040(
        rung="mid",
        time_window_size=2e-05,
        max_time=0.16,
        numerics_label="adr040-candidate",
        mpi_ranks=4,
    )
    assert spec.gated is False


def test_a_non_record_template_can_never_carry_the_gated_verdict(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The fence lives in the FACTORY, not only at the submission boundary.

    `--probe` submits with `gated_intent=False`, so a boundary-only check would let a
    probe at the gated five-tuple mint a bundle claiming `gated=True` the moment B2's
    sentinels were filled — on a coupling template the campaign never adopted.
    """
    import aero.vv.fsi.hg2007_flexible_foil as campaign

    # Arm the five-input predicate exactly as filling B2's sentinels would.
    monkeypatch.setattr(campaign, "GATED_040_TIME_WINDOW_S", 2e-05)
    monkeypatch.setattr(campaign, "GATED_040_MAX_TIME_S", 0.16)
    monkeypatch.setattr(campaign, "GATED_040_NUMERICS_LABEL", "adr040-candidate")
    monkeypatch.setattr(campaign, "GATED_040_MPI_RANKS", 4)
    knobs = dict(
        arm="flexible",
        rung="mid",
        time_window_size=2e-05,
        max_time=0.16,
        wall_clock_ceiling_s=43200,
        numerics_label="adr040-candidate",
        mpi_ranks=4,
    )

    assert campaign.hg2007_case_spec(**knobs).gated is True

    # ...and now the same five inputs rendered from a template that is not the record.
    monkeypatch.setattr(campaign, "is_template_of_record", lambda _digest: False)
    assert campaign.hg2007_case_spec(**knobs).gated is False


# --- ADR-044 Z1: a completed span with zero activation ---------------------------------


def _inconclusive(**kw: Any) -> DivergenceReport:
    d: dict[str, Any] = {
        "verdict": "inconclusive",
        "n_windows": 8000,
        "complete_chunks": 395,
        "active_chunks": 0,
        "active_fraction": 0.0,
        "contiguous": True,
        "evaluated_windows": (101, 8000),
        "reason": "only 0.0% of chunks reach the 1.0 N activation floor",
    }
    d.update(kw)
    return DivergenceReport(**d)


def test_a_completed_span_with_zero_activation_eliminates() -> None:
    """ADR-044 Z1, the path that exists because success removes the detector's signal.

    The 1.0 N floor does not separate signal from noise: both sick runs of record were
    above it by w135, and the healthy rigid control not until w72261 at FULL amplitude.
    """
    verdict, why = adr041_rung_verdict(_inconclusive(), completed=True)
    assert verdict == "eliminated"
    assert "ADR-044 Z1" in why


def test_z1_is_keyed_to_zero_and_cannot_be_tuned() -> None:
    """One active chunk is not zero. A rule keyed to zero has no dial."""
    verdict, _ = adr041_rung_verdict(
        _inconclusive(active_chunks=1, active_fraction=1 / 395), completed=True
    )
    assert verdict == "inconclusive"


def test_z1_requires_the_probe_to_have_completed_its_span() -> None:
    """A run that died tells us nothing about the span it did not reach."""
    verdict, _ = adr041_rung_verdict(_inconclusive(), completed=False)
    assert verdict == "died-undiagnosed"


def test_z1_requires_the_span_bar_fixed_before_the_result() -> None:
    """A short quiet span is not evidence: every sick run activated by w135.

    The bar is 10x that. A 4000-window fallback probe clears it; a probe that stopped at
    w900 does not, however quiet it was.
    """
    from aero.vv.fsi.hg2007_flexible_foil import ADR044_MIN_EVALUATED_WINDOW

    assert ADR044_MIN_EVALUATED_WINDOW == 1350
    short, _ = adr041_rung_verdict(
        _inconclusive(evaluated_windows=(101, 900), complete_chunks=40), completed=True
    )
    assert short == "inconclusive"
    ok, _ = adr041_rung_verdict(
        _inconclusive(evaluated_windows=(101, 1360), complete_chunks=63), completed=True
    )
    assert ok == "eliminated"


def test_z1_requires_a_contiguous_series_so_zero_is_a_measurement() -> None:
    """A gap makes zero activation an absence of data rather than a fact about the run."""
    verdict, _ = adr041_rung_verdict(_inconclusive(contiguous=False), completed=True)
    assert verdict == "inconclusive"


def test_z1_never_rescues_a_rung_that_diverged() -> None:
    """It can only ADD an elimination path. A fired prong still fails, as before."""
    verdict, _ = adr041_rung_verdict(_report("precursor", fired=True), completed=True)
    assert verdict == "recurrence-detected"
