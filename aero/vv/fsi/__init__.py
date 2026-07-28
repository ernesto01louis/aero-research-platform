"""Fluid-structure-interaction validation cases (Stage 19, ADR-016/035/036).

Cases that run PARTITIONED coupling — two solvers exchanging interface data through
preCICE at run time — against published FSI benchmark values. The FSI tier of the
validation ladder (`.claude/rules/flapping-validation-ladder.md`); the machinery the
flexible-flapping flagship stands on.

Registry pattern mirrors `aero.vv.external_geometry`.
"""

from aero.vv._base import BenchmarkCase
from aero.vv.fsi.turek_hron_fsi3 import (
    TUREK_HRON_FSI3_EXPECTATION,
    TurekHronFSI3,
    fsi3_case_spec,
)

FSI_CASES: dict[str, BenchmarkCase] = {
    TurekHronFSI3.name: TurekHronFSI3(),
}

__all__ = ["FSI_CASES", "TUREK_HRON_FSI3_EXPECTATION", "TurekHronFSI3", "fsi3_case_spec"]
