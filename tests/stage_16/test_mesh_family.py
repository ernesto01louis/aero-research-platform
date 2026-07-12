"""Stage 16 — graded (fixed-mapping) mesh-family invariants.

An observed-order GCI is only valid on a geometrically self-similar family: every grid must
sample the SAME stretching mapping. These tests pin the Stage-16 contract: the end-to-end
expansion G of every count-dependent grading (wall-normal, front, wake) is invariant across
``refined()`` grids, first cells scale ~1/ratio, the family never crosses the ``nut``
wall-treatment branch, baseline↔optimum topology stays matched, and ``graded=False`` still
reproduces the Stage-15 count-only family for diagnostics.
"""

from __future__ import annotations

import pytest
from aero.adapters.openfoam._foam_common import expansion
from aero.adapters.openfoam.case_writer import NUT_LOW_RE_FIRST_CELL_MAX, _blockmeshdict
from aero.adapters.openfoam.schemas import CaseSpec
from aero.optimize.mesh_family import graded_refined_spec, pinned_first_cell
from aero.optimize.turbulent_airfoil import ShapedTurbulentAirfoil

pytestmark = pytest.mark.stage_16

_RATIO = 1.7


def _family_g(spec: CaseSpec) -> tuple[float, float, float]:
    """The three count-dependent end-to-end expansions, in chord units (chord cancels)."""
    ext = spec.farfield_extent_chords
    return (
        expansion(ext, spec.n_normal, spec.first_cell_height),
        expansion(ext, spec.n_front, spec.first_cell_front),
        expansion(ext, spec.n_wake, spec.first_cell_wake),
    )


def test_pinned_g_invariant_across_family() -> None:
    base = ShapedTurbulentAirfoil()
    g_base = _family_g(base.case_spec())
    for ratio in (1.0 / _RATIO, _RATIO, _RATIO**2):
        g = _family_g(base.refined(ratio).case_spec())
        assert g == pytest.approx(g_base, rel=1.0e-6), f"mapping drifted at ratio {ratio}"


def test_first_cells_scale_inverse_ratio() -> None:
    base = ShapedTurbulentAirfoil().case_spec()
    fine = ShapedTurbulentAirfoil().refined(1.0 / _RATIO).case_spec()
    coarse = ShapedTurbulentAirfoil().refined(_RATIO).case_spec()
    assert fine.n_normal == 136 and coarse.n_normal == 47
    # Asymptotically first ~ 1/ratio; on a stretched finite grid the factor is near but not
    # exactly the count ratio — bound it instead of pinning a magic value.
    for field in ("first_cell_height", "first_cell_front", "first_cell_wake"):
        f_base, f_fine, f_coarse = (getattr(s, field) for s in (base, fine, coarse))
        assert 1.3 < f_base / f_fine < 2.0, f"{field}: fine first-cell not ~1/ratio"
        assert 1.3 < f_coarse / f_base < 2.2, f"{field}: coarse first-cell not ~ratio"


def test_refined_identity_at_ratio_one() -> None:
    spec = ShapedTurbulentAirfoil().case_spec()
    assert graded_refined_spec(spec, 1.0) is spec


def test_chained_refinement_matches_direct() -> None:
    base = ShapedTurbulentAirfoil()
    chained = base.refined(_RATIO).refined(_RATIO).case_spec()
    direct = base.refined(_RATIO**2).case_spec()
    assert chained.n_normal == direct.n_normal == 28
    # G is the family's fixed point, so chaining and refining direct agree.
    assert chained.first_cell_height == pytest.approx(direct.first_cell_height, rel=1.0e-9)


def test_bc_branch_crossing_raises() -> None:
    # A base just above the wall-resolved branch refines across it -> the family would flip
    # wall models mid-study; must fail loud, never silently change the physics.
    near_branch = (
        ShapedTurbulentAirfoil().case_spec().model_copy(update={"first_cell_height": 1.2e-4})
    )
    assert near_branch.first_cell_height >= NUT_LOW_RE_FIRST_CELL_MAX
    with pytest.raises(ValueError, match="wall-treatment branch"):
        graded_refined_spec(near_branch, 1.0 / _RATIO)


def test_uniform_direction_stays_uniform() -> None:
    assert pinned_first_cell(100.0, 10, 10.0, 20) == pytest.approx(5.0)


def test_graded_false_reproduces_stage15_family() -> None:
    fine = ShapedTurbulentAirfoil().refined(1.0 / _RATIO, graded=False).case_spec()
    assert fine.n_normal == 136
    assert fine.first_cell_height == 1.0e-3  # pinned — the Stage-15 (drifting-mapping) family
    assert fine.first_cell_front == 0.01
    assert fine.first_cell_wake == 0.01


def test_graded_family_matched_topology() -> None:
    # Baseline and optimum refined at the same ratio must produce identical mesh resolution
    # AND identical gradings — the matched-condition delta's legitimacy.
    baseline = ShapedTurbulentAirfoil().refined(1.0 / _RATIO).case_spec()
    optimum = (
        ShapedTurbulentAirfoil(max_camber=0.0727, camber_position=0.2045)
        .refined(1.0 / _RATIO)
        .case_spec()
    )
    for field in (
        "n_surface",
        "n_normal",
        "n_front",
        "n_wake",
        "first_cell_height",
        "first_cell_front",
        "first_cell_wake",
    ):
        assert getattr(baseline, field) == getattr(optimum, field)
    b_dict, o_dict = _blockmeshdict(baseline), _blockmeshdict(optimum)
    assert b_dict.count("hex (") == o_dict.count("hex (") == 8
    assert b_dict.count("polyLine") == o_dict.count("polyLine") == 8


def test_default_first_cell_fields_preserve_blockmeshdict() -> None:
    # The new spec fields default to the pre-Stage-16 hardcoded 0.01c: rendering with the
    # defaults must equal rendering with the old constants made explicit.
    spec = ShapedTurbulentAirfoil().case_spec()
    explicit = spec.model_copy(update={"first_cell_front": 0.01, "first_cell_wake": 0.01})
    assert _blockmeshdict(spec) == _blockmeshdict(explicit)
