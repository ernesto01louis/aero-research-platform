"""The CFD objective: a design-variable vector → one ground-truth CFD solve → a scalar (Stage 15).

Bridges the backend-free optimizer (:mod:`aero.optimize.bo`) to the real solver: given a raw design
vector, build the airfoil `CaseSpec`/`BenchmarkCase` (via a caller-supplied ``make_case``), compute
the four-fold provenance, run ONE steady CFD solve through the existing
:class:`~aero.vv._base.BenchmarkRunner`, and return the objective scalar (L/D) with its provenance.
Direct CFD every call — no surrogate optimum (Hard Rule 14). Clean-tree provenance
(``allow_dirty=False``) so a thesis-grade optimization result never carries a ``-dirty`` SHA (P1b).
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

import numpy as np
from pydantic import BaseModel, ConfigDict, Field

from aero.optimize.design_space import DesignSpace
from aero.provenance import compute_provenance
from aero.provenance.four_fold import ProvenanceTuple
from aero.vv._base import BenchmarkRunner

_STRICT = ConfigDict(extra="forbid", frozen=True, validate_assignment=True, validate_default=True)


class ObjectiveEval(BaseModel):
    """One evaluated design: the objective value + its CFD provenance."""

    model_config = _STRICT

    design: tuple[float, ...]
    value: float = Field(..., description="The optimized scalar (e.g. lift-to-drag ratio).")
    mlflow_run_id: str | None = None
    provenance: ProvenanceTuple


class CFDObjective:
    """Callable ``DV vector -> ObjectiveEval`` (one ground-truth CFD solve per call)."""

    def __init__(
        self,
        *,
        space: DesignSpace,
        make_case: Callable[[dict[str, float]], Any],
        runner: BenchmarkRunner,
        repo_root: Path,
        metric: str = "ld",
        container_sif: str = "openfoam-esi.sif",
        allow_dirty: bool = False,
        log_mlflow: bool = True,
    ) -> None:
        self.space = space
        self.make_case = make_case
        self.runner = runner
        self.repo_root = repo_root
        self.metric = metric
        self.container_sif = container_sif
        self.allow_dirty = allow_dirty
        self.log_mlflow = log_mlflow

    def provenance_for(self, x: np.ndarray) -> ProvenanceTuple:
        """The four-fold provenance of the design ``x`` (config_hash reflects the shape DVs)."""
        case = self.make_case(self.space.as_named(x))
        return compute_provenance(
            repo_root=self.repo_root,
            container_sif=self.container_sif,
            resolved_config=case.case_spec().model_dump(mode="json"),
            allow_dirty=self.allow_dirty,
        )

    def __call__(self, x: np.ndarray) -> ObjectiveEval:
        x = np.asarray(x, dtype=np.float64)
        dv = self.space.as_named(x)
        case = self.make_case(dv)
        prov = compute_provenance(
            repo_root=self.repo_root,
            container_sif=self.container_sif,
            resolved_config=case.case_spec().model_dump(mode="json"),
            allow_dirty=self.allow_dirty,
        )
        obs = self.runner.measure_scalar(
            case, self.metric, provenance=prov, repo_root=self.repo_root, log_mlflow=self.log_mlflow
        )
        return ObjectiveEval(
            design=tuple(float(v) for v in x),
            value=float(obs.value),
            mlflow_run_id=obs.mlflow_run_id,
            provenance=prov,
        )
