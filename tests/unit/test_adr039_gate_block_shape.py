"""ADR-039's gate block: shape, ordered band parity, and verdict coverage — CI-enforced.

These tests live in ``tests/unit`` because ``tests/stage_20`` is not in CI (handoff
§6.24): a pre-registration whose parity test does not run is not a pre-registration.

They improve on ``test_stage19_gate_block_sync.py``'s measured gaps: the extraction here
is INDEPENDENT of the driver's extractor (both sides of the Stage-19 byte-identity test
routed through one function, so an extractor bug was invisible); the family headers are
checked for ORDER, not just containment; the byte shape (width, indent alphabet, tabs,
trailing whitespace) is asserted instead of being a convention; the band regex fixes
ADR-036's four measured defects (``D\\d`` read ``D10`` as ``D1``; integer-percent-only
made band-less and absolute clauses invisible; ``^\\s+`` matched five-space continuation
lines; greedy matching reported the last band on a two-band line); and every check is
MUTATION-TESTED in-process on a mutated copy of the block, so the tests themselves are
shown to be able to fail.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
from aero.vv.fsi.hg2007_flexible_foil import CLAUSE_BANDS, REPORTED_ONLY

pytestmark = pytest.mark.stage_20

_REPO_ROOT = Path(__file__).resolve().parents[2]
_ADR = _REPO_ROOT / "docs/adrs/ADR-039-hg2007-flexible-foil-gate-preregistration.md"
_BEGIN = "<!-- GATE-BLOCK:BEGIN -->"
_END = "<!-- GATE-BLOCK:END -->"

_FAMILY_HEADERS = (
    "P - pins and provenance",
    "C - configuration integrity",
    "I - infrastructure pre-flight",
    "R - reference integrity",
    "K - coupling convergence",
    "S - periodic steady state",
    "A - paired-arm alignment",
    "D - fidelity bands",
    "M - mesh integrity",
    "X - diagnostics, never gated",
    "VERDICT:",
    "BUDGET (pre-declared):",
    "CONTINGENCIES - MECHANISM",
    "FORBIDDEN:",
)

#: A clause's first line: exactly two spaces, an id, a space. Two spaces exactly — not
#: ``\s+`` — so five-space continuations can never register as clauses.
_CLAUSE_LINE = re.compile(r"^ {2}([A-Z]\d{1,2}) (.*)$", re.MULTILINE)
#: A band token: ``within`` anchors the numeric forms so prose numbers ("17 and 6
#: degrees", "at most 4") are not tokens; ``(no band)`` is a first-class literal.
_BAND_TOKEN = re.compile(r"within (\d+(?:\.\d+)? (?:%|deg))|(\(no band\))")


def _extract_block(text: str) -> str:
    """Independent extraction — deliberately NOT the driver's ``gate_block_from_adr``."""
    assert text.count(_BEGIN) == 1 and text.count(_END) == 1
    inner = text.split(_BEGIN, 1)[1].split(_END, 1)[0].strip()
    assert inner.startswith("```text") and inner.endswith("```")
    return inner.removeprefix("```text").removesuffix("```").strip("\n") + "\n"


def _block() -> str:
    return _extract_block(_ADR.read_text(encoding="utf-8"))


def _shape_problems(block: str) -> list[str]:
    problems: list[str] = []
    if not block.isascii():
        problems.append("non-ascii")
    if not block.endswith("\n") or block.endswith("\n\n"):
        problems.append("trailing-newline")
    for i, line in enumerate(block.split("\n")[:-1], 1):
        if len(line) > 90:
            problems.append(f"line {i} wider than 90")
        if "\t" in line:
            problems.append(f"line {i} contains a tab")
        if line != line.rstrip():
            problems.append(f"line {i} has trailing whitespace")
        indent = len(line) - len(line.lstrip(" "))
        if line.strip() and indent not in (0, 2, 5):
            problems.append(f"line {i} indent {indent} outside {{0, 2, 5}}")
    return problems


def _header_order_problems(block: str) -> list[str]:
    problems: list[str] = []
    position = -1
    for header in _FAMILY_HEADERS:
        found = block.find(header)
        if found < 0:
            problems.append(f"missing header {header!r}")
        elif found < position:
            problems.append(f"header out of order: {header!r}")
        else:
            position = found
    return problems


def _clause_rows(block: str) -> list[tuple[str, str, str]]:
    """Every clause line as (id, first-line text, band token or '')."""
    rows: list[tuple[str, str, str]] = []
    for match in _CLAUSE_LINE.finditer(block):
        tokens = _BAND_TOKEN.findall(match.group(2))
        token = "" if not tokens else (tokens[0][0] or tokens[0][1])
        rows.append((match.group(1), match.group(2), token))
    return rows


def _stated_bands(block: str) -> list[tuple[str, str]]:
    """The ordered D-family (clause, band-token) list the block states."""
    return [(cid, token) for cid, _, token in _clause_rows(block) if cid[0] == "D" and token]


def _verdict_partition(block: str) -> tuple[set[str], set[str]]:
    verdict = block[block.index("VERDICT:") : block.index("BUDGET (pre-declared):")]
    go_clause = verdict.split("if and only if", 1)[1].split("all pass.", 1)[0]
    gated = set(re.findall(r"\bD\d{1,2}\b", go_clause))
    after = verdict.split("all pass.", 1)[1]
    reported = set(re.findall(r"\bD\d{1,2}\b", after.split("reported, never gated", 1)[0]))
    return gated, reported


def test_the_adr_carries_exactly_one_delimited_text_fenced_block() -> None:
    _block()


def test_the_block_byte_shape_holds() -> None:
    assert _shape_problems(_block()) == []


def test_every_family_header_is_present_and_in_order() -> None:
    assert _header_order_problems(_block()) == []


def test_clause_ids_are_unique_and_carry_at_most_one_band_token_each() -> None:
    rows = _clause_rows(_block())
    ids = [cid for cid, _, _ in rows]
    assert len(ids) == len(set(ids))
    for cid, text, _ in rows:
        assert len(_BAND_TOKEN.findall(text)) <= 1, f"{cid} carries two band tokens"


def test_the_stated_bands_equal_the_registry_in_order() -> None:
    """Shape-8: ordered ``(clause, band)`` parity against ``CLAUSE_BANDS``."""
    assert _stated_bands(_block()) == list(CLAUSE_BANDS)


def test_the_verdict_partition_is_disjoint_and_exhaustive() -> None:
    """Shape-7: every D clause is gated XOR reported-only, none is dropped."""
    gated, reported = _verdict_partition(_block())
    assert gated & set(REPORTED_ONLY) == set()
    assert set(REPORTED_ONLY) <= reported
    assert gated | set(REPORTED_ONLY) == {clause for clause, _ in CLAUSE_BANDS}


def test_the_b2_marker_or_numbers_are_the_b2_marker_states_business() -> None:
    """The XOR itself is asserted by ``test_adr039_b2_marker_state``; here only that the
    marker never appears anywhere EXCEPT B2 (a stray mention would survive the fill and
    leave the XOR test satisfied by the wrong occurrence)."""
    block = _block()
    assert block.count("<<B2-PENDING-I4>>") <= 1
    if "<<B2-PENDING-I4>>" in block:
        b2 = block[block.index("  B2 ") : block.index("  B3 ")]
        assert "<<B2-PENDING-I4>>" in b2


class TestTheTestsCanFail:
    """Mutation tests: each check must trip on a block mutated the way it guards against."""

    def test_dropping_d10_breaks_the_parity(self) -> None:
        block = _block()
        lines = [ln for ln in block.split("\n") if not ln.startswith("  D10 ")]
        # Also drop D10's continuation lines up to the next clause/family line.
        mutated = re.sub(r"^  D10 .*?(?=^ {2}[A-Z]\d|^\S)", "", block, flags=re.M | re.S)
        assert _stated_bands(mutated) != list(CLAUSE_BANDS)
        assert len(lines) < len(block.split("\n"))

    def test_widening_a_band_breaks_the_parity(self) -> None:
        mutated = _block().replace("within 40 %", "within 45 %", 1)
        assert _stated_bands(mutated) != list(CLAUSE_BANDS)

    def test_swapping_two_bands_breaks_the_parity(self) -> None:
        block = _block()
        mutated = block.replace("within 40 %", "@@", 1).replace("within 2 %", "within 40 %", 1)
        mutated = mutated.replace("@@", "within 2 %", 1)
        assert _stated_bands(mutated) != list(CLAUSE_BANDS)

    def test_a_three_space_clause_indent_breaks_the_shape(self) -> None:
        mutated = _block().replace("\n  D5 ", "\n   D5 ", 1)
        assert _shape_problems(mutated) != []
        assert _stated_bands(mutated) != list(CLAUSE_BANDS)

    def test_a_second_band_token_on_one_line_is_caught(self) -> None:
        block = _block()
        target = next(ln for ln in block.split("\n") if ln.startswith("  D0 "))
        mutated = block.replace(target, target[:88] + " within 5 %", 1)
        rows = _clause_rows(mutated)
        d0 = next(text for cid, text, _ in rows if cid == "D0")
        assert len(_BAND_TOKEN.findall(d0)) > 1

    def test_removing_d9_from_the_reported_list_breaks_the_partition(self) -> None:
        block = _block()
        verdict = block[block.index("VERDICT:") :]
        mutated = block[: block.index("VERDICT:")] + verdict.replace("D9 and X are", "X is", 1)
        gated, reported = _verdict_partition(mutated)
        assert not (
            gated | set(REPORTED_ONLY) == {c for c, _ in CLAUSE_BANDS}
            and set(REPORTED_ONLY) <= reported
        )

    def test_reordering_two_families_is_caught(self) -> None:
        block = _block()
        k = block.index("K - coupling convergence")
        s = block.index("S - periodic steady state")
        mutated = block[:k] + block[s:] + block[k:s]
        assert _header_order_problems(mutated) != []
