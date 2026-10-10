"""The ADR-040 driver seams: schema v2, the new knobs, `--submit-040`, and B0.

Four properties, each closing a way a two-day run could end in a raise or a wrong number.

**Any new spec knob must ride in ``spec_knobs``.** ``_reattach`` rebuilds the spec weeks
later by calling ``hg2007_case_spec(**spec_knobs)`` and refuses to collect if the digest
moved. A knob that does not ride there is a knob that makes every collect refuse, and it
would be discovered at the end of the wave rather than at the start.

**A v1 submission must be refused BY NAME.** Handed one, ``_reattach`` would rebuild an
ADR-039-numerics serial spec, get a digest that does not match, and report "the code moved
under a live campaign" -- true, but the wrong diagnosis and the wrong action.

**``--submit`` keeps refusing forever and ``--submit-040`` is its own mode.** ADR-039's
sentinels can never be filled (its campaign was measured infeasible), so the two paths
cannot share one.

**B0 is enforced, not just declared.** A pre-declared ceiling the driver does not check is
a wish.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest
from aero.adapters.precice.case import spec_config_digest
from aero.vv.fsi.hg2007_flexible_foil import hg2007_case_spec

pytestmark = pytest.mark.stage_20

_REPO_ROOT = Path(__file__).resolve().parents[2]


def _driver():  # type: ignore[no-untyped-def]
    sys.path.insert(0, str(_REPO_ROOT / "scripts"))
    import stage20_hg2007_flexible_foil  # type: ignore[import-not-found]

    return stage20_hg2007_flexible_foil


def test_spec_knobs_are_exactly_what_rebuilds_the_spec() -> None:
    """The contract `_reattach` depends on, checked without a cluster.

    Written as a round trip rather than a field list: the failure being prevented is a
    knob that reaches the spec by some other route, and only a rebuild-and-compare notices
    that.
    """
    knobs = {
        "arm": "flexible",
        "rung": "mid",
        "time_window_size": 2.0e-5,
        "max_time": 0.01,
        "wall_clock_ceiling_s": 259200,
        "numerics_label": "adr040-candidate",
        "mpi_ranks": 4,
    }
    original = hg2007_case_spec(**knobs)  # type: ignore[arg-type]
    rebuilt = hg2007_case_spec(**json.loads(json.dumps(knobs)))  # type: ignore[arg-type]
    assert spec_config_digest(original) == spec_config_digest(rebuilt)

    # And the two new knobs actually MOVE the digest — otherwise riding in spec_knobs
    # would be ceremony rather than a contract.
    baseline = hg2007_case_spec(**(knobs | {"numerics_label": "adr039-baseline"}))  # type: ignore[arg-type]
    serial = hg2007_case_spec(**(knobs | {"mpi_ranks": 1}))  # type: ignore[arg-type]
    digests = {spec_config_digest(s) for s in (original, baseline, serial)}
    assert len(digests) == 3


def test_a_v1_submission_is_refused_by_naming_the_bump(tmp_path: Path) -> None:
    driver = _driver()
    path = tmp_path / "v1.json"
    path.write_text(json.dumps({"schema": "stage20-submission-v1"}), encoding="utf-8")
    with pytest.raises(SystemExit, match="stage20-submission-v2"):
        driver._submission(path)
    with pytest.raises(SystemExit, match="numerics_label and mpi_ranks"):
        driver._submission(path)


def test_a_v2_submission_is_accepted(tmp_path: Path) -> None:
    driver = _driver()
    path = tmp_path / "v2.json"
    path.write_text(json.dumps({"schema": driver.SUBMISSION_SCHEMA, "x": 1}), encoding="utf-8")
    assert driver._submission(path)["x"] == 1


def test_an_unknown_schema_is_refused_too(tmp_path: Path) -> None:
    driver = _driver()
    path = tmp_path / "other.json"
    path.write_text(json.dumps({"schema": "something-else"}), encoding="utf-8")
    with pytest.raises(SystemExit, match="not a stage20-submission-v2 file"):
        driver._submission(path)


def test_submit_040_refuses_while_its_own_sentinels_are_none() -> None:
    from aero.vv.fsi.hg2007_flexible_foil import GATED_040_MAX_TIME_S, GATED_040_TIME_WINDOW_S

    if GATED_040_TIME_WINDOW_S is not None and GATED_040_MAX_TIME_S is not None:
        pytest.skip("ADR-040's sentinels are filled; the refusal branch no longer applies")
    driver = _driver()
    with pytest.raises(SystemExit, match="ADR-040 sentinels are None"):
        driver.main(["--submit-040", "flexible", "--host", "nowhere"])


def test_submit_still_refuses_on_adr_039s_own_sentinels() -> None:
    """The ADR-039 path is untouched: its refusal is unchanged and permanent."""
    driver = _driver()
    with pytest.raises(SystemExit, match="sentinels are None"):
        driver.main(["--submit", "flexible", "--host", "nowhere"])


def test_the_two_submit_modes_are_separate_refusals() -> None:
    """Distinct messages, so an operator learns which pre-registration is pending."""
    driver = _driver()
    with pytest.raises(SystemExit) as adr039:
        driver.main(["--submit", "flexible", "--host", "nowhere"])
    with pytest.raises(SystemExit) as adr040:
        driver.main(["--submit-040", "flexible", "--host", "nowhere"])
    assert "ADR-039 B2" in str(adr039.value)
    assert "ADR-040 B2" in str(adr040.value)


def test_a_probe_above_b0_is_refused() -> None:
    driver = _driver()
    with pytest.raises(SystemExit, match="exceeds ADR-040 B0"):
        driver.main(
            [
                "--probe",
                "flexible",
                "mid",
                "--probe-dt",
                "2e-5",
                "--probe-windows",
                "76090",
                "--ranks",
                "4",
                "--numerics",
                "adr040-candidate",
                "--timeout",
                str(driver.PROBE_CEILING_040_S + 1),
                "--host",
                "nowhere",
            ]
        )


def test_a_probe_whose_windows_do_not_round_trip_is_refused() -> None:
    """50725 x 2e-5 does not survive `.13e`; 50726 does (handoff §6.30)."""
    driver = _driver()
    assert float(format(50725 * 2.0e-5, ".13e")) != 50725 * 2.0e-5
    assert float(format(50726 * 2.0e-5, ".13e")) == 50726 * 2.0e-5
    with pytest.raises(SystemExit, match="does not survive"):
        driver.main(
            [
                "--probe",
                "flexible",
                "mid",
                "--probe-dt",
                "2e-5",
                "--probe-windows",
                "50725",
                "--host",
                "nowhere",
            ]
        )


def test_the_n3_window_count_round_trips() -> None:
    """The count ADR-040 N3 pre-registers, checked here so a typo is a CI failure."""
    assert 76090 * 2.0e-5 == 1.5218
    assert float(format(1.5218, ".13e")) == 1.5218
