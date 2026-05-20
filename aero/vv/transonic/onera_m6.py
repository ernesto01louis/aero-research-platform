"""ONERA M6 wing — Cp vs Schmitt-Charpin (ONERA TR-1) at fixed span stations.

Stage 06 (ADR-006): the platform's first 3D case. Canonical transonic test:
M = 0.84, AoA = 3.06 deg, Re ≈ 1.17e7. The wing mesh is the BSD-licensed
`.su2` asset from the SU2 tutorial repository, mirrored under
`data/meshes/su2/onera_m6.su2` (DVC-tracked — `dvc pull` to fetch).

Cp distributions at four canonical span stations (η = 0.20, 0.44, 0.65, 0.80)
are compared pointwise (5% normalised, ADR-006) against the Schmitt-Charpin
experimental reference. The `evaluate` here returns the η=0.44 station as the
single pointwise metric the harness compares; the others are recorded as
artefacts in the post-stage handoff once cluster runs land.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from aero.adapters.su2.schemas import SU2MeshFileSpec
from aero.vv._base import (
    BenchmarkError,
    MetricSpec,
    ReferenceData,
    Series,
    SolverLike,
    load_series_csv,
)


class OneraM6:
    """ONERA M6 (M = 0.84, AoA = 3.06 deg) — Cp validation at fixed span stations."""

    name = "onera_m6"
    description = (
        "ONERA M6 wing (M=0.84, AoA=3.06 deg) — Cp at η=0.44 vs Schmitt-Charpin "
        "(ONERA TR-1, 5% normalised tolerance, ADR-006)."
    )
    sweep_metric = "cp"

    def __init__(self, spec: SU2MeshFileSpec | None = None) -> None:
        self._spec = spec or SU2MeshFileSpec(
            name=self.name,
            mach=0.84,
            aoa_deg=3.06,
            reynolds=1.17e7,
            mesh_file="data/meshes/su2/onera_m6.su2",
            n_dim=3,
            ref_area=0.7587,
            ref_length=0.64607,
            wall_markers=("WING",),
            farfield_markers=("FARFIELD",),
            symmetry_markers=("SYMMETRY",),
            turbulence_model="SA",
            iterations=10000,
            cfl=5.0,
        )

    def case_spec(self) -> SU2MeshFileSpec:
        return self._spec

    def reference(self, repo_root: Path) -> ReferenceData:
        ref_dir = repo_root / "data" / "references" / "transonic" / "onera_m6"
        cp_csv = ref_dir / "cp_station_0.44.csv"
        if not cp_csv.is_file():
            raise BenchmarkError(
                f"ONERA M6 reference data not present ({cp_csv}) — see "
                f"{ref_dir / 'reference.md'}; DVC-tracked, pull with `dvc pull`."
            )
        return ReferenceData(
            case_name=self.name,
            source="Schmitt-Charpin (ONERA TR-1) experimental Cp at eta=0.44",
            series={"cp": load_series_csv(cp_csv, x_col="x_over_c", y_col="cp")},
        )

    def metrics(self) -> tuple[MetricSpec, ...]:
        return (MetricSpec(name="cp", kind="pointwise", tolerance=0.05, comparison="normalized"),)

    def evaluate(self, solver: SolverLike, result: Any) -> dict[str, float | Series]:
        # On a 3D wing surface SU2 writes `surface_flow.csv` over all wall faces;
        # extracting the eta=0.44 chordwise section requires slicing on `y`. SU2
        # supports the slice via `MARKER_ANALYZE` or post-processing; the cluster
        # run extends `wall_distribution` with the slicing logic. Until then this
        # case is harness-skipped (BenchmarkError above when reference is missing).
        raise BenchmarkError(
            "ONERA M6 eta=0.44 Cp extraction requires a 3D wing-slice post-step "
            "not yet implemented host-side — flagged for the Stage-06 handoff."
        )

    def refined(self, ratio: float) -> OneraM6:
        # Mesh refinement on a supplied-file 3D case requires regenerating the
        # `.su2` from a parametric mesh source (not in Stage-06 scope). A GCI
        # sweep on ONERA M6 is deferred — flagged in ADR-006.
        del ratio
        return OneraM6(self._spec)
