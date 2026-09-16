"""`transient_fvschemes(ddt_scheme=...)`: additive, and inert at its default.

The companion of `test_fvschemes_bytes_before_ddt_scheme.py`, which pinned the rendered
bytes on PRE-CHANGE code. That pin is what makes this commit safe: without it, a mistake
in the new default branch would silently rewrite the fvSchemes of the Stage-10 static
cylinder, the Stage-11 plunging foil and the Stage-13 URANS decks -- invalidating the
records those decks produced, with nothing going red.

Stage 20 needs the parameter because second-order time is admissible only if the preCICE
OpenFOAM adapter checkpoints and restores `U.oldTime().oldTime()` across coupling
iterations (pre-flight I8). It is NOT the default, and cannot become one by accident.
"""

from __future__ import annotations

import hashlib

import pytest
from aero.adapters.openfoam._foam_common import transient_fvschemes

pytestmark = pytest.mark.stage_20

# Measured on pre-change code and pinned in the companion module; repeated here so this
# test fails loudly if the default ever drifts, rather than only the other one failing.
# Note 781 is CHARACTERS, not bytes -- the dictionary header carries an em dash, so the
# UTF-8 encoding is 783 bytes. The digest is over the encoded bytes, and is the real pin.
_LAMINAR_SHA = "1df84e211d7836d8fe9b7b935f5cd4af339174ef3c0d8aacc84b190c0678e4ef"
_LAMINAR_CHARS = 781


class TestTheDefaultIsInert:
    def test_the_default_renders_the_pinned_bytes(self) -> None:
        rendered = transient_fvschemes()
        assert len(rendered) == _LAMINAR_CHARS
        assert hashlib.sha256(rendered.encode("utf-8")).hexdigest() == _LAMINAR_SHA

    def test_passing_the_default_explicitly_is_the_same_bytes(self) -> None:
        assert transient_fvschemes(ddt_scheme="Euler") == transient_fvschemes()

    @pytest.mark.parametrize("model", ["laminar", "kOmegaSST", "kOmegaSSTLM"])
    def test_the_turbulence_variants_are_unmoved(self, model: str) -> None:
        assert transient_fvschemes(turbulence_model=model, ddt_scheme="Euler") == (
            transient_fvschemes(turbulence_model=model)
        )


class TestTheParameterIsLive:
    def test_backward_actually_changes_the_rendered_scheme(self) -> None:
        rendered = transient_fvschemes(ddt_scheme="backward")
        assert "ddtSchemes      { default backward; }" in rendered
        assert "default Euler" not in rendered

    def test_only_the_time_scheme_line_moves(self) -> None:
        euler = transient_fvschemes().splitlines()
        backward = transient_fvschemes(ddt_scheme="backward").splitlines()
        differing = [i for i, (a, b) in enumerate(zip(euler, backward, strict=True)) if a != b]
        assert len(differing) == 1, "a time-scheme change must not disturb anything else"

    def test_it_composes_with_the_turbulence_model(self) -> None:
        rendered = transient_fvschemes(turbulence_model="kOmegaSSTLM", ddt_scheme="backward")
        assert "default backward" in rendered
        assert "div(phi,ReThetat) Gauss upwind;" in rendered

    @pytest.mark.parametrize("bad", ["backwards", "euler", "CrankNicolson", "", "Gauss linear"])
    def test_an_unvalidated_scheme_is_refused(self, bad: str) -> None:
        # OpenFOAM would accept several of these and run; a typo would surface as a
        # solver failure hours into a coupled run, not as a bad argument.
        with pytest.raises(ValueError, match="ddt_scheme must be one of"):
            transient_fvschemes(ddt_scheme=bad)
