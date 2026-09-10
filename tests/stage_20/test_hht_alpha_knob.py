"""ADR-043: the HHT-alpha knob, the deck it writes, and the fence that keeps it diagnostic.

Three parallel runs diverged in a period-2, window-alternating mode, and the deck
integrates at `*DYNAMIC, ALPHA=0.0` — Newmark average-acceleration, which has EXACTLY zero
dissipation at every frequency including Nyquist. The Nyquist mode of a window-stepped
solve is precisely a period-2 alternation, so the parameter and the signature match.

The properties worth pinning are not "the number changed":

* **The default writes the deck it always wrote.** ADR-043 Y2 claims the digest move is a
  RECORD move for unmitigated specs, and that claim is only true if the bytes are
  identical. `_alpha_text` exists for that and `_num` would have broken it.
* **A non-record alpha can never be gated.** The knob is a rung's to vary and the
  campaign's to fix; without a fence a probe at the gated five-tuple would mint a bundle
  claiming `gated=True` the moment B2's sentinels were filled.
* **The value that ran is read back out of the bytes.** That is what replaces D10's
  secondary role ("holding also proves ALPHA=0 held") once alpha can be non-zero.
"""

from __future__ import annotations

import pytest
from aero.adapters.precice.calculix import _alpha_text
from aero.vv.fsi.hg2007_flexible_foil import (
    ALPHA_OF_RECORD,
    LEGACY_HHT_ALPHA,
    hg2007_case_spec,
    is_campaign_configuration,
)

pytestmark = pytest.mark.stage_20

_KNOBS = dict(
    arm="flexible",
    rung="mid",
    time_window_size=2e-05,
    max_time=0.16,
    wall_clock_ceiling_s=43200,
    numerics_label="adr040-candidate",
    mpi_ranks=4,
)


def test_the_default_writes_the_historical_deck_bytes() -> None:
    """`ALPHA=0.0`, not `ALPHA=0.0000000000000e+00`.

    ADR-043 Y2 rests on this: at the default the deck is byte-identical, so the digest
    move is a record move rather than a case move, and the goldens do not shift.
    """
    assert _alpha_text(0.0) == "0.0"
    assert _alpha_text(-0.05) == "-0.05"
    assert LEGACY_HHT_ALPHA == 0.0 == ALPHA_OF_RECORD


def test_alpha_reaches_the_deck_and_is_read_back_from_it(tmp_path) -> None:  # type: ignore[no-untyped-def]
    """Written, then re-read and asserted — the check that replaces D10's ALPHA proof."""
    from aero.adapters.precice.calculix import write_calculix_deck

    for alpha, expected in (
        (0.0, "*DYNAMIC, ALPHA=0.0, DIRECT"),
        (-0.05, "*DYNAMIC, ALPHA=-0.05, DIRECT"),
    ):
        spec = hg2007_case_spec(**_KNOBS, hht_alpha=alpha)  # type: ignore[arg-type]
        dest = tmp_path / f"deck{alpha}"
        dest.mkdir()
        deck = write_calculix_deck(spec.source.solid, dest_dir=dest)
        assert deck.dynamic_alpha == alpha
        assert expected in (dest / deck.path.name).read_text(encoding="utf-8")


def test_a_non_record_alpha_can_never_claim_the_gated_verdict(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The fence is one-way: it refuses, it never promotes."""
    import aero.vv.fsi.hg2007_flexible_foil as campaign

    monkeypatch.setattr(campaign, "GATED_040_TIME_WINDOW_S", 2e-05)
    monkeypatch.setattr(campaign, "GATED_040_MAX_TIME_S", 0.16)
    monkeypatch.setattr(campaign, "GATED_040_NUMERICS_LABEL", "adr040-candidate")
    monkeypatch.setattr(campaign, "GATED_040_MPI_RANKS", 4)

    assert campaign.hg2007_case_spec(**_KNOBS).gated is True  # type: ignore[arg-type]
    assert campaign.hg2007_case_spec(**_KNOBS, hht_alpha=-0.05).gated is False  # type: ignore[arg-type]


def test_the_fence_predicate_states_both_conjuncts() -> None:
    from aero.adapters.precice.template import template_sha256

    good = template_sha256()
    assert is_campaign_configuration(template_sha256_hex=good, hht_alpha=0.0)
    assert not is_campaign_configuration(template_sha256_hex=good, hht_alpha=-0.05)
    assert not is_campaign_configuration(template_sha256_hex="0" * 64, hht_alpha=0.0)


def test_calculix_own_range_is_enforced() -> None:
    """CalculiX clamps silently in dynamics.f:106-113; the spec refuses loudly instead."""
    from pydantic import ValidationError

    hg2007_case_spec(**_KNOBS, hht_alpha=-1.0 / 3.0)  # type: ignore[arg-type]
    for bad in (-0.4, 0.1):
        with pytest.raises(ValidationError):
            hg2007_case_spec(**_KNOBS, hht_alpha=bad)  # type: ignore[arg-type]


def test_the_knob_rides_in_spec_knobs_so_reattach_can_rebuild() -> None:
    """A knob that cannot ride there is a knob that makes every collect refuse."""
    import sys
    from pathlib import Path

    sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
    import stage20_hg2007_flexible_foil as driver  # type: ignore[import-not-found]

    assert driver.LEGACY_HHT_ALPHA == 0.0
    # the rebuild path supplies the historical value for records written before the knob
    knobs = dict(_KNOBS)
    rebuilt = hg2007_case_spec(**knobs, hht_alpha=driver.LEGACY_HHT_ALPHA)  # type: ignore[arg-type]
    assert rebuilt.source.solid.hht_alpha == 0.0
