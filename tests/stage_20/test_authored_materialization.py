"""The authored case materializes, and the ways it could quietly not be itself.

Stage 19's integrity contract was "these bytes ARE the pinned bytes". An authored case has
no pin, so the contract inverts to "these bytes are exactly what this spec renders, and
re-reading them reproduces the spec" (ADR-037). Two consequences drive this file:

* the physical spec rides ON ``AuthoredSource``, so ``config_hash`` covers it. Without that,
  the flexible and rigid arms -- which differ ONLY in the plate's thickness -- would hash
  identically, and the gated increment's two halves would be indistinguishable in the
  provenance record;
* nothing else in the repo compares the solid's geometry against the fluid's.
  ``assert_calculix_deck`` compares a deck against the spec it was written from, which is
  self-consistent by construction, and a spec pair carrying the flexible plate on the fluid
  and the rigid plate on the solid would validate, write, mesh, couple, converge, and report
  a thrust coefficient somewhere between the two arms. Every disagreement below is therefore
  driven with a wrong value rather than asserted in prose.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any

import numpy as np
import pytest
from aero.adapters._base import CaseDir
from aero.adapters.openfoam.geometry import hg2007_coordinates, hg2007_half_thickness
from aero.adapters.precice.calculix import (
    INTERFACE_NSET,
    NOSE_NSET,
    read_adapter_config,
    read_calculix_deck,
    watch_points,
)
from aero.adapters.precice.case import (
    CASE_ROOT_DIRNAME,
    AuthoredSource,
    CoupledCaseError,
    CoupledCaseSpec,
    spec_config_digest,
)
from aero.adapters.precice.config import read_precice_config
from aero.adapters.precice.manifest import AUTHORED_MANIFEST_SCHEMA
from aero.adapters.precice.solver import PreciceCoupledSolver
from aero.adapters.precice.template import HG2007_TEMPLATE, RENDERER_VERSION, template_sha256
from aero.provenance.four_fold import config_hash
from pydantic import ValidationError

from tests.stage_20._hg2007 import (
    BC_RIGID,
    CHORD,
    DT,
    MAX_TIME,
    N_SURFACE,
    authored_source,
    fluid,
    participants,
    section,
    solid,
    surface_x,
)
from tests.stage_20._hg2007 import authored_spec as _spec

pytestmark = pytest.mark.stage_20


def _source(**overrides: Any) -> AuthoredSource:
    return authored_source(**overrides)


def _rebuild(**solid_overrides: Any) -> AuthoredSource:
    """An authored source whose SOLID disagrees with the fluid in one field."""
    sec = section()
    return authored_source(fluid=fluid(sec), solid=solid(sec, **solid_overrides))


@pytest.fixture
def materialized(tmp_path: Path) -> tuple[Path, CoupledCaseSpec]:
    spec = _spec()
    PreciceCoupledSolver()._write_case(spec, tmp_path)
    return tmp_path / CASE_ROOT_DIRNAME, spec


# --------------------------------------------------------------------------------------
# The case materializes, and re-reading it reproduces the spec
# --------------------------------------------------------------------------------------


def test_every_participant_gets_its_bytes(materialized: tuple[Path, CoupledCaseSpec]) -> None:
    root, spec = materialized
    case = root / spec.case_subdir
    for relative in (
        "precice-config.xml",
        "fluid-openfoam/system/blockMeshDict",
        "fluid-openfoam/system/controlDict",
        "fluid-openfoam/system/preciceDict",
        "fluid-openfoam/constant/dynamicMeshDict",
        "fluid-openfoam/0/pointDisplacement",
        "solid-calculix/hg2007-solid.inp",
        "solid-calculix/all.msh",
        "solid-calculix/interface.nam",
        "solid-calculix/nose.nam",
        "solid-calculix/plunge.amp",
        "solid-calculix/config.yml",
    ):
        assert (case / relative).is_file(), f"the authored case is missing {relative}"


def test_config_for_resolves_the_rendered_configuration(tmp_path: Path) -> None:
    """``config_for`` hard-codes ``<case root>/<case_subdir>/precice-config.xml``.

    A literal, so it goes stale silently if the authored layout ever gains a level -- and
    the symptom would be a FileNotFoundError several minutes into a run rather than here.
    """
    spec = _spec()
    solver = PreciceCoupledSolver()
    solver._write_case(spec, tmp_path)
    case_dir = CaseDir(
        run_id="authored-test", host_path=tmp_path, remote_path=Path("/remote"), spec=spec
    )
    config = solver.config_for(case_dir)
    assert config.coupling_scheme.time_window_size == DT
    assert config.coupling_scheme.max_time == MAX_TIME


def test_the_three_relative_config_paths_name_one_file(
    materialized: tuple[Path, CoupledCaseSpec],
) -> None:
    """Fluid, solid and the exchange directory must all resolve to the same place.

    A mismatch does not fail: preCICE writes ``precice-run/`` somewhere the supervisor's
    pre-run cleanup does not look, a stale socket from an earlier run hangs both
    participants, and the run ends ``stopped_by="ceiling"`` with everyone still alive --
    which gate K2 accepts as a budget outcome. One wave's ceiling to notice.
    """
    root, spec = materialized
    case = root / spec.case_subdir
    rendered = case / "precice-config.xml"

    fluid_dir = case / spec.source.fluid_participant_dir
    precice_dict = (fluid_dir / "system" / "preciceDict").read_text(encoding="utf-8")
    assert 'preciceConfig "../precice-config.xml"' in precice_dict
    assert (fluid_dir / "../precice-config.xml").resolve() == rendered.resolve()

    solid_dir = case / spec.source.solid_participant_dir
    adapter = read_adapter_config(solid_dir / "config.yml")
    assert (solid_dir / adapter.precice_config_file).resolve() == rendered.resolve()

    values = spec.source.coupling_values()
    assert (fluid_dir / values.exchange_directory).resolve() == case.resolve()
    assert (solid_dir / values.exchange_directory).resolve() == case.resolve()


def test_the_deck_reads_back_as_the_spec_wrote_it(
    materialized: tuple[Path, CoupledCaseSpec],
) -> None:
    root, spec = materialized
    solid = spec.source.solid
    deck = read_calculix_deck(root / spec.case_subdir / "solid-calculix" / "hg2007-solid.inp")
    assert deck.element_type == "C3D8I"
    assert deck.nlgeom is True
    assert deck.dt == solid.time_window_size
    assert deck.total_time == solid.max_time
    assert deck.span == solid.span == spec.source.fluid.span
    assert deck.max_increments >= 10 * solid.n_windows
    assert INTERFACE_NSET in deck.nsets and NOSE_NSET in deck.nsets
    # The adapter OVERWRITES this block; missing, the solid runs silently force-free.
    assert {dof for _, dof, _ in deck.cload} == {1, 2, 3}
    assert all(magnitude == 0.0 for _, _, magnitude in deck.cload)


def test_the_solids_wetted_curve_is_the_fluids(
    materialized: tuple[Path, CoupledCaseSpec],
) -> None:
    """Not "close to": the same stations, evaluated by the same half-thickness function."""
    root, spec = materialized
    section = spec.source.fluid.section
    deck = read_calculix_deck(root / spec.case_subdir / "solid-calculix" / "hg2007-solid.inp")
    expected = hg2007_coordinates(
        2 * spec.source.fluid.n_surface + 1,
        chord=CHORD,
        nose_length=section.nose_length,
        max_half_thickness=section.max_half_thickness,
        join_x=section.join_x,
        plate_half_thickness=section.plate_half_thickness,
    )[1:]
    got = np.asarray(deck.wetted_upper, dtype=np.float64)
    assert got.shape == expected.shape
    assert np.max(np.abs(got - expected)) < 1e-12


# --------------------------------------------------------------------------------------
# The manifest
# --------------------------------------------------------------------------------------


def _manifest(root: Path) -> dict[str, Any]:
    return json.loads((root / "aero-manifest.json").read_text(encoding="utf-8"))


def test_the_manifest_is_schema_v2_and_does_not_describe_itself(
    materialized: tuple[Path, CoupledCaseSpec],
) -> None:
    root, spec = materialized
    manifest = _manifest(root)
    assert manifest["schema"] == AUTHORED_MANIFEST_SCHEMA
    assert manifest["case_dir"] == spec.case_subdir
    assert "pin" not in manifest, "an authored case must never emit a tutorial pin block"

    paths = [entry["path"] for entry in manifest["files"]]
    assert "aero-manifest.json" not in paths
    assert paths == sorted(paths), "the files array's order is part of the manifest bytes"
    on_disk = {
        str(p.relative_to(root))
        for p in root.rglob("*")
        if p.is_file() and p.name != "aero-manifest.json"
    }
    assert set(paths) == on_disk


def test_the_manifests_spec_digest_is_the_one_config_hash_will_compute(
    materialized: tuple[Path, CoupledCaseSpec],
) -> None:
    """The manifest claims to describe the spec the MLflow ``config_hash`` tag names.

    ``sha256(spec.model_dump_json())`` is the obvious way to compute this and is a DIFFERENT
    number -- ``config_hash`` sorts keys and drops whitespace -- so the claim would be false
    while looking right.
    """
    root, spec = materialized
    assert _manifest(root)["authored"]["spec_sha256"] == spec_config_digest(spec)
    assert spec_config_digest(spec) == config_hash(json.loads(spec.model_dump_json()))


def test_the_two_model_dump_spellings_agree(materialized: tuple[Path, CoupledCaseSpec]) -> None:
    """``cli.py`` serializes with ``model_dump(mode="json")``; the drivers use
    ``json.loads(model_dump_json())``. They must be the same dict for the same spec, or a
    run's manifest and its MLflow tag describe the spec differently."""
    _, spec = materialized
    assert spec.model_dump(mode="json") == json.loads(spec.model_dump_json())
    assert config_hash(spec.model_dump(mode="json")) == spec_config_digest(spec)


def test_an_authored_spec_carries_no_filesystem_path(
    materialized: tuple[Path, CoupledCaseSpec],
) -> None:
    """``config_hash`` covers every serialized field, so a path in one makes the digest a
    property of the checkout rather than of the case. The tutorial source has this problem
    (its archive and manifest paths are absolute); the authored source must not inherit it.
    """
    _, spec = materialized
    serialized = spec.source.model_dump_json()
    assert "/" not in serialized.replace("\\/", "").replace("../precice-config.xml", ""), (
        f"the authored source serializes a path-like value: {serialized}"
    )


def test_the_declared_mutations_are_read_back_not_asserted(
    materialized: tuple[Path, CoupledCaseSpec],
) -> None:
    root, spec = materialized
    mutations = _manifest(root)["declared_mutations"]
    assert [m["kind"] for m in mutations] == ["authored"] * 3
    assert all(m["before_sha256"] is None for m in mutations), (
        "authored bytes replaced nothing; a placeholder digest reads as a real prior version"
    )
    by_path = {m["path"]: m for m in mutations}
    deck_path = f"{spec.case_subdir}/solid-calculix/hg2007-solid.inp"
    assert "C3D8I" in by_path[deck_path]["detail"]
    assert f"INC={spec.source.solid.max_increments}" in by_path[deck_path]["detail"]
    # Every mutation's digest must be the file's ACTUAL digest.
    import hashlib

    for mutation in mutations:
        raw = (root / mutation["path"]).read_bytes()
        assert mutation["after_sha256"] == hashlib.sha256(raw).hexdigest()


# --------------------------------------------------------------------------------------
# The ways the fluid and the solid can describe two different problems
# --------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("field", "wrong", "needle"),
    [
        # The one that matters most: the arms differ ONLY in this number.
        ("plate_half_thickness", BC_RIGID * CHORD / 2.0, "plate_half_thickness"),
        ("span", 1.0, "span"),
        ("chord", 0.100, "chord"),
        ("nose_length", 0.0090, "nose_length"),
        ("max_half_thickness", 0.0050, "max_half_thickness"),
        ("join_x", 0.031, "join_x"),
        ("max_time", 0.2, "max_time"),
        ("time_window_size", 2.0e-3, "time_window_size"),
    ],
)
def test_a_solid_that_disagrees_with_the_fluid_is_refused(
    field: str, wrong: float, needle: str
) -> None:
    with pytest.raises((ValidationError, CoupledCaseError)) as excinfo:
        _rebuild(**{field: wrong})
    assert needle in str(excinfo.value)


def test_a_hand_built_station_list_is_refused() -> None:
    """``surface_x`` must BE the fluid's stations, not merely resemble them.

    A linear spacing over the same interval passes every other check in the deck writer and
    produces a solid surface the RBF quietly interpolates across.
    """
    linear = tuple(np.linspace(CHORD / (2 * N_SURFACE), CHORD, 2 * N_SURFACE).tolist())
    with pytest.raises((ValidationError, CoupledCaseError)) as excinfo:
        _rebuild(surface_x=linear)
    assert "surface_x is not the fluid's station list" in str(excinfo.value)


def test_a_station_list_of_the_wrong_length_is_refused() -> None:
    sec = section()
    with pytest.raises((ValidationError, CoupledCaseError)) as excinfo:
        _rebuild(surface_x=surface_x(sec, n_surface=N_SURFACE + 1))
    assert "stations" in str(excinfo.value)


def test_an_end_time_that_is_not_a_whole_number_of_windows_is_refused() -> None:
    """The fluid rounds and the solid takes a ceiling; they agree only on a whole multiple.

    When they disagree the ``.dat`` is checked against the wrong window count -- loud, but
    only at readout, after the run has been paid for.
    """
    sec = section()
    with pytest.raises((ValidationError, CoupledCaseError)) as excinfo:
        AuthoredSource(
            case_dir_name="hg2007-flexible-foil",
            template=HG2007_TEMPLATE,
            template_sha256=template_sha256(),
            renderer_version=RENDERER_VERSION,
            fluid=fluid(sec, max_time=0.10050),
            solid=solid(sec, max_time=0.10050),
        )
    assert "exact multiple" in str(excinfo.value)


def test_every_disagreement_is_reported_at_once() -> None:
    """Six wrong fields must not take six runs to find."""
    with pytest.raises((ValidationError, CoupledCaseError)) as excinfo:
        _rebuild(span=1.0, max_time=0.2, time_window_size=2.0e-3)
    message = str(excinfo.value)
    assert all(needle in message for needle in ("span", "max_time", "time_window_size"))
    assert "3 disagreement(s)" in message


def test_the_materializer_re_checks_consistency_because_model_copy_bypasses_validators(
    tmp_path: Path,
) -> None:
    """``model_copy(update=...)`` skips ``mode="after"`` validators -- this module's own
    ``select_fluid_mesh`` and ``record_max_time_mutation`` use exactly that idiom -- so the
    after-validator is a convention and the materializer is the mechanism."""
    spec = _spec()
    forged_solid = spec.source.solid.model_copy(
        update={"plate_half_thickness": BC_RIGID * CHORD / 2.0}
    )
    forged = spec.model_copy(
        update={"source": spec.source.model_copy(update={"solid": forged_solid})}
    )
    # The forgery really did bypass the validator...
    assert (
        forged.source.solid.plate_half_thickness != forged.source.fluid.section.plate_half_thickness
    )
    # ...and the materializer refuses it anyway, before writing a byte.
    with pytest.raises(CoupledCaseError, match="plate_half_thickness"):
        PreciceCoupledSolver()._write_case(forged, tmp_path)
    assert not (tmp_path / CASE_ROOT_DIRNAME / spec.case_subdir).exists() or not list(
        (tmp_path / CASE_ROOT_DIRNAME / spec.case_subdir).rglob("*.inp")
    )


# --------------------------------------------------------------------------------------
# The watch-points, and why an odd through-thickness count is refused
# --------------------------------------------------------------------------------------


def test_an_odd_through_thickness_count_is_refused() -> None:
    """preCICE SNAPS a watch-point to the nearest vertex with no diagnostic.

    ``_grid`` lays nodes at ``eta = linspace(-1, 1, n+1)``, which contains 0.0 only for even
    ``n``. At an odd count there is no mid-surface node, both watch-points land on a face,
    and D0 becomes the angle of a surface fibre -- offset by the plate half-thickness times
    the local rotation, and entirely plausible.
    """
    sec = section()
    with pytest.raises(ValidationError, match=r"multiple_of|even"):
        solid(sec, n_through_thickness=3)


def test_the_watch_points_are_mid_surface_interface_vertices() -> None:
    the_solid = solid(section())
    nose, trailing_edge = watch_points(the_solid)
    assert nose == (the_solid.surface_x[0], 0.0)
    assert trailing_edge == (the_solid.surface_x[-1], 0.0)
    assert trailing_edge[0] == pytest.approx(the_solid.chord, abs=1e-12)
    # Mid-surface: the section's half-thickness is non-zero at both stations, so y = 0 is
    # genuinely the mid-surface rather than a degenerate point.
    half = hg2007_half_thickness(
        np.asarray([nose[0], trailing_edge[0]]),
        chord=the_solid.chord,
        nose_length=the_solid.nose_length,
        max_half_thickness=the_solid.max_half_thickness,
        join_x=the_solid.join_x,
        plate_half_thickness=the_solid.plate_half_thickness,
    )
    assert np.all(half > 0.0)


def test_the_rendered_configuration_watches_where_the_solid_says(
    materialized: tuple[Path, CoupledCaseSpec],
) -> None:
    root, spec = materialized
    config = read_precice_config(root / spec.case_subdir / "precice-config.xml")
    nose, trailing_edge = watch_points(spec.source.solid)
    assert config.watch_point("Solid", "Nose").coordinate == nose
    assert config.watch_point("Solid", "Trailing-Edge").coordinate == trailing_edge


# --------------------------------------------------------------------------------------
# The spec binds the source to the participants that will actually be launched
# --------------------------------------------------------------------------------------


def test_a_workdir_that_is_not_the_sources_participant_directory_is_refused() -> None:
    with pytest.raises(ValidationError, match="workdirs"):
        _spec(participants=participants(workdir="solid-nutils"))


def test_a_solid_command_that_does_not_name_the_deck_is_refused() -> None:
    with pytest.raises(ValidationError, match="does not name the deck"):
        _spec(participants=participants(command="ccx_preCICE -i flap -precice-participant Solid"))


def test_a_spec_max_time_that_disagrees_with_the_fluids_is_refused() -> None:
    with pytest.raises(ValidationError, match="max_time"):
        _spec(max_time=0.2)


def test_mixed_participant_uids_are_refused() -> None:
    """The quiet one: a root participant creates ``precice-run/`` its unprivileged peer
    cannot write into, both block, and the ceiling stop that follows is an ending gate K2
    ADMITS as a budget outcome. One full wave to notice."""
    with pytest.raises(ValidationError, match="uids"):
        _spec(participants=participants(run_as_uid=1001))


def test_the_adapter_config_is_checked_against_the_rendered_mesh_name(tmp_path: Path) -> None:
    """Fed the spec's own ``mesh_name`` the check compares a value with itself.

    Driven by rendering a configuration whose Solid provides a differently-named mesh: the
    adapter config still says ``Solid-Mesh``, and the materializer must refuse.
    """
    spec = _spec(source=_source(solid=solid(section(), mesh_name="Not-The-Rendered-Mesh")))
    with pytest.raises(Exception) as excinfo:
        PreciceCoupledSolver()._write_case(spec, tmp_path)
    assert "nodes-mesh" in str(excinfo.value) or "mesh_name" in str(excinfo.value)


# --------------------------------------------------------------------------------------
# The import graph
# --------------------------------------------------------------------------------------


def test_importing_case_directly_does_not_deadlock_the_package() -> None:
    """``case.py`` now imports two sibling writer modules at module level.

    ``import aero.adapters.precice.case`` runs ``precice/__init__`` FIRST, which imports
    ``case`` -- so if either writer ever did a package-level
    ``from aero.adapters.precice import X`` this would raise ImportError against a
    half-initialised package. A fresh interpreter is the only way to test it: within this
    session everything is already in ``sys.modules``.
    """
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "import aero.adapters.precice.case as c; "
            "assert c.AuthoredSource is not None; print('ok')",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert "ok" in result.stdout
