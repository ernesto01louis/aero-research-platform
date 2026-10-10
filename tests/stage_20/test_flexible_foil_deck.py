"""The dimensional fluid deck: what has to be there, and what must not be missing.

The Stage-20 fluid participant is the first DIMENSIONAL case in this package. Everything
else here solves a dimensionless problem with `U_INF = RHO_INF = 1.0`, which is exactly
why `plunging_airfoil.py` cannot be reused: preCICE exchanges Force in newtons and
CalculiX solves in SI, so a dimensionless fluid would disagree with the solid about what a
force is by `rho U^2` -- while converging.

The headline test is `test_the_wall_patch_set_is_the_same_everywhere`: it parses the
rendered `blockMeshDict` for the wall patches the mesh actually declares and requires that
exact set in every place a wall is named. Dropping `airfoil_te` from the force objects
would bias `C_T` on ONE ARM ONLY -- the blunt base is 76.5 um on the flexible foil and
380.7 um on the rigid one -- landing straight in the gated increment.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
from aero.adapters.openfoam.flexible_foil import (
    INTERFACE_POWER_TAG,
    WALL_PATCHES,
    FlexibleFoilSpec,
    write_flexible_foil_case,
)
from aero.adapters.openfoam.schemas import TeardropPlateSection
from pydantic import ValidationError

pytestmark = pytest.mark.stage_20

CHORD = 0.090
BC_FLEXIBLE = 0.85e-3
SPAN = 0.0025


def _section(b_over_c: float = BC_FLEXIBLE) -> TeardropPlateSection:
    return TeardropPlateSection(
        nose_length=0.0085,
        max_half_thickness=0.0048,
        join_x=0.030,
        plate_half_thickness=b_over_c * CHORD / 2.0,
    )


def _spec(**overrides) -> FlexibleFoilSpec:
    return FlexibleFoilSpec(
        **{
            "name": "hg2007_flexible",
            "u_inf": 0.1,
            "rho": 1000.0,
            "nu": 1.0e-6,
            "chord": CHORD,
            "span": SPAN,
            "section": _section(),
            "time_window_size": 3.5e-4,
            "max_time": 1.0145,
            "n_surface": 20,
            "n_normal": 20,
            "n_front": 10,
            "n_wake": 16,
            **overrides,
        }
    )


@pytest.fixture
def case(tmp_path: Path) -> Path:
    write_flexible_foil_case(_spec(), tmp_path)
    return tmp_path


def _read(case: Path, relative: str) -> str:
    return (case / relative).read_text(encoding="utf-8")


def _blockmesh_wall_patches(text: str) -> set[str]:
    """The patch names the rendered blockMeshDict declares as `type wall`."""
    boundary = text.split("boundary\n(", 1)[1]
    return {
        name for name, body in re.findall(r"(\w+)\s*\{([^}]*)\}", boundary) if "type wall" in body
    }


class TestTheWallPatchSetIsClosed:
    def test_the_wall_patch_set_is_the_same_everywhere(self, case: Path) -> None:
        walls = _blockmesh_wall_patches(_read(case, "system/blockMeshDict"))
        assert walls == set(WALL_PATCHES), "the C-grid's blunt TE must emit a second wall patch"

        control = _read(case, "system/controlDict")
        for block in ("forces1", "forceCoeffs1"):
            body = control.split(block, 1)[1]
            patches = re.search(r"patches\s+\(([^)]*)\)", body)
            assert patches is not None
            assert set(patches.group(1).split()) == walls, f"{block} must integrate every wall"

        precice = _read(case, "system/preciceDict")
        interface = re.search(r"patches\s+\(([^)]*)\)", precice)
        assert interface is not None
        assert set(interface.group(1).split()) == walls

        motion = _read(case, "constant/dynamicMeshDict")
        diffusivity = re.search(r"inverseDistance\s+\(([^)]*)\)", motion)
        assert diffusivity is not None
        assert set(diffusivity.group(1).split()) == walls

    @pytest.mark.parametrize("field", ["U", "p", "pointDisplacement"])
    def test_every_field_declares_every_wall(self, case: Path, field: str) -> None:
        text = _read(case, f"0/{field}")
        for patch in WALL_PATCHES:
            assert re.search(rf"^\s+{patch}\s*$", text, re.MULTILINE), (
                f"0/{field} does not name the {patch} patch; OpenFOAM would refuse the case, "
                "but only after the mesh is built"
            )


class TestTheCouplingIsActuallyWired:
    def test_the_adapter_function_object_is_present(self, case: Path) -> None:
        # Without these two, pimpleFoam runs a happy UNCOUPLED solve to endTime and exits 0.
        control = _read(case, "system/controlDict")
        assert 'libs ("libpreciceAdapterFunctionObject.so");' in control
        assert "type            preciceAdapterFunctionObject;" in control
        assert "errors          strict;" in control

    def test_the_interface_reads_displacement_and_writes_force(self, case: Path) -> None:
        precice = _read(case, "system/preciceDict")
        assert re.search(r"readData\s*\(\s*Displacement\s*\)", precice)
        assert re.search(r"writeData\s*\(\s*Force\s*\)", precice)
        assert "locations         faceCenters;" in precice

    def test_the_wall_displacement_is_adapter_driven_not_prescribed(self, case: Path) -> None:
        # A prescribed oscillation here would drive the foil independently of the solid,
        # and the run would still converge -- to the wrong problem.
        text = _read(case, "0/pointDisplacement")
        assert "oscillatingDisplacement" not in text
        assert text.count("type fixedValue;") == len(WALL_PATCHES) + 1  # + farfield

    def test_the_wall_velocity_is_the_moving_frame_one(self, case: Path) -> None:
        assert _read(case, "0/U").count("type movingWallVelocity;") == len(WALL_PATCHES)


class TestTheDeckIsDimensional:
    def test_the_real_density_reaches_both_the_adapter_and_the_forces(self, case: Path) -> None:
        assert "rho rho [1 -3 0 0 0 0 0] 1000;" in _read(case, "system/preciceDict")
        assert "rhoInf          1000;" in _read(case, "system/controlDict")

    def test_the_viscosity_is_water_not_a_reynolds_derived_value(self, case: Path) -> None:
        assert "1e-06" in _read(case, "constant/transportProperties")

    def test_the_freestream_is_the_real_tunnel_speed(self, case: Path) -> None:
        assert "uniform (0.1 0 0)" in _read(case, "0/U")

    def test_the_reynolds_number_follows_from_the_dimensional_state(self) -> None:
        assert _spec().reynolds == pytest.approx(9000.0)


class TestTheTimeSteppingIsFixed:
    def test_the_step_is_the_coupling_window_and_is_not_adaptive(self, case: Path) -> None:
        control = _read(case, "system/controlDict")
        assert "adjustTimeStep  no;" in control
        assert "deltaT          0.00035;" in control
        assert "maxCo" not in control, "an adaptive step would fight the adapter for dt"

    def test_the_time_precision_is_raised(self, case: Path) -> None:
        # At the default 6, consecutive force rows collapse to the same printed time at
        # this dt and force_io's de-duplication deletes them.
        assert "timePrecision   12;" in _read(case, "system/controlDict")

    def test_the_time_scheme_is_euler_until_the_checkpoint_probe(self, case: Path) -> None:
        assert "default Euler" in _read(case, "system/fvSchemes")

    def test_second_order_time_is_expressible_but_not_the_default(self, tmp_path: Path) -> None:
        write_flexible_foil_case(_spec(ddt_scheme="backward"), tmp_path)
        assert "default backward" in _read(tmp_path, "system/fvSchemes")

    def test_every_reporting_object_runs_every_step(self, case: Path) -> None:
        # forces1, forceCoeffs1 and the interface-power object all sample every step; the
        # readout pairs them by time, so a mismatched cadence would silently misalign them.
        control = _read(case, "system/controlDict")
        assert control.count("writeControl    timeStep;\n        writeInterval   1;") == 3


class TestTheInterfacePowerObject:
    """P2 -- the rate at which the fluid does work on the DEFORMING structure.

    Verified live on aero-dev before this landed (the I6 probe): the coded object compiles
    under `setpriv --reuid 1000` and runs, its summed force reproduces `force.dat`'s total
    to twelve significant figures, and on a stationary mesh the power comes out at 1e-18 --
    which is the null result that proves it reads the WALL velocity rather than a
    cell-centre one.
    """

    def test_it_sums_openfoams_own_force_field(self, case: Path) -> None:
        # Re-deriving the stress tensor would be a second implementation of the quantity
        # being gated; summing the registered `force` field means P2 and C_T come from one
        # computation. That requires writeFields on the force object.
        control = _read(case, "system/controlDict")
        assert "writeFields     yes;" in control
        assert 'lookupObject<volVectorField>("force")' in control

    def test_it_names_the_same_walls_as_the_force_object(self, case: Path) -> None:
        control = _read(case, "system/controlDict")
        coded = control.split("interfacePower", 1)[1]
        named = set(re.findall(r'"(\w+)"', coded.split("wordList patchNames", 1)[1][:200]))
        assert named == set(WALL_PATCHES)

    def test_a_missing_patch_is_fatal_inside_the_solver(self, case: Path) -> None:
        # A silently-skipped patch would under-report P2 on one arm only.
        assert "FatalErrorInFunction" in _read(case, "system/controlDict")

    def test_it_runs_after_the_force_object_that_registers_the_field(self, case: Path) -> None:
        control = _read(case, "system/controlDict")
        assert control.index("forces1") < control.index("interfacePower"), (
            "function objects execute in declaration order; the power object looks up a "
            "field the force object registers"
        )

    def test_it_reports_through_the_log_with_a_greppable_tag(self, case: Path) -> None:
        assert f'Info<< "{INTERFACE_POWER_TAG} ' in _read(case, "system/controlDict")


class TestTheMeshIsThePreRegisteredOne:
    def test_the_wall_spacing_is_the_pre_registered_value(self) -> None:
        # CaseSpec defaults to 2.0e-6 chords -- 0.18 um here, which would need dt ~ 1.7e-6.
        assert _spec().first_cell_height == 5.0e-4
        assert _spec().mesh_spec().first_cell_height == 5.0e-4

    def test_the_blunt_base_is_exactly_the_plate_thickness(self) -> None:
        spec = _spec()
        assert spec.trailing_edge_thickness == pytest.approx(BC_FLEXIBLE)
        assert spec.mesh_spec().trailing_edge_thickness == pytest.approx(BC_FLEXIBLE)

    def test_the_two_arms_differ_only_in_the_plate(self, tmp_path: Path) -> None:
        flexible = _spec()
        rigid = _spec(section=_section(4.23e-3))
        assert flexible.mesh_spec().n_surface == rigid.mesh_spec().n_surface
        assert flexible.trailing_edge_thickness != rigid.trailing_edge_thickness

    def test_the_span_is_carried_through_to_the_mesh(self) -> None:
        assert _spec().mesh_spec().span == SPAN


class TestTheRbfRadiusIsScaled:
    def test_it_is_a_few_surface_cells_not_a_metre(self) -> None:
        spec = _spec()
        assert spec.rbf_support_radius == pytest.approx(
            spec.rbf_support_radius_spacings * spec.surface_spacing
        )
        # Upstream's literal 1. is eleven chords here; the point of the rule is the order.
        assert spec.rbf_support_radius < 0.5 * spec.chord
        assert spec.rbf_support_radius > 2.0 * spec.surface_spacing

    def test_it_tracks_the_mesh_rather_than_being_a_constant(self) -> None:
        coarse = _spec(n_surface=20).rbf_support_radius
        fine = _spec(n_surface=80).rbf_support_radius
        assert fine < coarse, "a refined interface must not keep a coarse mesh's radius"


class TestTheSpecRefusesNonsense:
    def test_a_join_outside_the_chord_is_refused(self) -> None:
        with pytest.raises(ValidationError, match="must lie inside the chord"):
            _spec(
                section=TeardropPlateSection(
                    nose_length=0.0085,
                    max_half_thickness=0.0048,
                    join_x=0.5,
                    plate_half_thickness=BC_FLEXIBLE * CHORD / 2.0,
                )
            )

    def test_an_unvalidated_time_scheme_is_refused_at_write_time(self, tmp_path: Path) -> None:
        with pytest.raises(ValueError, match="ddt_scheme must be one of"):
            write_flexible_foil_case(_spec(ddt_scheme="backwards"), tmp_path)
