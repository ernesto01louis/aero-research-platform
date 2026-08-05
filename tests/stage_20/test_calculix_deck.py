"""The authored CalculiX solid: every claim the deck makes is read back and asserted.

A wrong CalculiX deck almost never crashes -- it converges, exits 0, and produces a
plausible deflection. So each test here drives one specific wrong deck and requires a loud
refusal, rather than checking that the right deck is right.

The three that would otherwise be silent, all learned from upstream's proven
`perpendicular-flap/solid-calculix` bytes:

- **no `*CLOAD`** on the interface node set: the adapter injects forces by OVERWRITING
  that block, so without it the solid runs force-free and reports a pitch amplitude of
  zero rather than an error;
- **`INC` too small**: at CalculiX's default of 100, ccx finishes its step mid-run, writes
  its `.frd` and exits ZERO -- the supervisor records `all-exited` and the K2 gate PASSES;
- **a slab whose z-extent is not the fluid's span**: preCICE `Force` is an absolute force,
  so a 1 m slab under a 2.5 mm span's load is 400x too stiff while everything converges.
"""

from __future__ import annotations

import math
from pathlib import Path

import numpy as np
import pytest
from aero.adapters.openfoam.geometry import hg2007_coordinates, hg2007_half_thickness
from aero.adapters.precice.calculix import (
    INTERFACE_NSET,
    INTERFACE_PATCH,
    NOSE_NSET,
    CalculiXAdapterConfig,
    CalculiXDeckError,
    CalculiXMaterial,
    CalculiXSolidSpec,
    assert_adapter_config,
    assert_calculix_deck,
    read_adapter_config,
    read_calculix_deck,
    write_adapter_config,
    write_calculix_deck,
)
from aero.postprocess.flapping_kinematics import FlappingKinematics
from pydantic import ValidationError

pytestmark = pytest.mark.stage_20

# The gated operating point's geometry (reference.md): 90 mm chord, 30 mm aluminium
# teardrop + 60 mm steel plate, flexible arm b/c = 0.85e-3. dt and max_time are kept small
# here so the amplitude table stays a few hundred rows; the campaign's are set by I7/I4.
CHORD = 0.090
NOSE_X = 0.0085
MAX_HALF_T = 0.0048
JOIN_X = 0.030
BC_FLEXIBLE = 0.85e-3
SPAN = 0.0025
PERIOD = 1.0145
PLUNGE_AMPLITUDE = 0.0175

STEEL = CalculiXMaterial(name="STEEL", youngs_modulus=2.05e11, poisson_ratio=0.30, density=7850.0)
ALUMINIUM = CalculiXMaterial(
    name="ALUMINIUM", youngs_modulus=7.0e10, poisson_ratio=0.33, density=2700.0
)


def _kinematics(**overrides) -> FlappingKinematics:
    return FlappingKinematics(
        **{
            "stroke_amplitude": PLUNGE_AMPLITUDE,
            "frequency": 1.0 / PERIOD,
            "pitch_amplitude_deg": 0.0,
            "stroke_plane_deg": 90.0,
            "ramp_cycles": 1.0,
            **overrides,
        }
    )


def _surface_x(n_points: int = 41) -> tuple[float, ...]:
    """The fluid's surface stations, leading-edge point excluded (see the spec validator)."""
    curve = hg2007_coordinates(
        n_points,
        chord=CHORD,
        nose_length=NOSE_X,
        max_half_thickness=MAX_HALF_T,
        join_x=JOIN_X,
        plate_half_thickness=BC_FLEXIBLE * CHORD / 2.0,
    )
    return tuple(float(x) for x in curve[1:, 0])


def _spec(**overrides) -> CalculiXSolidSpec:
    return CalculiXSolidSpec(
        **{
            "name": "hg2007_flexible",
            "surface_x": _surface_x(),
            "chord": CHORD,
            "nose_length": NOSE_X,
            "max_half_thickness": MAX_HALF_T,
            "join_x": JOIN_X,
            "plate_half_thickness": BC_FLEXIBLE * CHORD / 2.0,
            "span": SPAN,
            "n_through_thickness": 4,
            "plate": STEEL,
            "nose": ALUMINIUM,
            "time_window_size": 5.0e-3,
            "max_time": 0.5,
            "kinematics": _kinematics(),
            **overrides,
        }
    )


def _written(tmp_path: Path, **overrides):
    spec = _spec(**overrides)
    return spec, write_calculix_deck(spec, dest_dir=tmp_path)


def _tamper(tmp_path: Path, replacements: dict[str, str]) -> None:
    """Edit the written main deck in place, then the caller re-reads and asserts."""
    path = tmp_path / "hg2007_flexible.inp"
    text = path.read_text(encoding="utf-8")
    for old, new in replacements.items():
        assert old in text, f"{old!r} is not in the written deck"
        text = text.replace(old, new)
    path.write_text(text, encoding="utf-8")


class TestTheDeckRoundTrips:
    def test_a_written_deck_reads_back_and_asserts(self, tmp_path: Path) -> None:
        spec, deck = _written(tmp_path)
        assert_calculix_deck(deck, spec)

    def test_the_element_type_is_the_incompatible_modes_hex(self, tmp_path: Path) -> None:
        _, deck = _written(tmp_path)
        assert deck.element_type == "C3D8I"

    def test_the_mesh_is_one_element_thick(self, tmp_path: Path) -> None:
        spec, deck = _written(tmp_path)
        n_x = len(spec.surface_x)
        assert len(deck.z_levels) == 2
        assert deck.n_nodes == n_x * (spec.n_through_thickness + 1) * 2
        assert deck.n_elements == (n_x - 1) * spec.n_through_thickness

    def test_every_element_has_a_positive_jacobian(self, tmp_path: Path) -> None:
        """A collapsed node column at the leading edge would make ccx refuse the mesh.

        This is why the spec REQUIRES the leading-edge point to be excluded: the section's
        half-thickness is zero there, so a station at x=0 gives every element in that
        column zero volume. The check is a real one -- element volumes are re-derived from
        the written coordinates, not asserted from the writer's intent.
        """
        spec, _ = _written(tmp_path)
        nodes, elements = _read_mesh(tmp_path / "all.msh")
        volumes = [_hex_volume([nodes[n] for n in conn]) for conn in elements.values()]
        assert min(volumes) > 0.0, "a non-positive Jacobian would make ccx refuse the mesh"
        # Sanity: the total volume is the section's area times the span.
        x = np.asarray(spec.surface_x)
        area = float(np.trapezoid(2.0 * spec.half_thickness(x), x))
        assert sum(volumes) == pytest.approx(area * SPAN, rel=2e-3)

    def test_the_solid_wetted_curve_is_the_fluids(self, tmp_path: Path) -> None:
        spec, deck = _written(tmp_path)
        x = np.asarray([point[0] for point in deck.wetted_upper])
        y = np.asarray([point[1] for point in deck.wetted_upper])
        want = hg2007_half_thickness(
            x,
            chord=CHORD,
            nose_length=NOSE_X,
            max_half_thickness=MAX_HALF_T,
            join_x=JOIN_X,
            plate_half_thickness=BC_FLEXIBLE * CHORD / 2.0,
        )
        # Not bitwise: CalculiX truncates numeric fields at 20 characters, which caps the
        # deck at 14 significant digits (measured -- see _DECK_FIELD_WIDTH). On a 0.09 m
        # chord that is ~1e-15 m, four orders inside this tolerance and eleven orders below
        # the 76.5 um plate thickness, so the wetted curves are the same curve.
        assert np.allclose(x, np.asarray(spec.surface_x), rtol=0.0, atol=1e-12)
        assert float(np.max(np.abs(y - want))) < 1e-12

    def test_the_nose_is_prescribed_and_the_plate_is_not(self, tmp_path: Path) -> None:
        spec, deck = _written(tmp_path)
        n_nose_stations = sum(1 for x in spec.surface_x if x <= JOIN_X)
        assert deck.nsets[NOSE_NSET] == n_nose_stations * (spec.n_through_thickness + 1) * 2
        assert deck.nsets[NOSE_NSET] < deck.n_nodes  # the plate is free

    def test_the_interface_is_the_wetted_boundary_at_both_z_faces(self, tmp_path: Path) -> None:
        spec, deck = _written(tmp_path)
        n_x = len(spec.surface_x)
        n_eta = spec.n_through_thickness + 1
        # Perimeter of the (i, j) block, both z faces: 2*(n_x + n_eta) - 4 corners, x2.
        assert deck.nsets[INTERFACE_NSET] == 2 * (2 * (n_x + n_eta) - 4)


class TestTheSilentFailuresAreRefused:
    def test_a_missing_cload_is_refused(self, tmp_path: Path) -> None:
        _written(tmp_path)
        _tamper(tmp_path, {f"{INTERFACE_NSET}, 3, 0.0\n": ""})
        with pytest.raises(CalculiXDeckError, match="CLOAD"):
            assert_calculix_deck(read_calculix_deck(tmp_path / "hg2007_flexible.inp"), _spec())

    def test_a_nonzero_cload_is_refused(self, tmp_path: Path) -> None:
        _written(tmp_path)
        _tamper(tmp_path, {f"{INTERFACE_NSET}, 2, 0.0": f"{INTERFACE_NSET}, 2, 1.0"})
        with pytest.raises(CalculiXDeckError, match=r"not all exactly 0\.0"):
            assert_calculix_deck(read_calculix_deck(tmp_path / "hg2007_flexible.inp"), _spec())

    def test_the_calculix_default_increment_cap_is_refused(self, tmp_path: Path) -> None:
        spec, deck = _written(tmp_path)
        _tamper(tmp_path, {f"INC={deck.max_increments}": "INC=100"})
        with pytest.raises(CalculiXDeckError, match="exit ZERO"):
            assert_calculix_deck(read_calculix_deck(tmp_path / "hg2007_flexible.inp"), spec)

    def test_the_increment_cap_is_computed_from_the_window_count(self, tmp_path: Path) -> None:
        spec, deck = _written(tmp_path)
        assert deck.max_increments == 10 * math.ceil(spec.max_time / spec.time_window_size)

    def test_a_slab_thicker_than_the_fluid_span_is_refused(self, tmp_path: Path) -> None:
        spec, deck = _written(tmp_path)
        # The exact upstream mistake: keep the flap's 1 m slab under a 2.5 mm span's load.
        wrong = _spec(span=1.0)
        with pytest.raises(CalculiXDeckError, match="absolute force"):
            assert_calculix_deck(deck, wrong)
        assert deck.span == pytest.approx(spec.span, abs=1e-15)

    def test_a_plain_c3d8_is_refused(self, tmp_path: Path) -> None:
        _written(tmp_path)
        text = (tmp_path / "all.msh").read_text(encoding="utf-8")
        (tmp_path / "all.msh").write_text(text.replace("C3D8I", "C3D8"), encoding="utf-8")
        with pytest.raises(CalculiXDeckError, match="shear-lock"):
            assert_calculix_deck(read_calculix_deck(tmp_path / "hg2007_flexible.inp"), _spec())

    def test_a_deck_without_nlgeom_is_refused(self, tmp_path: Path) -> None:
        _written(tmp_path)
        _tamper(tmp_path, {"*STEP, NLGEOM,": "*STEP,"})
        with pytest.raises(CalculiXDeckError, match="NLGEOM"):
            assert_calculix_deck(read_calculix_deck(tmp_path / "hg2007_flexible.inp"), _spec())

    def test_numerical_damping_is_refused(self, tmp_path: Path) -> None:
        _written(tmp_path)
        _tamper(tmp_path, {"ALPHA=0.0": "ALPHA=-0.05"})
        with pytest.raises(CalculiXDeckError, match="ALPHA"):
            assert_calculix_deck(read_calculix_deck(tmp_path / "hg2007_flexible.inp"), _spec())

    def test_a_solid_dt_that_is_not_the_window_size_is_refused(self, tmp_path: Path) -> None:
        _, deck = _written(tmp_path)
        with pytest.raises(CalculiXDeckError, match="time-window size"):
            assert_calculix_deck(deck, _spec(time_window_size=2.5e-3, max_time=0.5))

    def test_dropping_direct_is_refused(self, tmp_path: Path) -> None:
        _written(tmp_path)
        _tamper(tmp_path, {"*DYNAMIC, ALPHA=0.0, DIRECT": "*DYNAMIC, ALPHA=0.0"})
        with pytest.raises(CalculiXDeckError, match="DIRECT"):
            assert_calculix_deck(read_calculix_deck(tmp_path / "hg2007_flexible.inp"), _spec())

    def test_unsuppressing_the_out_of_plane_dof_is_refused(self, tmp_path: Path) -> None:
        _written(tmp_path)
        _tamper(tmp_path, {"*BOUNDARY\nNall, 3\n": ""})
        with pytest.raises(CalculiXDeckError, match="dof 3"):
            assert_calculix_deck(read_calculix_deck(tmp_path / "hg2007_flexible.inp"), _spec())

    def test_an_unfixed_chordwise_nose_is_refused(self, tmp_path: Path) -> None:
        _written(tmp_path)
        _tamper(tmp_path, {f"*BOUNDARY\n{NOSE_NSET}, 1, 1\n": ""})
        with pytest.raises(CalculiXDeckError, match="drift chordwise"):
            assert_calculix_deck(read_calculix_deck(tmp_path / "hg2007_flexible.inp"), _spec())


class TestThePrescribedPlunge:
    def test_the_table_reproduces_the_analytic_plunge(self, tmp_path: Path) -> None:
        spec, deck = _written(tmp_path)
        t = np.asarray(deck.amplitude.t)
        analytic = spec.kinematics.evaluate(t)["y"]
        error = float(np.max(np.abs(np.asarray(deck.amplitude.value) - analytic)))
        assert error < 1e-6 * PLUNGE_AMPLITUDE

    def test_the_table_is_sampled_at_the_coupling_window(self, tmp_path: Path) -> None:
        # Rows land exactly where a DIRECT step evaluates its boundary conditions, so the
        # linear interpolation error at the evaluation points is zero rather than bounded.
        spec, deck = _written(tmp_path)
        steps = np.diff(np.asarray(deck.amplitude.t))
        assert np.allclose(steps, spec.time_window_size, rtol=0, atol=1e-15)

    def test_the_table_extends_past_the_end_time(self, tmp_path: Path) -> None:
        spec, deck = _written(tmp_path)
        assert deck.amplitude.t[-1] > spec.max_time

    def test_a_truncated_table_is_refused(self, tmp_path: Path) -> None:
        spec, _ = _written(tmp_path)
        amp = tmp_path / "plunge.amp"
        rows = amp.read_text(encoding="utf-8").splitlines()
        amp.write_text("\n".join(rows[: len(rows) // 2]) + "\n", encoding="utf-8")
        with pytest.raises(CalculiXDeckError, match="extrapolate"):
            assert_calculix_deck(read_calculix_deck(tmp_path / "hg2007_flexible.inp"), spec)

    def test_the_motion_starts_from_rest_at_the_built_position(self, tmp_path: Path) -> None:
        # The C1 (1-cos) ramp (ADR-024) is what keeps the impulsive start from tearing the
        # fluid mesh; the deck must inherit it rather than re-derive a cosine.
        _, deck = _written(tmp_path)
        assert deck.amplitude.t[0] == 0.0
        assert deck.amplitude.value[0] == 0.0

    def test_a_prescribed_pitch_is_refused_at_construction(self) -> None:
        with pytest.raises(ValidationError, match="arises from the plate"):
            _spec(kinematics=_kinematics(pitch_amplitude_deg=5.35))

    def test_the_default_horizontal_stroke_plane_is_refused(self) -> None:
        # FlappingKinematics defaults stroke_plane_deg to 0, at which evaluate()['vy'] is
        # identically zero -- a deck that prescribes no motion at all, silently.
        with pytest.raises(ValidationError, match="stroke_plane_deg must be 90"):
            _spec(kinematics=_kinematics(stroke_plane_deg=0.0))


class TestTheSpecRefusesADegenerateSection:
    def test_including_the_leading_edge_point_is_refused(self) -> None:
        with pytest.raises(ValidationError, match="zero volume"):
            _spec(surface_x=(0.0, *_surface_x()))

    def test_a_non_monotone_station_list_is_refused(self) -> None:
        stations = list(_surface_x())
        stations[3], stations[4] = stations[4], stations[3]
        with pytest.raises(ValidationError, match="strictly increasing"):
            _spec(surface_x=tuple(stations))

    def test_stations_that_do_not_reach_the_chord_are_refused(self) -> None:
        with pytest.raises(ValidationError, match="must end at the chord"):
            _spec(surface_x=_surface_x()[:-1])


class TestTheAdapterConfig:
    def _config(self, **overrides) -> CalculiXAdapterConfig:
        return CalculiXAdapterConfig(
            **{
                "participant": "Solid",
                "nodes_mesh": "Solid-Mesh",
                "patch": INTERFACE_PATCH,
                "read_data": ("Force",),
                "write_data": ("Displacement",),
                "precice_config_file": "../precice-config.xml",
                **overrides,
            }
        )

    def test_it_round_trips(self, tmp_path: Path) -> None:
        config = self._config()
        assert write_adapter_config(config, dest=tmp_path / "config.yml") == config

    def test_the_patch_name_resolves_to_the_decks_node_set(self, tmp_path: Path) -> None:
        spec, deck = _written(tmp_path)
        config = write_adapter_config(self._config(), dest=tmp_path / "config.yml")
        assert config.interface_nset == INTERFACE_NSET
        assert_adapter_config(config, spec=spec, deck=deck, mesh_name=spec.mesh_name)

    def test_a_patch_the_deck_does_not_declare_is_refused(self, tmp_path: Path) -> None:
        spec, deck = _written(tmp_path)
        with pytest.raises(CalculiXDeckError, match="does not declare"):
            assert_adapter_config(
                self._config(patch="wing"), spec=spec, deck=deck, mesh_name=spec.mesh_name
            )

    def test_reading_stress_instead_of_force_is_refused(self, tmp_path: Path) -> None:
        spec, deck = _written(tmp_path)
        with pytest.raises(CalculiXDeckError, match="not Turek-Hron FSI3's Stress"):
            assert_adapter_config(
                self._config(read_data=("Stress",)),
                spec=spec,
                deck=deck,
                mesh_name=spec.mesh_name,
            )

    def test_a_mesh_name_the_configuration_does_not_declare_is_refused(
        self, tmp_path: Path
    ) -> None:
        spec, deck = _written(tmp_path)
        with pytest.raises(CalculiXDeckError, match="nodes-mesh"):
            assert_adapter_config(self._config(), spec=spec, deck=deck, mesh_name="Structure-Mesh")

    def test_a_second_interface_is_refused(self, tmp_path: Path) -> None:
        path = tmp_path / "config.yml"
        write_adapter_config(self._config(), dest=path)
        text = path.read_text(encoding="utf-8")
        block = text.split("        - ")[1].split("\n\n")[0]
        path.write_text(text.replace("\n\nprecice", f"\n        - {block}\n\nprecice"), "utf-8")
        with pytest.raises(CalculiXDeckError, match="exactly one interface"):
            read_adapter_config(path)

    def test_an_unknown_top_level_key_is_refused(self, tmp_path: Path) -> None:
        path = tmp_path / "config.yml"
        write_adapter_config(self._config(), dest=path)
        path.write_text(path.read_text(encoding="utf-8") + "log-level: DEBUG\n", encoding="utf-8")
        with pytest.raises(CalculiXDeckError, match="unexpected top-level key"):
            read_adapter_config(path)


class TestTheDeckFitsCalculiXsReader:
    """CalculiX reads numeric fields as ``(1:20)``, and truncates anything wider.

    MEASURED, not assumed. A first spike of this deck written at `%.16e` (22 characters)
    made ccx 2.20 fail every numeric card it read -- *NODE, *ELASTIC, *DENSITY, *AMPLITUDE
    and *DYNAMIC alike -- with `*ERROR reading ...` and rc=201, before a single increment.
    At `%.13e` (19 characters) the same deck reads, solves and exits 0.
    """

    def test_no_written_number_exceeds_the_readers_field_width(self, tmp_path: Path) -> None:
        _written(tmp_path)
        for name in ("all.msh", "plunge.amp", "hg2007_flexible.inp"):
            for lineno, line in enumerate(
                (tmp_path / name).read_text(encoding="utf-8").splitlines(), start=1
            ):
                if line.startswith("*"):
                    continue
                for field in line.split(","):
                    assert len(field.strip()) <= 20, f"{name}:{lineno}: {field!r} is too wide"

    def test_a_time_step_that_cannot_be_written_exactly_is_refused(self) -> None:
        # 14 significant digits is all the format carries, so a dt needing 17 would be
        # silently rounded -- and the solid would then step at a different dt than the
        # coupling while converging perfectly happily.
        with pytest.raises(ValidationError, match="do not survive the deck"):
            _spec(time_window_size=1.2345678901234567e-4)

    def test_a_representable_time_step_is_accepted(self) -> None:
        assert _spec(time_window_size=3.5e-4, max_time=0.5).time_window_size == 3.5e-4


class TestPlaneStrainIsNotPlaneStress:
    def test_the_effective_modulus_carries_the_one_over_one_minus_nu_squared(self) -> None:
        # `*BOUNDARY Nall, 3` is plane STRAIN, so a naive E*b^3/12 hand-check of the
        # plate's stiffness is ~10 % low. The reference value is recorded so a future
        # reader does not re-derive it from the wrong assumption.
        assert STEEL.plane_strain_modulus == pytest.approx(2.2527e11, rel=1e-4)
        assert STEEL.plane_strain_modulus / STEEL.youngs_modulus == pytest.approx(1.0989, rel=1e-4)


# --------------------------------------------------------------------------------------
# Local mesh reader, so the geometry checks read the FILE rather than the writer's intent
# --------------------------------------------------------------------------------------


def _read_mesh(path: Path):
    nodes: dict[int, tuple[float, float, float]] = {}
    elements: dict[int, tuple[int, ...]] = {}
    mode = None
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("**"):
            continue
        if line.startswith("*"):
            upper = line.upper()
            mode = (
                "node"
                if upper.startswith("*NODE")
                else "elem"
                if upper.startswith("*ELEMENT")
                else None
            )
            continue
        values = [v.strip() for v in line.split(",") if v.strip()]
        if mode == "node":
            nodes[int(values[0])] = (float(values[1]), float(values[2]), float(values[3]))
        elif mode == "elem":
            elements[int(values[0])] = tuple(int(v) for v in values[1:])
    return nodes, elements


def _hex_volume(corners) -> float:
    """Volume of a trilinear hex by 2x2x2 Gauss quadrature of the Jacobian determinant."""
    nodes = np.asarray(corners, dtype=np.float64)
    signs = np.array(
        [
            (-1, -1, -1),
            (1, -1, -1),
            (1, 1, -1),
            (-1, 1, -1),
            (-1, -1, 1),
            (1, -1, 1),
            (1, 1, 1),
            (-1, 1, 1),
        ],
        dtype=np.float64,
    )
    g = 1.0 / math.sqrt(3.0)
    volume = 0.0
    for xi in (-g, g):
        for eta in (-g, g):
            for zeta in (-g, g):
                local = np.array([xi, eta, zeta])
                # dN/dxi_k for the trilinear shape functions.
                grads = np.empty((8, 3))
                for a in range(8):
                    s = signs[a]
                    for k in range(3):
                        other = [j for j in range(3) if j != k]
                        grads[a, k] = (
                            0.125
                            * s[k]
                            * (1.0 + s[other[0]] * local[other[0]])
                            * (1.0 + s[other[1]] * local[other[1]])
                        )
                volume += float(np.linalg.det(nodes.T @ grads))
    return volume
