"""Format v1's bytes are pinned (ADR-047 D7): the synthetic crates' digests are constants.

A crate digest is the sha256 of its SHA256SUMS, so it changes whenever any byte of any member
changes. That covers the encoder, the envelope schema, the projections and the payload rule. A
failure here means format v1's bytes moved. Before ratification that is a deliberate update of
these constants, in the same commit as the change. After ratification, ADR-047 freezes format v1,
so such a change is format v2 and needs an ADR.
"""

from __future__ import annotations

import pytest
from aero.crate import verify_members

from tests.unit._crate_fixtures import built

pytestmark = pytest.mark.stage_21

FROZEN = {
    "steady_optimization": "87749d9977c4",
    "thesis_grade_paired": "60c9e95ff5a9",
    "independent_inf": "c2f9fb627db0",
    "evidence_only": "599be2d851fc",
}


@pytest.mark.parametrize("shape", sorted(FROZEN))
def test_format_v1_bytes_are_frozen(shape: str) -> None:
    assert verify_members(built(shape)).digest.startswith(FROZEN[shape])
