"""ADR-040's load-bearing property: two numerics do not share a `config_hash`.

Until this commit every `fvSolution` token was a literal inside the writer, while
`config_hash` is computed over the *spec* (`case.py:575-585`). Two campaigns run at
different numerics therefore carried the SAME four-tuple — provenance that cannot tell
apart the two things the tuple exists to distinguish.

That is ADR-037's rung-knob argument one layer down: it rejected deriving the rung knobs
at materialization because "the three GCI rungs would hash identically — a strictly worse
hole than the one being closed". A linear-solver stack chosen by a screening sweep is a
decision of exactly that kind.

The hole also disarmed a live guard. `scripts/stage20_hg2007_flexible_foil.py:547-553`
re-derives `spec_config_digest` on collect precisely to catch "the code moved under a live
campaign" — and it was blind to this class of edit.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from aero.adapters.openfoam._foam_common import FluidNumericsSpec, transient_fvsolution
from aero.adapters.openfoam.flexible_foil import write_flexible_foil_case
from aero.adapters.precice.case import spec_config_digest
from aero.vv.fsi.hg2007_flexible_foil import hg2007_case_spec
from pydantic import ValidationError

pytestmark = pytest.mark.stage_20

#: The stack the ADR-040 screening ranked first: DICGaussSeidel measured 2.2x faster than
#: GaussSeidel on this mesh, and one outer corrector a further 1.5x.
_ADR040_CANDIDATE = FluidNumericsSpec(
    label="adr040-dicgs-outer1",
    p_smoother="DICGaussSeidel",
    n_outer_correctors=1,
)


def _spec_with(numerics: FluidNumericsSpec):  # type: ignore[no-untyped-def]
    spec = hg2007_case_spec(
        arm="flexible", rung="mid", time_window_size=2e-5, max_time=0.01, wall_clock_ceiling_s=3600
    )
    fluid = spec.source.fluid.model_copy(update={"numerics": numerics})
    source = spec.source.model_copy(update={"fluid": fluid})
    return spec.model_copy(update={"source": source})


def test_two_specs_differing_only_in_the_linear_solver_stack_do_not_hash_equal() -> None:
    """The binding property. Without it the four-tuple cannot describe what ran."""
    baseline = _spec_with(FluidNumericsSpec())
    candidate = _spec_with(_ADR040_CANDIDATE)

    assert spec_config_digest(baseline) != spec_config_digest(candidate)


def test_the_same_numerics_hash_equal() -> None:
    """The symmetric guard: a field whose serialization is order-dependent would break it.

    `gamg_controls` is an ordered tuple of pairs rather than a mapping for this reason —
    a dict's iteration order would make the digest depend on construction order, and two
    identical stacks would hash differently.
    """
    controls = (("nCellsInCoarsestLevel", "100"), ("cacheAgglomeration", "no"))
    a = _spec_with(FluidNumericsSpec(p_smoother="DICGaussSeidel", gamg_controls=controls))
    b = _spec_with(FluidNumericsSpec(p_smoother="DICGaussSeidel", gamg_controls=controls))

    assert spec_config_digest(a) == spec_config_digest(b)


@pytest.mark.parametrize(
    "update",
    [
        {"purge_write": 5},
        {"forces_write_interval_steps": 2},
        {"numerics": FluidNumericsSpec(label="something-else")},
        {"numerics": FluidNumericsSpec(p_tolerance="1e-6")},
        {"numerics": FluidNumericsSpec(n_correctors=1)},
        {"numerics": FluidNumericsSpec(gamg_controls=(("nCellsInCoarsestLevel", "100"),))},
    ],
    ids=["purgeWrite", "forcesInterval", "label", "tolerance", "nCorrectors", "gamgControls"],
)
def test_every_output_and_numerics_knob_moves_the_digest(update: dict[str, object]) -> None:
    """Including `label`, which renders nothing.

    A stack is identified by the decision behind it, not only by its tokens; two sweeps
    that happened to land on the same values but were chosen for different reasons are
    different pre-registrations, and the bundle should say so.
    """
    baseline = hg2007_case_spec(
        arm="flexible", rung="mid", time_window_size=2e-5, max_time=0.01, wall_clock_ceiling_s=3600
    )
    fluid = baseline.source.fluid.model_copy(update=update)
    source = baseline.source.model_copy(update={"fluid": fluid})
    moved = baseline.model_copy(update={"source": source})

    assert spec_config_digest(moved) != spec_config_digest(baseline)


def test_an_unknown_solver_or_smoother_is_refused_at_construction() -> None:
    """A typo must be a ValidationError, not an OpenFOAM abort hours into a solve."""
    with pytest.raises(ValidationError, match="p_solver"):
        FluidNumericsSpec(p_solver="GAGM")
    with pytest.raises(ValidationError, match="p_smoother"):
        FluidNumericsSpec(p_smoother="DICGuassSeidel")


def test_a_single_outer_corrector_renders_the_cell_displacement_regex() -> None:
    """MEASURED (screening variant s6): the deck ABORTS without it.

    At `nOuterCorrectors 1` OpenFOAM tags every inner iteration final and looks up
    `cellDisplacementFinal`; a deck carrying only `cellDisplacement` dies with
    `FOAM FATAL IO ERROR: Entry 'cellDisplacementFinal' not found` on the first time
    step. So a single-outer-corrector campaign is a deck change, not a PIMPLE knob.
    """
    two = transient_fvsolution(cell_displacement=True)
    one = transient_fvsolution(
        cell_displacement=True, numerics=FluidNumericsSpec(n_outer_correctors=1)
    )

    assert "    cellDisplacement\n" in two
    assert '"cellDisplacement.*"' not in two
    assert '    "cellDisplacement.*"\n' in one
    assert "nOuterCorrectors    1;" in one


def test_the_candidate_stack_reaches_the_rendered_deck(tmp_path: Path) -> None:
    """End to end: spec -> writer -> bytes. A knob that never reaches the deck is a lie."""
    spec = _spec_with(_ADR040_CANDIDATE)
    write_flexible_foil_case(spec.source.fluid, tmp_path)
    rendered = (tmp_path / "system" / "fvSolution").read_text(encoding="utf-8")

    assert "smoother        DICGaussSeidel;" in rendered
    assert "nOuterCorrectors    1;" in rendered
    assert '"cellDisplacement.*"' in rendered


def test_gamg_controls_render_only_when_asked(tmp_path: Path) -> None:
    controls = (("nCellsInCoarsestLevel", "100"), ("cacheAgglomeration", "no"))
    rendered = transient_fvsolution(
        cell_displacement=True, numerics=FluidNumericsSpec(gamg_controls=controls)
    )
    # A key longer than the pad width must still be SEPARATED from its value:
    # `nCellsInCoarsestLevel100;` is a token OpenFOAM cannot parse, and it would abort
    # the solve on the first time step rather than at write time.
    assert "nCellsInCoarsestLevel100" not in rendered
    assert "        nCellsInCoarsestLevel 100;\n" in rendered
    assert "        cacheAgglomeration no;\n" in rendered
    # ...and in BOTH the p and pcorr blocks, which is what the screen varied together.
    assert rendered.count("nCellsInCoarsestLevel") == 2
