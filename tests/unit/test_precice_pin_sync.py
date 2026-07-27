"""One-source-of-truth checks for the Stage-19 pins and the pre-registered gate bands.

Version drift between the Python bindings and the preCICE library baked into the SIF is
an ABI problem: it does not announce itself, it produces wrong numbers or a segfault
deep inside a multi-hour run. Band drift between the ADR and the code is worse — the
pre-registration stops meaning anything. Both are cheap to assert, so they are asserted.
"""

from __future__ import annotations

import tomllib
from pathlib import Path

import pytest
from aero.adapters.precice import (
    PINNED_OPENFOAM_ADAPTER_COMMIT,
    PINNED_PRECICE_VERSION,
    PINNED_PYPRECICE_VERSION,
)

pytestmark = pytest.mark.stage_19

_REPO_ROOT = Path(__file__).resolve().parents[2]


def _pyproject() -> dict[str, object]:
    return tomllib.loads((_REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8"))


def test_precice_extra_pins_the_recorded_binding_version() -> None:
    extras = _pyproject()["project"]["optional-dependencies"]  # type: ignore[index]
    assert extras["precice"] == [f"pyprecice=={PINNED_PYPRECICE_VERSION}"]  # type: ignore[index]


def test_the_binding_pin_matches_the_precice_library_minor() -> None:
    """pyprecice's first two components track the preCICE release it supports."""
    assert PINNED_PYPRECICE_VERSION.split(".")[:2] == PINNED_PRECICE_VERSION.split(".")[:2]


def test_the_openfoam_adapter_pin_is_a_full_commit_sha() -> None:
    """Taken from upstream's own attested tools/tests/reference_versions.yaml.

    A branch name or short sha would let the build drift between the pre-registration
    and the campaign.
    """
    assert len(PINNED_OPENFOAM_ADAPTER_COMMIT) == 40
    assert set(PINNED_OPENFOAM_ADAPTER_COMMIT) <= set("0123456789abcdef")


def test_container_recipe_installs_the_pinned_versions() -> None:
    recipe = _REPO_ROOT / "containers" / "precice-fsi.Dockerfile"
    if not recipe.is_file():
        pytest.skip("container recipe not present in this checkout")
    text = recipe.read_text(encoding="utf-8")
    assert f"pyprecice=={PINNED_PYPRECICE_VERSION}" in text
    assert PINNED_PRECICE_VERSION in text
    assert PINNED_OPENFOAM_ADAPTER_COMMIT[:7] in text


def test_stage_19_marker_is_registered() -> None:
    """--strict-markers makes an unregistered marker a hard collection error."""
    markers = _pyproject()["tool"]["pytest"]["ini_options"]["markers"]  # type: ignore[index]
    assert any(str(m).startswith("stage_19:") for m in markers)  # type: ignore[union-attr]


# --- the pre-registered bands -------------------------------------------------------


def test_fsi3_tolerances_are_the_pre_registered_bands() -> None:
    """These five numbers are the stage's product. They are pinned here so that changing
    one requires changing a test that says, in its own name, that it must not change."""
    from aero.vv.fsi import TurekHronFSI3

    bands = {m.name: m.tolerance for m in TurekHronFSI3().metrics()}
    assert bands == {
        "tip_uy_amplitude": 0.15,
        "tip_uy_frequency": 0.05,
        "tip_ux_amplitude": 0.25,
        "tip_ux_mean": 0.25,
        "tip_ux_frequency": 0.05,
    }


def test_the_transverse_mean_is_not_gated() -> None:
    """It is ~3 % of its own amplitude and moves ~50 % for a 1.5 % change in period.

    A relative tolerance on it would report the segmentation, not the physics.
    """
    from aero.vv.fsi import TurekHronFSI3

    assert "tip_uy_mean" not in {m.name for m in TurekHronFSI3().metrics()}


def test_the_analysis_rule_is_pre_registered() -> None:
    from aero.vv.fsi.turek_hron_fsi3 import ANALYSIS_DISCARD_S, ANALYSIS_MIN_CYCLES

    assert ANALYSIS_DISCARD_S == 4.0
    assert ANALYSIS_MIN_CYCLES == 4


def test_the_config_expectation_matches_the_pinned_benchmark() -> None:
    from aero.vv.fsi import TUREK_HRON_FSI3_EXPECTATION

    expected = TUREK_HRON_FSI3_EXPECTATION
    assert expected.coupling_scheme == "parallel-implicit"
    assert expected.time_window_size == 1e-3
    assert expected.max_iterations == 100
    assert dict(expected.convergence_limits) == {"Stress": 1e-4, "Displacement": 1e-4}
    assert dict(expected.watch_points) == {"Solid/Flap-Tip": (0.6, 0.2)}
    assert expected.acceleration_kind == "IQN-ILS"


def test_the_gated_case_forbids_a_multi_container_run() -> None:
    """The four-fold tuple carries ONE container digest; a gated coupled run must not
    silently span two images."""
    from aero.adapters.precice import CoupledCaseSpec, ParticipantSpec, TutorialPin

    common = {
        "name": "x",
        "pin": TutorialPin(commit="a" * 40, archive_sha256="b" * 64, manifest_path=Path("m.csv")),
        "archive_path": Path("a.tar.gz"),
        "max_time": 8.0,
        "wall_clock_ceiling_s": 600,
        "analysis_discard_s": 4.0,
    }
    participants = (
        ParticipantSpec(name="Fluid", workdir="f", command="true", sif="precice-fsi.sif"),
        ParticipantSpec(name="Solid", workdir="s", command="true", sif="calculix-precice.sif"),
    )
    with pytest.raises(ValueError, match="single container"):
        CoupledCaseSpec(
            **common,  # type: ignore[arg-type]
            participants=participants,
            container_of_record="precice-fsi.sif",
            gated=True,
        )
    # The same shape is fine for an explicitly non-gated diagnostic.
    spec = CoupledCaseSpec(
        **common,  # type: ignore[arg-type]
        participants=participants,
        container_of_record="precice-fsi.sif",
        gated=False,
    )
    assert spec.multi_container
    assert spec.extra_container_sifs == ("calculix-precice.sif",)
