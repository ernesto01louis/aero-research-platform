#!/usr/bin/env python3
"""Independent read of the V&V experiment, to cross-check `aero vv report --latest` (Stage 22).

    PATH=.venv/bin:$PATH python scripts/vv_report_crosscheck.py
    PATH=.venv/bin:$PATH aero vv report --latest --json > latest.json
    PATH=.venv/bin:$PATH python scripts/vv_report_crosscheck.py --against latest.json

READ-ONLY. It pages the WHOLE MLflow experiment with `page_token` (no per-case query, no window),
and for every registered case keeps the newest run whose `solver_version` tag starts with one of
its stack's prefixes. It prints that table, the census of `validation_tag` values that are not
registered cases, and any off-stack run newer than a case's on-stack run. With `--against` it
compares, case for case, the status and run id the report printed; exit 1 on any mismatch.

It deliberately does not import `aero.vv.report`: the point is a second, differently-shaped read.
It shares only the case-to-stack table (`aero.vv.stacks`), which is the definition both reads use.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

RUN_STATUSES = {"pass", "fail", "regress"}


def simplify(run: Any) -> dict[str, Any]:
    """An mlflow Run as a plain dict (the only fields this script reads)."""
    return {
        "run_id": str(run.info.run_id),
        "start_time": int(run.info.start_time),
        "tags": dict(run.data.tags),
    }


def page_all(client: Any, experiment_id: str) -> list[dict[str, Any]]:
    """Every run of the experiment, by explicit pagination."""
    runs: list[dict[str, Any]] = []
    token = None
    seen: set[str] = set()
    while True:
        page = client.search_runs([experiment_id], max_results=1000, page_token=token)
        runs.extend(simplify(r) for r in page)
        token = getattr(page, "token", None) or None
        if token is None:
            return runs
        if token in seen:
            raise SystemExit("MLflow returned a page token twice")
        seen.add(token)


def newest_by_case(
    runs: Iterable[Mapping[str, Any]],
    case_stack: Mapping[str, str],
    stack_prefixes: Mapping[str, tuple[str, ...]],
) -> tuple[dict[str, Mapping[str, Any]], dict[str, Mapping[str, Any]], Counter[str]]:
    """(newest on-stack run per case, newest run of any solver per case, unregistered-tag census)."""
    on_stack: dict[str, Mapping[str, Any]] = {}
    any_solver: dict[str, Mapping[str, Any]] = {}
    census: Counter[str] = Counter()
    for run in runs:
        tag = run["tags"].get("validation_tag")
        if not tag:
            census["<no validation_tag>"] += 1
            continue
        if tag not in case_stack:
            census[tag] += 1
            continue
        if tag not in any_solver or run["start_time"] > any_solver[tag]["start_time"]:
            any_solver[tag] = run
        solver = run["tags"].get("solver_version", "")
        if not solver.startswith(stack_prefixes[case_stack[tag]]):
            continue
        if tag not in on_stack or run["start_time"] > on_stack[tag]["start_time"]:
            on_stack[tag] = run
    return on_stack, any_solver, census


def expected_status(
    case: str,
    run: Mapping[str, Any] | None,
    case_stack: Mapping[str, str],
    frozen_stacks: set[str],
    deferred: set[str],
) -> str:
    """The status the report must print for `case`, derived independently."""
    if run is not None:
        tag = run["tags"].get("vv_status")
        return tag if tag in RUN_STATUSES else "unknown"
    if case in deferred:
        return "deferred"
    if case_stack[case] in frozen_stacks:
        return "frozen"
    return "missing"


def compare(
    expected: Mapping[str, tuple[str, str]], report_rows: Iterable[Mapping[str, Any]]
) -> list[str]:
    """Mismatches between the independent table and the report's `--json` rows."""
    got = {r["case"]: (r["status"], r.get("run_id", "")) for r in report_rows}
    problems = []
    for case in sorted(expected.keys() | got.keys()):
        if case not in got:
            problems.append(f"{case}: absent from the report")
        elif case not in expected:
            problems.append(f"{case}: in the report but not registered")
        elif got[case] != expected[case]:
            problems.append(
                f"{case}: report says {got[case]}, independent read says {expected[case]}"
            )
    return problems


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    ap.add_argument("--against", type=Path, help="`aero vv report --latest --json` output")
    ap.add_argument("--tracking-uri", default="", help="default: from conf/ (aero.cli)")
    ap.add_argument("--experiment", default="", help="default: from conf/ (aero.cli)")
    args = ap.parse_args(argv)

    from aero.vv.stacks import CASE_STACK, DEFERRED_CASES, STACKS, registered_cases
    from mlflow.tracking import MlflowClient

    registered_cases()  # fails loudly if the stack table and the registries disagree
    uri, experiment = args.tracking_uri, args.experiment
    if not uri or not experiment:
        from aero.cli import _repo_root, _vv_settings

        conf_uri, conf_exp, _ = _vv_settings(_repo_root())
        uri, experiment = uri or conf_uri, experiment or conf_exp
    client = MlflowClient(tracking_uri=uri)
    exp = client.get_experiment_by_name(experiment)
    if exp is None:
        print(f"no MLflow experiment {experiment!r}", file=sys.stderr)
        return 2

    runs = page_all(client, str(exp.experiment_id))
    prefixes = {name: s.solver_version_prefixes for name, s in STACKS.items()}
    frozen = {name for name, s in STACKS.items() if s.disposition == "frozen"}
    on_stack, any_solver, census = newest_by_case(runs, CASE_STACK, prefixes)

    print(f"independent read: {len(runs)} runs paged from {uri}, experiment {experiment!r}\n")
    expected: dict[str, tuple[str, str]] = {}
    for case in sorted(CASE_STACK, key=lambda c: (list(STACKS).index(CASE_STACK[c]), c)):
        run = on_stack.get(case)
        status = expected_status(case, run, CASE_STACK, frozen, set(DEFERRED_CASES))
        run_id = run["run_id"] if run else ""
        expected[case] = (status, run_id)
        print(f"  {CASE_STACK[case]:<9} {case:<34} {status:<9} {run_id}")
        newest = any_solver.get(case)
        if newest is not None and (run is None or newest["start_time"] > run["start_time"]):
            print(
                f"      note: a newer OFF-stack run exists: {newest['run_id']} "
                f"({newest['tags'].get('solver_version', '?')})"
            )
    tally = Counter(s for s, _ in expected.values())
    print("\n  totals: " + ", ".join(f"{n} {s}" for s, n in sorted(tally.items())))
    print("\n  validation_tag values that are not registered cases (never in the verdict):")
    sweeps = sum(n for t, n in census.items() if t.endswith("-sweep"))
    print(
        f"    {sweeps} run(s) across {sum(1 for t in census if t.endswith('-sweep'))} '-sweep' tags"
    )
    for tag, n in sorted(census.items()):
        if not tag.endswith("-sweep"):
            print(f"    {tag}: {n}")

    if args.against is None:
        return 0
    problems = compare(expected, json.loads(args.against.read_text(encoding="utf-8")))
    if problems:
        print(f"\nMISMATCH: {len(problems)} case(s) disagree with {args.against}:")
        for p in problems:
            print(f"  - {p}")
        return 1
    print(f"\nAGREE: all {len(expected)} cases match {args.against} (status and run id).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
