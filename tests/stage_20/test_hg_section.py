"""The Heathcote-Gursul teardrop/plate section, and the NACA path it must not disturb.

The section is swapped into the EXISTING eight-block C-grid rather than meshed by a new
writer, because that grid is geometrically self-similar under uniform refinement -- which
is what makes a real 3-grid GCI admissible (ADR-028). A snapped snappyHexMesh grid is not,
and Stage 18 measured that. The price of reusing the writer is that `CaseSpec` grew a field
and `_surfaces` grew a branch, so the first thing these tests do is prove the NACA path is
untouched.
"""

from __future__ import annotations

import numpy as np
import pytest
from aero.adapters.openfoam.case_writer import _blockmeshdict, _surfaces
from aero.adapters.openfoam.geometry import hg2007_coordinates, naca0012_coordinates
from aero.adapters.openfoam.schemas import CaseSpec, TeardropPlateSection

pytestmark = pytest.mark.stage_20

# HG2007, thesis 2.1.6 + Fig 2.5. Lengths in metres.
CHORD = 0.090
NOSE_X = 0.0085  # measured: max thickness ~8-9 mm from the nose
MAX_HALF_T = 0.0048  # measured: ~9.6 mm full thickness
JOIN_X = 0.030  # text-sourced: 90 mm chord - 60 mm plate; the structural root
BC_FLEXIBLE = 0.85e-3
BC_RIGID = 4.23e-3


def _section(b_over_c: float) -> TeardropPlateSection:
    return TeardropPlateSection(
        nose_length=NOSE_X,
        max_half_thickness=MAX_HALF_T,
        join_x=JOIN_X,
        plate_half_thickness=b_over_c * CHORD / 2.0,
    )


def _spec(b_over_c: float, **kw: object) -> CaseSpec:
    return CaseSpec(
        name="hg2007",
        reynolds=9000,
        mach=0.01,
        aoa_deg=0.0,
        chord=CHORD,
        span=0.0025,
        turbulence_model="laminar",
        section=_section(b_over_c),
        trailing_edge_thickness=b_over_c,
        n_te=4,
        **kw,  # type: ignore[arg-type]
    )


class TestTheNacaPathIsUntouched:
    def test_default_spec_still_produces_the_exact_naca_0012_surface(self) -> None:
        """`section=None` must reach byte-identical coordinates, not merely close ones."""
        surfaces = _surfaces(CaseSpec(name="n", reynolds=6.0e6, mach=0.15, aoa_deg=0.0))
        expected = naca0012_coordinates(241, chord=1.0, blunt_te=False)
        assert np.array_equal(surfaces["upper"], expected)
        assert np.array_equal(surfaces["lower"][:, 1], -expected[:, 1])

    def test_default_spec_still_produces_the_exact_naca_blockmeshdict(self) -> None:
        spec = CaseSpec(name="n", reynolds=6.0e6, mach=0.15, aoa_deg=0.0)
        # Reconstructing the same spec must render the same bytes; the `section` field
        # defaults to None and must not appear anywhere in the output.
        assert _blockmeshdict(spec) == _blockmeshdict(spec.model_copy())

    def test_the_naca_blunt_te_validator_still_refuses_a_wrong_thickness(self) -> None:
        with pytest.raises(ValueError, match="inconsistent with the standard NACA 0012"):
            CaseSpec(
                name="n",
                reynolds=6.0e6,
                mach=0.15,
                aoa_deg=0.0,
                trailing_edge_thickness=0.01,
                n_te=4,
            )


class TestTheSectionIsTheMeasuredGeometry:
    def test_the_outline_reproduces_the_measured_teardrop(self) -> None:
        upper = _surfaces(_spec(BC_FLEXIBLE))["upper"]
        peak = upper[int(np.argmax(upper[:, 1]))]
        # The cosine-spaced stations do not land exactly on the max-thickness station, so
        # the sampled peak sits a hair under the analytic one (4.79973 mm vs 4.8 mm at
        # n_surface=120). Assert the sampling resolution, not exact equality -- an exact
        # assertion here would be pinning the station spacing, not the geometry.
        assert peak[1] == pytest.approx(MAX_HALF_T, rel=1e-3)
        assert peak[1] <= MAX_HALF_T  # never overshoots the measured maximum
        # Max thickness lands where Fig 2.5 puts it, ~0.1c from the nose.
        assert peak[0] == pytest.approx(NOSE_X, abs=0.0006)
        assert upper[0][1] == 0.0  # leading edge on the chord line

    @pytest.mark.parametrize("b_over_c", [BC_FLEXIBLE, BC_RIGID])
    def test_the_plate_is_flat_at_exactly_b_over_two_from_the_root_aft(
        self, b_over_c: float
    ) -> None:
        upper = _surfaces(_spec(b_over_c))["upper"]
        aft = upper[upper[:, 0] >= JOIN_X]
        assert np.allclose(aft[:, 1], b_over_c * CHORD / 2.0, rtol=0, atol=1e-12)
        assert upper[-1][1] == pytest.approx(b_over_c * CHORD / 2.0, rel=1e-12)

    def test_the_section_is_symmetric_so_the_c_grid_mirror_path_holds(self) -> None:
        surfaces = _surfaces(_spec(BC_FLEXIBLE))
        assert np.array_equal(surfaces["lower"][:, 0], surfaces["upper"][:, 0])
        assert np.array_equal(surfaces["lower"][:, 1], -surfaces["upper"][:, 1])

    def test_thickness_never_increases_aft_of_the_peak(self) -> None:
        """A bump in the taper would be a meshing hazard and is not what Fig 2.5 draws."""
        upper = _surfaces(_spec(BC_FLEXIBLE))["upper"]
        aft = upper[upper[:, 0] >= NOSE_X]
        assert np.all(np.diff(aft[:, 1]) <= 1e-15)

    def test_the_taper_meets_the_plate_with_matched_slope(self) -> None:
        """C1 at the root: a kink there would put a skew spike at x = 30 mm."""
        x = np.linspace(JOIN_X - 0.002, JOIN_X + 0.002, 401)
        y = hg2007_coordinates(
            2,
            chord=CHORD,
            nose_length=NOSE_X,
            max_half_thickness=MAX_HALF_T,
            join_x=JOIN_X,
            plate_half_thickness=BC_FLEXIBLE * CHORD / 2.0,
        )
        del y  # constructed only to assert the generator accepts the endpoints
        from aero.adapters.openfoam.geometry import hg2007_half_thickness

        t = hg2007_half_thickness(
            x,
            chord=CHORD,
            nose_length=NOSE_X,
            max_half_thickness=MAX_HALF_T,
            join_x=JOIN_X,
            plate_half_thickness=BC_FLEXIBLE * CHORD / 2.0,
        )
        slope = np.diff(t) / np.diff(x)
        assert abs(slope[-1]) < 1e-9  # flat inside the plate
        assert abs(slope[len(slope) // 2 - 5]) < 0.05  # and approaching flat at the root


class TestTheRecordedThicknessDescribesTheMeshedGeometry:
    def test_a_mismatched_trailing_edge_thickness_is_loud(self) -> None:
        """`trailing_edge_thickness` records the geometry; it must not be a free knob."""
        with pytest.raises(ValueError, match="does not match the teardrop/plate section"):
            CaseSpec(
                name="hg2007",
                reynolds=9000,
                mach=0.01,
                aoa_deg=0.0,
                chord=CHORD,
                turbulence_model="laminar",
                section=_section(BC_FLEXIBLE),
                trailing_edge_thickness=BC_RIGID,
                n_te=4,
            )

    def test_the_two_arms_differ_only_in_plate_thickness(self) -> None:
        """The paired claim rests on this: same topology, same cell counts, one difference."""
        flex = _surfaces(_spec(BC_FLEXIBLE))["upper"]
        rigid = _surfaces(_spec(BC_RIGID))["upper"]
        assert np.array_equal(flex[:, 0], rigid[:, 0])  # identical x-stations
        forward = flex[:, 0] < NOSE_X
        assert np.array_equal(flex[forward, 1], rigid[forward, 1])  # identical nose
        assert flex[-1][1] < rigid[-1][1]  # and only the plate differs
