"""`--size-040`: the wiring between collected bundles and ADR-040 B2's sizing rule.

The rule itself is pure and already tested. What this file guards is the WIRING, because
the wiring is the part that can quietly make a refusal unreachable — and every refusal
here exists because a specific wrong number nearly got published once.

Three properties:

**The mode still refuses for every reason the rule refuses for.** Six of the rule's
refusals had no ADR-040 coverage at all before this file — they existed only against the
ADR-039 twin, on different code lines — and a mode that swallowed or reordered them would
look like it worked right up until it sized a campaign it should have refused.

**The stack and the rank count are EXPECTATIONS, not observations.** The rule refuses a
confirmation measured on another stack or at another rank count. It does that by comparing
the record against what it was told to expect, so a mode that told it "expect whatever the
record says" would turn that refusal into a tautology.

**It fills nothing.** B1/B2/B3 and the four `GATED_040_*` sentinels are filled by the
commit that adds `data/vv/stage20_n3_confirmation.json`, after the operator's B3 ceiling
decision. A sizing mode that filled them would collapse two deliberate acts into one.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import pytest
from aero.vv.fsi.hg2007_flexible_foil import (
    ANALYSIS_DISCARD_S,
    ANALYSIS_MIN_CYCLES,
    FREQUENCY_HZ,
    GATED_040_MAX_TIME_S,
    GATED_040_MPI_RANKS,
    GATED_040_NUMERICS_LABEL,
    GATED_040_TIME_WINDOW_S,
)

from tests.unit._stage20_bundles import DT, admissible_record, bundle, i4_block, i7_block

pytestmark = pytest.mark.stage_20

_REPO_ROOT = Path(__file__).resolve().parents[2]

#: Comfortably above the ~20-day projection the fixture rate implies, so the ceiling is
#: not what refuses except in the test that means it to.
_CEILING_S = 30 * 24 * 3600


def _driver():  # type: ignore[no-untyped-def]
    sys.path.insert(0, str(_REPO_ROOT / "scripts"))
    import stage20_hg2007_flexible_foil  # type: ignore[import-not-found]

    return stage20_hg2007_flexible_foil


def _run(
    tmp_path: Path,
    bundles: list[dict[str, Any]],
    *,
    ceiling_s: int | None = _CEILING_S,
) -> tuple[int, dict[str, Any]]:
    paths = []
    for i, b in enumerate(bundles):
        p = tmp_path / f"bundle_{i}.json"
        p.write_text(json.dumps(b, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        paths.append(str(p))
    out = tmp_path / "size.json"
    argv = ["--size-040", *paths, "--out", str(out)]
    if ceiling_s is not None:
        argv += ["--ceiling-s", str(ceiling_s)]
    rc = _driver().main(argv)
    written = json.loads(out.read_text(encoding="utf-8")) if out.exists() else {}
    return rc, written


# --------------------------------------------------------------------------------------
# The happy path, and what it does NOT do
# --------------------------------------------------------------------------------------


def test_a_complete_record_sizes_a_campaign(tmp_path: Path) -> None:
    rc, record = _run(tmp_path, admissible_record())
    assert rc == 0, record.get("verdict")
    assert record["verdict"] == "SIZED"
    sized = record["sized_campaign"]
    assert sized["rung"] == "mid"
    assert sized["time_window_size"] == DT
    assert sized["settled_cycles"] == 20
    assert set(sized["projected_wall_s_by_arm"]) == {"flexible", "rigid"}


def test_sizing_fills_nothing(tmp_path: Path) -> None:
    """The sentinels are filled by a later, deliberate commit — never as a side effect."""
    _run(tmp_path, admissible_record())
    assert GATED_040_TIME_WINDOW_S is None
    assert GATED_040_MAX_TIME_S is None
    assert GATED_040_NUMERICS_LABEL is None
    assert GATED_040_MPI_RANKS is None
    assert not (_REPO_ROOT / "data/vv/stage20_n3_confirmation.json").exists()


def test_the_sized_campaign_is_long_enough_for_its_own_readout(tmp_path: Path) -> None:
    """The cross-check the Q1 collect exposed.

    `--collect` runs `analyse_limit_cycle` with the S2 discard on the watch-point base
    before it reads anything else, so a campaign shorter than the discard plus
    ANALYSIS_MIN_CYCLES settled cycles would be refused by its own readout AFTER it had
    been paid for. The rule builds max_time from the discard plus 20 settled cycles, so
    20 >= 10 makes this hold by construction today — which is exactly why it is asserted
    rather than assumed, because ADR-040 B4 permits cutting the settled cycles to 10.
    """
    _, record = _run(tmp_path, admissible_record())
    needed = ANALYSIS_DISCARD_S + ANALYSIS_MIN_CYCLES / FREQUENCY_HZ
    assert record["sized_campaign"]["max_time"] >= needed


# --------------------------------------------------------------------------------------
# The refusal battery — every reason the rule refuses, driven through the mode
# --------------------------------------------------------------------------------------


def test_the_ceiling_is_required(tmp_path: Path) -> None:
    """ADR-040 B3: the ceiling is an operator decision taken against a measured rate."""
    with pytest.raises(SystemExit, match="requires --ceiling-s"):
        _run(tmp_path, admissible_record(), ceiling_s=None)


def test_a_transient_probe_is_refused(tmp_path: Path) -> None:
    record = admissible_record()
    record[0]["i4"] = i4_block(windows_completed=40_000)
    rc, written = _run(tmp_path, record)
    assert rc == 1
    assert "read from a transient" in written["verdict"]


def test_a_probe_that_did_not_exit_cleanly_is_refused(tmp_path: Path) -> None:
    record = admissible_record()
    record[0]["i4"] = i4_block(stopped_by="ceiling")
    rc, written = _run(tmp_path, record)
    assert rc == 1
    assert "not 'all-exited'" in written["verdict"]


def test_probes_at_two_dts_are_refused(tmp_path: Path) -> None:
    """dt is fixed across rungs, so two dts means two campaigns."""
    record = admissible_record()
    record[2]["i7"] = i7_block(rung="fine", dt=3.5e-4)
    record[2]["i4"] = i4_block(rung="fine", dt=3.5e-4)
    rc, written = _run(tmp_path, record)
    assert rc == 1
    assert "disagree on dt" in written["verdict"]


def test_a_dt_that_does_not_round_trip_is_refused(tmp_path: Path) -> None:
    """CalculiX truncates numeric fields at 20 characters (handoff §6.17)."""
    bad = 2.0000000000000012e-05
    assert float(format(bad, ".13e")) != bad, "pick a dt that genuinely fails the round trip"
    record = [
        bundle(arm=a, rung=r, n3=n)
        for a, r, n in (
            ("flexible", "mid", True),
            ("rigid", "mid", True),
            ("flexible", "fine", False),
        )
    ]
    for b in record:
        b["i7"] = i7_block(arm=b["i7"]["arm"], rung=b["i7"]["rung"], dt=bad)
        b["i4"] = i4_block(arm=b["i4"]["arm"], rung=b["i4"]["rung"], dt=bad)
        if "n3" in b:
            b["n3"]["dt"] = bad
    rc, written = _run(tmp_path, record)
    assert rc == 1
    assert "round trip" in written["verdict"]


def test_the_missing_fine_rung_probe_is_refused(tmp_path: Path) -> None:
    """THE refusal a real record hits today: N3 covers only the mid rung, on both arms.

    The fine-rung I7 probe can only run AFTER N3 — nothing else may share aero-dev while
    N3 measures a contention rate — so this refusal stands until then, by design.
    """
    rc, written = _run(tmp_path, admissible_record()[:2])
    assert rc == 1
    assert "no I7 probe for arm='flexible' rung='fine'" in written["verdict"]
    assert "measured, not assumed" in written["verdict"]


def test_a_failing_courant_probe_is_refused(tmp_path: Path) -> None:
    record = admissible_record()
    record[2]["i7"] = i7_block(rung="fine", max_courant_post_ramp=1.31)
    rc, written = _run(tmp_path, record)
    assert rc == 1
    assert "never adjusts" in written["verdict"]


def test_probes_without_a_confirmation_are_refused(tmp_path: Path) -> None:
    """Only a coupled confirmation may size (ADR-040 N3) — an I7 record alone may not."""
    record = [
        bundle(arm="flexible", rung="mid", n3=False),
        bundle(arm="rigid", rung="mid", n3=False),
        bundle(arm="flexible", rung="fine", n3=False),
    ]
    rc, written = _run(tmp_path, record)
    assert rc == 1
    assert "only a coupled confirmation may size" in written["verdict"]


def test_a_ramp_phase_confirmation_is_refused(tmp_path: Path) -> None:
    """The state N3 is in today — and the reason `--project-n3` exists."""
    from tests.unit._stage20_bundles import n3_block_inside_the_ramp

    record = admissible_record()
    record[0]["n3"] = n3_block_inside_the_ramp(concurrent_with=["hg2007_other_flexible-x"])
    rc, written = _run(tmp_path, record)
    assert rc == 1
    assert "ramp-phase rate may not size" in written["verdict"]


def test_an_uncontended_confirmation_is_refused(tmp_path: Path) -> None:
    record = admissible_record()
    record[0]["n3"]["concurrent_with"] = []
    rc, written = _run(tmp_path, record)
    assert rc == 1
    assert "measured alone" in written["verdict"]


def test_a_projection_over_the_ceiling_is_a_budget_no_go(tmp_path: Path) -> None:
    rc, written = _run(tmp_path, admissible_record(), ceiling_s=3600)
    assert rc == 1
    assert "does not fit the per-wave ceiling" in written["verdict"]
    assert "NO-GO" in written["verdict"]


# --------------------------------------------------------------------------------------
# The expectations are the driver's, not the record's
# --------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("key", "value"),
    [("numerics_label", "adr039-baseline"), ("mpi_ranks", 8)],
    ids=["wrong-stack", "wrong-rank-count"],
)
def test_a_confirmation_from_another_campaign_is_refused(
    tmp_path: Path, key: str, value: object
) -> None:
    """Reachable ONLY because the mode does not read these back off the bundle.

    If `--size-040` sourced the expected stack and rank count from the record it was
    handed, this refusal could never fire — the record would always match itself.
    """
    record = admissible_record()
    for b in record[:2]:
        b["n3"][key] = value
    rc, written = _run(tmp_path, record)
    assert rc == 1
    assert "not at the pre-registered" in written["verdict"]


def test_the_expectations_are_the_ones_adr040_pre_registers() -> None:
    """N1's stack token and L3's rank count, checked against the gate block itself.

    The constants are duplicated out of the ADR into the driver so the sizing call can be
    read without cross-referencing; this is what stops the duplicate from drifting.
    """
    driver = _driver()
    block = driver.PREREGISTERED_GATE_BLOCK_040
    assert f"label {driver.SIZING_040_NUMERICS_LABEL}" in block
    assert f"{driver.SIZING_040_MPI_RANKS} fluid ranks each" in block
    assert f"{driver.SIZING_040_SETTLED_CYCLES} settled cycles" in block
    assert driver.SIZING_040_SETTLED_CYCLES >= ANALYSIS_MIN_CYCLES


def test_the_record_says_where_its_expectations_came_from(tmp_path: Path) -> None:
    """A bundle that did not record this would be unauditable a month later."""
    _, record = _run(tmp_path, admissible_record())
    expectations = record["expectations"]
    assert expectations["numerics_label"] == "adr040-candidate"
    assert expectations["mpi_ranks"] == 4
    assert expectations["ceiling_s"] == _CEILING_S
    assert "never from the bundles" in expectations["note"]
