"""The driver's PREREGISTERED_GATE_BLOCK is byte-identical to ADR-039 — three ways.

The Stage-19 sync test compared ``gate_block_from_adr(_ADR) == PREREGISTERED_GATE_BLOCK``
— both sides through the driver's own extractor, so an extractor bug (an over-eager
strip, a fence mishap) would have been invisible. Here the test extracts the block
ITSELF, independently, and closes the triangle: test-extraction == driver-extraction ==
driver-constant. The shape/parity/mutation coverage lives in
``test_adr039_gate_block_shape.py``; this file owns only the byte identity and the
driver-side wiring.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.stage_20

_REPO_ROOT = Path(__file__).resolve().parents[2]
_ADR = _REPO_ROOT / "docs/adrs/ADR-039-hg2007-flexible-foil-gate-preregistration.md"


def _driver_module():  # type: ignore[no-untyped-def]
    sys.path.insert(0, str(_REPO_ROOT / "scripts"))
    import stage20_hg2007_flexible_foil  # type: ignore[import-not-found]

    return stage20_hg2007_flexible_foil


def _independent_extraction() -> str:
    text = _ADR.read_text(encoding="utf-8")
    inner = text.split("<!-- GATE-BLOCK:BEGIN -->", 1)[1].split("<!-- GATE-BLOCK:END -->", 1)[0]
    fenced = inner.strip()
    assert fenced.startswith("```text") and fenced.endswith("```")
    return fenced.removeprefix("```text").removesuffix("```").strip("\n") + "\n"


def test_the_three_copies_are_byte_identical() -> None:
    driver = _driver_module()
    independent = _independent_extraction()
    assert independent == driver.gate_block_from_adr(_ADR)
    assert independent == driver.PREREGISTERED_GATE_BLOCK


def test_the_driver_refuses_a_gated_submit_while_the_sentinels_are_none() -> None:
    """P4's driver half: --submit must be structurally impossible pre-fill.

    The refusal itself lives in ``main`` and needs no cluster to check: while the case
    module's sentinels are None the branch raises SystemExit before touching a host.
    """
    from aero.vv.fsi.hg2007_flexible_foil import GATED_MAX_TIME_S, GATED_TIME_WINDOW_S

    driver = _driver_module()
    if GATED_TIME_WINDOW_S is not None and GATED_MAX_TIME_S is not None:
        pytest.skip("sentinels are filled; the refusal branch no longer applies")
    with pytest.raises(SystemExit, match="sentinels are None"):
        driver.main(["--submit", "flexible", "--host", "nowhere"])


def test_the_probe_max_time_is_an_exact_multiple_of_the_probe_dt() -> None:
    """1.52 s is not constructible — assert_authored_consistent demands n*dt exactly."""
    driver = _driver_module()
    max_time = driver.PROBE_N_WINDOWS * driver.PROBE_DT_S
    assert max_time == 1.5225
    assert float(format(max_time, ".13e")) == max_time
