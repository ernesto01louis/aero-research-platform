"""The driver's PREREGISTERED_GATE_BLOCK_040 is byte-identical to ADR-040 — three ways.

The ADR-039 sibling's reasoning applies unchanged: the test extracts the block ITSELF,
independently of the driver's extractor, and closes the triangle test-extraction ==
driver-extraction == driver-constant, so an extractor bug cannot hide behind itself.

What is new here is that there are now TWO blocks in one driver, and the failure mode that
creates is cross-contamination: an extractor that found the wrong fence, a constant that
quietly carried the other document's text, or a marker-locality test satisfied by an
occurrence in the wrong file. ADR-040 uses its own delimiters
(``GATE-BLOCK-040:BEGIN/END``) so the two can never be extracted from each other, and this
file asserts the separation directly rather than trusting the naming.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.stage_20

_REPO_ROOT = Path(__file__).resolve().parents[2]
_ADR_039 = _REPO_ROOT / "docs/adrs/ADR-039-hg2007-flexible-foil-gate-preregistration.md"
_ADR_040 = _REPO_ROOT / "docs/adrs/ADR-040-campaign-numerics-re-preregistration.md"


def _driver_module():  # type: ignore[no-untyped-def]
    sys.path.insert(0, str(_REPO_ROOT / "scripts"))
    import stage20_hg2007_flexible_foil  # type: ignore[import-not-found]

    return stage20_hg2007_flexible_foil


def _independent_extraction(path: Path, *, begin: str, end: str) -> str:
    text = path.read_text(encoding="utf-8")
    assert text.count(begin) == 1 and text.count(end) == 1
    fenced = text.split(begin, 1)[1].split(end, 1)[0].strip()
    assert fenced.startswith("```text") and fenced.endswith("```")
    return fenced.removeprefix("```text").removesuffix("```").strip("\n") + "\n"


def _block_040() -> str:
    return _independent_extraction(
        _ADR_040, begin="<!-- GATE-BLOCK-040:BEGIN -->", end="<!-- GATE-BLOCK-040:END -->"
    )


def test_the_three_copies_are_byte_identical() -> None:
    driver = _driver_module()
    independent = _block_040()
    assert independent == driver.gate_block_040_from_adr(_ADR_040)
    assert independent == driver.PREREGISTERED_GATE_BLOCK_040


def test_the_two_blocks_are_different_documents_and_cannot_be_confused() -> None:
    """Neither extractor can reach the other's fence, and the constants differ."""
    driver = _driver_module()
    assert driver.PREREGISTERED_GATE_BLOCK != driver.PREREGISTERED_GATE_BLOCK_040
    # ADR-039 carries no ADR-040 delimiters and vice versa, so a mis-aimed extractor
    # raises rather than silently returning the wrong document.
    assert "<!-- GATE-BLOCK-040:BEGIN -->" not in _ADR_039.read_text(encoding="utf-8")
    with pytest.raises(ValueError, match="no <!-- GATE-BLOCK-040"):
        driver.gate_block_040_from_adr(_ADR_039)


def test_adr_039s_marker_still_stands_in_adr_039s_own_file() -> None:
    """ADR-040 U11 quotes the marker; that must not be mistaken for the marker itself.

    ``test_adr039_b2_marker_state`` reads ADR-039's path only, so the quotation in
    ADR-040 is harmless to it — but a reader (or a future grep) now finds the literal in
    two files. Turn that hazard into a guard: ADR-039's own copy must still be there,
    exactly once, for as long as ADR-040 claims it is.
    """
    assert "<<B2-PENDING-I4>>" in _block_040(), "U11 no longer states the permanent state"
    assert _ADR_039.read_text(encoding="utf-8").count("<<B2-PENDING-I4>>") == 1


def test_the_probe_ceiling_matches_b0() -> None:
    """B0 is a budget clause and a driver constant; a drift between them is unpoliced."""
    driver = _driver_module()
    assert driver.PROBE_CEILING_040_S == 345600
    assert "B0 the ADR-040 PROBE ceiling: 345600 s (96 h) per submission" in _block_040()
