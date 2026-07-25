"""The declared mesh fallback ladder for external geometry (Stage 18, ADR-034 F-gates).

`mesh_with_ladder()` walks the DECLARED rungs top-down: each rung re-derives the case
spec (coarser background / fewer layers), prepares a fresh case directory, meshes it,
runs `checkMesh`, and evaluates the ONE pre-registered `MeshQualityGate`. The first
rung whose mesh passes wins; every attempt — including the failures — is recorded in
the returned `MeshLadderReport` so a campaign bundle shows the full descent.

F4 is structural here: the gate object is constructed once by the caller and never
rebuilt per rung — the ladder degrades *cost* (resolution, layers), never *quality
thresholds*. An exhausted ladder raises `GeometryError` (the loud NO-GO) with the
report attached as `exc.ladder_report`, so the honest failure is still bundle-able.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from pydantic import BaseModel, ConfigDict, Field

from aero.adapters._base import build_apptainer_exec
from aero.adapters.openfoam.external_geometry import ExternalGeometrySpec
from aero.adapters.openfoam.mesh_quality import (
    MeshGateResult,
    MeshQualityGate,
    parse_checkmesh,
)
from aero.geometry import GeometryError

if TYPE_CHECKING:
    from pathlib import Path

    from aero.adapters._base import CaseDir, MeshHandle, SolverProtocol
    from aero.orchestration._base import Executor

_STRICT = ConfigDict(
    extra="forbid",
    frozen=True,
    str_strip_whitespace=True,
    validate_assignment=True,
    validate_default=True,
)

__all__ = [
    "DEFAULT_LADDER",
    "MeshLadderReport",
    "MeshLadderRung",
    "MeshRungAttempt",
    "mesh_with_ladder",
]


class MeshLadderRung(BaseModel):
    """One declared rung: a cost level, never a quality level."""

    model_config = _STRICT

    name: str = Field(..., min_length=1, description="Rung id (R0, R1, ...).")
    cell_size_factor: float = Field(
        ..., gt=0.0, description="Multiplier on the spec's base_cell_size."
    )
    n_surface_layers: int = Field(..., ge=0, description="Prism layers on the body patch.")


# The pre-registered ladder (ADR-034 F1) — duplicated verbatim in the campaign
# driver's docstring; any drift between the two is a bug.
DEFAULT_LADDER: tuple[MeshLadderRung, ...] = (
    MeshLadderRung(name="R0", cell_size_factor=1.0, n_surface_layers=2),
    MeshLadderRung(name="R1", cell_size_factor=1.0, n_surface_layers=0),
    MeshLadderRung(name="R2", cell_size_factor=1.5, n_surface_layers=0),
)


class MeshRungAttempt(BaseModel):
    """The full record of one rung attempt (kept for passes AND failures)."""

    model_config = _STRICT

    rung: MeshLadderRung
    run_id: str
    base_cell_size: float = Field(..., gt=0.0)
    mesh_completed: bool = Field(
        ..., description="The mesh pipeline wrote a polyMesh (snappy did not die)."
    )
    gate: MeshGateResult | None = Field(
        ..., description="checkMesh gate evaluation; None when the mesh never completed."
    )
    passed: bool


class MeshLadderReport(BaseModel):
    """Every attempt in descent order + which rung (if any) passed."""

    model_config = _STRICT

    attempts: tuple[MeshRungAttempt, ...]
    passed_rung: str | None


def _rung_spec(spec: ExternalGeometrySpec, rung: MeshLadderRung) -> ExternalGeometrySpec:
    return spec.model_copy(
        update={
            "name": f"{spec.name}-{rung.name.lower()}",
            "base_cell_size": spec.base_cell_size * rung.cell_size_factor,
            "n_surface_layers": rung.n_surface_layers,
        }
    )


def mesh_with_ladder(
    *,
    solver: SolverProtocol,
    executor: Executor,
    spec: ExternalGeometrySpec,
    sif_path: Path | str,
    gate: MeshQualityGate | None = None,
    rungs: tuple[MeshLadderRung, ...] = DEFAULT_LADDER,
    checkmesh_timeout_s: int = 900,
) -> tuple[CaseDir, MeshHandle, MeshLadderReport]:
    """Mesh `spec` down the declared ladder; first gate-passing rung wins.

    Returns `(case_dir, mesh_handle, report)` for the winning rung. Raises
    `GeometryError` (with `.ladder_report`) when every rung fails — never ships a
    mesh that did not pass the pre-registered gate.
    """
    the_gate = gate or MeshQualityGate()
    attempts: list[MeshRungAttempt] = []
    for rung in rungs:
        rung_spec = _rung_spec(spec, rung)
        case_dir = solver.prepare(rung_spec)
        handle = solver.mesh(case_dir, executor)
        if not handle.ok:
            attempts.append(
                MeshRungAttempt(
                    rung=rung,
                    run_id=case_dir.run_id,
                    base_cell_size=rung_spec.base_cell_size,
                    mesh_completed=False,
                    gate=None,
                    passed=False,
                )
            )
            continue
        check = executor.run(
            build_apptainer_exec(
                sif_path=str(sif_path),
                case_bind_source=str(case_dir.remote_path),
                command="checkMesh",
            ),
            timeout_s=checkmesh_timeout_s,
        )
        # Parse whatever checkMesh printed even on rc!=0 — the gate fails loud on
        # missing metrics, so a crashed checkMesh can never read as a pass.
        gate_result = the_gate.evaluate(parse_checkmesh(check.stdout))
        attempt = MeshRungAttempt(
            rung=rung,
            run_id=case_dir.run_id,
            base_cell_size=rung_spec.base_cell_size,
            mesh_completed=True,
            gate=gate_result,
            passed=gate_result.passed and check.ok,
        )
        attempts.append(attempt)
        if attempt.passed:
            return (
                case_dir,
                handle,
                MeshLadderReport(attempts=tuple(attempts), passed_rung=rung.name),
            )
    report = MeshLadderReport(attempts=tuple(attempts), passed_rung=None)
    summary = "; ".join(
        f"{a.rung.name}: "
        + ("mesh pipeline failed" if not a.mesh_completed else ", ".join(a.gate.failures))  # type: ignore[union-attr]
        for a in attempts
    )
    exc = GeometryError(
        f"mesh fallback ladder exhausted for {spec.name!r} — no rung passed the "
        f"pre-registered gate (NO-GO, thresholds were never relaxed): {summary}"
    )
    exc.ladder_report = report  # type: ignore[attr-defined]
    raise exc
