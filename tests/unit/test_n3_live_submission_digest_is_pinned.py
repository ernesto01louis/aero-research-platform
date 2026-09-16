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
            # The adopted stack (ADR-043/ADR-044). Pinned explicitly rather than
            # inherited, so a later default move announces itself here.
            "hht_alpha": -0.05,
        },
        "be97434a412c953546939fd057c1ac89f65fc4c3c702d6841ed96473fc6f7b9a",
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
            # The adopted stack (ADR-043/ADR-044). Pinned explicitly rather than
            # inherited, so a later default move announces itself here.
            "hht_alpha": -0.05,
        },
        "5fcc563f529a6981a920b7cf1a1187c7ba29426867808f5c3bb33e78200da9e8",
    ),
}


#: The digests these knobs produced in earlier generations of the serialization -- what
#: the attempt-1 and attempt-2 submissions on NFS still name. Kept so each supersession is
#: checkable rather than merely asserted; nothing rebuilds to them any more, which is the
#: point.
_SUPERSEDED = {
    "flexible": (
        # attempt 1, pre-hht_alpha-field
        "bfc60a49d85e81d909ebcc87da6140a12a35c4ea153cd810fbec1d3a29cd1a8c",
        # the same knobs after ADR-043 added the field, still at alpha 0.0
        "0891e66d4ef5d44d127a223d042d406e39479b18a3aa84b290de71123df71f25",
        # N3 attempt 2 (hg2007_flexible_foil-20260914-122525, died w21 897, 2026-09-15):
        # alpha -0.05 under renderer version "1", before ADR-045 A1 bumped it
        "bebec2d3a1203f9d1b3d44ae327af26357a67872e9f5dd52e1ce53c8682001d7",
        # renderer "2" on the UNPATCHED solid container of record (2026-09-15, before
        # ADR-045 R1's rebuild moved SOLID_SIF_OF_RECORD to calculix-precice-adr045.sif)
        "162b2d25b0509c1afe2cf6efc24b57bc44aa30a981a113c8f7d8f80d82f4b651",
    ),
    "rigid": (
        "ed1ba571cb3d4a69c7ec24ea9a29658c0d3e7154eb0bdad01c81bb2ccab2117c",
        "fae61ffaf316e37fa7110a49f4fd51cd484d6cf2a665b54b4f4012fd55852c40",
        # N3 attempt 2 (hg2007_rigid_foil-20260914-122543, killed at w60 622 by the stop
        # rule): renderer version "1"
        "7724059880bffc5c7cd38489e113f1db4e9bdf5de9eeb7615e30109a0ce99cdb",
        # renderer "2" on the unpatched solid container of record
        "f89d8e6b6b2c8654ad2627b6504282ef11ef37c79ff14c805c4221ae623368ff",
    ),
}


@pytest.mark.parametrize("arm", sorted(_LIVE))
def test_the_attempt1_records_are_superseded_not_silently_broken(arm: str) -> None:
    """The declared cost of ADR-043, asserted so it cannot happen by accident later.

    A digest that moved without anyone noticing is indistinguishable from one that moved
    because an ADR said so. This states which of the two happened.
    """
    knobs, current = _LIVE[arm]
    assert current not in _SUPERSEDED[arm]
    assert spec_config_digest(hg2007_case_spec(**knobs)) not in _SUPERSEDED[arm]  # type: ignore[arg-type]


@pytest.mark.parametrize("arm", sorted(_LIVE))
def test_the_running_arms_spec_still_rebuilds_to_the_submitted_digest(arm: str) -> None:
    """The one assertion that keeps N3 collectable — and it guards live runs again.

    **The standing instruction on this test was "if this fails, do NOT update the
    constant", and it was correct for as long as the digests described runs that could
    still be collected. ADR-043 ended that**, deliberately and with the operator's
    acceptance: adding ``hht_alpha`` to the solid spec moves EVERY spec's digest, so both
    uncollected N3 attempt-1 records — the completed 76 090-window rigid arm included —
    became permanently unreattachable. That cost was declared in ADR-041's D-C form 1,
    re-declared in ADR-043 Y2, and paid here.

    N3 attempt 2 (`hg2007_flexible_foil-20260914-122525` / `hg2007_rigid_foil-20260914-122543`)
    ran on these knobs at renderer version "1" and **died on 2026-09-15** (flexible at
    w21 897; the rigid partner killed by the stop rule) -- there is NO submission executing.
    **ADR-045 A1 then moved the renderer to "2"** (`*AMPLITUDE ... TIME=TOTAL TIME`,
    `writePrecision 17`), and **ADR-045 R1's rebuild moved `SOLID_SIF_OF_RECORD` to
    `calculix-precice-adr045.sif`** (2026-09-16); each moves every spec digest. The
    attempt-2 records on NFS are the third superseded generation, the renderer-2/unpatched
    digests the fourth, and nothing downstream reads them through `_reattach` (their facts
    are in the handoff). The constants below are the N3 shape re-pinned to the
    serialization as it stands, so the next submission on this shape is collectable.

    **While a submission is executing, if this fails, do NOT update the constant.** Revert
    whatever moved the spec serialization instead: editing the expectation to match new
    code would make ``_reattach`` pass while comparing a spec that is not the one that ran.
    A deliberate move -- an accepted ADR that declares its digest cost -- re-pins here in
    the same commit and widens `_SUPERSEDED`, as ADR-043 and ADR-045 did.
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
