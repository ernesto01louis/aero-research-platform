"""Which solver stack each registered V&V case measures (ADR-051 D2 (b); Stage 22).

No registered case records its solver: the solver is chosen at run time (`aero vv run
--solver`), and the TMR cases are also run through SU2 under the same `validation_tag`. The
production gate needs the stack explicitly, so this module is the single table of record:

* every registered case maps to exactly one stack (`CASE_STACK`); a case added to a registry
  without an entry here fails `check_stack_map` loudly instead of silently gating nothing;
* a stack lists the `solver_version` tag prefixes that count as a run ON that stack, so a newer
  SU2 run of a TMR case is never attributed to the OpenFOAM stack;
* the preCICE-coupled cases gate the OpenFOAM stack (their fluid solver is OpenFOAM-ESI v2412),
  which is what ADR-051's Stage-24 arithmetic (20 active-stack cases) already assumes;
* `hg2007_flexible_foil` is deferred (ADR-046 S4): shown, never gating.

Pure stdlib + pydantic. The registries are imported lazily inside `registered_cases`.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import TYPE_CHECKING, Literal

from pydantic import BaseModel, ConfigDict, Field

from aero.vv.status import Disposition, StackName

if TYPE_CHECKING:
    from aero.vv._base import BenchmarkCase


class SolverStack(BaseModel):
    """A solver stack the V&V verdict is scoped to."""

    model_config = ConfigDict(extra="forbid", frozen=True, validate_default=True)

    name: StackName
    disposition: Literal["active", "frozen"]
    solver_version_prefixes: tuple[str, ...] = Field(
        ..., min_length=1, description="`solver_version` tag prefixes that count as this stack."
    )
    record: str = Field(..., min_length=1, description="The decision of record for its status.")
    description: str = Field(..., min_length=1)


STACKS: dict[StackName, SolverStack] = {
    "openfoam": SolverStack(
        name="openfoam",
        disposition="active",
        # "OpenFOAM-ESI v2412" for single-solver runs; "preCICE 3.4.1 (OpenFOAM-ESI v2412 + ...)"
        # for the coupled cases (aero/cli.py `_SOLVER_VERSIONS` / `_CASE_PROVENANCE`).
        solver_version_prefixes=("OpenFOAM-ESI", "preCICE"),
        record="ADR-051 D2",
        description="OpenFOAM-ESI v2412, including the preCICE-coupled OpenFOAM cases",
    ),
    "su2": SolverStack(
        name="su2",
        disposition="frozen",
        solver_version_prefixes=("SU2",),
        record="ADR-013",
        description="SU2 v8, frozen-optional",
    ),
    "pyfr": SolverStack(
        name="pyfr",
        disposition="frozen",
        solver_version_prefixes=("PyFR",),
        record="ADR-013",
        description="PyFR 1.15.0 (GPU), frozen-optional",
    ),
}

#: Every registered case and the one stack it measures. Kept equal to the registries' union by
#: `check_stack_map` (and by tests/unit/test_vv_stacks.py).
CASE_STACK: dict[str, StackName] = {
    # NASA TMR (Stage 05)
    "flat_plate_te": "openfoam",
    "bump_2d": "openfoam",
    "naca0012_verification": "openfoam",
    # forward regime (Stage 10)
    "blasius_flat_plate": "openfoam",
    "laminar_airfoil_naca0012": "openfoam",
    "cylinder_strouhal_re100": "openfoam",
    # transition / ERCOFTAC (Stage 13)
    "t3a_flat_plate_transition": "openfoam",
    # unsteady / moving body (Stages 11, 13)
    "oscillating_cylinder_lockin": "openfoam",
    "plunging_airfoil_hg2007": "openfoam",
    "plunging_airfoil_hg2007_st02": "openfoam",
    "plunging_airfoil_hg2007_st02_lm": "openfoam",
    "plunging_airfoil_hg2007_st03": "openfoam",
    "plunging_airfoil_hg2007_st03_lm": "openfoam",
    # rigid flapping wing (Stage 14)
    "flapping_wing_wbd2004": "openfoam",
    "flapping_wing_wbd2004_advanced": "openfoam",
    "flapping_wing_wbd2004_delayed": "openfoam",
    # external geometry (Stage 18)
    "turek_hron_cfd2": "openfoam",
    "turek_hron_cfd3": "openfoam",
    # FSI, preCICE-coupled OpenFOAM (Stages 19, 20)
    "turek_hron_fsi3": "openfoam",
    "hg2007_rigid_foil": "openfoam",
    "hg2007_flexible_foil": "openfoam",
    # transonic, SU2 (Stage 06; frozen-optional, ADR-013)
    "naca0012_transonic": "su2",
    "onera_m6": "su2",
    # scale-resolving, PyFR GPU (Stage 07; frozen-optional, ADR-013)
    "taylor_green_p3_32": "pyfr",
    "periodic_hill_2d": "pyfr",
}

#: Deferred cases and the decision of record. Shown in the report, never gating (ADR-051 D2).
DEFERRED_CASES: dict[str, str] = {
    "hg2007_flexible_foil": "ADR-046 S4",
}


class StackMapError(RuntimeError):
    """The stack table and the case registries disagree."""


def case_disposition(case: str) -> Disposition:
    """`deferred` for a deferred case, else its stack's disposition (`active` / `frozen`)."""
    if case in DEFERRED_CASES:
        return "deferred"
    return STACKS[CASE_STACK[case]].disposition


def check_stack_map(names: Iterable[str]) -> None:
    """Fail loudly unless `names` (the registered cases) equal the keys of `CASE_STACK`."""
    registered = set(names)
    unmapped = sorted(registered - CASE_STACK.keys())
    stale = sorted(CASE_STACK.keys() - registered)
    bad_deferred = sorted(DEFERRED_CASES.keys() - CASE_STACK.keys())
    problems = []
    if unmapped:
        problems.append(f"registered but not in CASE_STACK: {', '.join(unmapped)}")
    if stale:
        problems.append(f"in CASE_STACK but not registered: {', '.join(stale)}")
    if bad_deferred:
        problems.append(f"in DEFERRED_CASES but not in CASE_STACK: {', '.join(bad_deferred)}")
    if problems:
        raise StackMapError(
            "the V&V stack table (aero/vv/stacks.py) disagrees with the case registries — "
            + "; ".join(problems)
        )


def registered_cases() -> dict[str, BenchmarkCase]:
    """The union of the nine case registries, keyed by case name, checked against the stacks.

    Raises `StackMapError` on a name registered twice or on any disagreement with `CASE_STACK`.
    """
    from aero.vv.ercoftac import ERCOFTAC_CASES
    from aero.vv.external_geometry import EXTERNAL_GEOMETRY_CASES
    from aero.vv.flapping import FLAPPING_CASES
    from aero.vv.forward_regime import FORWARD_REGIME_CASES
    from aero.vv.fsi import FSI_CASES
    from aero.vv.scale_resolving import SCALE_RESOLVING_CASES
    from aero.vv.tmr import TMR_CASES
    from aero.vv.transonic import TRANSONIC_CASES
    from aero.vv.unsteady import UNSTEADY_CASES

    union: dict[str, BenchmarkCase] = {}
    for registry in (
        TMR_CASES,
        FORWARD_REGIME_CASES,
        ERCOFTAC_CASES,
        UNSTEADY_CASES,
        FLAPPING_CASES,
        TRANSONIC_CASES,
        SCALE_RESOLVING_CASES,
        EXTERNAL_GEOMETRY_CASES,
        FSI_CASES,
    ):
        for name, case in registry.items():
            if name in union:
                raise StackMapError(f"V&V case {name!r} is registered twice")
            union[name] = case
    check_stack_map(union)
    return union
