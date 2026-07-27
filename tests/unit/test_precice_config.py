"""Unit tests for the preCICE configuration reader, expectation gate and max-time rewrite."""

from __future__ import annotations

from pathlib import Path

import pytest
from aero.adapters.precice.config import (
    PreciceConfigError,
    PreciceConfigExpectation,
    assert_config,
    parse_precice_config,
    read_precice_config,
    rewrite_max_time,
)

pytestmark = pytest.mark.stage_19

_SHA = "0" * 64

# The pinned upstream Turek-Hron FSI3 configuration, verbatim. Kept inline rather than
# behind a DVC pull so the required unit job exercises the real bytes with no cluster
# and no data dependency.
FSI3_CONFIG = """<?xml version="1.0" encoding="UTF-8" ?>
<precice-configuration>
  <log>
    <sink filter="%Severity% &gt; debug and %Rank% = 0" enabled="true" />
  </log>

  <profiling mode="fundamental" synchronize="false" />

  <data:vector name="Stress" />
  <data:vector name="Displacement" />

  <mesh name="Fluid-Mesh-Centers" dimensions="2">
    <use-data name="Stress" />
  </mesh>

  <mesh name="Fluid-Mesh-Nodes" dimensions="2">
    <use-data name="Displacement" />
  </mesh>

  <mesh name="Solid-Mesh" dimensions="2">
    <use-data name="Displacement" />
    <use-data name="Stress" />
  </mesh>

  <participant name="Fluid">
    <provide-mesh name="Fluid-Mesh-Nodes" />
    <provide-mesh name="Fluid-Mesh-Centers" />
    <receive-mesh name="Solid-Mesh" from="Solid" />
    <read-data name="Displacement" mesh="Fluid-Mesh-Nodes" />
    <write-data name="Stress" mesh="Fluid-Mesh-Centers" />
    <mapping:rbf direction="read" from="Solid-Mesh" to="Fluid-Mesh-Nodes" constraint="consistent">
      <basis-function:compact-polynomial-c6 support-radius="0.35" />
    </mapping:rbf>
  </participant>

  <participant name="Solid">
    <provide-mesh name="Solid-Mesh" />
    <receive-mesh name="Fluid-Mesh-Centers" from="Fluid" />
    <read-data name="Stress" mesh="Solid-Mesh" />
    <write-data name="Displacement" mesh="Solid-Mesh" />
    <watch-point mesh="Solid-Mesh" name="Flap-Tip" coordinate="0.6;0.2" />
    <mapping:rbf direction="read" from="Fluid-Mesh-Centers" to="Solid-Mesh" constraint="consistent">
      <basis-function:compact-polynomial-c6 support-radius="0.35" />
    </mapping:rbf>
  </participant>

  <m2n:sockets acceptor="Fluid" connector="Solid" exchange-directory=".." />

  <coupling-scheme:parallel-implicit>
    <time-window-size value="1e-3" />
    <max-time value="15" />
    <participants first="Fluid" second="Solid" />
    <exchange data="Stress" mesh="Fluid-Mesh-Centers" from="Fluid" to="Solid" />
    <exchange data="Displacement" mesh="Solid-Mesh" from="Solid" to="Fluid" />
    <max-iterations value="100" />
    <relative-convergence-measure limit="1e-4" data="Stress" mesh="Fluid-Mesh-Centers" />
    <relative-convergence-measure limit="1e-4" data="Displacement" mesh="Solid-Mesh" />
    <acceleration:IQN-ILS>
      <data name="Displacement" mesh="Solid-Mesh" />
      <data name="Stress" mesh="Fluid-Mesh-Centers" />
      <preconditioner type="residual-sum" />
      <filter type="QR2" limit="1.2e-3" />
      <initial-relaxation value="0.1" />
      <max-used-iterations value="60" />
      <time-windows-reused value="15" />
    </acceleration:IQN-ILS>
  </coupling-scheme:parallel-implicit>
</precice-configuration>
"""

EXPECTATION = PreciceConfigExpectation(
    participants=("Fluid", "Solid"),
    coupling_scheme="parallel-implicit",
    m2n_kind="sockets",
    time_window_size=1e-3,
    max_iterations=100,
    convergence_limits={"Stress": 1e-4, "Displacement": 1e-4},
    watch_points={"Solid/Flap-Tip": (0.6, 0.2)},
    acceleration_kind="IQN-ILS",
)


def _parse(text: str = FSI3_CONFIG):  # type: ignore[no-untyped-def]
    return parse_precice_config(text, source=Path("precice-config.xml"), sha256=_SHA)


def test_parses_undeclared_prefixes() -> None:
    """ElementTree/minidom reject these tags outright; the expat reader must not."""
    config = _parse()
    assert {d.name: d.kind for d in config.data} == {"Stress": "vector", "Displacement": "vector"}
    assert config.coupling_scheme.kind == "parallel-implicit"
    assert config.m2n[0].kind == "sockets"
    assert config.coupling_scheme.acceleration is not None
    assert config.coupling_scheme.acceleration.kind == "IQN-ILS"


def test_reads_the_full_coupling_scheme() -> None:
    scheme = _parse().coupling_scheme
    assert scheme.time_window_size == 1e-3
    assert scheme.max_time == 15.0
    assert scheme.max_iterations == 100
    assert (scheme.first, scheme.second) == ("Fluid", "Solid")
    assert {m.data: m.limit for m in scheme.convergence_measures} == {
        "Stress": 1e-4,
        "Displacement": 1e-4,
    }
    acceleration = scheme.acceleration
    assert acceleration is not None
    assert acceleration.filter_type == "QR2"
    assert acceleration.filter_limit == 1.2e-3
    assert acceleration.initial_relaxation == 0.1
    assert acceleration.max_used_iterations == 60
    assert acceleration.time_windows_reused == 15


def test_watchpoint_columns_follow_use_data_order() -> None:
    """The predicted header is what the watch-point parser is checked against.

    Solid-Mesh declares Displacement before Stress, and preCICE writes a 2-D vector as
    `<name>0  <name>1`, so this exact tuple is the file's header. Upstream's own
    plot-displacement.sh plots column 5, i.e. Displacement1 — the transverse deflection.
    """
    config = _parse()
    assert config.watchpoint_columns("Solid", "Flap-Tip") == (
        "Time",
        "Coordinate0",
        "Coordinate1",
        "Displacement0",
        "Displacement1",
        "Stress0",
        "Stress1",
    )


def test_watchpoint_coordinate_is_point_a() -> None:
    point = _parse().watch_point("Solid", "Flap-Tip")
    assert point.coordinate == (0.6, 0.2)
    assert point.mesh == "Solid-Mesh"


def test_assert_config_accepts_the_pinned_case() -> None:
    assert_config(_parse(), EXPECTATION)


@pytest.mark.parametrize(
    ("substitution", "needle"),
    [
        (('<max-iterations value="100" />', '<max-iterations value="200" />'), "max-iterations"),
        (('limit="1e-4" data="Stress"', 'limit="1e-2" data="Stress"'), "convergence limits"),
        (("coupling-scheme:parallel-implicit", "coupling-scheme:serial-implicit"), "scheme"),
        (('coordinate="0.6;0.2"', 'coordinate="0.5;0.2"'), "watch-point"),
        (('<time-window-size value="1e-3" />', '<time-window-size value="1e-2" />'), "window-size"),
        (("acceleration:IQN-ILS", "acceleration:aitken"), "acceleration"),
    ],
)
def test_assert_config_rejects_drift(substitution: tuple[str, str], needle: str) -> None:
    """Every knob that would make the benchmark easier must fail the expectation."""
    old, new = substitution
    text = FSI3_CONFIG.replace(old, new)
    assert text != FSI3_CONFIG, "the test substitution did not apply"
    with pytest.raises(PreciceConfigError, match=needle):
        assert_config(_parse(text), EXPECTATION)


def test_dangling_data_reference_is_loud() -> None:
    text = FSI3_CONFIG.replace('<use-data name="Stress" />', '<use-data name="Typo" />', 1)
    with pytest.raises(PreciceConfigError, match="no data 'Typo'"):
        _parse(text)


def test_watchpoint_dimension_mismatch_is_loud() -> None:
    text = FSI3_CONFIG.replace('coordinate="0.6;0.2"', 'coordinate="0.6;0.2;0.1"')
    with pytest.raises(PreciceConfigError, match="3 coordinates"):
        _parse(text)


def test_rewrite_max_time_changes_only_max_time(tmp_path: Path) -> None:
    source = tmp_path / "precice-config.xml"
    source.write_text(FSI3_CONFIG, encoding="utf-8")
    dest = tmp_path / "out" / "precice-config.xml"

    produced = rewrite_max_time(source, dest, max_time=8.0)

    assert produced.coupling_scheme.max_time == 8.0
    assert produced.coupling_scheme.max_iterations == 100
    original_lines = FSI3_CONFIG.splitlines()
    new_lines = dest.read_text(encoding="utf-8").splitlines()
    assert len(original_lines) == len(new_lines)
    differing = [
        i for i, (a, b) in enumerate(zip(original_lines, new_lines, strict=True)) if a != b
    ]
    assert len(differing) == 1, "exactly one line may change"
    assert "max-time" in new_lines[differing[0]]


def test_rewrite_max_time_refuses_ambiguous_source(tmp_path: Path) -> None:
    source = tmp_path / "precice-config.xml"
    source.write_text(
        FSI3_CONFIG.replace(
            '<max-time value="15" />', '<max-time value="15" />\n    <max-time value="9" />'
        ),
        encoding="utf-8",
    )
    with pytest.raises(PreciceConfigError, match="max-time"):
        rewrite_max_time(source, tmp_path / "out.xml", max_time=8.0)


def test_rewrite_max_time_structural_check_catches_a_smuggled_change(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The equality check, not the regex, is what makes C2 a guarantee.

    Simulated by making the write step also loosen `max-iterations`: the re-parse must
    notice and abort, even though the max-time substitution itself was correct.
    """
    import aero.adapters.precice.config as config_module

    source = tmp_path / "precice-config.xml"
    source.write_text(FSI3_CONFIG, encoding="utf-8")

    real_write = Path.write_text

    def sneaky(self: Path, data: str, *args: object, **kwargs: object) -> int:
        if self.name == "precice-config.xml" and "max-time" in data:
            data = data.replace('<max-iterations value="100" />', '<max-iterations value="500" />')
        return real_write(self, data, *args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(Path, "write_text", sneaky)
    with pytest.raises(config_module.PreciceConfigError, match="changed something else"):
        rewrite_max_time(source, tmp_path / "out" / "precice-config.xml", max_time=8.0)


def test_read_precice_config_records_the_digest(tmp_path: Path) -> None:
    import hashlib

    path = tmp_path / "precice-config.xml"
    path.write_text(FSI3_CONFIG, encoding="utf-8")
    config = read_precice_config(path)
    assert config.source_sha256 == hashlib.sha256(FSI3_CONFIG.encode()).hexdigest()
