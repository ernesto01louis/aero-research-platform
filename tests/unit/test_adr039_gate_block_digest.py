"""ADR-039's gate block is pinned by DIGEST, so an edit is a named CI failure.

``test_adr039_gate_block_sync.py`` proves the ADR, the driver's extractor and the driver's
constant agree with each other; ``test_adr039_gate_block_shape.py`` proves the block's form
and its ordered band parity. Neither pins the block's *identity*: an edit applied
consistently to the ADR and to ``PREREGISTERED_GATE_BLOCK`` passes both, and the three
committed ``data/vv`` records that embed the block would then be the only witnesses that
anything moved -- as a diff in a 20 kB JSON string, not as a message.

This file names the number. ADR-039 is ``accepted`` and FROZEN: its bands, its S/R/K/A/M
families, C1-C6 and the rungs all carry over into ADR-040 UNCHANGED, and its B2 marker
stands unfilled permanently because the campaign it sized was measured infeasible and
never ran. So the block is not merely stable, it is final, and the honest way to say that
is a digest a deliberate change has to edit on purpose.

Landed ALONE, on pre-change code, immediately before the ADR-040 work that puts a SECOND
gate block in the same driver -- the Phase-3A precedent (handoff 3): pin the thing you are
about to work beside, before you work beside it.
"""

from __future__ import annotations

import hashlib
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.stage_20

_REPO_ROOT = Path(__file__).resolve().parents[2]
_ADR = _REPO_ROOT / "docs/adrs/ADR-039-hg2007-flexible-foil-gate-preregistration.md"

#: Measured at session 10 on `cf3da36`, from the extraction below.
_EXPECTED_BYTES = 19898
_EXPECTED_SHA256 = "c9cdde9463a4bf202dd3b692dded86242814268b8ac62c8c8d3b4e1cc569863d"

_WHY = (
    "ADR-039's gate block moved. It is accepted, frozen, and carries over into ADR-040 "
    "clause by clause; its B2 marker stands unfilled permanently. If the change is "
    "deliberate, it needs a new ADR and this pin edited in the same commit, with the old "
    "and new digests in the commit body -- exactly the way ADR-037 recorded the FSI3 "
    "config_hash divergence rather than letting it pass silently."
)


def _driver_module():  # type: ignore[no-untyped-def]
    sys.path.insert(0, str(_REPO_ROOT / "scripts"))
    import stage20_hg2007_flexible_foil  # type: ignore[import-not-found]

    return stage20_hg2007_flexible_foil


def _independent_extraction() -> str:
    """Deliberately NOT the driver's ``gate_block_from_adr``, for the same reason sync isn't."""
    text = _ADR.read_text(encoding="utf-8")
    inner = text.split("<!-- GATE-BLOCK:BEGIN -->", 1)[1].split("<!-- GATE-BLOCK:END -->", 1)[0]
    fenced = inner.strip()
    assert fenced.startswith("```text") and fenced.endswith("```")
    return fenced.removeprefix("```text").removesuffix("```").strip("\n") + "\n"


def _digest(block: str) -> tuple[int, str]:
    raw = block.encode("utf-8")
    return len(raw), hashlib.sha256(raw).hexdigest()


def test_the_adr_block_has_its_pinned_length_and_digest() -> None:
    n_bytes, sha256 = _digest(_independent_extraction())
    assert (n_bytes, sha256) == (_EXPECTED_BYTES, _EXPECTED_SHA256), _WHY


def test_the_driver_constant_has_the_same_pinned_digest() -> None:
    """Pinned on the driver side too, so neither copy can move alone or together."""
    n_bytes, sha256 = _digest(_driver_module().PREREGISTERED_GATE_BLOCK)
    assert (n_bytes, sha256) == (_EXPECTED_BYTES, _EXPECTED_SHA256), _WHY


def test_the_pinned_digest_actually_discriminates() -> None:
    """The pin can fail: a one-character edit inside the block changes the digest."""
    mutated = _independent_extraction().replace("within 40 %", "within 45 %", 1)
    assert mutated != _independent_extraction()
    assert _digest(mutated) != (_EXPECTED_BYTES, _EXPECTED_SHA256)
