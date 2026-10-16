"""The V&V report's read of MLflow: one query per registered case, never a window (Stage 22).

Until Stage 22, `aero vv report --latest` read the newest 500 runs of the V&V experiment and
derived each case's status from whatever came back. `vv-smoke` logs four cases on every push, so
those runs filled the window and every older run was reported `missing`: three failures and three
passes were invisible (ADR-051 §1). This module replaces the window:

* `--latest` asks MLflow, for each registered case and each `solver_version` prefix of the case's
  stack, for the single newest run (`collect_latest`). A run older than any window is found; a
  failing case hidden behind thousands of newer runs of other cases is still `fail`. Unregistered
  tags (`<case>-sweep`, and the tier names `thesis-grade` / `validated` the reportable scripts
  write) can never enter, because only registered names are queried.
* the history listing pages the whole experiment explicitly with `page_token` and states its
  bound and everything it left out (`collect_history`). It never truncates silently.

The client is a parameter (anything with mlflow's `search_runs` signature), so the logic is
unit-tested with a fake and `import aero.vv.report` loads no mlflow.
"""

from __future__ import annotations

import re
from collections import Counter
from collections.abc import Iterable, Sequence
from datetime import UTC, datetime
from typing import Any, Protocol

from pydantic import BaseModel, ConfigDict, Field

from aero.vv.stacks import CASE_STACK, DEFERRED_CASES, STACKS, case_disposition, check_stack_map
from aero.vv.status import (
    RUN_STATUSES,
    STACK_ORDER,
    VV_STATUSES,
    Disposition,
    StackName,
    StackVerdict,
    VVStatus,
    stack_verdicts,
)

#: Runs per page when the history listing pages the experiment (mlflow's default page size).
PAGE_SIZE = 1000

_STRICT = ConfigDict(extra="forbid", frozen=True, validate_default=True)
_SAFE_CASE = re.compile(r"^[A-Za-z0-9_.-]+$")
_SAFE_PREFIX = re.compile(r"^[A-Za-z0-9_. -]+$")


class ReportError(RuntimeError):
    """The report could not be assembled faithfully (bad name, paging loop, ...)."""


class RunSearcher(Protocol):
    """The slice of `mlflow.tracking.MlflowClient` the report uses."""

    def get_experiment_by_name(self, name: str) -> Any: ...

    def search_runs(
        self,
        experiment_ids: list[str],
        filter_string: str = ...,
        run_view_type: int = ...,
        max_results: int = ...,
        order_by: list[str] | None = ...,
        page_token: str | None = ...,
    ) -> Any: ...


class ReportRow(BaseModel):
    """One row of the report: a registered case and its newest on-stack run, or why it has none."""

    model_config = _STRICT

    case: str = Field(..., min_length=1)
    stack: StackName
    disposition: Disposition
    status: VVStatus
    run_id: str = ""
    git_sha: str = ""
    solver_version: str = ""
    start_time: str = Field(default="", description="Run start, ISO-8601 UTC; '' for no run.")
    metric_errors: dict[str, float] = Field(default_factory=dict)


class HistoryListing(BaseModel):
    """The bounded, explicitly paged run history (the non-`--latest` report)."""

    model_config = _STRICT

    rows: tuple[ReportRow, ...]
    limit: int = Field(..., ge=1)
    total_gated: int = Field(..., ge=0, description="Runs whose tag is a registered case.")
    sweep_runs: int = Field(..., ge=0)
    unregistered: dict[str, int] = Field(default_factory=dict)
    untagged: int = Field(..., ge=0)
    total_runs: int = Field(..., ge=0)

    @property
    def truncated(self) -> bool:
        return self.total_gated > len(self.rows)


def case_filter(case: str, solver_prefix: str) -> str:
    """The MLflow filter for `case`'s runs on solvers whose version tag starts `solver_prefix`."""
    if not _SAFE_CASE.match(case):
        raise ReportError(f"refusing to build an MLflow filter for case name {case!r}")
    if not _SAFE_PREFIX.match(solver_prefix):
        raise ReportError(f"refusing to build an MLflow filter for prefix {solver_prefix!r}")
    return f"tags.validation_tag = '{case}' AND tags.solver_version LIKE '{solver_prefix}%'"


def _iso(start_time_ms: Any) -> str:
    if start_time_ms is None:
        return ""
    return datetime.fromtimestamp(int(start_time_ms) / 1000, UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def run_status(run: Any) -> VVStatus:
    """The run's `vv_status` tag if it is pass / fail / regress; anything else is `unknown`."""
    tag = run.data.tags.get("vv_status")
    if tag in RUN_STATUSES:
        return tag  # type: ignore[no-any-return]
    return "unknown"


def row_from_run(case: str, run: Any) -> ReportRow:
    """The row for `case` from one of its runs."""
    errors = {
        k[: -len("_error")]: float(v) for k, v in run.data.metrics.items() if k.endswith("_error")
    }
    return ReportRow(
        case=case,
        stack=CASE_STACK[case],
        disposition=case_disposition(case),
        status=run_status(run),
        run_id=str(run.info.run_id),
        git_sha=str(run.data.tags.get("git_sha", "")),
        solver_version=str(run.data.tags.get("solver_version", "")),
        start_time=_iso(run.info.start_time),
        metric_errors=errors,
    )


def row_without_run(case: str) -> ReportRow:
    """The row for a case with no on-stack run: `missing`, `frozen` or `deferred`."""
    disposition = case_disposition(case)
    status: VVStatus = "missing" if disposition == "active" else disposition
    return ReportRow(case=case, stack=CASE_STACK[case], disposition=disposition, status=status)


def latest_run_for_case(client: RunSearcher, experiment_id: str, case: str) -> Any | None:
    """The newest run of `case` on its own stack, or None. One query per stack prefix."""
    best: Any | None = None
    for prefix in STACKS[CASE_STACK[case]].solver_version_prefixes:
        page = client.search_runs(
            experiment_ids=[experiment_id],
            filter_string=case_filter(case, prefix),
            order_by=["start_time DESC"],
            max_results=1,
        )
        for run in list(page)[:1]:
            if best is None or int(run.info.start_time) > int(best.info.start_time):
                best = run
    return best


def _order(row: ReportRow) -> tuple[int, str]:
    return (STACK_ORDER.index(row.stack), row.case)


def collect_latest(
    client: RunSearcher, experiment_id: str, cases: Iterable[str]
) -> list[ReportRow]:
    """One row per registered case, from its newest on-stack run (`--latest`; no window)."""
    names = sorted(set(cases))
    check_stack_map(names)
    rows = []
    for case in names:
        run = latest_run_for_case(client, experiment_id, case)
        rows.append(row_without_run(case) if run is None else row_from_run(case, run))
    return sorted(rows, key=_order)


def verdicts_of(rows: Iterable[ReportRow]) -> dict[StackName, StackVerdict]:
    """The per-stack verdicts of a set of report rows."""
    return stack_verdicts((r.case, r.stack, r.disposition, r.status) for r in rows)


def collect_history(client: RunSearcher, experiment_id: str, limit: int) -> HistoryListing:
    """Page the WHOLE experiment newest first; list up to `limit` gated runs; count the rest."""
    if limit < 1:
        raise ReportError(f"--limit must be at least 1, got {limit}")
    rows: list[ReportRow] = []
    total = gated = sweeps = untagged = 0
    unregistered: Counter[str] = Counter()
    token: str | None = None
    seen_tokens: set[str] = set()
    while True:
        page = client.search_runs(
            experiment_ids=[experiment_id],
            order_by=["start_time DESC"],
            max_results=PAGE_SIZE,
            page_token=token,
        )
        for run in page:
            total += 1
            tag = run.data.tags.get("validation_tag")
            if not tag:
                untagged += 1
            elif tag in CASE_STACK:
                gated += 1
                if len(rows) < limit:
                    rows.append(row_from_run(tag, run))
            elif tag.endswith("-sweep"):
                sweeps += 1
            else:
                unregistered[tag] += 1
        token = getattr(page, "token", None) or None
        if token is None:
            break
        if token in seen_tokens:
            raise ReportError("MLflow returned a page token twice; refusing to loop")
        seen_tokens.add(token)
    return HistoryListing(
        rows=tuple(rows),
        limit=limit,
        total_gated=gated,
        sweep_runs=sweeps,
        unregistered=dict(sorted(unregistered.items())),
        untagged=untagged,
        total_runs=total,
    )


# --- text rendering -------------------------------------------------------------------------

_MARK: dict[VVStatus, str] = {
    "pass": "GREEN ",
    "fail": "RED   ",
    "regress": "RED   ",
    "missing": "RED   ",
    "unknown": "RED   ",
    "frozen": "FROZEN",
    "deferred": "DEFER ",
}


def _no_run_note(row: ReportRow) -> str:
    if row.status == "deferred":
        return f"no run; deferred ({DEFERRED_CASES[row.case]}), gates nothing"
    if row.status == "frozen":
        return f"no run; frozen-optional stack ({STACKS[row.stack].record})"
    return "no run"


def _row_line(row: ReportRow) -> str:
    head = f"    [{_MARK[row.status]}] {row.case:<34} {row.status:<9}"
    if not row.run_id:
        return f"{head}{_no_run_note(row)}"
    return (
        f"{head}{row.run_id}  {row.start_time[:10]}  {row.git_sha[:12]:<12}  {row.solver_version}"
    )


def _counts(rows: Sequence[ReportRow]) -> str:
    tally = Counter(r.status for r in rows)
    return ", ".join(f"{tally[s]} {s}" for s in VV_STATUSES if tally[s])


def _verdict_lines(v: StackVerdict) -> list[str]:
    stack = STACKS[v.stack]
    if v.verdict == "GREEN":
        head = f"all {len(v.gating)} gating case(s) pass; clear for production-tagged runs"
    elif v.verdict == "FROZEN":
        head = (
            f"never fully evaluated (frozen-optional, {stack.record}); "
            "not clear for production-tagged runs on this stack"
        )
    else:
        head = "not clear for production-tagged runs on this stack"
    lines = [f"  VERDICT {v.stack}: {v.verdict} — {head}."]
    by_status: dict[str, list[str]] = {}
    for case, status in v.not_passing:
        by_status.setdefault(status, []).append(case)
    for status in VV_STATUSES:
        if status in by_status:
            names = by_status[status]
            lines.append(f"      {len(names)} {status}: {', '.join(names)}")
    if v.not_gating:
        names = [c for c, _ in v.not_gating]
        lines.append(f"      shown but not gating (deferred): {', '.join(names)}")
    return lines


def render_latest(rows: Sequence[ReportRow]) -> str:
    """The `--latest` text report: rows grouped by stack, then one verdict per stack."""
    verdicts = verdicts_of(rows)
    out = [
        "",
        "  V&V report: the newest run of every registered case on its own solver stack",
        "  (one MLflow query per case and stack prefix; no window)",
        "",
        f"  {len(rows)} registered case(s): {_counts(rows)}",
    ]
    for stack in STACK_ORDER:
        stack_rows = [r for r in rows if r.stack == stack]
        if not stack_rows:
            continue
        s = STACKS[stack]
        out += ["", f"  stack {stack}: {s.description} ({s.disposition}; {s.record})"]
        out += [_row_line(r) for r in stack_rows]
    out.append("")
    for stack in STACK_ORDER:
        if stack in verdicts:
            out += _verdict_lines(verdicts[stack])
    clear = [s for s in STACK_ORDER if s in verdicts and verdicts[s].clear_for_production]
    out += [
        "",
        "  A production-tagged run is gated by its OWN solver stack's verdict "
        "(ADR-005, scoped by ADR-051 D2).",
        f"  Stacks clear for production-tagged runs: {', '.join(clear) if clear else 'none'}.",
    ]
    return "\n".join(out)


def render_history(listing: HistoryListing) -> str:
    """The bounded history listing, with its bound and every exclusion stated."""
    out = ["", "  V&V run history, newest first (a bounded listing; NOT the production gate)", ""]
    out += [_row_line(r) for r in listing.rows]
    shown = len(listing.rows)
    unreg = ", ".join(f"{t} {n}" for t, n in listing.unregistered.items()) or "none"
    out += [
        "",
        f"  listed {shown} of {listing.total_gated} gated run(s) (newest first; bound --limit "
        f"{listing.limit}){'; TRUNCATED at the bound' if listing.truncated else ''}.",
        f"  The experiment holds {listing.total_runs} run(s), all paged. Not listed: "
        f"{listing.sweep_runs} sweep run(s) (`<case>-sweep`), "
        f"{sum(listing.unregistered.values())} run(s) with an unregistered tag ({unreg}), "
        f"{listing.untagged} run(s) with no validation_tag.",
        "  The production gate is `aero vv report --latest`.",
    ]
    return "\n".join(out)
