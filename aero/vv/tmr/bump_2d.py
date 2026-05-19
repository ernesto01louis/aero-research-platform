"""The NASA TMR 2D bump-in-channel V&V case.

The bump carries two distinct checks (see `data/references/tmr/bump_2d/`):

* **Verification** — a Grid Convergence Index mesh sweep on the suction-peak
  Cp (`cp_min`). A GCI compares the solution against itself at three grids and
  needs no external reference data.
* **Validation** — the pointwise Cp / Cf distributions vs. the TMR-published
  data. Those data files were not available offline at Stage 05, so
  `reference()` fails loud until they are mirrored; the bump *validation* test
  is skipped while the *verification* sweep runs.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from aero.adapters.openfoam.fields import extract_wall_distributions
from aero.adapters.openfoam.tmr_specs import Bump2DSpec
from aero.vv._base import (
    BenchmarkError,
    MetricSpec,
    ReferenceData,
    Series,
    SolverLike,
    load_series_csv,
    scaled_count,
)


class Bump2D:
    """TMR 2D bump-in-channel (Re = 3e6, M = 0.2) — Cp/Cf, with a GCI sweep."""

    name = "bump_2d"
    description = "NASA TMR 2D bump-in-channel — Cp/Cf validation and a GCI mesh sweep."
    sweep_metric = "cp_min"

    def __init__(self, spec: Bump2DSpec | None = None) -> None:
        self._spec = spec or Bump2DSpec(name=self.name, reynolds=3.0e6, mach=0.2)

    def case_spec(self) -> Bump2DSpec:
        return self._spec

    def reference(self, repo_root: Path) -> ReferenceData:
        ref_dir = repo_root / "data" / "references" / "tmr" / "bump_2d"
        cp_csv = ref_dir / "cp.csv"
        cf_csv = ref_dir / "cf.csv"
        if not (cp_csv.is_file() and cf_csv.is_file()):
            raise BenchmarkError(
                "bump_2d: TMR Cp/Cf reference data is not present "
                f"({ref_dir}) — see reference.md. The GCI mesh sweep "
                "(`--mesh-sweep`) needs no reference data and still runs."
            )
        return ReferenceData(
            case_name=self.name,
            source="NASA TMR 2D bump-in-channel (turbmodels.larc.nasa.gov/bump.html)",
            series={
                "cp": load_series_csv(cp_csv, x_col="x", y_col="cp"),
                "cf": load_series_csv(cf_csv, x_col="x", y_col="cf"),
            },
        )

    def metrics(self) -> tuple[MetricSpec, ...]:
        return (
            MetricSpec(name="cp", kind="pointwise", tolerance=0.03, comparison="normalized"),
            MetricSpec(name="cf", kind="pointwise", tolerance=0.05, comparison="relative"),
        )

    def evaluate(self, solver: SolverLike, result: Any) -> dict[str, float | Series]:
        wd = extract_wall_distributions(result.post_processing_host_path, patch="wall")
        # Restrict to the bump itself: 0 <= x <= bump_length.
        pts = [
            (x, cp, cf)
            for x, cp, cf in zip(wd.x, wd.cp, wd.cf, strict=True)
            if 0.0 <= x <= self._spec.bump_length
        ]
        if len(pts) < 2:
            raise BenchmarkError("bump_2d: fewer than two wall samples on the bump")
        cp = Series(x=tuple(p[0] for p in pts), y=tuple(p[1] for p in pts))
        cf = Series(x=tuple(p[0] for p in pts), y=tuple(p[2] for p in pts))
        # `cp_min` (the suction peak) is the scalar the GCI mesh sweep tracks —
        # a clear extremum that converges cleanly with the grid.
        return {"cp": cp, "cf": cf, "cp_min": min(cp.y)}

    def refined(self, ratio: float) -> Bump2D:
        s = self._spec
        return Bump2D(
            s.model_copy(
                update={
                    "n_bump": scaled_count(s.n_bump, ratio),
                    "n_inlet": scaled_count(s.n_inlet, ratio),
                    "n_outlet": scaled_count(s.n_outlet, ratio),
                    "n_normal": scaled_count(s.n_normal, ratio),
                }
            )
        )
