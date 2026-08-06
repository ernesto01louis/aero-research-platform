"""The additive `PreciceConfigExpectation` extension: inert for Stage 19, live for Stage 20.

The C-family's authored-case claim is "every token this renderer substituted is observable
in the parsed model". Before this extension that claim was **not achievable**:
`MappingDecl.support_radius` and every `AccelerationDecl` field were parsed and never
asserted, so upstream's `support-radius="1."` — one metre on a 0.09 m chord — would have
rendered, parsed and run without a word.

Two properties are tested here, and they pull in opposite directions:

1. **Inert.** Stage 19's expectation mentions no new field, so `assert_config` must behave
   exactly as it did against the tagged v0.0.19 record.
2. **Live.** Every new field must actually be able to fail, or the extension is decorative.
   Each is driven with a deliberately wrong value.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from aero.adapters.precice.config import (
    UNSET,
    MappingExpectation,
    MeshExpectation,
    ParticipantDataExpectation,
    PreciceConfigError,
    PreciceConfigExpectation,
    assert_config,
    parse_precice_config,
)

pytestmark = pytest.mark.stage_20

# A minimal but structurally complete config in the perpendicular-flap shape: two RBF
# mappings with the SAME support radius (which is what makes the ordered-tuple choice
# load-bearing), an IQN-ILS acceleration with a filter but NO preconditioner.
_XML = """<?xml version="1.0" encoding="UTF-8" ?>
<precice-configuration>
  <data:vector name="Force" />
  <data:vector name="Displacement" />
  <mesh name="Fluid-Mesh" dimensions="2">
    <use-data name="Force" />
    <use-data name="Displacement" />
  </mesh>
  <mesh name="Solid-Mesh" dimensions="2">
    <use-data name="Displacement" />
    <use-data name="Force" />
  </mesh>
  <participant name="Fluid">
    <provide-mesh name="Fluid-Mesh" />
    <receive-mesh name="Solid-Mesh" from="Solid" />
    <write-data name="Force" mesh="Fluid-Mesh" />
    <read-data name="Displacement" mesh="Fluid-Mesh" />
    <mapping:rbf direction="write" from="Fluid-Mesh" to="Solid-Mesh" constraint="conservative">
      <basis-function:compact-polynomial-c6 support-radius="0.018" />
    </mapping:rbf>
    <mapping:rbf direction="read" from="Solid-Mesh" to="Fluid-Mesh" constraint="consistent">
      <basis-function:compact-polynomial-c6 support-radius="0.018" />
    </mapping:rbf>
  </participant>
  <participant name="Solid">
    <provide-mesh name="Solid-Mesh" />
    <write-data name="Displacement" mesh="Solid-Mesh" />
    <read-data name="Force" mesh="Solid-Mesh" />
    <watch-point mesh="Solid-Mesh" name="LE" coordinate="0.0;0.0" />
  </participant>
  <m2n:sockets acceptor="Fluid" connector="Solid" exchange-directory=".." />
  <coupling-scheme:parallel-implicit>
    <time-window-size value="0.001" />
    <max-time value="30.0" />
    <participants first="Fluid" second="Solid" />
    <exchange data="Force" mesh="Solid-Mesh" from="Fluid" to="Solid" />
    <exchange data="Displacement" mesh="Solid-Mesh" from="Solid" to="Fluid" />
    <max-iterations value="50" />
    <relative-convergence-measure limit="5e-3" data="Displacement" mesh="Solid-Mesh" />
    <relative-convergence-measure limit="5e-3" data="Force" mesh="Solid-Mesh" />
    <acceleration:IQN-ILS>
      <data name="Displacement" mesh="Solid-Mesh" />
      <data name="Force" mesh="Solid-Mesh" />
      <filter type="QR2" limit="1e-2" />
      <initial-relaxation value="0.5" />
      <max-used-iterations value="100" />
      <time-windows-reused value="15" />
    </acceleration:IQN-ILS>
  </coupling-scheme:parallel-implicit>
</precice-configuration>
"""


@pytest.fixture
def config():  # type: ignore[no-untyped-def]
    return parse_precice_config(_XML, source=Path("precice-config.xml"), sha256="0" * 64)


def _stage19_shaped() -> PreciceConfigExpectation:
    """Exactly the nine fields Stage 19 knew about. Nothing else is mentioned."""
    return PreciceConfigExpectation(
        participants=("Fluid", "Solid"),
        coupling_scheme="parallel-implicit",
        m2n_kind="sockets",
        time_window_size=1e-3,
        max_iterations=50,
        convergence_limits={"Displacement": 5e-3, "Force": 5e-3},
        convergence_kinds={
            "Displacement": "relative-convergence-measure",
            "Force": "relative-convergence-measure",
        },
        watch_points={"Solid/LE": (0.0, 0.0)},
        acceleration_kind="IQN-ILS",
    )


def _fully_specified(**overrides: object) -> PreciceConfigExpectation:
    fields: dict[str, object] = {
        **_stage19_shaped().model_dump(exclude={"max_time"}),
        "max_time": 30.0,
        "data_kinds": {"Force": "vector", "Displacement": "vector"},
        "meshes": {
            "Fluid-Mesh": MeshExpectation(dimensions=2, use_data=("Force", "Displacement")),
            "Solid-Mesh": MeshExpectation(dimensions=2, use_data=("Displacement", "Force")),
        },
        "participant_data": {
            "Solid": ParticipantDataExpectation(
                read_data=(("Force", "Solid-Mesh"),),
                write_data=(("Displacement", "Solid-Mesh"),),
            )
        },
        "mappings": (
            MappingExpectation(
                kind="rbf",
                direction="write",
                from_mesh="Fluid-Mesh",
                to_mesh="Solid-Mesh",
                constraint="conservative",
                basis_function="compact-polynomial-c6",
                support_radius=0.018,
            ),
            MappingExpectation(
                kind="rbf",
                direction="read",
                from_mesh="Solid-Mesh",
                to_mesh="Fluid-Mesh",
                constraint="consistent",
                basis_function="compact-polynomial-c6",
                support_radius=0.018,
            ),
        ),
        "acceleration_data": (("Displacement", "Solid-Mesh"), ("Force", "Solid-Mesh")),
        "acceleration_preconditioner": None,  # assert ABSENT — not "do not check"
        "acceleration_filter_type": "QR2",
        "acceleration_filter_limit": 1e-2,
        "acceleration_initial_relaxation": 0.5,
        "acceleration_max_used_iterations": 100,
        "acceleration_time_windows_reused": 15,
        "m2n_exchange_directory": "..",
        "exchanges": (
            ("Force", "Solid-Mesh", "Fluid", "Solid"),
            ("Displacement", "Solid-Mesh", "Solid", "Fluid"),
        ),
        "first_participant": "Fluid",
        "second_participant": "Solid",
    }
    fields.update(overrides)
    return PreciceConfigExpectation(**fields)  # type: ignore[arg-type]


class TestTheExtensionIsInertForStage19:
    def test_an_expectation_mentioning_no_new_field_still_passes(self, config) -> None:  # type: ignore[no-untyped-def]
        assert_config(config, _stage19_shaped())

    def test_every_new_field_defaults_to_do_not_check(self) -> None:
        """`None` on the plain fields, and the `UNSET` sentinel on the two that need to be
        able to assert ABSENCE. That distinction is not cosmetic: upstream's flap has no
        `<preconditioner>` while FSI3 has `residual-sum`, so an authored case must be able
        to pin either, and `None` is already spoken for by "assert absent"."""
        expectation = _stage19_shaped()
        assert expectation.max_time is None
        assert expectation.meshes is None
        assert expectation.mappings is None
        assert expectation.acceleration_preconditioner is UNSET
        assert expectation.acceleration_filter_type is UNSET

    def test_the_real_stage19_expectation_is_unchanged(self) -> None:
        """The tagged record's own literal must still construct and still say nothing new."""
        from aero.vv.fsi import TUREK_HRON_FSI3_EXPECTATION

        e = TUREK_HRON_FSI3_EXPECTATION

        assert e.time_window_size == 1e-3
        assert e.max_iterations == 100
        assert e.convergence_limits == {"Stress": 1e-4, "Displacement": 1e-4}
        assert e.watch_points == {"Solid/Flap-Tip": (0.6, 0.2)}
        assert e.max_time is None
        assert e.mappings is None
        assert e.acceleration_preconditioner is UNSET


class TestEveryNewFieldCanActuallyFail:
    """A field that cannot fail is decorative. Each is driven with a wrong value."""

    def test_the_fully_specified_expectation_passes(self, config) -> None:  # type: ignore[no-untyped-def]
        assert_config(config, _fully_specified())

    @pytest.mark.parametrize(
        ("override", "fragment"),
        [
            ({"max_time": 8.0}, "max-time"),
            ({"data_kinds": {"Force": "scalar", "Displacement": "vector"}}, "data kinds"),
            (
                {
                    "meshes": {
                        "Solid-Mesh": MeshExpectation(
                            dimensions=3, use_data=("Displacement", "Force")
                        )
                    }
                },
                "dimensions",
            ),
            (
                {
                    "participant_data": {
                        "Solid": ParticipantDataExpectation(
                            read_data=(("Stress", "Solid-Mesh"),),
                            write_data=(("Displacement", "Solid-Mesh"),),
                        )
                    }
                },
                "read-data",
            ),
            ({"acceleration_filter_type": "QR1"}, "filter type"),
            ({"acceleration_filter_limit": 1e-3}, "filter limit"),
            ({"acceleration_initial_relaxation": 0.1}, "initial-relaxation"),
            ({"acceleration_max_used_iterations": 50}, "max-used-iterations"),
            ({"acceleration_time_windows_reused": 10}, "time-windows-reused"),
            ({"acceleration_preconditioner": "residual-sum"}, "preconditioner"),
            ({"acceleration_data": (("Force", "Solid-Mesh"),)}, "acceleration data"),
            ({"m2n_exchange_directory": "."}, "exchange-directory"),
            ({"exchanges": (("Force", "Solid-Mesh", "Solid", "Fluid"),)}, "exchanges"),
            ({"first_participant": "Solid"}, "first participant"),
            ({"second_participant": "Fluid"}, "second participant"),
        ],
    )
    def test_a_wrong_value_is_refused(self, config, override, fragment) -> None:  # type: ignore[no-untyped-def]
        with pytest.raises(PreciceConfigError, match=fragment):
            assert_config(config, _fully_specified(**override))

    def test_a_mis_scaled_rbf_support_radius_is_refused(self, config) -> None:  # type: ignore[no-untyped-def]
        """The concrete failure this whole extension exists for.

        Upstream's perpendicular-flap declares `support-radius="1."` — one METRE, on a flap
        whose domain is order 1 m. Copied onto a 0.09 m chord it is ~11 chords wide: the RBF
        system stays solvable, the coupling converges, and the conservative force map is
        smeared across the entire foil. Nothing is loud. Before this extension there was no
        field in which to state the scaled value, so nothing could have caught it.
        """
        wrong = list(_fully_specified().mappings or ())
        wrong[0] = wrong[0].model_copy(update={"support_radius": 1.0})
        with pytest.raises(PreciceConfigError, match="mappings"):
            assert_config(config, _fully_specified(mappings=tuple(wrong)))

    def test_mapping_multiplicity_survives_because_the_field_is_ordered(self, config) -> None:  # type: ignore[no-untyped-def]
        """Both mappings share a support radius; only their direction differs.

        A set — or a dict keyed by radius — would collapse the two into one and a swapped
        read/write constraint would pass. This is the same multiplicity bug ADR-036's own
        band-parity test warns about.
        """
        swapped = list(_fully_specified().mappings or ())
        swapped[0], swapped[1] = swapped[1], swapped[0]
        with pytest.raises(PreciceConfigError, match="mappings"):
            assert_config(config, _fully_specified(mappings=tuple(swapped)))
