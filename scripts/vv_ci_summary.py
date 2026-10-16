#!/usr/bin/env python3
"""Write a V&V job's step summary: what it measured, and what it did not, in words (Stage 22).

    python3 -I scripts/vv_ci_summary.py --title "V&V smoke" --selection "<the -m expression>" \
        --junit vv-junit.xml --deselected vv-deselected.jsonl >> "$GITHUB_STEP_SUMMARY"

Stdlib only. It reads pytest's `--junitxml` report and the JSON lines that
`tests/vv/conftest.py::pytest_deselected` writes (`AERO_VV_DESELECTED_JSON`), and prints Markdown:
one row per selected test with its outcome and reason, then every deselected V&V solve grouped
by WHY it was not measured (frozen-optional SU2 stack, documented NO-GO, nightly-only sweep,
multi-hour moving case). A missing JUnit file is reported as "pytest produced no report", never as
an empty green table. ADR-051: no V&V workflow may be green while it measured nothing.
"""

from __future__ import annotations

import argparse
import json
import sys
import xml.etree.ElementTree as ET
from collections.abc import Iterable
from pathlib import Path

#: Deselection groups, checked in order; the first marker a test carries decides its group.
GROUPS = (
    ("unmeasurable", "documented NO-GO whose solve cannot complete (reason per test)"),
    (
        "su2",
        "frozen-optional SU2 stack (ADR-013, ADR-051 D2); measured only by the vv-transonic dispatch",
    ),
    ("moving", "multi-hour moving-mesh case; measured by moving-vv"),
    ("mesh_sweep", "GCI mesh sweep; measured by the nightly vv-smoke run"),
)


def _cell(text: str) -> str:
    return " ".join(text.split()).replace("|", "\\|")[:300]


def outcomes(junit: Path) -> list[tuple[str, str, str]]:
    """(test id, outcome, detail) per test case in a pytest JUnit XML report."""
    root = ET.parse(junit).getroot()
    rows = []
    for case in root.iter("testcase"):
        name = f"{case.get('classname', '')}::{case.get('name', '')}"
        outcome, detail = "passed", ""
        for child in case:
            msg = child.get("message", "") or (child.text or "")
            if child.tag == "failure":
                outcome, detail = "FAILED", msg
            elif child.tag == "error":
                outcome, detail = "ERROR", msg
            elif child.tag == "skipped":
                kind = child.get("type", "")
                outcome = "xfailed" if kind == "pytest.xfail" else "SKIPPED"
                detail = msg
        rows.append((name, outcome, detail))
    return rows


def deselected(lines: Iterable[str]) -> dict[str, list[tuple[str, str]]]:
    """Deselected V&V solves grouped by `GROUPS`; tests that are not V&V solves are counted only."""
    groups: dict[str, list[tuple[str, str]]] = {g: [] for g, _ in GROUPS}
    groups["other"] = []
    seen: set[str] = set()
    for line in lines:
        if not line.strip():
            continue
        rec = json.loads(line)
        if rec["nodeid"] in seen:
            continue
        seen.add(rec["nodeid"])
        markers = set(rec["markers"])
        for group, _ in GROUPS:
            if group in markers:
                groups[group].append((rec["nodeid"], rec.get("reason", "")))
                break
        else:
            groups["other"].append((rec["nodeid"], ""))
    return groups


def render(title: str, selection: str, junit: Path | None, deselected_file: Path | None) -> str:
    out = [f"## {title}: what this job measured", ""]
    if selection:
        out += [f'Selection: `-m "{selection}"`', ""]
    if junit is None or not junit.is_file():
        out += [
            "**pytest produced no report**, so nothing can be claimed as measured. See the log.",
            "",
        ]
        results: list[tuple[str, str, str]] = []
    else:
        results = outcomes(junit)
        if not results:
            out += ["**No test ran.** This job measured nothing.", ""]
        else:
            out += ["| Test | Outcome | Detail |", "|---|---|---|"]
            out += [f"| `{_cell(n)}` | {o} | {_cell(d) or '—'} |" for n, o, d in results]
            tally: dict[str, int] = {}
            for _, o, _ in results:
                tally[o] = tally.get(o, 0) + 1
            out += [
                "",
                "**Totals:** " + ", ".join(f"{n} {o}" for o, n in sorted(tally.items())),
                "",
            ]
            out += [
                "`xfailed` means a measured tolerance miss of a documented open item (only an",
                "`AssertionError` may xfail since Stage 22); a solver or harness error is `FAILED`.",
                "",
            ]
    if deselected_file is not None and deselected_file.is_file():
        groups = deselected(deselected_file.read_text(encoding="utf-8").splitlines())
        out += ["### Not measured by this job, by design", ""]
        any_listed = False
        for group, why in GROUPS:
            if groups[group]:
                any_listed = True
                out.append(f"- **{why}:**")
                for nodeid, reason in groups[group]:
                    out.append(f"  - `{nodeid}`" + (f": {_cell(reason)}" if reason else ""))
        if groups["other"]:
            out.append(
                f"- {len(groups['other'])} other test(s) outside this selection (not cluster V&V solves)."
            )
        if not any_listed and not groups["other"]:
            out.append("- nothing was deselected.")
        out.append("")
    out.append(
        "The per-case production gate is `aero vv report --latest` (ADR-005, scoped by ADR-051 D2)."
    )
    return "\n".join(out) + "\n"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    ap.add_argument("--title", required=True)
    ap.add_argument("--selection", default="")
    ap.add_argument("--junit", type=Path)
    ap.add_argument("--deselected", type=Path)
    args = ap.parse_args(argv)
    sys.stdout.write(render(args.title, args.selection, args.junit, args.deselected))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
