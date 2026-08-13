"""N3 is in flight, and these two digests are what make it collectable.

``_reattach`` rebuilds the spec weeks after the submit by calling
``hg2007_case_spec(**submission["spec_knobs"])`` and refuses to collect unless the rebuilt
spec's ``config_hash`` still equals the one recorded at submit time. So any edit to
``CoupledCaseSpec``, ``ParticipantSpec``, ``FlexibleFoilSpec``, ``CalculiXSolidSpec`` or
``AuthoredSource`` -- including one that adds a field nothing reads -- silently converts a
running multi-day solve into an uncollectable one. The symptom appears only at the collect,
which is three days and 76090 windows after the mistake.

This file is the ADR-039 gate-block digest pin applied to a live run rather than to a
document: it lands BEFORE the work that happens beside it, it asserts only what is already
true, and it turns "do not move the HG spec's config_hash" from a rule someone has to
remember into a named CI failure.

The knobs and the expected digests are hard-coded rather than read from the submission
JSONs on the NFS mount, for two reasons. A test that read the record would move with it,
which is exactly the drift being guarded against; and CI has no NFS mount, so a
mount-gated test would skip on the only machine that runs it on every push.

Provenance of the four values below -- read from the submissions the running jobs were
launched with, ``/mnt/aero-nfs/runs/<run_id>/n3-submission.json``, both
``schema=stage20-submission-v2``, submitted 2026-08-12 23:01 UTC:

* ``hg2007_flexible_foil-20260812-230102`` -- session ``fsi-hg2007_flexible_foil-20260812-230102``
* ``hg2007_rigid_foil-20260812-230109``    -- session ``fsi-hg2007_rigid_foil-20260812-230109``

Each run's own ``tutorial/aero-manifest.json`` carries the same digest under
``authored.spec_sha256``, written by the materializer at prepare time, so the pin has an
independent on-disk witness that did not come through the submission record.

**When N3 has been collected and no live run depends on these bytes, delete this file.** A
digest pin for a run nobody will ever collect again is a pin that only breaks builds.
"""

from __future__ import annotations

import pytest
from aero.adapters.precice.case import spec_config_digest
from aero.vv.fsi.hg2007_flexible_foil import hg2007_case_spec

pytestmark = pytest.mark.stage_20

#: EXACTLY the ``spec_knobs`` block of each in-flight submission, transcribed. The two arms
#: differ in ``arm`` alone; everything else is the ADR-040 N3 configuration (N1 stack, L3
#: rank count, dt 2e-5, 76090 windows = 1.5218 s, B0's 96 h ceiling).
_LIVE: dict[str, tuple[dict[str, object], str]] = {
    "flexible": (
        {
            "arm": "flexible",
            "rung": "mid",
            "time_window_size": 2e-05,
            "max_time": 1.5218,
            "wall_clock_ceiling_s": 345600,
            "numerics_label": "adr040-candidate",
            "mpi_ranks": 4,
        },
        "bfc60a49d85e81d909ebcc87da6140a12a35c4ea153cd810fbec1d3a29cd1a8c",
    ),
    "rigid": (
        {
            "arm": "rigid",
            "rung": "mid",
            "time_window_size": 2e-05,
            "max_time": 1.5218,
            "wall_clock_ceiling_s": 345600,
            "numerics_label": "adr040-candidate",
            "mpi_ranks": 4,
        },
        "ed1ba571cb3d4a69c7ec24ea9a29658c0d3e7154eb0bdad01c81bb2ccab2117c",
    ),
}


@pytest.mark.parametrize("arm", sorted(_LIVE))
def test_the_running_arms_spec_still_rebuilds_to_the_submitted_digest(arm: str) -> None:
    """The one assertion that keeps N3 collectable.

    If this fails, do NOT update the constant. The correct response is to revert whatever
    moved the spec serialization: the record on disk describes the run that is actually
    executing, and editing the expectation to match new code would make ``_reattach`` pass
    while comparing a spec that is not the one that ran.
    """
    knobs, expected = _LIVE[arm]
    assert spec_config_digest(hg2007_case_spec(**knobs)) == expected  # type: ignore[arg-type]


def test_the_two_arms_are_distinguishable_by_digest() -> None:
    """The pin would be satisfiable by a degenerate hash; this says it is not.

    The arms differ in exactly one number -- the plate's b/c -- and that number is the
    gated increment's entire subject. A serialization that collapsed them would make both
    assertions above pass while the campaign compared an arm against itself.
    """
    digests = {
        arm: spec_config_digest(hg2007_case_spec(**knobs)) for arm, (knobs, _) in _LIVE.items()
    }  # type: ignore[arg-type]
    assert len(set(digests.values())) == len(digests)
