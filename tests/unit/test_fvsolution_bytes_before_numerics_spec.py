"""Byte-pin `transient_fvsolution` BEFORE it grows a `FluidNumericsSpec` parameter.

ADR-040 moves the fluid linear-solver stack onto the spec, so that `config_hash` can tell
an ADR-039-numerics run from an ADR-040-numerics run (today it cannot: every solver token
is a literal inside the writer, and `config_hash` is computed over the *spec*). The
migration is only admissible if it is provably INERT at its defaults — otherwise it
silently rewrites the `fvSolution` of every deck that shares this helper.

Six writers call it: `flexible_foil`, `cylinder`, `transient_airfoil`, `plunging_airfoil`,
`external_geometry`, `flapping_wing`. That covers the Stage-10 static cylinder, the
Stage-11 plunging foil, the Stage-13 URANS decks, the Stage-16/17 optimizer rungs and the
Stage-18 external-geometry cases. A default-branch mistake would invalidate the records
those decks produced with no test going red — because `tests/stage_11`'s existing check
compares the writer's output against the same function, pinning writer/consumer AGREEMENT
and nothing about the bytes (the §6.15 lesson, which is why this file exists at all).

So this lands FIRST, on pre-change code, exactly as the Phase-3A non-regression pins and
`test_fvschemes_bytes_before_ddt_scheme.py` did — but in `tests/unit` rather than beside
that precedent, because `tests/stage_20` is not in CI (§6.24) and a pin protecting six
stages' records must be enforced, not merely green in the local suite.

Measured on pre-change code:

    static laminar        len =  915  sha256 = 7da9dd24...
    moving laminar        len = 1242  sha256 = 0e35c4f5...   <- the gated HG2007 deck
    moving kOmegaSST      len = 1413  sha256 = 427cf057...
    static kOmegaSSTLM    len = 1104  sha256 = 498091152...

The moving-laminar digest is also pinned end to end through `write_flexible_foil_case`,
because that is the one the campaign actually runs.
"""

from __future__ import annotations

import hashlib
import inspect
from pathlib import Path

import pytest
from aero.adapters.openfoam import _foam_common as fc
from aero.adapters.openfoam.flexible_foil import write_flexible_foil_case
from aero.vv.fsi.hg2007_flexible_foil import hg2007_case_spec

pytestmark = pytest.mark.stage_20

_STATIC_LAMINAR = ("7da9dd24d268e236f8b28f69c5ad17cdab8665d4839a2ba6c2fe3b490252008d", 915)
_MOVING_LAMINAR = ("0e35c4f5778ba3ca13abe9036dadaff9e9b3d36ea31fd29c018f8ae7b5c72b80", 1242)
_MOVING_KOSST = ("427cf057cdb7feeb4804b4bca2da6cd2d501b9b7d826034574ee8b7fcaa5d64d", 1413)
_STATIC_KOSSTLM = ("498091152b58e471664cddfc81d06d732b0d872480104b5742d43d66ff2771dc", 1104)


def _digest(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


@pytest.mark.parametrize(
    ("kwargs", "expected"),
    [
        ({}, _STATIC_LAMINAR),
        ({"cell_displacement": True}, _MOVING_LAMINAR),
        ({"cell_displacement": True, "turbulence_model": "kOmegaSST"}, _MOVING_KOSST),
        ({"turbulence_model": "kOmegaSSTLM"}, _STATIC_KOSSTLM),
    ],
    ids=["static-laminar", "moving-laminar", "moving-kOmegaSST", "static-kOmegaSSTLM"],
)
def test_the_rendered_bytes_are_what_every_prior_stage_wrote(
    kwargs: dict[str, object], expected: tuple[str, int]
) -> None:
    """Four call shapes, four digests. A numerics parameter must not move any of them."""
    rendered = fc.transient_fvsolution(**kwargs)  # type: ignore[arg-type]
    sha, length = expected
    assert len(rendered) == length
    assert _digest(rendered) == sha


def test_the_gated_hg2007_deck_renders_the_moving_laminar_bytes(tmp_path: Path) -> None:
    """End to end through the writer the campaign runs, not just through the helper."""
    spec = hg2007_case_spec(
        arm="flexible", rung="mid", time_window_size=2e-5, max_time=0.01, wall_clock_ceiling_s=3600
    )
    write_flexible_foil_case(spec.source.fluid, tmp_path)
    rendered = (tmp_path / "system" / "fvSolution").read_text(encoding="utf-8")

    sha, length = _MOVING_LAMINAR
    assert len(rendered) == length
    assert _digest(rendered) == sha
    # The ADR-039 numerics, stated so the diff of the migration commit is readable.
    assert "solver          GAMG;" in rendered
    assert "smoother        GaussSeidel;" in rendered
    assert "tolerance       1e-7;" in rendered
    assert "nOuterCorrectors    2;" in rendered
    assert "nCorrectors         2;" in rendered
    assert "nNonOrthogonalCorrectors 1;" in rendered


def test_every_sibling_writer_still_calls_the_shared_helper() -> None:
    """The blast radius, asserted rather than remembered.

    If the migration gives the helper a required parameter, these six call sites are what
    breaks — and if one is quietly given a private copy of the numerics instead, the decks
    drift apart silently. Both failures are what this test is for.
    """
    from aero.adapters.openfoam import (
        cylinder,
        external_geometry,
        flapping_wing,
        flexible_foil,
        plunging_airfoil,
        transient_airfoil,
    )

    for module in (
        cylinder,
        external_geometry,
        flapping_wing,
        flexible_foil,
        plunging_airfoil,
        transient_airfoil,
    ):
        source = inspect.getsource(module)
        assert "transient_fvsolution(" in source, (
            f"{module.__name__} no longer calls transient_fvsolution — if it grew its own "
            "copy of the linear-solver stack, the decks drift apart with no test going red"
        )
