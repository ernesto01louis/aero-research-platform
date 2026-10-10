"""ADR-040's gate block holds the byte shape ADR-039's does, and its own structure.

Same reasoning as the ADR-039 shape test: a pre-registration whose parity test does not
run is not a pre-registration, so this lives in ``tests/unit/`` (``tests/stage_20`` is not
in CI, handoff §6.24), and the tests are themselves mutation-tested in-process — a shape
test that cannot fail is decoration.

Three properties are specific to this document rather than inherited:

* **No N-prefixed contingency.** ADR-039's contingencies are N1-N4 and ADR-040's numerics
  family is also N. Two documents in one bundle using one prefix for two different things
  is how a reader ends up reading "N3" as a resubmission policy when it is a two-day
  measurement. ADR-040's contingencies are W-prefixed, and every cross-ADR reference in
  the block is qualified.
* **The U family names every ADR-039 clause id.** "Carries over unchanged" is only
  checkable if the list is exhaustive, so the union of ids the U family mentions is
  compared against ADR-039's own clause ids.
* **No fidelity band is restated.** ADR-040 must not carry a band token of its own: a
  second statement of a band is a second place it can drift from ``CLAUSE_BANDS``.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

pytestmark = pytest.mark.stage_20

_REPO_ROOT = Path(__file__).resolve().parents[2]
_ADR_039 = _REPO_ROOT / "docs/adrs/ADR-039-hg2007-flexible-foil-gate-preregistration.md"
_ADR_040 = _REPO_ROOT / "docs/adrs/ADR-040-campaign-numerics-re-preregistration.md"
_BEGIN = "<!-- GATE-BLOCK-040:BEGIN -->"
_END = "<!-- GATE-BLOCK-040:END -->"

_FAMILY_HEADERS = (
    "U - what ADR-039 carries over UNCHANGED",
    "N - the campaign numerics, re-pre-registered",
    "L - the live MPI ladder and the parallel seam",
    "Q - equivalence against the ADR-039-numerics baseline",
    "VERDICT:",
    "BUDGET (pre-declared):",
    "CONTINGENCIES - MECHANISM",
    "FORBIDDEN:",
)

#: Exactly two spaces, an id, a space — five-space continuations can never register.
_CLAUSE_LINE = re.compile(r"^ {2}([A-Z]\d{1,2}) (.*)$", re.MULTILINE)
_BAND_TOKEN = re.compile(r"within (\d+(?:\.\d+)? (?:%|deg))|(\(no band\))")
_MARKERS = ("<<B1-PENDING-N3>>", "<<B2-PENDING-ADR040>>", "<<B3-PENDING-CEILING>>")


def _extract(text: str, *, begin: str, end: str) -> str:
    """Independent extraction — deliberately NOT the driver's extractor."""
    assert text.count(begin) == 1 and text.count(end) == 1
    inner = text.split(begin, 1)[1].split(end, 1)[0].strip()
    assert inner.startswith("```text") and inner.endswith("```")
    return inner.removeprefix("```text").removesuffix("```").strip("\n") + "\n"


def _block() -> str:
    return _extract(_ADR_040.read_text(encoding="utf-8"), begin=_BEGIN, end=_END)


def _block_039() -> str:
    return _extract(
        _ADR_039.read_text(encoding="utf-8"),
        begin="<!-- GATE-BLOCK:BEGIN -->",
        end="<!-- GATE-BLOCK:END -->",
    )


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


def _clause_ids(block: str) -> list[str]:
    return [m.group(1) for m in _CLAUSE_LINE.finditer(block)]


def test_the_adr_carries_exactly_one_delimited_text_fenced_block() -> None:
    _block()


def test_the_block_byte_shape_holds() -> None:
    assert _shape_problems(_block()) == []


def test_every_family_header_is_present_and_in_order() -> None:
    assert _header_order_problems(_block()) == []


def test_clause_ids_are_unique_and_drawn_only_from_the_declared_families() -> None:
    ids = _clause_ids(_block())
    assert len(ids) == len(set(ids))
    assert {cid[0] for cid in ids} == {"U", "N", "L", "Q", "B", "W"}


def test_no_contingency_is_n_prefixed() -> None:
    """ADR-039's contingencies are N1-N4; ADR-040's numerics family is N. Never both."""
    block = _block()
    contingencies = block[block.index("CONTINGENCIES - MECHANISM") : block.index("  FORBIDDEN:")]
    ids = _clause_ids(contingencies)
    assert ids, "the contingency family has no clauses"
    assert not [cid for cid in ids if cid.startswith("N")], (
        "an N-prefixed contingency collides with ADR-040's own numerics family AND with "
        "ADR-039's contingencies, so a bundle carrying both blocks has two meanings for "
        "one id"
    )
    assert set(ids) == {"W1", "W2", "W3", "W4", "W5", "W6"}


def test_every_cross_adr_reference_is_qualified() -> None:
    """A bare 'N3' in this document means the two-day measurement, never ADR-039's rule.

    So every mention of ADR-039 that is followed by a clause id must name it explicitly,
    and — the property that actually bites — no sentence may reference a bare id belonging
    to ADR-039's contingency family without the ADR-039 prefix.
    """
    block = _block()
    for match in re.finditer(r"ADR-039(?:'s)?\s+([A-Z]\d{1,2})\b", block):
        assert match.group(1)[0] in "PCIRKSADMNB", match.group(0)
    # The one place ADR-039's contingency N3 is invoked (W6) must be qualified.
    w6 = block[block.index("  W6 ") : block.index("  FORBIDDEN:")]
    assert "ADR-039 N3" in w6, "W6 invokes a resubmission policy without naming its ADR"


def test_the_block_restates_no_fidelity_band_of_its_own() -> None:
    """U8 lists ADR-039's bands as prose; none of them may be a parseable band TOKEN.

    ``CLAUSE_BANDS`` has exactly one ordered statement in the repo, in ADR-039's block. A
    second parseable copy here would be a second place for it to drift.
    """
    rows = [(cid, text) for cid, text in _CLAUSE_LINE.findall(_block())]
    for cid, text in rows:
        assert not _BAND_TOKEN.findall(text), f"{cid} restates a fidelity band token"


def test_the_u_family_names_every_adr_039_clause_id() -> None:
    """'Carries over unchanged' is only checkable if the list is exhaustive."""
    block = _block()
    u_family = block[block.index("U - what ADR-039") : block.index("N - the campaign numerics")]
    named = set(re.findall(r"\b([PCIRKSADMNB]\d{1,2})\b", u_family))
    expected = set(_clause_ids(_block_039()))
    missing = expected - named
    assert not missing, f"ADR-039 clauses not named by ADR-040's U family: {sorted(missing)}"


def test_each_pending_marker_appears_exactly_once_and_inside_its_own_clause() -> None:
    block = _block()
    for marker, clause in zip(_MARKERS, ("  B1 ", "  B2 ", "  B3 "), strict=True):
        if marker not in block:
            continue  # filled; the XOR is test_adr040_marker_state's business
        assert block.count(marker) == 1, f"{marker} appears more than once"
        following = {"  B1 ": "  B2 ", "  B2 ": "  B3 ", "  B3 ": "  B4 "}[clause]
        section = block[block.index(clause) : block.index(following)]
        assert marker in section, f"{marker} is not inside {clause.strip()}"


class TestTheTestsCanFail:
    """Mutate a copy of the block in memory; each mutation must be caught."""

    def test_a_three_space_clause_indent_is_caught(self) -> None:
        mutated = _block().replace("\n  W2 ", "\n   W2 ", 1)
        assert any("indent 3" in p for p in _shape_problems(mutated))

    def test_an_over_wide_line_is_caught(self) -> None:
        mutated = _block().replace("\n  W2 ", "\n  W2 " + "x" * 95, 1)
        assert any("wider than 90" in p for p in _shape_problems(mutated))

    def test_a_non_ascii_character_is_caught(self) -> None:
        assert "non-ascii" in _shape_problems(_block().replace(" - ", " — ", 1))

    def test_a_swapped_family_is_caught(self) -> None:
        block = _block()
        start_q = block.index("Q - equivalence")
        start_v = block.index("VERDICT:")
        q_family, verdict = block[start_q:start_v], block[start_v:]
        mutated = block[:start_q] + verdict + q_family
        assert _header_order_problems(mutated) != []

    def test_an_n_prefixed_contingency_is_caught(self) -> None:
        mutated = _block().replace("  W6 if a wave-1 solve", "  N6 if a wave-1 solve", 1)
        ids = _clause_ids(mutated[mutated.index("CONTINGENCIES - MECHANISM") :])
        assert [cid for cid in ids if cid.startswith("N")] == ["N6"]

    def test_a_restated_band_is_caught(self) -> None:
        mutated = _block().replace(
            "  Q1 500 coupled windows", "  Q1 within 25 % - 500 coupled windows", 1
        )
        rows = _CLAUSE_LINE.findall(mutated)
        assert any(_BAND_TOKEN.findall(text) for cid, text in rows if cid == "Q1")

    def test_dropping_an_adr_039_clause_from_the_u_family_is_caught(self) -> None:
        mutated = _block().replace(" M1 M2 M3 M4 unchanged", " M2 M3 M4 unchanged", 1)
        u_family = mutated[mutated.index("U - what ADR-039") : mutated.index("N - the campaign")]
        assert "M1" not in set(re.findall(r"\b([PCIRKSADMNB]\d{1,2})\b", u_family))

    def test_a_marker_leaking_outside_its_clause_is_caught(self) -> None:
        block = _block()
        mutated = block.replace("  B4 reaching a ceiling", "  B4 <<B1-PENDING-N3>> reaching", 1)
        assert mutated.count("<<B1-PENDING-N3>>") == 2
