"""Geometry ingestion: load -> quality -> (declared repair) -> gate (Stage 18, ADR-033).

``ingest()`` is the one entry point every external surface passes through before it may
reach a mesher: it loads STL/3MF (core) or STEP (behind ``aero[cad]``), computes the
:class:`~aero.geometry.quality.QualityReport`, optionally runs the bounded declared
repair pipeline (opt-in — repair is never implicit), re-computes quality on the
repaired surface, and evaluates the pre-registered Q-gates. A failing gate raises
:class:`~aero.geometry._base.GeometryError` naming every failed check and every repair
already applied — never a silent repair-and-proceed.

The returned :class:`IngestedGeometry` carries ``surface_sha256`` (SHA-256 of the
source file bytes). Downstream case specs embed that digest so the four-fold
provenance ``config_hash`` covers the geometry identity; the file itself is
DVC-tracked so ``dvc_input_hash`` covers the bytes.
"""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from aero.geometry._base import STRICT, GeometryError, TriSurface
from aero.geometry.quality import QualityReport, compute_quality
from aero.geometry.repair import RepairAction, RepairConfig, repair
from aero.geometry.stl import read_stl
from aero.geometry.threemf import read_3mf

__all__ = [
    "IngestConfig",
    "IngestedGeometry",
    "QualityGateConfig",
    "evaluate_gate",
    "ingest",
]

_SHA256_RE = r"^[0-9a-f]{64}$"


class QualityGateConfig(BaseModel):
    """The pre-registered ingestion gate (Q-gates, ADR-034). Defaults ARE the gate —
    loosening any field for a specific geometry is a declared, visible act."""

    model_config = STRICT

    require_watertight: bool = Field(default=True, description="Q1: zero boundary edges.")
    require_manifold: bool = Field(default=True, description="Q2a: no edge on more than two faces.")
    require_orientation_consistent: bool = Field(
        default=True, description="Q2b: consistent winding."
    )
    forbid_duplicate_faces: bool = Field(
        default=True, description="Q2c: no repeated vertex triple."
    )
    forbid_self_intersections: bool = Field(
        default=True, description="Q3: zero intersecting non-adjacent pairs (check must have run)."
    )
    forbid_degenerate_faces: bool = Field(
        default=True, description="Q4: zero degenerate triangles."
    )
    min_feature_size: float | None = Field(
        default=None,
        gt=0.0,
        description=(
            "Q5: min(min_edge_length, min_altitude) floor, absolute units — set per case "
            "from the target near-wall cell size; None skips the gate (report-only)."
        ),
    )


class IngestConfig(BaseModel):
    """Ingestion behaviour: the gate, the (opt-in) repair bounds, and check toggles."""

    model_config = STRICT

    gate: QualityGateConfig = Field(default_factory=QualityGateConfig)
    repair: RepairConfig | None = Field(
        default=None, description="Bounded repair config; None (default) = no repair pass."
    )
    check_self_intersections: bool = Field(
        default=True, description="Run the pairwise intersection check (the only super-linear one)."
    )


class IngestedGeometry(BaseModel):
    """The typed record of a successfully ingested external geometry.

    ``surface`` is the in-memory mesh (excluded from serialization — bundles carry the
    metadata + quality report + repair ledger; the mesh travels as the DVC-tracked
    source file identified by ``surface_sha256``).
    """

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        str_strip_whitespace=True,
        validate_assignment=True,
        validate_default=True,
        arbitrary_types_allowed=True,
    )

    source: str = Field(..., min_length=1, description="Path the geometry was read from.")
    fmt: Literal["stl", "3mf", "step"]
    surface_sha256: str = Field(..., pattern=_SHA256_RE)
    n_vertices: int = Field(..., ge=3)
    n_faces: int = Field(..., ge=1)
    quality: QualityReport
    repairs: tuple[RepairAction, ...] = Field(
        ..., description="Every repair applied, in order — empty when none were needed."
    )
    surface: TriSurface = Field(..., exclude=True, repr=False)


def evaluate_gate(report: QualityReport, gate: QualityGateConfig) -> tuple[str, ...]:
    """Evaluate the Q-gates against a quality report; returns failure descriptions."""
    failures: list[str] = []
    if gate.require_watertight and not report.watertight:
        failures.append(f"Q1 not watertight: {report.n_boundary_edges} boundary edges")
    if gate.require_manifold and not report.manifold:
        failures.append(f"Q2a non-manifold: {report.n_non_manifold_edges} edges on >2 faces")
    if gate.require_orientation_consistent and not report.orientation_consistent:
        failures.append("Q2b inconsistent winding: a directed edge appears more than once")
    if gate.forbid_duplicate_faces and report.n_duplicate_faces > 0:
        failures.append(f"Q2c duplicate faces: {report.n_duplicate_faces}")
    if gate.forbid_self_intersections:
        if not report.self_intersections_checked:
            failures.append("Q3 self-intersection check did not run but the gate requires it")
        elif report.n_intersecting_pairs > 0:
            failures.append(f"Q3 self-intersecting: {report.n_intersecting_pairs} triangle pairs")
    if gate.forbid_degenerate_faces and report.n_degenerate_faces > 0:
        failures.append(f"Q4 degenerate triangles: {report.n_degenerate_faces}")
    if gate.min_feature_size is not None:
        feature = min(report.min_edge_length, report.min_altitude)
        if feature < gate.min_feature_size:
            failures.append(
                f"Q5 feature size {feature:.3e} below the declared floor "
                f"{gate.min_feature_size:.3e}"
            )
    return tuple(failures)


def _load(path: Path) -> tuple[TriSurface, Literal["stl", "3mf", "step"]]:
    suffix = path.suffix.lower()
    if suffix == ".stl":
        return read_stl(path), "stl"
    if suffix == ".3mf":
        return read_3mf(path), "3mf"
    if suffix in (".step", ".stp"):
        # Lazy import — the CAD kernel lives behind aero[cad] (PLATFORM-NOT-HUB).
        from aero.geometry.cad import load_step

        return load_step(path), "step"
    raise GeometryError(
        f"{path}: unsupported geometry format {suffix!r} (supported: .stl, .3mf, .step/.stp)"
    )


def ingest(path: Path, *, config: IngestConfig | None = None) -> IngestedGeometry:
    """Load, quality-check, optionally repair, and gate an external geometry."""
    cfg = config or IngestConfig()
    if not path.is_file():
        raise GeometryError(f"{path}: geometry file does not exist")
    surface_sha256 = hashlib.sha256(path.read_bytes()).hexdigest()
    surface, fmt = _load(path)

    repairs: tuple[RepairAction, ...] = ()
    if cfg.repair is not None:
        surface, repairs = repair(surface, cfg.repair)
    quality = compute_quality(surface, check_self_intersections=cfg.check_self_intersections)

    failures = evaluate_gate(quality, cfg.gate)
    if failures:
        applied = (
            "; repairs already applied: " + ", ".join(f"{a.kind} (x{a.count})" for a in repairs)
            if repairs
            else "; no repairs applied" + (" (repair disabled)" if cfg.repair is None else "")
        )
        raise GeometryError(
            f"{path}: geometry failed the ingestion quality gate — " + "; ".join(failures) + applied
        )
    return IngestedGeometry(
        source=str(path),
        fmt=fmt,
        surface_sha256=surface_sha256,
        n_vertices=surface.n_vertices,
        n_faces=surface.n_faces,
        quality=quality,
        repairs=repairs,
        surface=surface,
    )
