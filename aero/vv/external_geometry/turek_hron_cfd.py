"""Turek-Hron CFD tests (rigid flag) on the INGESTED external geometry (Stage 18).

The Turek & Hron (2006) benchmark defines fluid-only tests with the flag held rigid:
CFD2 (U-bar = 1, Re = 100, steady) and CFD3 (U-bar = 2, Re = 200, unsteady periodic
vortex shedding). Both run here on the **externally-acquired** cylinder+flag STL
(`data/references/fsi/turek_hron_fsi3/` — extraction provenance in its reference.md)
through the full Stage-18 path: ingestion gate -> snappyHexMesh ladder -> laminar
solve -> validation against the published values.

Reference values are stored coefficient-normalized (`Cd = F / (0.5 rho U-bar^2 D)`,
D = 0.1 — the conversion from the paper's forces is documented in reference.md);
relative tolerances are normalization-invariant, so this compares exactly the
published quantities. CFD3's small mean lift (|CL| ~ 2.6% of its own oscillation
amplitude) is a diagnostic, NOT gated — a relative tolerance on a near-zero mean
invites dishonest tolerance inflation (the WBD2004 gated-vs-diagnostic pattern).

GCI caveat: `refined()` scales the uniform background cell size, but snapped snappy
grids are NOT geometrically self-similar (no fixed mapping — contrast ADR-028), so a
formal observed-order GCI claim is out of scope for Stage 18 (single evaluation,
`validated` tier target).
"""

from __future__ import annotations

import hashlib
import re
from pathlib import Path
from typing import Any

import numpy as np

from aero.adapters.openfoam.external_geometry import ExternalGeometrySpec
from aero.vv._base import (
    BenchmarkError,
    MetricSpec,
    ReferenceData,
    Series,
    SolverLike,
    load_scalar_csv,
)

__all__ = ["TurekHronCFD2", "TurekHronCFD3"]

# simpleFoam's early-exit banner — the machine-checkable form of ADR-034's V2.
_SIMPLE_CONVERGED_RE = re.compile(r"SIMPLE solution converged in \d+ iterations")

_REFERENCE_DIR = Path("data") / "references" / "fsi" / "turek_hron_fsi3"
_STL_NAME = "cylinder_flag.stl"


def _repo_root() -> Path:
    # aero/vv/external_geometry/turek_hron_cfd.py -> repo root.
    return Path(__file__).resolve().parents[3]


def _gated_stl(repo_root: Path) -> tuple[str, str]:
    """(stl_path, sha256) of the acquired geometry; loud if not yet acquired/pulled.

    The sha256 sidecar is git-tracked next to the DVC-tracked STL; the spec embeds the
    digest (provenance) and `write_external_geometry_case` re-verifies the bytes.
    """
    stl = repo_root / _REFERENCE_DIR / _STL_NAME
    sidecar = stl.with_suffix(stl.suffix + ".sha256")
    if not sidecar.is_file():
        raise BenchmarkError(
            f"{sidecar} not found — the Turek-Hron geometry has not been acquired "
            "(Stage-18 acquisition step) or the repo checkout is incomplete"
        )
    recorded = sidecar.read_text(encoding="utf-8").strip()
    if not stl.is_file():
        raise BenchmarkError(f"{stl} not found — run `dvc pull` to fetch the geometry")
    actual = hashlib.sha256(stl.read_bytes()).hexdigest()
    if actual != recorded:
        raise BenchmarkError(
            f"{stl}: SHA-256 {actual[:12]}... != recorded {recorded[:12]}... — "
            "the pulled geometry does not match the acquisition record"
        )
    return str(stl), recorded


def _benchmark_spec(
    *,
    name: str,
    u_mean: float,
    transient: bool,
    base_cell_size: float,
    end_time: float,
) -> ExternalGeometrySpec:
    stl_path, sha = _gated_stl(_repo_root())
    return ExternalGeometrySpec(
        name=name,
        surface_source=stl_path,
        surface_name="cylinderFlag",
        surface_sha256=sha,
        domain_min=(0.0, 0.0),
        domain_max=(2.5, 0.41),
        base_cell_size=base_cell_size,
        location_in_mesh=(2.2, 0.2),
        u_mean=u_mean,
        nu=1e-3,
        rho=1000.0,
        ref_length=0.1,
        transient=transient,
        end_time=end_time,
    )


def _reference_scalar(repo_root: Path, *, test_id: float, column: str) -> float:
    return load_scalar_csv(
        repo_root / _REFERENCE_DIR / "cfd_reference.csv",
        key_col="test_id",
        key=test_id,
        value_col=column,
    )


class TurekHronCFD2:
    """Turek-Hron CFD2 — steady laminar channel flow (U-bar=1, Re=100), rigid flag."""

    name = "turek_hron_cfd2"
    description = (
        "Turek-Hron CFD2 (rigid flag, Re=100, steady) on the ingested external "
        "cylinder+flag STL — drag/lift vs the published benchmark values."
    )
    sweep_metric = "cd"

    def __init__(self, spec: ExternalGeometrySpec | None = None) -> None:
        self._spec = spec

    def case_spec(self) -> ExternalGeometrySpec:
        if self._spec is None:
            self._spec = _benchmark_spec(
                name=self.name,
                u_mean=1.0,
                transient=False,
                base_cell_size=0.005,
                end_time=15.0,
            )
        return self._spec

    def reference(self, repo_root: Path) -> ReferenceData:
        return ReferenceData(
            case_name=self.name,
            source="Turek & Hron (2006), CFD2 reference values (coefficient-normalized)",
            scalars={
                "cd": _reference_scalar(repo_root, test_id=2.0, column="cd"),
                "cl": _reference_scalar(repo_root, test_id=2.0, column="cl"),
            },
        )

    def metrics(self) -> tuple[MetricSpec, ...]:
        # Pre-registered V3 (ADR-034): drag 5 %, lift 10 % relative.
        return (
            MetricSpec(name="cd", kind="scalar", tolerance=0.05, comparison="relative"),
            MetricSpec(name="cl", kind="scalar", tolerance=0.10, comparison="relative"),
        )

    def evaluate(self, solver: SolverLike, result: Any) -> dict[str, float | Series]:
        solve = solver.load(result)
        if solve.cd is None or solve.cl is None:
            raise BenchmarkError(f"{self.name}: solve reported no cd/cl — no forceCoeffs output?")
        # ADR-034 gate V2 — the steady solve must actually have CONVERGED. simpleFoam
        # exits early on residualControl and logs "SIMPLE solution converged in N
        # iterations"; a run that burns every iteration while the force is still
        # drifting must NOT be reported, however close cd[-1] happens to land (the
        # `_load_moving` fail-loud precedent).
        if not _SIMPLE_CONVERGED_RE.search(getattr(result, "solver_log", "") or ""):
            raise BenchmarkError(
                f"{self.name}: V2 FAILED — simpleFoam never reported convergence "
                f"(final residual {solve.final_residual:.3e} after "
                f"{solve.iterations_to_convergence} iterations). A non-converged solve "
                "is not reportable; investigate, do not relax the gate."
            )
        return {"cd": solve.cd, "cl": solve.cl}

    def refined(self, ratio: float) -> TurekHronCFD2:
        s = self.case_spec()
        return TurekHronCFD2(s.model_copy(update={"base_cell_size": s.base_cell_size * ratio}))


class TurekHronCFD3:
    """Turek-Hron CFD3 — unsteady periodic shedding (U-bar=2, Re=200), rigid flag."""

    name = "turek_hron_cfd3"
    description = (
        "Turek-Hron CFD3 (rigid flag, Re=200, periodic) on the ingested external "
        "cylinder+flag STL — mean drag, lift amplitude + frequency vs published values."
    )
    sweep_metric = "cd"

    def __init__(self, spec: ExternalGeometrySpec | None = None) -> None:
        self._spec = spec

    def case_spec(self) -> ExternalGeometrySpec:
        if self._spec is None:
            self._spec = _benchmark_spec(
                name=self.name,
                u_mean=2.0,
                transient=True,
                base_cell_size=0.005,
                end_time=12.0,
            )
        return self._spec

    def reference(self, repo_root: Path) -> ReferenceData:
        return ReferenceData(
            case_name=self.name,
            source="Turek & Hron (2006), CFD3 reference values (coefficient-normalized)",
            scalars={
                "cd": _reference_scalar(repo_root, test_id=3.0, column="cd"),
                "cl_amplitude": _reference_scalar(repo_root, test_id=3.0, column="cl_amplitude"),
                "frequency": _reference_scalar(repo_root, test_id=3.0, column="frequency"),
            },
        )

    def metrics(self) -> tuple[MetricSpec, ...]:
        # Pre-registered V5 (ADR-034): mean drag 5 %, frequency 5 %, amplitude 15 %.
        # CFD3's near-zero mean lift is a diagnostic, not gated (module docstring).
        return (
            MetricSpec(name="cd", kind="scalar", tolerance=0.05, comparison="relative"),
            MetricSpec(name="frequency", kind="scalar", tolerance=0.05, comparison="relative"),
            MetricSpec(name="cl_amplitude", kind="scalar", tolerance=0.15, comparison="relative"),
        )

    def evaluate(self, solver: SolverLike, result: Any) -> dict[str, float | Series]:
        from aero.adapters._base import TimeHistory
        from aero.postprocess import Signal, dominant_frequency

        solve = solver.load(result)
        if solve.cd is None:
            raise BenchmarkError(f"{self.name}: solve reported no cd — no forceCoeffs output?")
        history = solve.history
        if not isinstance(history, TimeHistory):
            raise BenchmarkError(
                f"{self.name}: transient solve carries no TimeHistory — cannot "
                "measure the shedding frequency/amplitude"
            )
        t = np.asarray(history.t, dtype=np.float64)
        cl = np.asarray(history.monitor, dtype=np.float64)
        estimate = dominant_frequency(Signal.from_arrays(t, cl, name="lift_coefficient"))
        amplitude = 0.5 * float(cl.max() - cl.min())
        return {
            "cd": solve.cd,
            "frequency": estimate.frequency,
            "cl_amplitude": amplitude,
        }

    def refined(self, ratio: float) -> TurekHronCFD3:
        s = self.case_spec()
        return TurekHronCFD3(s.model_copy(update={"base_cell_size": s.base_cell_size * ratio}))
