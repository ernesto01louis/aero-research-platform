"""A fake MLflow client for the V&V report tests (Stage 22). No cluster, no mlflow import.

It implements the slice of `MlflowClient` the report uses: `get_experiment_by_name` and
`search_runs` with newest-first ordering, `max_results` and `page_token` paging. It accepts only
the two query shapes the report may send (no filter, or the per-case filter of
`aero.vv.report.case_filter`) and raises on anything else, so a new query shape cannot pass a
test by accident. Every call is recorded in `.calls`.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from types import SimpleNamespace
from typing import Any

_CASE_FILTER = re.compile(
    r"^tags\.validation_tag = '([A-Za-z0-9_.-]+)' AND tags\.solver_version LIKE '([^'%]*)%'$"
)


@dataclass
class FakeRun:
    run_id: str
    start_time: int
    tags: dict[str, str]
    metrics: dict[str, float] = field(default_factory=dict)

    @property
    def info(self) -> Any:
        return SimpleNamespace(run_id=self.run_id, start_time=self.start_time)

    @property
    def data(self) -> Any:
        return SimpleNamespace(tags=self.tags, metrics=self.metrics)


class FakePage(list):  # type: ignore[type-arg]
    """mlflow's `PagedList`: a list with a `.token` for the next page (None on the last)."""

    def __init__(self, items: list[FakeRun], token: str | None) -> None:
        super().__init__(items)
        self.token = token


def run(
    run_id: str,
    case: str,
    t: int,
    status: str | None = "pass",
    solver: str = "OpenFOAM-ESI v2412",
    **metrics: float,
) -> FakeRun:
    """A V&V run of `case` at start time `t` (ms). `status=None` leaves `vv_status` off."""
    tags = {"validation_tag": case, "solver_version": solver, "git_sha": f"sha-{run_id}"}
    if status is not None:
        tags["vv_status"] = status
    return FakeRun(run_id=run_id, start_time=t, tags=tags, metrics=dict(metrics))


class FakeClient:
    def __init__(self, runs: list[FakeRun], experiment: str = "aero-provenance") -> None:
        self.runs = list(runs)
        self.experiment = experiment
        self.calls: list[dict[str, Any]] = []

    def get_experiment_by_name(self, name: str) -> Any:
        return SimpleNamespace(experiment_id="1") if name == self.experiment else None

    def search_runs(
        self,
        experiment_ids: list[str],
        filter_string: str = "",
        run_view_type: int = 1,
        max_results: int = 1000,
        order_by: list[str] | None = None,
        page_token: str | None = None,
    ) -> FakePage:
        self.calls.append(
            {
                "experiment_ids": experiment_ids,
                "filter_string": filter_string,
                "max_results": max_results,
                "order_by": order_by,
                "page_token": page_token,
            }
        )
        assert experiment_ids == ["1"], experiment_ids
        assert order_by == ["start_time DESC"], order_by
        selected = sorted(self.runs, key=lambda r: r.start_time, reverse=True)
        if filter_string:
            m = _CASE_FILTER.match(filter_string)
            if m is None:
                raise AssertionError(f"unexpected MLflow filter shape: {filter_string!r}")
            case, prefix = m.groups()
            selected = [
                r
                for r in selected
                if r.tags.get("validation_tag") == case
                and r.tags.get("solver_version", "").startswith(prefix)
            ]
        start = int(page_token or 0)
        end = start + max_results
        return FakePage(selected[start:end], str(end) if end < len(selected) else None)
