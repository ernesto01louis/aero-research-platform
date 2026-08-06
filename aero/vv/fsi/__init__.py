"""Fluid-structure-interaction validation cases (Stage 19, ADR-016/035/036).

Cases that run PARTITIONED coupling — two solvers exchanging interface data through
preCICE at run time — against published FSI benchmark values. The FSI tier of the
validation ladder (`.claude/rules/flapping-validation-ladder.md`); the machinery the
flexible-flapping flagship stands on.

Registry pattern mirrors `aero.vv.external_geometry`.
"""

from aero.vv._base import BenchmarkCase
from aero.vv.fsi.hg2007_flexible_foil import (
    HG2007_CASES,
    HeathcoteGursulFoil,
    hg2007_case_spec,
)
from aero.vv.fsi.turek_hron_fsi3 import (
    TUREK_HRON_FSI3_EXPECTATION,
    TurekHronFSI3,
    fsi3_case_spec,
)

#: Both Stage-20 arms are registered separately. `aero vv report` is registry-driven since
#: Stage 19 -- a registered case with no run at all reports `missing`, renders red and denies
#: ALL GREEN -- so registering each arm is what stops one of them going quiet. The flexible-
#: minus-rigid INCREMENT has no row here by construction: it needs both arms, and the
#: campaign driver composes it (ADR-039 says so rather than leaving it to be noticed).
FSI_CASES: dict[str, BenchmarkCase] = {
    TurekHronFSI3.name: TurekHronFSI3(),
    **HG2007_CASES,
}

__all__ = [
    "FSI_CASES",
    "HG2007_CASES",
    "TUREK_HRON_FSI3_EXPECTATION",
    "HeathcoteGursulFoil",
    "TurekHronFSI3",
    "fsi3_case_spec",
    "hg2007_case_spec",
]
