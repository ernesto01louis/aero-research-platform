"""Byte-pin `transient_fvschemes` BEFORE it grows a `ddt_scheme=` parameter.

**The safety net the Stage-20 prompt tells you to rely on does not exist.** The prompt
says the default output is "byte-exact pinned by `tests/stage_11/test_dynamic_mesh_writers.py:62-63`".
That line reads:

    assert (tmp_path / "system" / "fvSchemes").read_text() == fc.transient_fvschemes()

Both sides call the same function. It pins WRITER/CONSUMER AGREEMENT — that the cylinder
writer really does render the shared helper — and nothing whatsoever about the bytes. Change
the default output and both sides move together; the test stays green.

That matters because Stage 20's flexible-foil deck needs `backward` instead of `Euler`, and
the additive way to get it is a `ddt_scheme=` keyword. Without a real pin, a mistake in the
default branch would silently rewrite the `fvSchemes` of the Stage-10 static cylinder, the
Stage-11 plunging foil and the Stage-13 URANS decks — invalidating the records those decks
produced, with no test going red.

So this file lands FIRST, on pre-change code, exactly as the Phase-3A non-regression pins
did. It is in `tests/stage_20/` on purpose: `tests/stage_11/` is NOT in the mandated
`pytest -q tests/unit tests/stage_20` suite, so a pin placed beside the test it corrects
would not be run by the command every commit is checked with.

Measured on pre-change code:  len = 781,
sha256 = 1df84e211d7836d8fe9b7b935f5cd4af339174ef3c0d8aacc84b190c0678e4ef
"""

from __future__ import annotations

import hashlib

import pytest
from aero.adapters.openfoam import _foam_common as fc

pytestmark = pytest.mark.stage_20

#: The laminar default, as it stands before `ddt_scheme=` exists. Any change to these bytes
#: changes what Stages 10, 11 and 13 wrote, so it must be a deliberate, separate decision.
_LAMINAR_SHA256 = "1df84e211d7836d8fe9b7b935f5cd4af339174ef3c0d8aacc84b190c0678e4ef"
_LAMINAR_LEN = 781


def _digest(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def test_the_laminar_default_bytes_are_pinned() -> None:
    text = fc.transient_fvschemes()
    assert len(text) == _LAMINAR_LEN
    assert _digest(text) == _LAMINAR_SHA256


def test_the_default_ddt_scheme_is_euler_and_appears_exactly_once() -> None:
    """Named explicitly so a `ddt_scheme=` parameter cannot change the default by accident.

    `ddtSchemes` is a literal inside the returned string today — there is no branch, no
    argument and no spec field. The parameter Stage 20 adds must leave this line untouched
    when it is not passed.
    """
    text = fc.transient_fvschemes()
    assert text.count("ddtSchemes") == 1
    assert "ddtSchemes      { default Euler; }" in text
    assert "backward" not in text


#: All three branches, measured on pre-change code. LITERALS, never computed from the
#: function under test: a digest derived from the same call it is compared against asserts
#: only that sha256 is deterministic, which is the vacuous-green shape this whole file
#: exists to replace.
_EXPECTED = {
    "laminar": (781, _LAMINAR_SHA256),
    "kOmegaSST": (886, "4edd1332bf0bba804327e9e52dd3f6c0c1100e45ea040404b5ad5908b3d4c302"),
    "kOmegaSSTLM": (958, "3703fe5ca9f6735f404d1a4df3d2e7fc607063c772872ca9f219e3f841fc0f90"),
}


@pytest.mark.parametrize("model", sorted(_EXPECTED))
def test_every_turbulence_branch_is_pinned_too(model: str) -> None:
    """The turbulence branches append fragments, so a `ddt_scheme=` refactor could disturb
    one of them while the laminar default stays fine."""
    want_len, want_sha = _EXPECTED[model]
    text = fc.transient_fvschemes(turbulence_model=model)
    assert (len(text), _digest(text)) == (want_len, want_sha)


def test_the_pin_is_falsifiable() -> None:
    """Mutation-test the pin itself: perturbing one byte must break it.

    Cheap, and it is the difference between a digest assertion and a digest assertion that
    is actually wired to the thing it names.
    """
    mutated = fc.transient_fvschemes().replace("Euler", "backward", 1)
    assert _digest(mutated) != _LAMINAR_SHA256
