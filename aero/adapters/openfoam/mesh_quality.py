"""Typed `checkMesh` parsing + the pre-registered mesh-quality gate (Stage 18, ADR-034).

This is the reusable home the Stage-16 campaign scripts never had (their ad-hoc
`run_checkmesh()` closures recorded metrics into untyped dicts and gated nothing —
left untouched as historical records). Here: `parse_checkmesh()` turns checkMesh
stdout into a strict `MeshQualityMetrics`, and `MeshQualityGate.evaluate()` applies
the pre-registered M-gate thresholds, failing LOUD when a metric the gate needs is
missing from the output — an unparseable checkMesh run must never read as a pass.

The gate's defaults ARE the pre-registered M-gates of ADR-034 (calibrated against
ADR-024's escalation floor non-ortho>70 / skew>4 / negative volumes, tightened to 65
because snappy hex-dominant meshes routinely achieve it). The fallback ladder
(:mod:`aero.adapters.openfoam.robust_mesh`) may step down refinement — it may NEVER
construct a looser gate (F4).

No heavy imports — host-testable in the required CI unit job.
"""

from __future__ import annotations

import re

from pydantic import BaseModel, ConfigDict, Field

_STRICT = ConfigDict(
    extra="forbid",
    frozen=True,
    str_strip_whitespace=True,
    validate_assignment=True,
    validate_default=True,
)

__all__ = ["MeshGateResult", "MeshQualityGate", "MeshQualityMetrics", "parse_checkmesh"]

# A proper float pattern — the naive `[0-9.eE+-]+` class swallows the sentence
# period after "Min volume = 1.2e-08." and breaks float().
_FLOAT = r"(-?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?)"
_RE_MESH_OK = re.compile(r"Mesh OK")
_RE_FAILED = re.compile(r"Failed (\d+) mesh checks")
_RE_CELLS = re.compile(r"^\s*cells:\s+(\d+)\s*$", re.MULTILINE)
# v2412 prints each diagnostic in TWO mutually exclusive branches — the pass branch
# ("Max aspect ratio = X OK.") and the fail branch ("***High aspect ratio cells found,
# Max aspect ratio: X, ..."), which uses a colon. Matching only the pass wording would
# drop the D1 diagnostics from the report exactly when the mesh is bad and the operator
# needs them to explain a loud NO-GO. Both spellings are matched.
_RE_ASPECT = re.compile(rf"Max aspect ratio[ =:]+{_FLOAT}")
_RE_NON_ORTHO = re.compile(rf"non-orthogonality Max[ =:]+{_FLOAT}")
_RE_SKEW = re.compile(rf"[Mm]ax skewness[ =:]+{_FLOAT}")
# Fail branch reports the negative extreme instead: "Minimum negative volume: X".
_RE_MIN_VOLUME = re.compile(rf"(?:Min volume|Minimum negative volume)[ =:]+{_FLOAT}")
_RE_NEGATIVE = re.compile(r"[Zz]ero or negative cell volume|negative cell volumes")


class MeshQualityMetrics(BaseModel):
    """What checkMesh reported. ``None`` = the line was absent from the output —
    the gate treats a missing gated metric as a failure, never as a pass."""

    model_config = _STRICT

    mesh_ok: bool = Field(..., description='checkMesh printed "Mesh OK".')
    failed_checks: int = Field(..., ge=0)
    n_cells: int | None = Field(..., ge=0)
    max_aspect_ratio: float | None
    max_non_orthogonality: float | None
    max_skewness: float | None
    min_volume: float | None
    negative_volumes: bool = Field(
        ..., description="checkMesh reported zero/negative cell volumes."
    )


class MeshGateResult(BaseModel):
    """One gate evaluation: the metrics judged and every failed check, by name."""

    model_config = _STRICT

    passed: bool
    failures: tuple[str, ...]
    metrics: MeshQualityMetrics


class MeshQualityGate(BaseModel):
    """The pre-registered M-gates (ADR-034). Defaults ARE the gate; the ladder never
    loosens them (F4) — a per-case override is a declared, visible act."""

    model_config = _STRICT

    require_mesh_ok: bool = Field(default=True, description='M1: checkMesh "Mesh OK".')
    max_non_orthogonality: float = Field(default=65.0, gt=0.0, description="M2 ceiling.")
    max_skewness: float = Field(default=4.0, gt=0.0, description="M3 ceiling.")
    forbid_negative_volumes: bool = Field(default=True, description="M4.")
    min_cells: int = Field(
        default=1000,
        ge=1,
        description="M5 floor — guards a degenerate near-empty mesh reading as a pass.",
    )

    def evaluate(self, metrics: MeshQualityMetrics) -> MeshGateResult:
        failures: list[str] = []
        if self.require_mesh_ok and not metrics.mesh_ok:
            failures.append(
                f'M1 checkMesh did not report "Mesh OK" ({metrics.failed_checks} failed checks)'
            )
        if metrics.max_non_orthogonality is None:
            failures.append("M2 max non-orthogonality missing from checkMesh output")
        elif metrics.max_non_orthogonality > self.max_non_orthogonality:
            failures.append(
                f"M2 max non-orthogonality {metrics.max_non_orthogonality:.2f} "
                f"> {self.max_non_orthogonality:.2f}"
            )
        if metrics.max_skewness is None:
            failures.append("M3 max skewness missing from checkMesh output")
        elif metrics.max_skewness > self.max_skewness:
            failures.append(f"M3 max skewness {metrics.max_skewness:.3f} > {self.max_skewness:.3f}")
        if self.forbid_negative_volumes and metrics.negative_volumes:
            failures.append("M4 zero/negative cell volumes reported")
        if metrics.n_cells is None:
            failures.append("M5 cell count missing from checkMesh output")
        elif metrics.n_cells < self.min_cells:
            failures.append(f"M5 cell count {metrics.n_cells} < floor {self.min_cells}")
        return MeshGateResult(passed=not failures, failures=tuple(failures), metrics=metrics)


def parse_checkmesh(text: str) -> MeshQualityMetrics:
    """Parse checkMesh stdout into typed metrics (missing lines become ``None``)."""

    def _f(pattern: re.Pattern[str]) -> float | None:
        m = pattern.search(text)
        return float(m.group(1)) if m else None

    failed = _RE_FAILED.search(text)
    cells = _RE_CELLS.search(text)
    return MeshQualityMetrics(
        mesh_ok=bool(_RE_MESH_OK.search(text)),
        failed_checks=int(failed.group(1)) if failed else 0,
        n_cells=int(cells.group(1)) if cells else None,
        max_aspect_ratio=_f(_RE_ASPECT),
        max_non_orthogonality=_f(_RE_NON_ORTHO),
        max_skewness=_f(_RE_SKEW),
        min_volume=_f(_RE_MIN_VOLUME),
        negative_volumes=bool(_RE_NEGATIVE.search(text)),
    )
