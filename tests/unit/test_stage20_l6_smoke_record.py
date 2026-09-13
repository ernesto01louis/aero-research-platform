"""The L6 record says what it measured, and refuses to say more than that.

Two jobs. The first is the ordinary one: the four L-clauses passed, on a run that was
actually parallel. The second matters more and is easy to get wrong — this record contains
a `seconds_per_step_solve`, and that number is *not* the campaign's. It comes from a
20-window smoke whose iterations per window are the coupling's start-up transient and
whose wall clock includes the coded function object's first compilation. Only ADR-040 N3
may size B2, so the record carries an admissibility clause and this file pins that it
does — the same guard the N2 and N4 screening records carry, for the same reason.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

pytestmark = pytest.mark.stage_20

_REPO_ROOT = Path(__file__).resolve().parents[2]
_RECORD = _REPO_ROOT / "data/vv/stage20_l6_smoke.json"


def _record() -> dict:
    return json.loads(_RECORD.read_text(encoding="utf-8"))


def test_the_record_is_an_adr040_smoke_and_it_passed() -> None:
    record = _record()
    assert record["adr"] == "ADR-040"
    assert record["clause"] == "L6-smoke"
    assert record["gated"] is False
    assert record["passed"] is True


def test_every_l_clause_passed() -> None:
    clauses = _record()["clauses"]
    assert set(clauses) == {
        "L1_mpirun_inside_the_uid_drop",
        "L2_force_dat_in_the_case_root",
        "L4_processor_count_equals_the_request",
        "L6_both_participants_exited_cleanly",
    }
    assert all(c["passed"] for c in clauses.values())


def test_the_smoke_was_actually_parallel() -> None:
    """A serial run would pass three of the four clauses vacuously."""
    record = _record()
    l4 = record["clauses"]["L4_processor_count_equals_the_request"]
    assert l4["requested"] >= 2
    assert l4["found"] == l4["requested"]
    assert l4["dirs"] == [f"processor{i}" for i in range(l4["requested"])]
    assert record["submission"]["spec_knobs"]["mpi_ranks"] == l4["requested"]
    assert record["submission"]["spec_knobs"]["numerics_label"] == "adr040-candidate"


def test_l2_was_re_measured_on_the_real_coupled_deck() -> None:
    """Session 9's L2 was a fluid-only screen; this deck has a second participant in it."""
    l2 = _record()["clauses"]["L2_force_dat_in_the_case_root"]
    assert len(l2["measured"]) == 1
    (path,) = l2["measured"]
    assert path.endswith("postProcessing/forces1/0/force.dat")
    assert "processor" not in path, "force.dat under processor*/ would break the readout"


def test_the_rank_aware_disk_accounting_is_not_a_no_op() -> None:
    """N5, measured: the maxdepth-3 form reads essentially nothing on a parallel run.

    Not a style change. The time-directory count is the F4 disk projection's input, and
    the projection is what stands between a 20-day wave and a full NFS four days in.
    """
    disk = _record()["n5_rank_aware_disk_accounting"]
    assert disk["time_dirs_maxdepth_4"] > 10 * max(1, disk["time_dirs_maxdepth_3"])


def test_the_record_refuses_to_size_anything() -> None:
    admissibility = _record()["cost"]["admissibility"]
    assert "MAY NOT SIZE ANYTHING" in admissibility
    assert "start-up transient" in admissibility
    assert "N3" in admissibility


def test_the_rank0_cpu_share_is_labelled_as_rank_0s() -> None:
    """It looks exactly like I10's 99.42 % aggregate bound and is a different quantity."""
    cost = _record()["cost"]
    assert 0.0 < cost["rank0_cpu_over_wall"] <= 1.0
    assert "RANK 0" in cost["admissibility"]
    assert "99.42" in cost["admissibility"]
