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

    Compared as an ORDERED list of (clause, band) pairs, not a set: a set of percentages
    loses multiplicity and association, so deleting D4 (25 %, same as D3) or swapping the
    amplitude and frequency bands would leave the set unchanged and the test green.
    """
    import re

    from aero.vv.fsi import TurekHronFSI3

    block = _driver_module().PREREGISTERED_GATE_BLOCK
    stated = [
        (clause, int(percent) / 100.0)
        for clause, percent in re.findall(
            r"^\s+(D\d) [^\n]*within (\d+) %", block, flags=re.MULTILINE
        )
    ]
    assert stated == [("D1", 0.15), ("D2", 0.05), ("D3", 0.25), ("D4", 0.25), ("D5", 0.05)]

    # ...and the code's metric -> band mapping, by name, in order.
    coded = [(m.name, m.tolerance) for m in TurekHronFSI3().metrics()]
    assert coded == [
        ("tip_uy_amplitude", 0.15),
        ("tip_uy_frequency", 0.05),
        ("tip_ux_amplitude", 0.25),
        ("tip_ux_mean", 0.25),
        ("tip_ux_frequency", 0.05),
    ]
    assert len(stated) == len(coded) == 5
    assert [band for _, band in stated] == [band for _, band in coded]


def test_only_the_pre_registered_configuration_can_be_gated() -> None:
    """ADR-036 B3 declares the refined run non-gated "so it cannot become a second
    attempt at the gate". That has to be structural, not a convention."""
    from aero.vv.fsi.turek_hron_fsi3 import GATED_MAX_TIME, GATED_MESH_DICT, fsi3_case_spec

    assert fsi3_case_spec(
        max_time=GATED_MAX_TIME, wall_clock_ceiling_s=172800, fluid_mesh_dict=GATED_MESH_DICT
    ).gated
    assert not fsi3_case_spec(
        max_time=GATED_MAX_TIME,
        wall_clock_ceiling_s=172800,
        fluid_mesh_dict="blockMeshDict_refined",
    ).gated
    assert not fsi3_case_spec(
        max_time=2.0, wall_clock_ceiling_s=172800, fluid_mesh_dict=GATED_MESH_DICT
    ).gated


def test_the_block_is_ascii() -> None:
    """It lives in a Python literal, a JSON bundle and a markdown fence; keep it portable."""
    block = _driver_module().PREREGISTERED_GATE_BLOCK
    assert block.isascii()
