"""Periodic-hill LES — canonical separated-flow benchmark (Stage 07 skeleton).

Reference: Breuer, Peller, Rapp & Manhart (2009, IJHFF 30), "Flow over
periodic hills — numerical and experimental study in a wide range of
Reynolds numbers". Stage 07 ships only the bulk re-attachment length
scalar (the headline number every LES paper reports); the full pointwise
mean-velocity profile comparison and the wall-shear distribution land in
Stage 12, when the periodic-hill mesh and wall-sampler plumbing mature.

The case fails loud (raises `BenchmarkError`) when the expected
host-side `wall_sample.csv` is missing — a clean skip is the wrong
behaviour at the validation tier.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Literal

from aero.adapters.nekrs.schemas import NekRSCaseDirSpec
from aero.adapters.pyfr.schemas import PyFRMeshFileSpec
from aero.vv._base import (
    BenchmarkError,
    MetricSpec,
    ReferenceData,
    Series,
    SolverLike,
    load_scalar_csv,
)

PeriodicHillSolverKind = Literal["pyfr", "nekrs"]


class PeriodicHillLES:
    """Breuer 2009 periodic-hill LES at Re=10595 — re-attachment-length scalar.

    Full mean-velocity-profile comparison is a Stage-12 follow-up; this
    Stage-07 skeleton ships only the re-attachment-length scalar (the
    headline summary metric in every periodic-hill paper). The case
    consumes a DVC-tracked mesh + ini template for PyFR (NekRS path is
    a Stage-12 hardening item).
    """

    name = "periodic_hill_2d"
    description = (
        "Breuer (2009) periodic-hill LES at Re=10595 — re-attachment-length "
        "(headline summary metric; full profile comparison is a Stage-12 item)."
    )
    sweep_metric = "reattachment_length"

    def __init__(self, *, solver_kind: PeriodicHillSolverKind = "pyfr") -> None:
        self.solver_kind = solver_kind

    def case_spec(self) -> PyFRMeshFileSpec | NekRSCaseDirSpec:
        if self.solver_kind == "pyfr":
            return PyFRMeshFileSpec(
                name=self.name,
                mesh_file="data/meshes/pyfr/periodic_hill.msh",
                cfg_template="data/cases/pyfr/periodic_hill.ini",
                polynomial_order=4,
                t_end=120.0,
                dt=5e-4,
                monitor_dt=1.0,
            )
        return NekRSCaseDirSpec(
            name=self.name,
            case_name="periodicHill",
            case_dir="data/cases/nekrs/periodic_hill",
            polynomial_order=7,
            t_end=120.0,
            dt=5e-4,
            monitor_dt=1.0,
        )

    def reference(self, repo_root: Path) -> ReferenceData:
        x_r = load_scalar_csv(
            repo_root
            / "data"
            / "references"
            / "scale_resolving"
            / "periodic_hill"
            / "reattachment.csv",
            key_col="reynolds",
            key=10595,
            value_col="x_over_h",
        )
        return ReferenceData(
            case_name=self.name,
            source=(
                "Breuer, Peller, Rapp & Manhart (2009), IJHFF 30, "
                "'Flow over periodic hills', Table 3 — Re=10595 LES."
            ),
            scalars={"reattachment_length": x_r},
        )

    def metrics(self) -> tuple[MetricSpec, ...]:
        # Periodic hill re-attachment scatters ~5% across reference LES studies
        # of comparable Re; 10% tolerance is the workshop convention.
        return (
            MetricSpec(
                name="reattachment_length",
                kind="scalar",
                tolerance=0.10,
                comparison="relative",
            ),
        )

    def evaluate(self, solver: SolverLike, result: Any) -> dict[str, float | Series]:
        """Read the wall-sample CSV the PyFR sampler plugin writes.

        Fails loud if missing — Stage 07 ships the case skeleton, not the
        sampler plumbing. Stage 12 lands the host-side wall-sample
        extractor and the full pointwise mean-velocity profile compare.
        """
        sample_path = result.case_dir.host_path / "wall_sample.csv"
        if not sample_path.is_file():
            raise BenchmarkError(
                f"{self.name}: wall_sample.csv missing at {sample_path}; "
                "periodic-hill wall-sampler plumbing is a Stage-12 follow-up "
                "and the case ships here only as a registry stub."
            )
        # When Stage 12 lands the sampler, derive re-attachment length from
        # the wall-shear sign change. For now the file's presence alone is
        # the contract — a Stage 12 PR replaces this stub with the real
        # parser + comparison.
        return {"reattachment_length": 0.0}

    def refined(self, ratio: float) -> PeriodicHillLES:
        return PeriodicHillLES(solver_kind=self.solver_kind)
