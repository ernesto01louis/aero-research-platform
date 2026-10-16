"""Typed V&V status and the per-solver-stack verdict (ADR-051 D2 (b); Stage 22).

`aero vv report --latest` is the production gate of ADR-005. Until Stage 22 its status was a free
string and its verdict was one suite-wide "all green". Two things changed at Stage 22:

* A case's status is one of seven typed values. An unknown string fails loudly at validation
  instead of rendering as a neutral grey cell.
* The verdict is per solver stack (operator decision D2 (b), 2026-10-16). A production run on the
  OpenFOAM stack needs every OpenFOAM-stack case `pass`; a PyFR production run needs every PyFR
  case `pass`. Frozen-optional stacks (ADR-013) and deferred cases (ADR-046 S4) stay registered
  and visible, are never `pass` by assignment, and no longer gate a stack they do not measure.

Pure stdlib + pydantic, so `import aero.vv` stays PLATFORM-NOT-HUB clean.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Literal, get_args

from pydantic import BaseModel, ConfigDict, Field

VVStatus = Literal["pass", "fail", "regress", "missing", "unknown", "frozen", "deferred"]
"""One registered case's status in the report.

* `pass` / `fail` / `regress` — the `vv_status` tag of the case's newest run on its own stack.
* `unknown` — that run exists but carries no (or an unrecognised) `vv_status`. Never `pass`.
* `missing` — an ACTIVE-stack case with no run at all. Rendered as red as `fail`.
* `frozen` — a frozen-optional-stack case (ADR-013) with no run.
* `deferred` — a deferred case (ADR-046 S4) with no run. It gates nothing.
"""

VV_STATUSES: tuple[VVStatus, ...] = get_args(VVStatus)

#: The statuses a `vv_status` MLflow tag may carry. Anything else on a real run is `unknown`.
RUN_STATUSES: frozenset[str] = frozenset({"pass", "fail", "regress"})

StackName = Literal["openfoam", "su2", "pyfr"]
"""The solver stack a registered case measures (see `aero.vv.stacks`)."""

STACK_ORDER: tuple[StackName, ...] = get_args(StackName)

Disposition = Literal["active", "frozen", "deferred"]
"""Whether a case gates its stack: `active` and `frozen` cases gate their own stack's verdict;
`deferred` cases are shown but gate nothing (ADR-046 S4)."""

Verdict = Literal["GREEN", "RED", "FROZEN"]
"""A stack's verdict. GREEN: every gating case passes. RED: a gating case failed, regressed, has
no run on an active stack, or has a run of unknown status. FROZEN: nothing failed, but some gating
case of a frozen-optional stack has never been evaluated. Only GREEN clears production runs."""

#: Statuses that make a stack RED. `frozen` alone makes it FROZEN; `deferred` never gates.
_RED_STATUSES: frozenset[VVStatus] = frozenset({"fail", "regress", "missing", "unknown"})

_STRICT = ConfigDict(extra="forbid", frozen=True, validate_default=True)


class StackVerdict(BaseModel):
    """One solver stack's verdict over the cases that gate it."""

    model_config = _STRICT

    stack: StackName
    verdict: Verdict
    gating: tuple[str, ...] = Field(..., description="Cases that gate this stack.")
    not_passing: tuple[tuple[str, VVStatus], ...] = Field(
        default=(), description="(case, status) of each gating case that is not `pass`."
    )
    not_gating: tuple[tuple[str, VVStatus], ...] = Field(
        default=(), description="(case, status) of each deferred case shown under this stack."
    )

    @property
    def clear_for_production(self) -> bool:
        """True only when this stack's verdict is GREEN."""
        return self.verdict == "GREEN"


def stack_verdicts(
    items: Iterable[tuple[str, StackName, Disposition, VVStatus]],
) -> dict[StackName, StackVerdict]:
    """Per-stack verdicts from `(case, stack, disposition, status)` items, in `STACK_ORDER`.

    Only stacks that appear in `items` get a verdict. A stack is GREEN iff it has at least one
    gating case and every gating case is `pass`; deferred cases never count either way.
    """
    by_stack: dict[StackName, list[tuple[str, Disposition, VVStatus]]] = {}
    for case, stack, disposition, status in items:
        by_stack.setdefault(stack, []).append((case, disposition, status))

    verdicts: dict[StackName, StackVerdict] = {}
    for stack in STACK_ORDER:
        if stack not in by_stack:
            continue
        rows = sorted(by_stack[stack])
        gating = [(c, s) for c, d, s in rows if d != "deferred"]
        not_gating = tuple((c, s) for c, d, s in rows if d == "deferred")
        not_passing = tuple((c, s) for c, s in gating if s != "pass")
        verdict: Verdict
        if gating and not not_passing:
            verdict = "GREEN"
        elif not gating or any(s in _RED_STATUSES for _, s in not_passing):
            verdict = "RED"
        else:
            verdict = "FROZEN"
        verdicts[stack] = StackVerdict(
            stack=stack,
            verdict=verdict,
            gating=tuple(c for c, _ in gating),
            not_passing=not_passing,
            not_gating=not_gating,
        )
    return verdicts
