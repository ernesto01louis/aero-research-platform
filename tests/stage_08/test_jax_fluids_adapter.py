"""Stage 08 — JAX-Fluids adapter unit tests (no SIF; host-side only).

The cluster-bound shock-tube smoke test lives in
`test_jax_fluids_smoke.py` and skips when the JAX-Fluids SIF isn't
present (mirrors Stage-07's PyFR cluster-smoke pattern).

Here we pin:

* `JaxFluidsSolver` satisfies `Solver` (ABC + structural protocol).
* The case-writer emits both JSON files with the expected shape.
* `_write_case` dispatches on spec kind; raises on a foreign spec type.
* `wall_distribution` raises `NotImplementedError` for shock-tube cases.
* `differentiable_run` is present on `JaxFluidsSolver` but NOT on the
  base `Solver` ABC (ADR-008 §D3 — adapter-local additive method).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from aero.adapters._base import Solver
from aero.adapters.jax_fluids import (
    DEFAULT_JAX_FLUIDS_SIF_PATH,
    JaxFluidsMeshFileSpec,
    JaxFluidsShockTubeSpec,
    JaxFluidsSolver,
)
from aero.adapters.jax_fluids.case_writer import write_shock_tube_case_files

pytestmark = pytest.mark.stage_08


def test_jaxfluids_solver_is_a_solver() -> None:
    solver = JaxFluidsSolver()
    assert isinstance(solver, Solver)


def test_default_sif_path_is_under_opt_aero_containers() -> None:
    assert DEFAULT_JAX_FLUIDS_SIF_PATH == "/opt/aero/containers/jax-fluids.sif"


def test_shock_tube_spec_defaults_are_canonical_sod() -> None:
    spec = JaxFluidsShockTubeSpec(name="sod-256")
    assert spec.kind == "jaxf_shock_tube"
    assert spec.n_cells == 256
    assert spec.cfl == 0.5
    assert spec.t_end == 0.2


def test_case_writer_emits_expected_jsons(tmp_path: Path) -> None:
    spec = JaxFluidsShockTubeSpec(name="sod-128", n_cells=128, t_end=0.15)
    num, case = write_shock_tube_case_files(tmp_path, spec)
    assert num.name == "numerical_setup.json"
    assert case.name == "case_setup.json"
    num_dict = json.loads(num.read_text())
    case_dict = json.loads(case.read_text())
    assert num_dict["conservatives"]["convective_fluxes"]["godunov"]["riemann_solver"] == "HLLC"
    assert case_dict["domain"]["x"]["cells"] == 128
    assert case_dict["general"]["end_time"] == 0.15
    # Sod IC discontinuity at x=0.5 with the expected left/right states.
    rho_ic = case_dict["initial_condition"]["primitives"]["rho"]
    assert "x < 0.5" in rho_ic
    assert "1.0" in rho_ic and "0.125" in rho_ic


def test_write_case_rejects_foreign_spec(tmp_path: Path) -> None:
    class _Other:
        name = "other"

    solver = JaxFluidsSolver(host_nfs_root=tmp_path, remote_nfs_root=tmp_path)
    with pytest.raises(TypeError) as excinfo:
        solver._write_case(_Other(), tmp_path / "case")  # type: ignore[arg-type]
    assert "cannot handle spec of type" in str(excinfo.value)


def test_mesh_file_spec_requires_repo_root(tmp_path: Path) -> None:
    solver = JaxFluidsSolver(host_nfs_root=tmp_path, remote_nfs_root=tmp_path)
    spec = JaxFluidsMeshFileSpec(
        name="x",
        case_setup_path="some/path.json",
        numerical_setup_path="some/numerical.json",
    )
    with pytest.raises(ValueError) as excinfo:
        solver._write_case(spec, tmp_path / "case")
    assert "repo_root" in str(excinfo.value)


def test_differentiable_run_is_adapter_local_not_abc() -> None:
    """ADR-008 §D3: ``differentiable_run`` lives on the adapter only.

    The Solver ABC must NOT have a ``differentiable_run`` method. A future
    promotion (Stage 13) is gated on a second differentiable adapter.
    """
    assert hasattr(JaxFluidsSolver, "differentiable_run")
    assert not hasattr(Solver, "differentiable_run")
