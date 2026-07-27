"""The pre-registered gate block must be byte-identical in ADR-036 and the driver.

Stage 18 kept the operational copy as a hand-maintained paraphrase and relied on
discipline to keep it aligned. Discipline is not a mechanism: the whole value of a
pre-registration is that the thing the campaign actually evaluated is provably the thing
that was committed beforehand, so the two copies are compared here, in the required unit
job, rather than by eye.

The driver embeds its copy in every bundle it writes, which is what carries the
pre-registration into the artifact instead of leaving it in a document beside it.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.stage_19

_REPO_ROOT = Path(__file__).resolve().parents[2]
_ADR = _REPO_ROOT / "docs" / "adrs" / "ADR-036-precice-fsi3-gate-preregistration.md"


def _driver_module():  # type: ignore[no-untyped-def]
    sys.path.insert(0, str(_REPO_ROOT / "scripts"))
    import stage19_turek_hron_fsi3  # type: ignore[import-not-found]

    return stage19_turek_hron_fsi3


def test_the_adr_carries_a_delimited_gate_block() -> None:
    text = _ADR.read_text(encoding="utf-8")
    assert text.count("<!-- GATE-BLOCK:BEGIN -->") == 1
    assert text.count("<!-- GATE-BLOCK:END -->") == 1


def test_driver_copy_is_byte_identical_to_the_adr() -> None:
    driver = _driver_module()
    assert driver.gate_block_from_adr(_ADR) == driver.PREREGISTERED_GATE_BLOCK


def test_the_block_states_every_gate_family() -> None:
    """A truncated or reordered block would still be 'identical' to a truncated ADR."""
    block = _driver_module().PREREGISTERED_GATE_BLOCK
    for marker in (
        "P - pins and provenance",
        "C - configuration integrity",
        "I - infrastructure pre-flight",
        "R - reference integrity",
        "K - coupling convergence",
        "S - periodic steady state",
        "D - displacement bands",
        "X - diagnostics, never gated",
        "VERDICT: GO if and only if",
        "BUDGET (pre-declared)",
        "CONTINGENCIES - MECHANISM",
        "FORBIDDEN:",
    ):
        assert marker in block, f"the gate block no longer states {marker!r}"


def test_the_bands_in_the_block_match_the_bands_in_the_code() -> None:
    """The document and the executable gate must not drift apart.

    Checked by parsing the D-clauses out of the prose, so that editing one without the
    other fails here rather than in a campaign six months from now.
    """
    import re

    from aero.vv.fsi import TurekHronFSI3

    block = _driver_module().PREREGISTERED_GATE_BLOCK
    stated = {
        int(percent) / 100.0
        for percent in re.findall(r"^\s+D\d [^\n]*within (\d+) %", block, flags=re.MULTILINE)
    }
    coded = {metric.tolerance for metric in TurekHronFSI3().metrics()}
    assert stated == coded, f"ADR-036 states bands {sorted(stated)}, code has {sorted(coded)}"


def test_the_block_is_ascii() -> None:
    """It lives in a Python literal, a JSON bundle and a markdown fence; keep it portable."""
    block = _driver_module().PREREGISTERED_GATE_BLOCK
    assert block.isascii()
