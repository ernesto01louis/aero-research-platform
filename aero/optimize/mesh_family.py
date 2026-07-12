"""Graded (fixed-mapping) mesh-family refinement for the optimizer's airfoil cases (Stage 16).

Stage 15's ``refined()`` scaled only the four cell counts while holding every first-cell size
fixed. That family is NOT geometrically self-similar: with a block's extent and first cell both
pinned, the geometric cell-to-cell ratio r is a pure function of the count (for the turbulent
base, wall-normal r = 1.468 at n=28 down to 1.067 at n=136), so the stretching mapping drifts
grid-to-grid and the grids do not nest. Contrary to the Stage-15 handoff's one-line diagnosis,
refining at a fixed first cell makes the near-wall grading GENTLER, not steeper — the steep
cells live on the COARSE grids (ADR-028 records the corrected mechanism).

The fix is FIXED-MAPPING refinement: hold each graded direction's end-to-end expansion
``G = expansion(length, n, first)`` (the blockMesh ``simpleGrading`` value) constant across the
family and scale the counts. With G pinned, the first cell shrinks ~1/ratio automatically
("grade the first cell WITH the refinement"), every grid samples the same stretching mapping,
and the family nests asymptotically — the geometry an observed-order GCI is actually valid on.

Wall-treatment consistency: the ``nut`` wall BC branches on ``first_cell_height`` at
``NUT_LOW_RE_FIRST_CELL_MAX`` (wall-resolved low-Re below, all-y+ Spalding at/above). A matched
family must sit entirely on one side — flipping the wall model mid-family would change the
modelled physics between grids and poison the delta. ``graded_refined_spec`` fails loud on a
crossing (Invariant 2 — FAIL-LOUD).
"""

from __future__ import annotations

from aero.adapters.openfoam._foam_common import expansion
from aero.adapters.openfoam.case_writer import NUT_LOW_RE_FIRST_CELL_MAX
from aero.adapters.openfoam.schemas import CaseSpec
from aero.vv._base import scaled_count

# expansion() returns exactly 1.0 for a uniform (unstretched) direction; treat anything at or
# below this as uniform and keep the refined direction uniform too.
_UNIFORM_G_EPS = 1.0e-12


def pinned_first_cell(length: float, n_base: int, first_base: float, n_new: int) -> float:
    """First-cell size at ``n_new`` cells preserving the base end-to-end expansion G.

    G = ``expansion(length, n_base, first_base)`` is the blockMesh ``simpleGrading`` value of
    the base direction. The refined direction keeps that mapping: its cell-to-cell ratio is
    ``r_new = G**(1/(n_new-1))`` and its first cell is the geometric-series fill
    ``length*(r_new-1)/(r_new**n_new - 1)``. Uniform directions (G ~ 1) stay uniform.

    Lengths and first-cell sizes share one unit (chords here); the result is in the same unit.
    """
    if length <= 0.0 or first_base <= 0.0:
        raise ValueError(
            f"pinned_first_cell: length ({length}) and first_base ({first_base}) must be > 0"
        )
    if n_base < 2 or n_new < 2:
        raise ValueError(f"pinned_first_cell: counts must be >= 2 (n_base={n_base}, n_new={n_new})")
    g = expansion(length, n_base, first_base)
    if g <= 1.0 + _UNIFORM_G_EPS:
        return length / n_new
    r_new = float(g ** (1.0 / (n_new - 1)))
    return length * (r_new - 1.0) / (r_new**n_new - 1.0)


def graded_refined_spec(spec: CaseSpec, ratio: float) -> CaseSpec:
    """A resolution-scaled `CaseSpec` on the FIXED stretching mapping (ratio>1 coarsens).

    Counts scale by ``scaled_count`` (round(n/ratio), floor 4) exactly like the Stage-15
    family; additionally the wall-normal / front / wake first cells are re-derived so each
    direction's end-to-end expansion G is invariant across the family. Identity at counts
    unchanged (``refined(1.0)`` returns the spec as-is — no bisection round-trip drift).

    Raises ``ValueError`` if the new ``first_cell_height`` crosses the
    ``NUT_LOW_RE_FIRST_CELL_MAX`` wall-treatment branch relative to the base spec.
    """
    if ratio <= 0.0:
        raise ValueError(f"graded_refined_spec: ratio must be > 0, got {ratio}")
    counts = {
        "n_surface": scaled_count(spec.n_surface, ratio),
        "n_normal": scaled_count(spec.n_normal, ratio),
        "n_front": scaled_count(spec.n_front, ratio),
        "n_wake": scaled_count(spec.n_wake, ratio),
    }
    if all(counts[k] == getattr(spec, k) for k in counts):
        return spec
    ext = spec.farfield_extent_chords  # chord units throughout; the chord factor cancels in r
    first_height = pinned_first_cell(ext, spec.n_normal, spec.first_cell_height, counts["n_normal"])
    first_front = pinned_first_cell(ext, spec.n_front, spec.first_cell_front, counts["n_front"])
    first_wake = pinned_first_cell(ext, spec.n_wake, spec.first_cell_wake, counts["n_wake"])
    base_low_re = spec.first_cell_height < NUT_LOW_RE_FIRST_CELL_MAX
    new_low_re = first_height < NUT_LOW_RE_FIRST_CELL_MAX
    if base_low_re != new_low_re:
        raise ValueError(
            "graded_refined_spec: refined first_cell_height "
            f"({first_height:.3e}) crosses the wall-treatment branch at "
            f"{NUT_LOW_RE_FIRST_CELL_MAX:.1e} (base {spec.first_cell_height:.3e}); a matched "
            "family must keep one wall model — choose a base first cell / ratio that stays on "
            "one side of the branch."
        )
    return spec.model_copy(
        update={
            **counts,
            "first_cell_height": first_height,
            "first_cell_front": first_front,
            "first_cell_wake": first_wake,
        }
    )
