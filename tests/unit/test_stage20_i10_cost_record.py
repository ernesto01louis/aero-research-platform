"""The I10 cost-split record — the evidence ADR-040 argues from, bound where it matters.

ADR-040 changes the campaign's numerics on the strength of this record. Three things
therefore have to hold in CI rather than in a session's memory: the record describes the
runs it claims to (provenance and source digest), its bounds are numbers rather than
prose, and it carries the pre-registration that was in force WHEN THOSE RUNS RAN.
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.stage_20

_REPO_ROOT = Path(__file__).resolve().parents[2]
_RECORD = _REPO_ROOT / "data/vv/stage20_i10_cost_split.json"
_I4 = _REPO_ROOT / "data/vv/stage20_i4_calibration.json"


def _record() -> dict:
    return json.loads(_RECORD.read_text(encoding="utf-8"))


def _driver_module():  # type: ignore[no-untyped-def]
    sys.path.insert(0, str(_REPO_ROOT / "scripts"))
    import stage20_hg2007_flexible_foil  # type: ignore[import-not-found]

    return stage20_hg2007_flexible_foil


def test_the_provenance_is_the_underlying_runs_not_a_fresh_tuple() -> None:
    """Recomputing the four-tuple here would staple today's SHA to August's bytes.

    The runs are finished. Their provenance is a property of what ran, so the record
    copies it verbatim from the I4 record rather than calling ``compute_provenance``.
    """
    record = _record()
    i4 = json.loads(_I4.read_text(encoding="utf-8"))

    for arm in ("flexible", "rigid"):
        assert (
            record["arms"][arm]["provenance"]
            == i4["collection_bundles"][arm]["submission"]["provenance"]
        )
        assert (
            record["arms"][arm]["run_id"] == i4["collection_bundles"][arm]["submission"]["run_id"]
        )


def test_the_record_cannot_drift_from_its_source() -> None:
    """The logs are not committed (11.7 MB), so the derivation must be auditable by digest."""
    record = _record()
    assert record["derived_from"]["record"]["path"] == "data/vv/stage20_i4_calibration.json"
    assert (
        record["derived_from"]["record"]["sha256"] == hashlib.sha256(_I4.read_bytes()).hexdigest()
    )
    for arm in ("flexible", "rigid"):
        entry = record["derived_from"]["logs"][arm]
        assert entry["path"].endswith("/Fluid.log")
        assert len(entry["sha256"]) == 64
        assert entry["bytes"] > 0


def test_the_overhead_levers_are_bounded_by_numbers_not_by_prose() -> None:
    """The two refutations, as the record states them.

    ``forces1`` write scheduling and every other I/O-shaped lever cannot beat the
    non-compute wall fraction; fluid subcycling cannot beat that plus the per-step
    overhead share, because the total fluid step-solve count is invariant in K. Both are
    an order of magnitude below the 15.5x the campaign needs, and that is why session 7's
    two leading hypotheses are dead.
    """
    record = _record()
    non_compute = record["bounds"]["non_compute_wall_fraction"]
    overhead = record["bounds"]["per_step_overhead_share"]

    assert non_compute["flexible"] < 0.01
    assert non_compute["rigid"] < 0.01
    # Subcycling's honest ceiling: the non-compute wall plus the per-step overhead.
    assert non_compute["flexible"] + overhead["flexible"] < 0.10
    # A speed-up of 15.5x needs 93.5 % of the wall removed. Neither bound is close.
    assert non_compute["flexible"] + overhead["flexible"] < 1.0 - 1.0 / 15.5


def test_the_bounds_are_labelled_as_rate_dependent() -> None:
    """A 0.58 % residual at 16 s/window is not a 0.58 % residual at 1.5 s/window.

    Every lever that shrinks the fluid raises the relative weight of what is left, so a
    bound carried forward unchanged would refute a lever that has since become real.
    """
    note = _record()["bounds"]["note"]
    assert "re-read" in note
    assert "measured rate" in note.lower()


def test_the_pressure_solve_is_what_remains() -> None:
    record = _record()
    for arm, floor in (("flexible", 0.80), ("rigid", 0.75)):
        attribution = record["arms"][arm]["attribution"]
        assert attribution["share_by_group"]["gamg_pressure"] > floor
        total = sum(attribution["share_by_group"].values()) + attribution["intercept_share"]
        assert total == pytest.approx(1.0, abs=1e-9)
        assert attribution["r_squared"] > 0.8


def test_the_disk_growth_is_the_frd_that_nothing_reads() -> None:
    """The handoff attributed the footprint to ``forces1``'s untracked field writes.

    Measured, it is the CalculiX ``.frd`` at ~78 %, and no code in this repo reads a
    ``.frd``; the fluid field writes are under a tenth. The lever is a FREQUENCY card on
    the solid deck, not a write-scheduling change on the fluid.
    """
    record = _record()
    for arm in ("flexible", "rigid"):
        shares = record["arms"][arm]["disk"]["share_by_term"]
        assert shares["solid_results_frd"] > 0.70
        assert shares["fluid_time_directories"] < 0.10
        assert shares["solid_results_frd"] > 5 * shares["fluid_time_directories"]


def test_the_embedded_block_is_adr039s_because_these_are_adr039_runs() -> None:
    """The measurement predates ADR-040; attaching ADR-040's block would misdate it."""
    record = _record()
    assert record["adr"] == "ADR-039"
    assert record["gated"] is False
    assert record["preregistered_gate_block"] == _driver_module().PREREGISTERED_GATE_BLOCK
